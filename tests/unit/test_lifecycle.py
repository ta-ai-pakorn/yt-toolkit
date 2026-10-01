import logging
import logging.handlers
import os
import sys
import urllib.error
from pathlib import Path

import httpx
import pytest

from yttoolkit import lifecycle, probe, runstate, tray
from yttoolkit.api.errors import redact_home
from yttoolkit.app import AppContext
from yttoolkit.config import CODE_ROOT
from yttoolkit.core import files, tools
from yttoolkit.core.db import Database
from yttoolkit.core.events import CLOSED, Event, EventBus
from yttoolkit.core.extractor import FakeExtractor, YtDlpExtractor
from yttoolkit.core.jobs import JobStore, NewJob, OutputFile
from yttoolkit.core.media import FakeMediaTools, FfmpegTools
from yttoolkit.core.queue import QueueRunner
from yttoolkit.core.settings import SettingsStore
from yttoolkit.core.videos import VideoService
from yttoolkit.runstate import RunInfo


@pytest.fixture(autouse=True)
def _restore_pythainlp_env(monkeypatch):
    """open_services ตั้ง PYTHAINLP_DATA ให้ชี้โฟลเดอร์ชั่วคราวของเทส คืนค่าเดิมหลังจบทุกเทส"""
    for name in ("PYTHAINLP_DATA", "PYTHAINLP_DATA_DIR"):
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)


class FakeResponse:
    def __init__(self, status_code: int, body: dict | None = None):
        self.status_code = status_code
        self._body = body or {}

    def json(self) -> dict:
        return self._body


def _running(paths, fake_platform, pid=4242, port=8787, holds_lock=True) -> RunInfo:
    info = RunInfo(port=port, pid=pid, token="tok", started_at="x")
    runstate.write(paths.app_json, info)
    fake_platform.alive.add(pid)
    if holds_lock:  # แอพที่รันอยู่จริงถือ run/app.lock ไว้ตลอดอายุ
        fake_platform.locked.add(paths.run / "app.lock")
    return info


def test_base_url():
    assert lifecycle.base_url(8787) == "http://127.0.0.1:8787"


def test_is_alive_handles_errors():
    def boom(url, timeout):
        raise urllib.error.URLError("refused")

    assert lifecycle.is_alive(8787, get=boom) is False
    assert lifecycle.is_alive(8787, get=lambda url, timeout: FakeResponse(200)) is True


def test_find_running_ignores_stale_file(paths, fake_platform):
    runstate.write(paths.app_json, RunInfo(8787, 999, "t", "x"))
    assert lifecycle.find_running(paths, fake_platform, alive=lambda port, pid: True) is None


def test_find_running_detects_live_instance(paths, fake_platform):
    info = _running(paths, fake_platform)
    assert lifecycle.find_running(paths, fake_platform, alive=lambda port, pid: True) == info
    assert lifecycle.find_running(paths, fake_platform, alive=lambda port, pid: False) is None


def test_default_output_dir(fake_platform):
    assert lifecycle.default_output_dir(fake_platform) == fake_platform.downloads / "YT-Toolkit"


def test_prepare_environment_puts_scripts_first(monkeypatch):
    monkeypatch.setenv("PATH", "somewhere")
    lifecycle.prepare_environment()
    assert os.environ["PATH"].split(os.pathsep)[0] == str(tools.scripts_dir())


def test_server_binds_localhost_only(paths, fake_platform):  # AC-SEC-01
    from yttoolkit.app import AppContext

    ctx = AppContext(paths, fake_platform, 8787, "t", "0.1.0", None, paths.data_root, lambda: None)
    assert lifecycle.Server(ctx).config.host == "127.0.0.1"


def test_start_waits_for_other_starter_and_opens_browser(paths, fake_platform, monkeypatch):  # FR-LIFE-2
    fake_platform.locked.add(paths.run / "app.lock")  # อีกโปรเซสถือ lock อยู่ก่อนแล้ว
    info = RunInfo(port=8787, pid=123, token="t", started_at="x")
    responses = iter([None, None, info])

    def fake_find_running(p, pl):
        return next(responses)

    monkeypatch.setattr(lifecycle, "find_running", fake_find_running)
    opened = []
    monkeypatch.setattr(lifecycle.webbrowser, "open", opened.append)

    def run_app_must_not_be_called(**kwargs):
        raise AssertionError("run_app ไม่ควรถูกเรียกตอนรอโปรเซสอื่นเปิดอยู่")

    monkeypatch.setattr(lifecycle, "run_app", run_app_must_not_be_called)

    result = lifecycle.start(paths, fake_platform, wait_timeout=1.0, sleep=lambda s: None)
    assert result == 0
    assert opened == ["http://127.0.0.1:8787"]


def test_start_gives_up_when_other_starter_never_finishes(paths, fake_platform, monkeypatch):  # FR-LIFE-2
    fake_platform.locked.add(paths.run / "app.lock")  # อีกโปรเซสถือ lock อยู่ก่อนแล้ว
    monkeypatch.setattr(lifecycle, "find_running", lambda p, pl: None)
    opened = []
    monkeypatch.setattr(lifecycle.webbrowser, "open", opened.append)

    def run_app_must_not_be_called(**kwargs):
        raise AssertionError("run_app ไม่ควรถูกเรียกตอนหาโปรเซสอื่นไม่เจอ")

    monkeypatch.setattr(lifecycle, "run_app", run_app_must_not_be_called)

    result = lifecycle.start(paths, fake_platform, wait_timeout=0.05, sleep=lambda s: None)
    assert result == 1
    assert opened == []


def test_stop_when_not_running(paths, fake_platform):
    out = []
    assert lifecycle.stop(paths, fake_platform, out=out.append) == 0
    assert out == ["YT Toolkit ไม่ได้เปิดอยู่"]


def test_stop_graceful(paths, fake_platform):
    info = _running(paths, fake_platform)
    posts = []

    def post(url, json, headers, timeout):
        posts.append((url, json, headers))
        fake_platform.alive.discard(info.pid)  # แอพปิดตัวเอง
        return FakeResponse(200, {"ok": True})

    out = []
    assert lifecycle.stop(paths, fake_platform, post=post, sleep=lambda s: None, out=out.append) == 0
    url, body, headers = posts[0]
    assert url == "http://127.0.0.1:8787/api/shutdown"
    assert body == {"force": False}
    assert headers == {"X-Toolkit-Token": "tok", "Origin": "http://127.0.0.1:8787"}
    assert fake_platform.killed == []
    assert not paths.app_json.exists()
    assert out == ["ปิดโปรแกรมแล้ว"]


def test_stop_pending_user_declines(paths, fake_platform):
    _running(paths, fake_platform)
    result = lifecycle.stop(
        paths,
        fake_platform,
        post=lambda url, json, headers, timeout: FakeResponse(409, {"pendingJobs": 2}),
        ask=lambda prompt: "n",
        sleep=lambda s: None,
        out=lambda msg: None,
    )
    assert result == 1
    assert fake_platform.killed == []
    assert paths.app_json.exists()


def test_stop_pending_user_confirms_forces(paths, fake_platform):
    info = _running(paths, fake_platform)
    bodies = []

    def post(url, json, headers, timeout):
        bodies.append(json)
        if json["force"]:
            fake_platform.alive.discard(info.pid)
            return FakeResponse(200, {"ok": True})
        return FakeResponse(409, {"pendingJobs": 1})

    prompts = []

    def ask(prompt):
        prompts.append(prompt)
        return "Y"

    assert lifecycle.stop(paths, fake_platform, post=post, ask=ask, sleep=lambda s: None, out=lambda m: None) == 0
    assert bodies == [{"force": False}, {"force": True}]
    assert prompts == ["มีงานค้าง 1 งาน ปิดเลยไหม (Y/N) "]


def test_stop_kills_when_app_does_not_exit(paths, fake_platform):
    info = _running(paths, fake_platform, holds_lock=True)
    result = lifecycle.stop(
        paths,
        fake_platform,
        post=lambda url, json, headers, timeout: FakeResponse(200, {"ok": True}),
        sleep=lambda s: None,
        out=lambda m: None,
    )
    assert result == 0
    assert fake_platform.killed == [info.pid]


def test_stop_kills_when_api_unreachable(paths, fake_platform):
    info = _running(paths, fake_platform, holds_lock=True)

    def refused(url, json, headers, timeout):
        raise httpx.ConnectError("refused")

    lifecycle.stop(paths, fake_platform, post=refused, sleep=lambda s: None, out=lambda m: None)
    assert fake_platform.killed == [info.pid]


def test_stop_does_not_kill_reused_pid_when_lock_is_free(paths, fake_platform):
    # app.json ค้างจากตอนเครื่องดับ แล้ว Windows เอา pid เดิมไปให้โปรแกรมอื่น (เช่น Excel)
    info = _running(paths, fake_platform, holds_lock=False)

    def post_must_not_be_called(url, json, headers, timeout):
        raise AssertionError("ไม่ควรเรียก /api/shutdown เมื่อไม่มีแอพถือ lock")

    out = []
    result = lifecycle.stop(paths, fake_platform, post=post_must_not_be_called, sleep=lambda s: None, out=out.append)
    assert result == 0
    assert fake_platform.killed == []
    assert info.pid in fake_platform.alive
    assert not paths.app_json.exists()
    assert out == ["YT Toolkit ไม่ได้เปิดอยู่"]
    assert fake_platform.locked == set()  # ปล่อย lock คืนทันที


