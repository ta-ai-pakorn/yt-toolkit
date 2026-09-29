import json
import logging
import logging.handlers
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from yttoolkit import lifecycle, probe, runstate


@pytest.fixture
def restore_root_logging():
    root = logging.getLogger()
    before = list(root.handlers)
    level = root.level
    yield root
    for h in list(root.handlers):
        if h not in before:
            root.removeHandler(h)
            h.close()
    root.setLevel(level)


def test_probe_and_its_imports_do_not_load_the_web_stack():
    code = (
        "import sys, yttoolkit.probe, yttoolkit.config, yttoolkit.runstate, yttoolkit.platform\n"
        "loaded = sorted({'httpx', 'fastapi', 'uvicorn', 'starlette'} & set(sys.modules))\n"
        "print(','.join(loaded))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60, check=True)
    assert out.stdout.strip() == ""


def test_lifecycle_reexports_the_single_probe_implementation():
    assert lifecycle.is_alive is probe.is_alive
    assert lifecycle.find_running is probe.find_running
    assert lifecycle.base_url is probe.base_url


class _PingHandler(BaseHTTPRequestHandler):
    pid = 42

    def do_GET(self):  # noqa: N802 (ชื่อที่ http.server กำหนด)
        body = json.dumps({"ok": True, "pid": self.pid}).encode()
        self.send_response(200 if self.path == "/api/ping" else 404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def ping_server():
    server = HTTPServer(("127.0.0.1", 0), _PingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


def test_is_alive_pings_with_urllib_and_checks_pid(ping_server):
    assert probe.is_alive(ping_server) is True
    assert probe.is_alive(ping_server, 42) is True
    assert probe.is_alive(ping_server, 43) is False


def test_is_alive_ignores_proxy_settings(ping_server, monkeypatch):
    # เครื่องในบริษัทอาจตั้ง proxy ไว้ แต่ 127.0.0.1 ต้องต่อตรงเสมอ
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    assert probe.is_alive(ping_server, 42) is True


def test_is_alive_false_when_nothing_listens():
    port = runstate.pick_port(range(8870, 8890))
    assert probe.is_alive(port) is False


def test_is_alive_uses_two_second_timeout():
    seen = []

    def get(url, timeout):
        seen.append((url, timeout))
        raise OSError("refused")

    assert probe.is_alive(8787, get=get) is False
    assert seen == [("http://127.0.0.1:8787/api/ping", 2)]


def test_setup_file_log_is_idempotent_and_shared_with_lifecycle(paths, restore_root_logging):
    root = restore_root_logging
    before = list(root.handlers)
    probe.setup_file_log(paths)
    probe.setup_file_log(paths)
    lifecycle.setup_file_logging(paths)  # start ใน __main__ ตั้งไว้แล้ว lifecycle ต้องไม่เพิ่มซ้ำ
    added = [h for h in root.handlers if h not in before]
    assert len(added) == 1
    handler = added[0]
    assert isinstance(handler, logging.handlers.RotatingFileHandler)
    assert handler.maxBytes == 1_000_000
    assert handler.backupCount == 3
    assert handler.encoding == "utf-8"
    assert handler.baseFilename == str((paths.logs / "app.log").resolve())
    assert root.level == logging.INFO


def test_cli_start_logs_crash_and_exits_1(tmp_path, monkeypatch, restore_root_logging):
    from yttoolkit import __main__ as cli

    monkeypatch.setenv("YT_TOOLKIT_DATA_ROOT", str(tmp_path))

    def boom():
        raise RuntimeError("พังตอนเปิด")

    monkeypatch.setattr(lifecycle, "start", boom)
    assert cli.main(["start"]) == 1
    for h in restore_root_logging.handlers:
        h.flush()
    text = (tmp_path / "run" / "logs" / "app.log").read_text(encoding="utf-8")
    assert "เปิดโปรแกรมไม่สำเร็จ" in text
    assert "Traceback" in text and "RuntimeError: พังตอนเปิด" in text


@pytest.mark.parametrize("exc", [KeyboardInterrupt, SystemExit])
def test_cli_start_reraises_exit_and_interrupt(tmp_path, monkeypatch, restore_root_logging, exc):
    from yttoolkit import __main__ as cli

    monkeypatch.setenv("YT_TOOLKIT_DATA_ROOT", str(tmp_path))

    def stop_now():
        raise exc()

    monkeypatch.setattr(lifecycle, "start", stop_now)
    with pytest.raises(exc):
        cli.main(["start"])


def test_cli_stop_writes_details_to_app_log(tmp_path, monkeypatch, restore_root_logging):
    # stop บอกผู้ใช้ให้ไปดู app.log เมื่อตรวจ lock ไม่ได้ จึงต้องมี handler ของไฟล์นั้นก่อนเรียก lifecycle.stop
    from yttoolkit import __main__ as cli

    monkeypatch.setenv("YT_TOOLKIT_DATA_ROOT", str(tmp_path))
    seen = []

    def fake_stop():
        seen.append([h.baseFilename for h in restore_root_logging.handlers if hasattr(h, "baseFilename")])
        return 0

    monkeypatch.setattr(lifecycle, "stop", fake_stop)
    assert cli.main(["stop"]) == 0
    assert len(seen) == 1
    assert str((tmp_path / "run" / "logs" / "app.log").resolve()) in seen[0]