def test_stop_does_not_kill_when_lock_frees_during_wait(paths, fake_platform):
    info = _running(paths, fake_platform, holds_lock=True)
    lock = paths.run / "app.lock"

    def sleep(seconds):
        fake_platform.locked.discard(lock)  # แอพปิดตัวและปล่อย lock ระหว่างรอ แต่ pid ยังไม่หายทันที

    out = []
    result = lifecycle.stop(
        paths,
        fake_platform,
        post=lambda url, json, headers, timeout: FakeResponse(200, {"ok": True}),
        sleep=sleep,
        out=out.append,
    )
    assert result == 0
    assert fake_platform.killed == []
    assert info.pid in fake_platform.alive
    assert not paths.app_json.exists()
    assert fake_platform.locked == set()


# ---- M1 follow-ups: Task 1 ----------------------------------------------------------------------------------------


class FakeServer:
    """แทน lifecycle.Server ในเทสที่ไม่ต้องการ uvicorn จริง"""

    def __init__(self, ready: bool = True):
        self.ready = ready
        self.started = False
        self.stopped = False
        self.joined: list[float | None] = []

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def join(self, timeout: float | None = None) -> None:
        self.joined.append(timeout)

    def wait_until_ready(self, timeout: float = 15.0) -> bool:
        return self.ready


def test_start_clears_stale_app_json_before_run_app(paths, fake_platform, monkeypatch):  # item 1
    runstate.write(paths.app_json, RunInfo(port=8787, pid=999, token="old", started_at="old"))
    seen = {}

    def fake_run_app(**kwargs):
        seen["app_json_exists"] = paths.app_json.exists()
        seen["locked"] = (paths.run / "app.lock") in fake_platform.locked
        return 0

    monkeypatch.setattr(lifecycle, "run_app", fake_run_app)
    assert lifecycle.start(paths, fake_platform, sleep=lambda s: None) == 0
    assert seen == {"app_json_exists": False, "locked": True}
    assert fake_platform.locked == set()


def test_serve_clears_stale_app_json_before_run_app(paths, fake_platform, monkeypatch):  # item 1
    runstate.write(paths.app_json, RunInfo(port=8787, pid=999, token="old", started_at="old"))
    seen = {}

    def fake_run_app(**kwargs):
        seen["app_json_exists"] = paths.app_json.exists()
        return 0

    monkeypatch.setattr(lifecycle, "default_paths", lambda: paths)
    monkeypatch.setattr(lifecycle, "current", lambda: fake_platform)
    monkeypatch.setattr(lifecycle, "run_app", fake_run_app)
    assert lifecycle.serve(port=9000) == 0
    assert seen == {"app_json_exists": False}
    assert fake_platform.locked == set()


def test_start_takes_over_when_lock_frees_during_wait(paths, fake_platform, monkeypatch):  # item 2
    lock = paths.run / "app.lock"
    fake_platform.locked.add(lock)  # อีกโปรเซสถือ lock อยู่ แล้วตายไประหว่างรอ โดยไม่เคยเขียน app.json
    runstate.write(paths.app_json, RunInfo(port=8787, pid=999, token="old", started_at="old"))
    monkeypatch.setattr(lifecycle, "find_running", lambda p, pl: None)
    opened = []
    monkeypatch.setattr(lifecycle.webbrowser, "open", opened.append)
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            fake_platform.locked.discard(lock)  # lock ว่างระหว่างรอ

    calls = {}

    def fake_run_app(**kwargs):
        calls["app_json_exists"] = paths.app_json.exists()
        calls["locked"] = lock in fake_platform.locked
        return 0

    monkeypatch.setattr(lifecycle, "run_app", fake_run_app)
    assert lifecycle.start(paths, fake_platform, wait_timeout=100.0, sleep=sleep) == 0
    assert len(sleeps) == 2
    assert calls == {"app_json_exists": False, "locked": True}
    assert opened == []
    assert fake_platform.locked == set()  # เจ้าของใหม่ปล่อย lock ตอนจบ


def test_stop_does_not_kill_when_app_json_was_replaced(paths, fake_platform):  # item 3
    info = _running(paths, fake_platform, holds_lock=True)
    newer = RunInfo(port=8788, pid=7777, token="new", started_at="newer")

    def sleep(seconds):
        runstate.write(paths.app_json, newer)  # แอพเดิมปิด แล้วมีอินสแตนซ์ใหม่เขียน app.json ทับ

    out = []
    result = lifecycle.stop(
        paths,
        fake_platform,
        post=lambda url, json, headers, timeout: FakeResponse(200, {"ok": True}),
        sleep=sleep,
        out=out.append,
    )
    assert result == 0
    assert fake_platform.killed == []
    assert info.pid in fake_platform.alive
    assert runstate.read(paths.app_json) == newer  # ห้ามลบ app.json ของอินสแตนซ์ใหม่
    assert out == ["ปิดโปรแกรมแล้ว"]  # final fix item 7: ส่งคำขอปิดสำเร็จแล้ว แอพเดิมปิดไปแล้ว


def test_stop_does_not_kill_when_same_pid_but_different_started_at(paths, fake_platform):  # item 3
    info = _running(paths, fake_platform, holds_lock=True)
    reused = RunInfo(port=info.port, pid=info.pid, token="new", started_at="later")

    def sleep(seconds):
        runstate.write(paths.app_json, reused)

    out = []
    lifecycle.stop(
        paths,
        fake_platform,
        post=lambda url, json, headers, timeout: FakeResponse(200, {"ok": True}),
        sleep=sleep,
        out=out.append,
    )
    assert fake_platform.killed == []
    assert runstate.read(paths.app_json) == reused
    assert out == ["ปิดโปรแกรมแล้ว"]  # final fix item 7: ส่งคำขอปิดสำเร็จแล้ว แอพเดิมปิดไปแล้ว


def test_stop_does_not_kill_when_app_json_vanished(paths, fake_platform):  # item 3
    _running(paths, fake_platform, holds_lock=True)

    def sleep(seconds):
        runstate.clear(paths.app_json)

    out = []
    lifecycle.stop(
        paths,
        fake_platform,
        post=lambda url, json, headers, timeout: FakeResponse(200, {"ok": True}),
        sleep=sleep,
        out=out.append,
    )
    assert fake_platform.killed == []
    assert out == ["ปิดโปรแกรมแล้ว"]  # final fix item 7: ส่งคำขอปิดสำเร็จแล้ว แอพเดิมปิดไปแล้ว


def test_stop_does_not_clear_newer_app_json_after_graceful_exit(paths, fake_platform):  # item 3
    info = _running(paths, fake_platform)
    newer = RunInfo(port=8788, pid=7777, token="new", started_at="newer")

    def post(url, json, headers, timeout):
        fake_platform.alive.discard(info.pid)  # แอพเดิมปิดตัวเอง
        runstate.write(paths.app_json, newer)  # และอินสแตนซ์ใหม่เขียนทับทันที
        return FakeResponse(200, {"ok": True})

    lifecycle.stop(paths, fake_platform, post=post, sleep=lambda s: None, out=lambda m: None)
    assert runstate.read(paths.app_json) == newer


def _run_app_kwargs(paths, fake_platform):
    return {
        "paths": paths,
        "plat": fake_platform,
        "port": 8787,
        "with_tray": False,
        "open_browser": False,
        "auto_ffmpeg": False,
    }


def test_run_app_cleans_up_after_startup_timeout(paths, fake_platform, monkeypatch, caplog):  # item 4
    server = FakeServer(ready=False)
    monkeypatch.setattr(lifecycle, "Server", lambda ctx: server)
    runstate.write(paths.app_json, RunInfo(port=1, pid=1, token="t", started_at="x"))
    with caplog.at_level("ERROR", logger="yttoolkit"):
        assert lifecycle.run_app(**_run_app_kwargs(paths, fake_platform)) == 1
    assert server.started and server.stopped
    assert len(server.joined) == 1 and server.joined[0] is not None  # join แบบมี timeout สั้น ๆ
    assert not paths.app_json.exists()
    assert "เปิดเซิร์ฟเวอร์ไม่สำเร็จ" in caplog.text


def test_start_releases_lock_after_startup_timeout(paths, fake_platform, monkeypatch):  # item 4
    server = FakeServer(ready=False)
    monkeypatch.setattr(lifecycle, "Server", lambda ctx: server)
    monkeypatch.setenv("YT_TOOLKIT_TRAY", "0")
    monkeypatch.setenv("YT_TOOLKIT_OPEN_BROWSER", "0")
    assert lifecycle.start(paths, fake_platform, sleep=lambda s: None) != 0
    assert server.stopped
    assert not paths.app_json.exists()
    assert fake_platform.locked == set()  # ปล่อย lock คืน เปิดใหม่ได้ทันที


def test_setup_file_logging_uses_rotating_handler(paths):  # item 6
    import logging
    import logging.handlers

    root = logging.getLogger()
    before = list(root.handlers)
    level = root.level
    try:
        lifecycle.setup_file_logging(paths)
        added = [h for h in root.handlers if h not in before]
        assert len(added) == 1
        handler = added[0]
        assert isinstance(handler, logging.handlers.RotatingFileHandler)
        assert handler.maxBytes == 1_000_000
        assert handler.backupCount == 3
        assert handler.encoding == "utf-8"
        assert handler.baseFilename == str((paths.logs / "app.log").resolve())
    finally:
        for h in list(root.handlers):
            if h not in before:
                root.removeHandler(h)
                h.close()
        root.setLevel(level)


def test_wait_succeeds_when_instance_answers(paths, fake_platform, monkeypatch):  # item 7
    info = RunInfo(port=8790, pid=1, token="t", started_at="x")
    responses = iter([None, None, info])
    monkeypatch.setattr(probe, "find_running", lambda p, pl: next(responses))
    sleeps = []
    out = []
    assert probe.wait(paths, fake_platform, timeout=25, sleep=sleeps.append, out=out.append) == 0
    assert sleeps == [0.5, 0.5]
    assert out == ["เปิด YT Toolkit แล้ว ที่ http://127.0.0.1:8790"]


def test_wait_times_out_with_log_path(paths, fake_platform, monkeypatch):  # item 7
    monkeypatch.setattr(probe, "find_running", lambda p, pl: None)
    out = []
    assert probe.wait(paths, fake_platform, timeout=0.05, sleep=lambda s: None, out=out.append) == 1
    expected = str((paths.logs / "app.log").absolute())
    assert out == [f"เปิดโปรแกรมไม่สำเร็จ ดูรายละเอียดได้ที่ {expected}"]


def test_wait_timeout_zero_checks_exactly_once(paths, fake_platform, monkeypatch):  # item 7
    calls = []

    def find(p, pl):
        calls.append(1)

    monkeypatch.setattr(probe, "find_running", find)
    sleeps = []
    out = []
    assert probe.wait(paths, fake_platform, timeout=0, sleep=sleeps.append, out=out.append) == 1
    assert len(calls) == 1
    assert sleeps == []
    assert out[0].startswith("เปิดโปรแกรมไม่สำเร็จ")

    info = RunInfo(port=8787, pid=1, token="t", started_at="x")
    monkeypatch.setattr(probe, "find_running", lambda p, pl: info)
    assert probe.wait(paths, fake_platform, timeout=0, sleep=sleeps.append, out=out.append) == 0


def test_cli_wait_passes_timeout(monkeypatch):  # item 7
    from yttoolkit import __main__ as cli

    seen = []
    monkeypatch.setattr(probe, "wait", lambda **kw: seen.append(kw) or 0)
    assert cli.main(["wait"]) == 0
    assert cli.main(["wait", "--timeout", "0"]) == 0
    assert cli.main(["wait", "--timeout", "3.5"]) == 0
    assert [kw["timeout"] for kw in seen] == [25.0, 0.0, 3.5]


# ---- M1 follow-ups: Task 1 fix round 1 ----------------------------------------------------------------------------


def test_stop_early_branch_does_not_clear_replaced_app_json(paths, fake_platform):  # fix round 1, item 2
    _running(paths, fake_platform, holds_lock=False)  # ล็อกว่าง = ไม่มีแอพเปิดอยู่
    newer = RunInfo(port=8788, pid=7777, token="new", started_at="newer")
    real_try_lock = fake_platform.try_lock

    def try_lock(path):
        runstate.write(paths.app_json, newer)  # อินสแตนซ์ใหม่เขียน app.json ทันทีหลังเราเช็ก lock
        return real_try_lock(path)

    fake_platform.try_lock = try_lock
    out = []
    assert lifecycle.stop(paths, fake_platform, out=out.append) == 0
    assert runstate.read(paths.app_json) == newer
    assert out == ["YT Toolkit ไม่ได้เปิดอยู่"]


def test_is_alive_checks_ping_pid():  # fix round 1, item 3
    class Ping:
        status_code = 200

        def __init__(self, pid):
            self._pid = pid

        def json(self):
            return {"ok": True, "pid": self._pid}

    assert lifecycle.is_alive(8787, 42, get=lambda url, timeout: Ping(42)) is True
    assert lifecycle.is_alive(8787, 42, get=lambda url, timeout: Ping(43)) is False
    assert lifecycle.is_alive(8787, 42, get=lambda url, timeout: FakeResponse(200, {"ok": True})) is False
    assert lifecycle.is_alive(8787, get=lambda url, timeout: FakeResponse(200)) is True  # ไม่ระบุ pid = เช็กแค่ตอบกลับ


def test_find_running_rejects_instance_whose_ping_reports_other_pid(paths, fake_platform):  # item 3
    _running(paths, fake_platform, pid=4242, port=8787)

    class Ping:
        status_code = 200

        def json(self):
            return {"ok": True, "pid": 9999}  # พอร์ตนี้มีโปรแกรมอื่นตอบ ไม่ใช่แอพตาม app.json

    def alive(port, pid):
        return lifecycle.is_alive(port, pid, get=lambda url, timeout: Ping())

    assert lifecycle.find_running(paths, fake_platform, alive=alive) is None


def test_git_commit_passes_platform_popen_flags(monkeypatch, tmp_path, fake_platform):
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured.update(kwargs)

        class Out:
            stdout = "abc1234\n"

        return Out()

    monkeypatch.setattr(lifecycle.subprocess, "run", fake_run)
    fake_platform.popen_flags = 0x1234
    assert lifecycle.git_commit(tmp_path, fake_platform) == "abc1234"
    assert captured["creationflags"] == 0x1234


def test_ensure_ffmpeg_installs_only_when_platform_supports_it(paths, fake_platform, monkeypatch):
    monkeypatch.setenv("YT_TOOLKIT_FFMPEG_PATH_LOOKUP", "0")
    calls: list = []
    monkeypatch.setattr(tools, "install_ffmpeg", lambda p, plat: calls.append(plat))
    fake_platform.name = "macos"  # ชื่อไม่เกี่ยว ดูแค่ความสามารถ
    lifecycle.ensure_ffmpeg(paths, fake_platform)
    assert calls == [fake_platform]
    calls.clear()
    fake_platform.ffmpeg_auto_install = False
    lifecycle.ensure_ffmpeg(paths, fake_platform)
    assert calls == []


def test_ensure_ffmpeg_skips_when_already_present(paths, fake_platform, monkeypatch):
    (paths.bin / fake_platform.exe_name("ffmpeg")).write_bytes(b"x")
    monkeypatch.setattr(tools, "install_ffmpeg", lambda p, plat: pytest.fail("must not install"))
    lifecycle.ensure_ffmpeg(paths, fake_platform)


def test_ensure_ffmpeg_logs_unexpected_errors(paths, fake_platform, monkeypatch, caplog):
    monkeypatch.setenv("YT_TOOLKIT_FFMPEG_PATH_LOOKUP", "0")

    def boom(p, plat):
        raise PermissionError("file is in use")

    monkeypatch.setattr(tools, "install_ffmpeg", boom)
    with caplog.at_level(logging.ERROR, logger="yttoolkit"):
        lifecycle.ensure_ffmpeg(paths, fake_platform)  # ต้องไม่หลุด exception ออกจาก thread
    assert any(r.exc_info and isinstance(r.exc_info[1], PermissionError) for r in caplog.records)


# ---- M1 follow-ups: final fix wave ---------------------------------------------------------------------------------


def _must_not_run_app(**kwargs):
    raise AssertionError("run_app ไม่ควรถูกเรียกเมื่อเปิดไฟล์ lock ไม่ได้")


def test_start_fails_fast_when_lock_file_cannot_be_opened(paths, fake_platform, monkeypatch, caplog):  # item 2
    fake_platform.unopenable.add(paths.run / "app.lock")
    monkeypatch.setattr(lifecycle, "run_app", _must_not_run_app)
    sleeps = []
    with caplog.at_level(logging.ERROR, logger="yttoolkit"):
        assert lifecycle.start(paths, fake_platform, wait_timeout=20.0, sleep=sleeps.append) == 1
    assert sleeps == []  # ไม่วนรอ 20 วินาที
    assert "app.lock" in caplog.text


def test_start_fails_fast_when_lock_becomes_unopenable_during_wait(paths, fake_platform, monkeypatch):  # item 2
    lock = paths.run / "app.lock"
    fake_platform.locked.add(lock)
    monkeypatch.setattr(lifecycle, "find_running", lambda p, pl: None)
    monkeypatch.setattr(lifecycle, "run_app", _must_not_run_app)
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        fake_platform.unopenable.add(lock)

    assert lifecycle.start(paths, fake_platform, wait_timeout=100.0, sleep=sleep) == 1
    assert len(sleeps) == 1


def test_serve_fails_fast_when_lock_file_cannot_be_opened(paths, fake_platform, monkeypatch, caplog):  # item 2
    fake_platform.unopenable.add(paths.run / "app.lock")
    monkeypatch.setattr(lifecycle, "default_paths", lambda: paths)
    monkeypatch.setattr(lifecycle, "current", lambda: fake_platform)
    monkeypatch.setattr(lifecycle, "run_app", _must_not_run_app)
    with caplog.at_level(logging.ERROR, logger="yttoolkit"):
        assert lifecycle.serve(port=9000) == 1
    assert "app.lock" in caplog.text


def _post_must_not_be_called(url, json, headers, timeout):
    raise AssertionError("ไม่ควรเรียก /api/shutdown เมื่อตรวจ lock ไม่ได้")


def test_stop_reports_when_lock_file_cannot_be_opened(paths, fake_platform):  # item 2
    info = _running(paths, fake_platform, holds_lock=False)
    fake_platform.unopenable.add(paths.run / "app.lock")
    out = []
    result = lifecycle.stop(paths, fake_platform, post=_post_must_not_be_called, sleep=lambda s: None, out=out.append)
    assert result == 1
    assert fake_platform.killed == []
    assert info.pid in fake_platform.alive
    assert runstate.read(paths.app_json) == info  # ห้ามลบ
    assert out == [f"ตรวจสถานะโปรแกรมไม่ได้ ดูรายละเอียดได้ที่ {(paths.logs / 'app.log').absolute()}"]


def test_stop_never_kills_when_lock_check_fails_after_waiting(paths, fake_platform):  # item 2
    info = _running(paths, fake_platform, holds_lock=True)

    def sleep(seconds):
        fake_platform.unopenable.add(paths.run / "app.lock")  # แอพไม่ยอมปิด แล้วเช็ก lock ซ้ำก่อน kill ไม่ได้

    out = []
    result = lifecycle.stop(
        paths,
        fake_platform,
        post=lambda url, json, headers, timeout: FakeResponse(200, {"ok": True}),
        sleep=sleep,
        out=out.append,
    )
    assert result == 1
    assert fake_platform.killed == []
    assert runstate.read(paths.app_json) == info
    assert out == [f"ตรวจสถานะโปรแกรมไม่ได้ ดูรายละเอียดได้ที่ {(paths.logs / 'app.log').absolute()}"]


def test_start_with_real_platform_fails_fast_when_lock_path_is_a_folder(paths, monkeypatch, caplog):  # AC-LIFE-02b
    from yttoolkit.platform import current

    (paths.run / "app.lock").mkdir()
    monkeypatch.setattr(lifecycle, "run_app", _must_not_run_app)
    monkeypatch.setattr(lifecycle, "setup_file_logging", lambda p: None)  # ไม่ทิ้ง handler ไว้ใน root logger ของเทส
    sleeps = []
    with caplog.at_level(logging.WARNING, logger="yttoolkit"):
        assert lifecycle.start(paths, current(), sleep=sleeps.append) == 1
    assert sleeps == []
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warnings and "app.lock" in warnings[0].getMessage()


def test_stop_says_closed_when_app_json_vanishes_after_failed_request(paths, fake_platform):  # item 7
    # ตอนเริ่ม stop มีแอพเปิดอยู่จริง (pid ยังอยู่และถือ lock) จึงไม่ใช่กรณี "ไม่ได้เปิดอยู่"
    _running(paths, fake_platform, holds_lock=True)

    def refused(url, json, headers, timeout):
        raise httpx.ConnectError("refused")

    def sleep(seconds):
        runstate.clear(paths.app_json)  # แอพปิดตัวเองและลบ app.json ระหว่างรอ

    out = []
    assert lifecycle.stop(paths, fake_platform, post=refused, sleep=sleep, out=out.append) == 0
    assert fake_platform.killed == []
    assert out == ["ปิดโปรแกรมแล้ว"]


# ---------- บริการของ M2 (ฐานข้อมูล, extractor, โหมดข้อมูลปลอม) ----------


def _run_capturing_ctx(paths, fake_platform, monkeypatch, ready: bool = True, **extra):
    """รัน run_app โดยให้เซิร์ฟเวอร์ปลอมสั่งปิดทันทีที่เริ่ม คืน (exit code, ctx)"""
    captured = []
    server = FakeServer(ready=ready)

    def make_server(ctx):
        captured.append(ctx)
        server.start = ctx.request_shutdown  # เริ่มแล้วปิดเลย ลูปรอใน run_app จะจบทันที
        return server

    monkeypatch.setattr(lifecycle, "Server", make_server)
    code = lifecycle.run_app(**_run_app_kwargs(paths, fake_platform), **extra)
    return code, captured[0]


def _db_closed(db) -> bool:
    import sqlite3

    try:
        db.execute("SELECT 1")
    except sqlite3.ProgrammingError:
        return True
    return False


def test_run_app_fake_mode_uses_fixture_extractor(paths, fake_platform, monkeypatch, caplog):
    from yttoolkit.config import CODE_ROOT
    from yttoolkit.core.extractor import FakeExtractor

    with caplog.at_level(logging.WARNING, logger="yttoolkit"):
        code, ctx = _run_capturing_ctx(paths, fake_platform, monkeypatch, fake=True)
    assert code == 0
    assert ctx.fake is True
    assert isinstance(ctx.extractor, FakeExtractor)
    assert ctx.extractor.root == CODE_ROOT / "tests" / "fixtures"
    assert ctx.videos is not None and ctx.cache_root == paths.cache
    assert any(
        "โหมดข้อมูลปลอม (YT_TOOLKIT_FAKE)" in r.getMessage() and r.levelno == logging.WARNING
        for r in caplog.records
    )
    assert paths.db.is_file()
    assert _db_closed(ctx.db)  # ปิดฐานข้อมูลตอนปิดโปรแกรม


def test_run_app_uses_real_extractor_by_default(paths, fake_platform, monkeypatch, caplog):
    from yttoolkit.core.extractor import YtDlpExtractor

    monkeypatch.delenv("YT_TOOLKIT_FAKE", raising=False)
    with caplog.at_level(logging.WARNING, logger="yttoolkit"):
        code, ctx = _run_capturing_ctx(paths, fake_platform, monkeypatch)
    assert code == 0
    assert isinstance(ctx.extractor, YtDlpExtractor)
    assert "YT_TOOLKIT_FAKE" not in caplog.text


def test_run_app_closes_db_when_server_fails_to_start(paths, fake_platform, monkeypatch):
    code, ctx = _run_capturing_ctx(paths, fake_platform, monkeypatch, ready=False)
    assert code == 1
    assert _db_closed(ctx.db)


def test_run_app_purges_stale_cache(paths, fake_platform, monkeypatch):
    from yttoolkit.core.db import Database

    db = Database(paths.db)
    db.migrate()
    db.execute(
        "INSERT INTO videos (video_id, title, probe_json, probed_at, opened_at) VALUES (?, ?, ?, ?, ?)",
        ("oldvideo001", "เก่า", "{}", "2020-01-01T00:00:00+00:00", "2020-01-01T00:00:00+00:00"),
    )
    db.close()
    (paths.cache / "oldvideo001").mkdir(parents=True)
    code, _ctx = _run_capturing_ctx(paths, fake_platform, monkeypatch)
    assert code == 0
    assert not (paths.cache / "oldvideo001").exists()


def test_run_app_starts_even_if_purge_fails(paths, fake_platform, monkeypatch, caplog):
    def broken_purge(*args, **kwargs):
        raise OSError("ดิสก์เสีย")

    monkeypatch.setattr(lifecycle, "purge_stale_cache", broken_purge)
    with caplog.at_level(logging.ERROR, logger="yttoolkit"):
        code, ctx = _run_capturing_ctx(paths, fake_platform, monkeypatch)
    assert code == 0
    assert ctx.videos is not None
    assert "ล้าง cache เก่าไม่สำเร็จ" in caplog.text


def test_run_app_fails_cleanly_when_db_cannot_open(paths, fake_platform, monkeypatch, caplog):
    def broken_services(paths, plat, **kwargs):
        raise RuntimeError("ฐานข้อมูลเป็นเวอร์ชัน 9 ใหม่กว่าโปรแกรมนี้")

    monkeypatch.setattr(lifecycle, "open_services", broken_services)
    monkeypatch.setattr(lifecycle, "Server", lambda ctx: pytest.fail("ห้ามเปิดเซิร์ฟเวอร์"))
    with caplog.at_level(logging.ERROR, logger="yttoolkit"):
        assert lifecycle.run_app(**_run_app_kwargs(paths, fake_platform)) == 1
    assert "ใหม่กว่าโปรแกรมนี้" in caplog.text


def test_open_services_closes_db_when_migrate_fails(paths, fake_platform, monkeypatch):
    from yttoolkit.core.db import Database

    closed = []
    original_close = Database.close

    def boom(self):
        raise RuntimeError("migrate พัง")

    def tracking_close(self):
        closed.append(self)
        original_close(self)

    monkeypatch.setattr(Database, "migrate", boom)
    monkeypatch.setattr(Database, "close", tracking_close)
    with pytest.raises(RuntimeError, match="migrate พัง"):
        lifecycle.open_services(paths, fake_platform)
    assert len(closed) == 1


# ---------- final review: warm-up yt-dlp ตอนเปิดแอพ ----------


class _WarmExtractor:
    def __init__(self, error: BaseException | None = None) -> None:
        self.error = error
        self.calls = 0

    def warm_up(self) -> None:
        self.calls += 1
        if self.error is not None:
            raise self.error


def test_warm_up_runs_in_a_daemon_thread():
    extractor = _WarmExtractor()
    thread = lifecycle.warm_up_in_background(extractor)
    assert thread is not None and thread.daemon
    thread.join(5)
    assert extractor.calls == 1


@pytest.mark.parametrize("error", [ImportError("No module named 'yt_dlp'"), RuntimeError("พัง")])
def test_warm_up_failure_is_logged_never_raised(error, caplog):
    extractor = _WarmExtractor(error)
    with caplog.at_level(logging.WARNING, logger="yttoolkit"):
        thread = lifecycle.warm_up_in_background(extractor)
        thread.join(5)  # -W error: exception ที่หลุดจาก thread จะทำให้เทสล้ม
    assert extractor.calls == 1
    assert "เตรียม yt-dlp ล่วงหน้าไม่สำเร็จ" in caplog.text


def test_warm_up_skipped_for_extractor_without_warm_up():
    from yttoolkit.config import CODE_ROOT
    from yttoolkit.core.extractor import FakeExtractor

    assert lifecycle.warm_up_in_background(FakeExtractor(CODE_ROOT / "tests" / "fixtures")) is None


def test_run_app_warms_up_extractor_after_server_is_ready(paths, fake_platform, monkeypatch):
    warmed = []
    monkeypatch.setattr(lifecycle, "warm_up_in_background", warmed.append)
    code, ctx = _run_capturing_ctx(paths, fake_platform, monkeypatch)
    assert code == 0
    assert warmed == [ctx.extractor]


def test_run_app_does_not_warm_up_when_server_fails(paths, fake_platform, monkeypatch):
    warmed = []
    monkeypatch.setattr(lifecycle, "warm_up_in_background", warmed.append)
    code, _ctx = _run_capturing_ctx(paths, fake_platform, monkeypatch, ready=False)
    assert code == 1
    assert warmed == []


def test_run_app_starts_even_if_warm_up_import_fails(paths, fake_platform, monkeypatch, caplog):
    import sys

    monkeypatch.delenv("YT_TOOLKIT_FAKE", raising=False)
    monkeypatch.setitem(sys.modules, "yt_dlp", None)  # import yt_dlp ล้ม
    threads = []
    original = lifecycle.warm_up_in_background

    def tracking(extractor):
        threads.append(original(extractor))
        return threads[-1]

    monkeypatch.setattr(lifecycle, "warm_up_in_background", tracking)
    with caplog.at_level(logging.WARNING, logger="yttoolkit"):
        code, _ctx = _run_capturing_ctx(paths, fake_platform, monkeypatch)
        threads[0].join(5)
    assert code == 0
    assert "เตรียม yt-dlp ล่วงหน้าไม่สำเร็จ" in caplog.text


# ---------- final review: ปิด httpx client ของ extractor ตอนปิดโปรแกรม ----------


class _ClosingExtractor:
    def __init__(self) -> None:
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


def _services_with(extractor, paths):
    def fake_open_services(p, *args, **kwargs):
        db = Database(paths.db)
        db.migrate()
        settings = SettingsStore(db, paths.data_root / "output")
        events = EventBus()
        queue = QueueRunner(JobStore(db), events, {}, settings=settings, work_root=paths.work, redact=redact_home)
        return lifecycle.Services(
            db=db,
            videos=VideoService(db, extractor),
            extractor=extractor,
            subtitles=None,
            settings=settings,
            events=events,
            media=FakeMediaTools(CODE_ROOT / "tests" / "fixtures" / "media"),
            queue=queue,
        )

    return fake_open_services


@pytest.mark.parametrize("ready", [True, False])
def test_run_app_closes_extractor_on_shutdown(paths, fake_platform, monkeypatch, ready):
    extractor = _ClosingExtractor()
    monkeypatch.setattr(lifecycle, "open_services", _services_with(extractor, paths))
    code, ctx = _run_capturing_ctx(paths, fake_platform, monkeypatch, ready=ready)
    assert code == (0 if ready else 1)
    assert extractor.closed == 1
    assert _db_closed(ctx.db)


def test_run_app_closes_db_even_if_extractor_close_fails(paths, fake_platform, monkeypatch, caplog):
    class Broken(_ClosingExtractor):
        def close(self) -> None:
            raise RuntimeError("ปิดไม่ได้")

    monkeypatch.setattr(lifecycle, "open_services", _services_with(Broken(), paths))
    with caplog.at_level(logging.WARNING, logger="yttoolkit"):
        code, ctx = _run_capturing_ctx(paths, fake_platform, monkeypatch)
    assert code == 0
    assert _db_closed(ctx.db)
    assert "ปิดการเชื่อมต่อของ extractor ไม่สำเร็จ" in caplog.text


def test_run_app_accepts_extractor_without_close(paths, fake_platform, monkeypatch):
    code, ctx = _run_capturing_ctx(paths, fake_platform, monkeypatch, fake=True)
    assert code == 0
    assert not hasattr(ctx.extractor, "close")


# ---------- final review: ล้าง cache เก่าทุก 24 ชม. ระหว่างเปิดโปรแกรม ----------


def _wait_for(predicate, timeout: float = 5.0) -> bool:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_periodic_purge_default_interval_is_24_hours():
    assert lifecycle.PURGE_INTERVAL_S == 24 * 60 * 60


def test_periodic_purge_runs_every_interval_until_stopped(paths, monkeypatch):
    import threading

    calls = []
    monkeypatch.setattr(lifecycle, "purge_stale_cache", lambda db, root, now: calls.append((db, root)) or 0)
    stop = threading.Event()
    thread = lifecycle.start_periodic_purge("db", paths.cache, stop, interval=0.01)
    assert thread.daemon
    assert _wait_for(lambda: len(calls) >= 3)
    stop.set()
    thread.join(5)
    assert not thread.is_alive()
    assert calls[0] == ("db", paths.cache)


def test_periodic_purge_waits_one_interval_before_first_run(paths, monkeypatch):
    import threading

    calls = []
    monkeypatch.setattr(lifecycle, "purge_stale_cache", lambda *a: calls.append(a) or 0)
    stop = threading.Event()
    thread = lifecycle.start_periodic_purge("db", paths.cache, stop, interval=60)
    stop.set()  # ตอนเปิดโปรแกรมล้างไปแล้วใน open_services รอบแรกของ timer จึงอยู่ที่ 24 ชม. ถัดไป
    thread.join(5)
    assert calls == []


def test_periodic_purge_survives_errors(paths, monkeypatch, caplog):
    import threading

    calls = []

    def broken(*args):
        calls.append(args)
        raise OSError("ดิสก์เสีย")

    monkeypatch.setattr(lifecycle, "purge_stale_cache", broken)
    stop = threading.Event()
    with caplog.at_level(logging.ERROR, logger="yttoolkit"):
        thread = lifecycle.start_periodic_purge("db", paths.cache, stop, interval=0.01)
        assert _wait_for(lambda: len(calls) >= 3)  # ล้มแล้วยังวนต่อ ไม่ตาย
        stop.set()
        thread.join(5)
    assert "ล้าง cache เก่าไม่สำเร็จ" in caplog.text


def test_run_app_starts_periodic_purge_and_stops_it_on_shutdown(paths, fake_platform, monkeypatch):
    import threading

    started = []

    def fake_start(db, cache_root, stop, interval=lifecycle.PURGE_INTERVAL_S):
        started.append((db, cache_root, stop, interval))
        thread = threading.Thread(target=stop.wait, daemon=True)
        thread.start()
        return thread

    monkeypatch.setattr(lifecycle, "start_periodic_purge", fake_start)
    code, ctx = _run_capturing_ctx(paths, fake_platform, monkeypatch)
    assert code == 0
    assert len(started) == 1
    db, cache_root, stop, interval = started[0]
    assert db is ctx.db and cache_root == paths.cache
    assert interval == lifecycle.PURGE_INTERVAL_S
    assert stop.is_set()  # ปิดโปรแกรมแล้ว timer หยุดก่อนปิดฐานข้อมูล


def test_run_app_does_not_start_periodic_purge_when_server_fails(paths, fake_platform, monkeypatch):
    started = []
    monkeypatch.setattr(lifecycle, "start_periodic_purge", lambda *a, **k: started.append(a))
    code, _ctx = _run_capturing_ctx(paths, fake_platform, monkeypatch, ready=False)
    assert code == 1
    assert started == []


# ---------- final review: YT_TOOLKIT_FAKE ใช้ได้กับ serve เท่านั้น ----------


def _capture_run_app(monkeypatch):
    seen = {}

    def fake_run_app(**kwargs):
        seen.update(kwargs)
        return 0

    monkeypatch.setattr(lifecycle, "run_app", fake_run_app)
    return seen


def test_start_ignores_fake_env(paths, fake_platform, monkeypatch, caplog):
    monkeypatch.setenv("YT_TOOLKIT_FAKE", "1")
    seen = _capture_run_app(monkeypatch)
    with caplog.at_level(logging.WARNING, logger="yttoolkit"):
        assert lifecycle.start(paths, fake_platform, sleep=lambda s: None) == 0
    assert seen["fake"] is False  # โปรแกรมที่พนักงานเปิดจาก start.bat ใช้ยูทูปจริงเสมอ
    assert "YT_TOOLKIT_FAKE" in caplog.text


def test_start_without_fake_env_says_nothing(paths, fake_platform, monkeypatch, caplog):
    monkeypatch.delenv("YT_TOOLKIT_FAKE", raising=False)
    seen = _capture_run_app(monkeypatch)
    with caplog.at_level(logging.WARNING, logger="yttoolkit"):
        assert lifecycle.start(paths, fake_platform, sleep=lambda s: None) == 0
    assert seen["fake"] is False
    assert "YT_TOOLKIT_FAKE" not in caplog.text


@pytest.mark.parametrize(("env", "expected"), [("1", True), ("0", False), (None, False)])
def test_serve_honours_fake_env(paths, fake_platform, monkeypatch, env, expected):
    if env is None:
        monkeypatch.delenv("YT_TOOLKIT_FAKE", raising=False)
    else:
        monkeypatch.setenv("YT_TOOLKIT_FAKE", env)
    monkeypatch.setattr(lifecycle, "default_paths", lambda: paths)
    monkeypatch.setattr(lifecycle, "current", lambda: fake_platform)
    seen = _capture_run_app(monkeypatch)
    assert lifecycle.serve(port=9000) == 0
    assert seen["fake"] is expected


def test_run_app_ignores_fake_env_unless_asked(paths, fake_platform, monkeypatch):
    from yttoolkit.core.extractor import YtDlpExtractor

    monkeypatch.setenv("YT_TOOLKIT_FAKE", "1")
    code, ctx = _run_capturing_ctx(paths, fake_platform, monkeypatch)
    assert code == 0
    assert ctx.fake is False
    assert isinstance(ctx.extractor, YtDlpExtractor)


# ---------- M4 T2: ตั้งค่า ----------


def test_open_services_fake_mode_output_defaults_under_data_root(paths, fake_platform):
    services = lifecycle.open_services(paths, fake_platform, fake=True)
    try:
        assert services.settings.get()["outputDir"] == str(paths.data_root / "output")
    finally:
        services.db.close()


def test_open_services_real_mode_output_defaults_to_platform_downloads(paths, fake_platform):
    services = lifecycle.open_services(paths, fake_platform, fake=False)
    try:
        assert services.settings.output_dir() == fake_platform.downloads / "YT-Toolkit"
    finally:
        services.db.close()


def test_run_app_sets_settings_on_the_context(paths, fake_platform, monkeypatch):
    code, ctx = _run_capturing_ctx(paths, fake_platform, monkeypatch)
    assert code == 0
    assert ctx.settings is not None
    assert ctx.output_dir == fake_platform.downloads / "YT-Toolkit"
    assert ctx.open_folder is None and ctx.reveal is None


def test_run_app_fake_mode_never_opens_real_folders(paths, fake_platform, monkeypatch, caplog):
    code, ctx = _run_capturing_ctx(paths, fake_platform, monkeypatch, fake=True)
    assert code == 0
    assert ctx.output_dir == paths.data_root / "output"
    assert ctx.open_folder is not None and ctx.reveal is not None
    with caplog.at_level(logging.INFO, logger="yttoolkit"):
        ctx.open_folder(ctx.output_dir)
        ctx.reveal(ctx.output_dir / "x.mp4")
    assert fake_platform.opened == [] and fake_platform.revealed == []
    assert caplog.text.count("โหมดข้อมูลปลอม: ไม่เปิดโฟลเดอร์") == 2
    assert str(paths.data_root) not in caplog.text  # ห้ามบันทึก path เต็มของโฟลเดอร์ผู้ใช้


# ---------- M4 T18: ต่อคิว ตั้งค่า ข่าว และเครื่องมือสื่อเข้ากับวงจรชีวิตของแอพ ----------

JOB_KINDS = {"video", "audio", "subtitle", "contact_sheet", "frames_zip"}


def test_open_services_fake_mode_wires_fakes(paths, fake_platform):
    services = lifecycle.open_services(paths, fake_platform, fake=True)
    try:
        assert isinstance(services.extractor, FakeExtractor)
        assert isinstance(services.media, FakeMediaTools)
        assert services.media.available()  # e2e ไม่มี ffmpeg แต่ POST /jobs ต้องไม่ได้ 409 E_FFMPEG_MISSING
        assert services.media._root == CODE_ROOT / "tests" / "fixtures" / "media"
        assert isinstance(services.events, EventBus)
        assert isinstance(services.queue, QueueRunner)
        assert services.queue._delay_range == lifecycle.FAKE_DELAY_RANGE == (0.05, 0.2)
        assert services.queue._redact is redact_home
        assert services.queue._work_root == paths.work
        assert services.queue._settings is services.settings
        assert set(services.queue._handlers) == JOB_KINDS
        assert services.queue._thread is None  # ยังไม่เริ่ม (เริ่มหลังเซิร์ฟเวอร์พร้อม)
        assert services.settings.output_dir() == paths.data_root / "output"
    finally:
        services.db.close()


def test_open_services_real_mode_wires_ffmpeg_tools(paths, fake_platform, monkeypatch):
    monkeypatch.setenv("YT_TOOLKIT_FFMPEG_PATH_LOOKUP", "0")
    fake_platform.popen_flags = 0x08000000
    services = lifecycle.open_services(paths, fake_platform, fake=False)
    try:
        assert isinstance(services.extractor, YtDlpExtractor)
        assert isinstance(services.media, FfmpegTools)
        assert services.media._popen_flags == 0x08000000
        assert services.media.available() is False  # ยังไม่มี ffmpeg ใน <data>/bin และปิดการหาใน PATH
        exe = paths.bin / fake_platform.exe_name("ffmpeg")
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_bytes(b"")
        assert services.media.ffmpeg_path() == exe  # หาใหม่ทุกครั้ง (ผู้ใช้เพิ่งติดตั้ง ffmpeg)
        assert services.queue._delay_range == (2.0, 5.0)  # ค่าเริ่มต้นของตัวรันคิว
    finally:
        services.db.close()


def test_open_services_closes_db_when_building_queue_fails(paths, fake_platform, monkeypatch):
    closed = []
    original_close = Database.close

    def tracking_close(self):
        closed.append(self)
        original_close(self)

    def broken_queue(*args, **kwargs):
        raise RuntimeError("สร้างคิวไม่ได้")

    monkeypatch.setattr(Database, "close", tracking_close)
    monkeypatch.setattr(lifecycle, "QueueRunner", broken_queue)
    with pytest.raises(RuntimeError, match="สร้างคิวไม่ได้"):
        lifecycle.open_services(paths, fake_platform, fake=True)
    assert len(closed) == 1


def test_run_app_sets_queue_fields_on_the_context(paths, fake_platform, monkeypatch):
    code, ctx = _run_capturing_ctx(paths, fake_platform, monkeypatch, fake=True)
    assert code == 0
    assert ctx.queue is not None and ctx.events is not None and ctx.media is not None
    assert ctx.settings is not None
    assert ctx.on_bot_check == ctx.queue.brake
    assert ctx.pending_jobs == ctx.queue.pending_count
    assert ctx.output_dir == paths.data_root / "output"


def test_run_app_starts_queue_after_server_is_ready(paths, fake_platform, monkeypatch):
    seen = {}
    server = FakeServer()

    def make_server(ctx):
        seen["ctx"] = ctx
        seen["started_at_create"] = ctx.queue._thread is not None
        server.start = ctx.request_shutdown
        return server

    def ready(timeout: float = 15.0) -> bool:
        seen["started_before_ready"] = seen["ctx"].queue._thread is not None
        return True

    server.wait_until_ready = ready
    monkeypatch.setattr(lifecycle, "Server", make_server)
    assert lifecycle.run_app(**_run_app_kwargs(paths, fake_platform), fake=True) == 0
    assert seen["started_at_create"] is False and seen["started_before_ready"] is False
    assert seen["ctx"].queue._thread is not None  # เริ่มแล้วหลังพร้อม
    assert seen["ctx"].queue._stopping  # และหยุดแล้วตอนปิดโปรแกรม


def test_run_app_does_not_start_queue_when_server_fails(paths, fake_platform, monkeypatch):
    code, ctx = _run_capturing_ctx(paths, fake_platform, monkeypatch, ready=False, fake=True)
    assert code == 1
    assert ctx.queue._thread is None
    assert ctx.events.subscribe().get(0) is CLOSED  # bus ปิดแล้ว


def test_run_app_shuts_queue_down_when_post_ready_setup_fails(paths, fake_platform, monkeypatch):
    """พังหลังเซิร์ฟเวอร์พร้อม (เช่นเริ่ม timer ล้าง cache ไม่ได้) ก็ยังหยุดคิว ปิด bus และหยุดเซิร์ฟเวอร์"""
    captured = []
    server = FakeServer()

    def make_server(ctx):
        captured.append(ctx)
        return server

    def broken_purge(*args, **kwargs):
        raise RuntimeError("เริ่ม timer ไม่ได้")

    monkeypatch.setattr(lifecycle, "Server", make_server)
    monkeypatch.setattr(lifecycle, "start_periodic_purge", broken_purge)
    with pytest.raises(RuntimeError, match="เริ่ม timer ไม่ได้"):
        lifecycle.run_app(**_run_app_kwargs(paths, fake_platform), fake=True)
    ctx = captured[0]
    assert ctx.queue._thread is not None and ctx.queue._stopping  # เริ่มแล้วและหยุดแล้ว
    assert ctx.events.subscribe().get(0) is CLOSED
    assert server.stopped
    assert not paths.app_json.exists()


def _job_running_in_db(paths):
    db = Database(paths.db)
    db.migrate()
    store = JobStore(db)
    (job,) = store.add([NewJob("aqz-KE-bpKQ", "video", {}, "Big Buck Bunny")])
    store.transition(job.id, "running")
    db.close()
    return job.id


def test_run_app_recovers_running_jobs_before_server_starts(paths, fake_platform, monkeypatch):  # AC-Q-05
    job_id = _job_running_in_db(paths)
    (paths.work / job_id).mkdir(parents=True)
    (paths.work / job_id / "media.mp4.part").write_bytes(b"x")
    seen = {}
    server = FakeServer()

    def make_server(ctx):
        job = ctx.queue.store.get(job_id)
        seen["status"], seen["code"] = job.status, job.error_code
        seen["work"] = list(paths.work.iterdir())
        server.start = ctx.request_shutdown
        return server

    monkeypatch.setattr(lifecycle, "Server", make_server)
    assert lifecycle.run_app(**_run_app_kwargs(paths, fake_platform), fake=True) == 0
    assert seen == {"status": "interrupted", "code": "E_INTERRUPTED", "work": []}


def test_run_app_shutdown_order(paths, fake_platform, monkeypatch):
    order = []
    real_open = lifecycle.open_services

    def recording_open(p, plat, fake=False):
        services = real_open(p, plat, fake=fake)
        real_shutdown, real_publish, real_close = (
            services.queue.shutdown, services.events.publish, services.events.close
        )

        def shutdown(timeout=5.0):
            order.append(("queue.shutdown", timeout))
            real_shutdown(timeout=timeout)

        def publish(name, data):
            order.append(("publish", name))
            real_publish(name, data)

        def close():
            order.append(("events.close",))
            real_close()

        services.queue.shutdown = shutdown
        services.events.publish = publish
        services.events.close = close
        return services

    server = FakeServer()

    def make_server(ctx):
        server.start = ctx.request_shutdown
        server.stop = lambda: order.append(("server.stop",))
        return server

    monkeypatch.setattr(lifecycle, "open_services", recording_open)
    monkeypatch.setattr(lifecycle, "Server", make_server)
    assert lifecycle.run_app(**_run_app_kwargs(paths, fake_platform), fake=True) == 0
    assert order[:4] == [
        ("queue.shutdown", 5.0),
        ("publish", "app.shutdown"),
        ("events.close",),
        ("server.stop",),
    ]


def test_server_config_has_graceful_shutdown_timeout(paths, fake_platform):
    ctx = AppContext(
        paths=paths, plat=fake_platform, port=8851, token="t", version="0", commit=None,
        output_dir=paths.data_root / "output", request_shutdown=lambda: None,
    )
    assert lifecycle.Server(ctx).config.timeout_graceful_shutdown == lifecycle.GRACEFUL_SHUTDOWN_S == 3


def test_stop_waits_longer_than_the_app_needs_to_shut_down():  # review M5
    # หยุดคิว (รองานหยุด) + uvicorn รอ request ค้าง + เผื่อ 1 วินาที ต้องจบก่อน stop ตัดสินใจ kill
    assert lifecycle.QUEUE_SHUTDOWN_TIMEOUT_S + lifecycle.GRACEFUL_SHUTDOWN_S + 1 < lifecycle.STOP_WAIT_S


def test_stop_polls_for_stop_wait_before_killing(paths, fake_platform):
    _running(paths, fake_platform, holds_lock=True)
    slept: list[float] = []
    lifecycle.stop(
        paths,
        fake_platform,
        post=lambda url, json, headers, timeout: FakeResponse(200, {"ok": True}),
        sleep=slept.append,
        out=lambda m: None,
    )
    assert sum(slept) == pytest.approx(lifecycle.STOP_WAIT_S)
    assert set(slept) == {lifecycle.STOP_POLL_S}


# ---------- ล้างไฟล์ค้างของงานที่หยุดกลางคัน ----------

TITLE = "Big Buck Bunny"


def _sweep_env(paths):
    db = Database(paths.db)
    db.migrate()
    store = JobStore(db)
    root = (paths.data_root / "output").resolve()
    folder = files.plan_output(root, TITLE, "aqz-KE-bpKQ", "", "mp4").parent
    folder.mkdir(parents=True)
    done, stopped = store.add([NewJob("aqz-KE-bpKQ", "subtitle", {}, TITLE), NewJob("aqz-KE-bpKQ", "video", {}, TITLE)])
    store.transition(done.id, "running")
    (folder / f"{TITLE} (2).th.srt").write_bytes(b"")  # ไฟล์ผลลัพธ์ของงานที่เสร็จ (ว่างจริง) ห้ามลบ
    output = OutputFile(str(root), f"{folder.name}/{TITLE} (2).th.srt", 0, "subtitle")
    store.transition(done.id, "done", outputs=(output,))
    store.transition(stopped.id, "running")
    return db, store, root, folder, stopped.id


@pytest.mark.parametrize(
    ("name", "ours"),
    [
        (f"{TITLE}.mp4", True),
        (f"{TITLE} (2).mp4", True),
        (f"{TITLE} (99).m4a", True),
        (f"{TITLE}.mp3.part", True),
        (f"{TITLE} (ไม่มีเสียง).mp4", True),
        (f"{TITLE} (ไม่มีเสียง) (3).mp4", True),
        (f"{TITLE} - contact sheet.jpg", True),
        (f"{TITLE} - frames (2).zip", True),
        (f"{TITLE}.wav", True),
        (f"{TITLE}.th.srt", True),
        (f"{TITLE} (2).en-US.md", True),
        (f"{TITLE}.th.txt.part", True),
        (f"{TITLE} notes.docx", False),
        (f"{TITLE} backup.part", False),
        (f"{TITLE}.docx.part", False),
        (f"{TITLE} (1).mp4", False),  # files ไม่เคยสร้าง (1)
        (f"{TITLE} (100).mp4", False),
        (f"{TITLE}.srt", False),  # ซับต้องมีรหัสภาษา
        (f"{TITLE}.png", False),
        (f"{TITLE}.MP4", False),
        ("notes.txt", False),
        ("แหล่งที่มา.txt", False),
    ],
)
def test_toolkit_name_pattern_matches_only_names_the_handlers_write(name, ours):
    assert bool(lifecycle.toolkit_name_pattern(TITLE).fullmatch(name)) is ours


def test_sweep_removes_placeholders_and_part_files_of_interrupted_jobs(paths):
    db, store, root, folder, job_id = _sweep_env(paths)
    try:
        leftovers = [
            f"{TITLE}.mp4",  # ชื่อที่จองไว้แล้วโปรแกรมดับก่อนย้ายไฟล์เข้า
            f"{TITLE} (ไม่มีเสียง) (2).mp4",
            f"{TITLE} - contact sheet.jpg",
        ]
        for name in leftovers:
            (folder / name).write_bytes(b"")
        (folder / f"{TITLE}.m4a.part").write_bytes(b"half")  # คัดลอกข้ามไดรฟ์ค้างครึ่งทาง
        (folder / f"{TITLE} (3).th.srt.part").write_bytes(b"half")
        kept = {
            f"{TITLE} (2).th.srt": b"",  # ผลลัพธ์ของงานที่เสร็จ
            f"{TITLE} (3).mp4": b"real video",  # ไฟล์จริง
            "แหล่งที่มา.txt": b"source",
            "notes.txt": b"",  # ไฟล์ของผู้ใช้
            f"{TITLE} notes.docx": b"",  # ไฟล์ของผู้ใช้ที่ชื่อขึ้นต้นด้วยชื่อคลิป ว่างเปล่า
            f"{TITLE} backup.part": b"",  # .part ที่โปรแกรมไม่ได้สร้าง
            f"{TITLE}.docx.part": b"x",
        }
        for name, data in kept.items():
            if not (folder / name).exists():
                (folder / name).write_bytes(data)
        stranded = [job.id for job in store.running()]
        store.interrupt_running("หยุดกลางคัน")
        assert lifecycle.sweep_interrupted_outputs(store, paths.data_root / "output", stranded) == 5
        assert sorted(p.name for p in folder.iterdir()) == sorted(kept)
        # เปิดโปรแกรมรอบถัดไป (งานเดิมยังอยู่ใน 20 งานล่าสุด) ไฟล์ของผู้ใช้ยังอยู่ครบ
        assert lifecycle.sweep_interrupted_outputs(store, paths.data_root / "output") == 0
        assert sorted(p.name for p in folder.iterdir()) == sorted(kept)
    finally:
        db.close()


def test_sweep_ignores_folders_of_jobs_that_are_not_interrupted(paths):
    db, store, root, folder, job_id = _sweep_env(paths)
    try:
        (folder / f"{TITLE}.mp4").write_bytes(b"")  # งานยังรันอยู่ (เช่นเรียกผิดเวลา) ไม่ใช่งานที่หยุดกลางคัน
        assert lifecycle.sweep_interrupted_outputs(store, root, [job_id]) == 0
        assert (folder / f"{TITLE}.mp4").exists()
    finally:
        db.close()


def test_sweep_missing_folder_is_fine(paths):
    db, store, root, folder, job_id = _sweep_env(paths)
    try:
        store.interrupt_running("หยุดกลางคัน")
        for child in folder.iterdir():
            child.unlink()
        folder.rmdir()
        assert lifecycle.sweep_interrupted_outputs(store, root, [job_id]) == 0
    finally:
        db.close()


def test_run_app_sweeps_outputs_of_recovered_jobs(paths, fake_platform, monkeypatch):
    _job_running_in_db(paths)
    folder = files.plan_output((paths.data_root / "output").resolve(), TITLE, "aqz-KE-bpKQ", "", "mp4").parent
    folder.mkdir(parents=True)
    (folder / f"{TITLE}.mp4").write_bytes(b"")
    code, _ctx = _run_capturing_ctx(paths, fake_platform, monkeypatch, fake=True)
    assert code == 0
    assert not (folder / f"{TITLE}.mp4").exists()


def test_recover_jobs_failure_is_logged_not_raised(paths, fake_platform, caplog):
    services = lifecycle.open_services(paths, fake_platform, fake=True)

    def boom():
        raise RuntimeError("ฐานข้อมูลล็อก")

    try:
        services.queue.recover = boom
        with caplog.at_level(logging.ERROR, logger="yttoolkit"):
            lifecycle.recover_jobs(services)
        assert "กู้งานที่ค้างจากรอบก่อนไม่สำเร็จ" in caplog.text
    finally:
        services.db.close()


# ---------- tray: จำนวนงานที่กำลังทำ ----------


class _FakeIcon:
    def __init__(self) -> None:
        self.updates = 0
        self.stopped = False

    def update_menu(self) -> None:
        self.updates += 1

    def run(self) -> None:
        pass

    def stop(self) -> None:
        self.stopped = True


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def _refresher(icon=None, interval: float = 1.0):
    bus = EventBus()
    clock = _Clock()
    icon = icon or _FakeIcon()
    return bus, clock, icon, lifecycle.TrayRefresher(bus, icon, interval=interval, monotonic=clock)


def test_tray_refresher_updates_menu_at_most_once_per_interval():
    bus, clock, icon, refresher = _refresher()
    try:
        refresher.handle(Event("job.created", {"id": "a"}))
        assert icon.updates == 1
        for n in range(5):  # มาติดกันภายในช่วงเดียว = รอจนครบช่วงแล้วอัปเดตครั้งเดียว
            refresher.handle(Event("job.updated", {"id": f"j{n}", "status": "running"}))
        assert icon.updates == 1
        assert refresher.next_wait() == pytest.approx(1.0)
        clock.now += 0.4
        assert refresher.next_wait() == pytest.approx(0.6)
        refresher.handle(None)
        assert icon.updates == 1
        clock.now += 0.6
        refresher.handle(None)  # รอครบช่วงแล้วไม่มีข่าวใหม่ = อัปเดตที่ค้างไว้
        assert icon.updates == 2
        assert refresher.next_wait() == 1.0  # ไม่มีอะไรค้าง
    finally:
        bus.close()


def test_tray_refresher_ignores_progress_and_other_events():
    bus, clock, icon, refresher = _refresher()
    try:
        refresher.handle(Event("job.updated", {"id": "p", "progress": 0.5, "speedBps": 10}))
        refresher.handle(Event("queue.paused", {"until": "x", "reason": "E_BOT_CHECK"}))
        refresher.handle(None)
        assert icon.updates == 0
        refresher.handle(Event("job.updated", {"id": "p", "status": "done"}))
        assert icon.updates == 1
    finally:
        bus.close()


def test_tray_refresher_survives_update_errors(caplog):
    class Broken(_FakeIcon):
        def update_menu(self) -> None:
            super().update_menu()
            raise RuntimeError("เมนูพัง")

    bus, clock, icon, refresher = _refresher(Broken())
    try:
        with caplog.at_level(logging.WARNING, logger="yttoolkit"):
            refresher.handle(Event("job.created", {"id": "a"}))
            clock.now += 1.0
            refresher.handle(Event("job.created", {"id": "b"}))
        assert icon.updates == 2
        assert "อัปเดตเมนู tray ไม่สำเร็จ" in caplog.text
    finally:
        bus.close()


def test_tray_refresher_poll_reads_the_bus_and_stops_when_it_closes():
    bus, clock, icon, refresher = _refresher()
    bus.publish("job.created", {"id": "a"})
    assert refresher.poll(0) is True
    assert icon.updates == 1
    bus.close()
    assert refresher.poll(0) is False


def test_tray_refresher_resubscribes_when_its_own_mailbox_closes():  # review M4
    bus, clock, icon, refresher = _refresher()
    try:
        refresher._sub.close()  # กล่องข่าวของตัวเองถูกปิด (เช่นอ่านไม่ทันจนล้น) แต่ bus ยังเปิดอยู่
        assert bus.subscriber_count == 0
        assert refresher.poll(0) is True  # ยังฟังต่อ
        assert bus.subscriber_count == 1
        assert icon.updates == 1  # อาจพลาดข่าวเปลี่ยนสถานะไป จึงอัปเดตเมนูหนึ่งครั้ง
        clock.now += 1.0
        bus.publish("job.created", {"id": "b"})
        assert refresher.poll(0) is True
        assert icon.updates == 2
    finally:
        bus.close()
    assert refresher.poll(0) is False  # bus ปิดจริง สมัครใหม่ก็ยังปิด = เลิกฟัง


def test_start_tray_refresher_thread_ends_when_bus_closes():
    bus = EventBus()
    icon = _FakeIcon()
    thread = lifecycle.start_tray_refresher(bus, icon)
    try:
        assert thread.daemon
        bus.publish("job.created", {"id": "a"})
        assert _wait_for(lambda: icon.updates == 1, 2)
    finally:
        bus.close()
        thread.join(2)
    assert not thread.is_alive()


def test_run_app_with_tray_passes_running_count_and_refreshes(paths, fake_platform, monkeypatch):
    _job_running_in_db(paths)
    seen = {}
    icon = _FakeIcon()
    refreshers = []

    def fake_build_tray(open_app, open_output, quit_app, running_count):
        seen["value"] = running_count()
        return icon

    monkeypatch.setattr(tray, "build_tray", fake_build_tray)
    monkeypatch.setattr(lifecycle, "start_tray_refresher", lambda bus, i: refreshers.append((bus, i)))
    monkeypatch.setattr(lifecycle, "Server", lambda ctx: FakeServer())
    kwargs = {**_run_app_kwargs(paths, fake_platform), "with_tray": True}
    assert lifecycle.run_app(**kwargs, fake=True) == 0
    assert seen["value"] == 0  # งานที่ค้าง running ถูกกู้เป็น interrupted ก่อน
    assert len(refreshers) == 1 and refreshers[0][1] is icon


def test_running_count_reflects_running_jobs_and_never_raises(paths, fake_platform):
    services = lifecycle.open_services(paths, fake_platform, fake=True)
    count = lifecycle.running_count(services)
    try:
        assert count() == 0
        (job,) = services.queue.store.add([NewJob("aqz-KE-bpKQ", "video", {})])
        services.queue.store.transition(job.id, "running")
        assert count() == 1
    finally:
        services.db.close()
    assert count() == 0  # ฐานข้อมูลปิดแล้ว เมนูยังเปิดได้


def test_tray_open_output_uses_current_settings(paths, fake_platform, monkeypatch):
    captured = []
    target = paths.data_root / "เลือกเอง"

    def fake_build_tray(open_app, open_output, quit_app, running_count):
        icon = _FakeIcon()

        def run() -> None:  # ระหว่างแอพเปิดอยู่ ผู้ใช้เปลี่ยนโฟลเดอร์ แล้วกด "เปิดโฟลเดอร์ผลลัพธ์" ใน tray
            open_output()
            captured[0].settings.patch({"outputDir": str(target)})
            open_output()

        icon.run = run
        return icon

    def make_server(ctx):
        captured.append(ctx)
        return FakeServer()

    monkeypatch.setattr(tray, "build_tray", fake_build_tray)
    monkeypatch.setattr(lifecycle, "start_tray_refresher", lambda bus, i: None)
    monkeypatch.setattr(lifecycle, "Server", make_server)
    kwargs = {**_run_app_kwargs(paths, fake_platform), "with_tray": True}
    assert lifecycle.run_app(**kwargs) == 0  # โหมดจริง: open_folder ของ platform
    assert fake_platform.opened == [fake_platform.downloads / "YT-Toolkit", target]


# ---------- log: ซ่อนโฟลเดอร์ผู้ใช้ (ruling M6) ----------


@pytest.fixture
def root_logger():
    """คืน root logger แล้วถอด handler ที่เทสเพิ่มออกหลังจบ (ไม่ให้ไฟล์ log ค้างข้ามเทส)"""
    root = logging.getLogger()
    before = list(root.handlers)
    level = root.level
    yield root, before
    for h in list(root.handlers):
        if h not in before:
            root.removeHandler(h)
            h.close()
    root.setLevel(level)


def _format_with_filter(record) -> str:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.addFilter(lifecycle.HomePathFilter())
    assert handler.filter(record)
    return handler.format(record)


def test_home_path_filter_redacts_message_args_and_traceback():
    home = str(Path.home())
    try:
        raise OSError(f"เขียนไม่ได้: {home}\\Downloads\\YT-Toolkit\\a.mp4")
    except OSError:
        exc_info = sys.exc_info()
    record = logging.LogRecord(
        "yttoolkit", logging.ERROR, __file__, 1, "ย้ายไฟล์ %s ไม่สำเร็จ", (f"{home}\\Downloads\\x.mp4",), exc_info
    )
    text = _format_with_filter(record)
    assert home not in text
    assert "~\\Downloads\\x.mp4" in text
    assert "~\\Downloads\\YT-Toolkit\\a.mp4" in text  # ใน traceback ด้วย
    assert "Traceback" in text


def test_home_path_filter_leaves_other_text_alone():
    record = logging.LogRecord("yttoolkit", logging.INFO, __file__, 1, "งาน %s จบด้วย %s", ("abc", "done"), None)
    assert _format_with_filter(record) == "งาน abc จบด้วย done"


def _app_log_filters(root, before) -> list:
    added = [h for h in root.handlers if h not in before]
    assert len(added) == 1
    assert isinstance(added[0], logging.handlers.RotatingFileHandler)
    return [f for f in added[0].filters if isinstance(f, lifecycle.HomePathFilter)]


def test_setup_file_logging_installs_home_filter_once(paths, root_logger):
    lifecycle.setup_file_logging(paths)
    lifecycle.setup_file_logging(paths)
    assert len(_app_log_filters(*root_logger)) == 1


def test_stop_installs_home_filter_on_app_log(paths, fake_platform, root_logger):  # review M3
    probe.setup_file_log(paths)  # สิ่งที่ __main__ ทำก่อนเรียก stop
    assert lifecycle.stop(paths, fake_platform, out=lambda m: None) == 0
    assert len(_app_log_filters(*root_logger)) == 1
    lifecycle.stop(paths, fake_platform, out=lambda m: None)
    assert len(_app_log_filters(*root_logger)) == 1  # เรียกซ้ำไม่ใส่ซ้ำ
