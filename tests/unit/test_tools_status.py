import sys
import urllib.error
from datetime import date
from pathlib import Path

from yttoolkit.core import tools
from yttoolkit.core.tools import ToolStatus
from yttoolkit.platform import current

REAL_FETCH_LATEST = tools._fetch_latest_ytdlp  # เก็บตัวจริงไว้ก่อน fixture กลางจะแทนเป็นออฟไลน์


def test_find_ffmpeg_prefers_bin(paths, fake_platform):
    exe = paths.bin / "ffmpeg.exe"
    exe.write_bytes(b"x")
    assert tools.find_ffmpeg(paths, fake_platform) == exe


def test_find_ffmpeg_path_lookup_can_be_disabled(paths, fake_platform, monkeypatch):
    monkeypatch.setattr(tools.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setenv("YT_TOOLKIT_FFMPEG_PATH_LOOKUP", "0")
    assert tools.find_ffmpeg(paths, fake_platform) is None
    monkeypatch.setenv("YT_TOOLKIT_FFMPEG_PATH_LOOKUP", "1")
    assert tools.find_ffmpeg(paths, fake_platform) == Path("/usr/bin/ffmpeg")


def test_parse_ffmpeg_version():
    line = "ffmpeg version 8.1-full_build-www.gyan.dev Copyright (c) 2000-2026"
    assert tools.parse_ffmpeg_version(line) == "8.1-full_build-www.gyan.dev"
    assert tools.parse_ffmpeg_version("garbage") is None
    assert tools.parse_ffmpeg_version(None) is None


def test_ffmpeg_status_missing(paths, fake_platform, monkeypatch):
    monkeypatch.setenv("YT_TOOLKIT_FFMPEG_PATH_LOOKUP", "0")
    status = tools.ffmpeg_status(paths, fake_platform)
    assert status.status == "error"
    assert status.name == "ffmpeg"


def test_ffmpeg_status_ok(paths, fake_platform, monkeypatch):
    (paths.bin / "ffmpeg.exe").write_bytes(b"x")
    monkeypatch.setattr(tools, "_run_version", lambda exe, plat, arg="--version": "ffmpeg version 8.1 Copyright")
    status = tools.ffmpeg_status(paths, fake_platform)
    assert status == ToolStatus("ok", name="ffmpeg", version="8.1", path=str(paths.bin / "ffmpeg.exe"))


def test_find_js_runtime_prefers_bundled_deno():
    # deno ติดตั้งมากับ dependency ของโปรเจกต์ จึงต้องเจอเสมอ (ยืนยัน PRD Q4 บนทุกระบบใน CI)
    status = tools.find_js_runtime(current())
    assert status.status == "ok"
    assert status.name == "deno"
    assert status.version and status.version[0].isdigit()


def test_find_js_runtime_uses_exe_name_for_bundled_deno(monkeypatch, tmp_path, fake_platform):
    monkeypatch.setattr(tools, "scripts_dir", lambda: tmp_path)
    monkeypatch.setattr(tools.shutil, "which", lambda name: None)
    seen: list[object] = []
    monkeypatch.setattr(tools, "_run_version", lambda exe, plat, arg="--version": seen.append(exe) or "deno 2.0.0 (stable)")
    # ชื่อที่ระบบนี้ไม่ใช้ต้องไม่ถูกลอง: FakePlatform (windows) ใช้ deno.exe เท่านั้น
    (tmp_path / "deno").write_bytes(b"x")
    assert tools.find_js_runtime(fake_platform).status == "warn"
    assert seen == []
    (tmp_path / "deno.exe").write_bytes(b"x")
    status = tools.find_js_runtime(fake_platform)
    assert status.status == "ok"
    assert status.path == str(tmp_path / "deno.exe")
    # ระบบที่ exe_name คืนชื่อเดิม (macOS) ใช้ deno เปล่า
    (tmp_path / "deno.exe").unlink()
    fake_platform.name = "macos"
    assert tools.find_js_runtime(fake_platform).path == str(tmp_path / "deno")


def test_find_ffmpeg_uses_exe_name(paths, fake_platform, monkeypatch):
    monkeypatch.setenv("YT_TOOLKIT_FFMPEG_PATH_LOOKUP", "0")
    fake_platform.name = "macos"
    (paths.bin / "ffmpeg.exe").write_bytes(b"x")
    assert tools.find_ffmpeg(paths, fake_platform) is None
    (paths.bin / "ffmpeg").write_bytes(b"x")
    assert tools.find_ffmpeg(paths, fake_platform) == paths.bin / "ffmpeg"


def test_run_version_passes_platform_popen_flags(monkeypatch, fake_platform):
    captured: dict = {}

    def fake_run(cmd, adopt, **kwargs):
        captured.update(kwargs, adopt=adopt)

        class Out:
            stdout = "x 1"
            stderr = ""

        return Out()

    monkeypatch.setattr(tools, "run_adopted", fake_run)
    fake_platform.popen_flags = 0x1234
    assert tools._run_version("exe", fake_platform) == "x 1"
    assert captured["creationflags"] == 0x1234
    assert captured["adopt"] == fake_platform.adopt_child  # M6 รอบ D1: ffmpeg -version ก็ผูกกับแอพ


def test_find_js_runtime_falls_back_to_node(monkeypatch, tmp_path, fake_platform):
    monkeypatch.setattr(tools, "scripts_dir", lambda: tmp_path)
    monkeypatch.setattr(tools.shutil, "which", lambda name: "node" if name == "node" else None)
    monkeypatch.setattr(tools, "_run_version", lambda exe, plat, arg="--version": "v24.14.0")
    status = tools.find_js_runtime(fake_platform)
    assert status.status == "warn"
    assert status.name == "node"
    assert status.version == "24.14.0"


def test_find_js_runtime_none(monkeypatch, tmp_path, fake_platform):
    monkeypatch.setattr(tools, "scripts_dir", lambda: tmp_path)
    monkeypatch.setattr(tools.shutil, "which", lambda name: None)
    status = tools.find_js_runtime(fake_platform)
    assert status.status == "warn"
    assert status.name is None
    assert status.message == "บางคุณภาพอาจไม่แสดง เพราะเครื่องยังไม่มีตัวช่วยที่ yt-dlp ต้องใช้"  # PRD ข้อ 7 E_JS_RUNTIME_MISSING


def test_ytdlp_status_age():
    fresh = tools.ytdlp_status(version="2026.09.20", today=date(2026, 9, 28))
    assert fresh.status == "ok"
    assert "8 วัน" in (fresh.message or "")
    old = tools.ytdlp_status(version="2026.08.01", today=date(2026, 9, 28))
    assert old.status == "warn"
    assert old.message == "อัปเดตล่าสุด 58 วันก่อน ถ้าโหลดคลิปไม่ได้ ให้ปิดแล้วเปิดใหม่ด้วย start.bat เพื่อรับเวอร์ชันล่าสุด"


def test_ytdlp_status_ok_when_already_latest_even_if_old():
    status = tools.ytdlp_status(version="2026.08.01", today=date(2026, 9, 28), fetch_latest=lambda: "2026.8.1")
    assert status.status == "ok"
    assert status.message == "อัปเดตล่าสุด 58 วันก่อน (เป็นเวอร์ชันล่าสุด)"


def test_ytdlp_status_warns_when_newer_version_exists():
    status = tools.ytdlp_status(version="2026.09.20", today=date(2026, 9, 28), fetch_latest=lambda: "2026.9.27")
    assert status.status == "warn"
    assert status.message == "มีเวอร์ชันใหม่ 2026.9.27 ถ้าโหลดคลิปไม่ได้ ให้ปิดแล้วเปิดใหม่ด้วย start.bat เพื่อรับเวอร์ชันล่าสุด"


def test_ytdlp_status_ok_within_grace_period_even_if_newer_exists():  # final fix item 4
    # bot อัปเดตทุกวันต้องมีเวลาทำงาน ติดตั้งมาไม่เกิน 7 วันยังไม่เตือน
    for installed, age in (("2026.09.28", 0), ("2026.09.21", 7)):
        status = tools.ytdlp_status(version=installed, today=date(2026, 9, 28), fetch_latest=lambda: "2026.9.28.1")
        assert status.status == "ok"
        assert status.message == f"อัปเดตล่าสุด {age} วันก่อน"


def test_ytdlp_status_warns_once_grace_period_is_over():  # final fix item 4
    status = tools.ytdlp_status(version="2026.09.20", today=date(2026, 9, 28), fetch_latest=lambda: "2026.9.21")
    assert status.status == "warn"
    assert status.message == "มีเวอร์ชันใหม่ 2026.9.21 ถ้าโหลดคลิปไม่ได้ ให้ปิดแล้วเปิดใหม่ด้วย start.bat เพื่อรับเวอร์ชันล่าสุด"


def test_ytdlp_status_falls_back_to_age_rule_when_lookup_fails():
    def offline() -> str:
        raise OSError("offline")

    def bad_json() -> str:
        raise ValueError("Expecting value")

    for fetch in (offline, bad_json, lambda: "not-a-version"):
        tools._latest_ytdlp_cache = None
        old = tools.ytdlp_status(version="2026.08.01", today=date(2026, 9, 28), fetch_latest=fetch)
        assert old.status == "warn"
        assert old.message == "อัปเดตล่าสุด 58 วันก่อน ถ้าโหลดคลิปไม่ได้ ให้ปิดแล้วเปิดใหม่ด้วย start.bat เพื่อรับเวอร์ชันล่าสุด"


def test_latest_ytdlp_version_is_cached_for_an_hour():
    calls = []
    clock = [1000.0]

    def fetch() -> str:
        calls.append(1)
        return "2026.9.27"

    def now() -> float:
        return clock[0]

    assert tools.latest_ytdlp_version(fetch, clock=now) == "2026.9.27"
    clock[0] += 3599
    assert tools.latest_ytdlp_version(fetch, clock=now) == "2026.9.27"
    assert len(calls) == 1
    clock[0] += 2
    tools.latest_ytdlp_version(fetch, clock=now)
    assert len(calls) == 2


def test_fetch_latest_ytdlp_reads_pypi_info_version(monkeypatch):
    import httpx

    seen = {}

    def fake_get(url, timeout):
        seen["url"], seen["timeout"] = url, timeout
        return httpx.Response(200, json={"info": {"version": "2026.9.27"}}, request=httpx.Request("GET", url))

    monkeypatch.setattr(tools.httpx, "get", fake_get)
    assert REAL_FETCH_LATEST() == "2026.9.27"
    assert seen == {"url": "https://pypi.org/pypi/yt-dlp/json", "timeout": 3}


def test_ytdlp_status_real_version_is_ok_shape():
    status = tools.ytdlp_status()
    assert status.name == "yt-dlp"
    assert status.version


def test_disk_status(tmp_path, monkeypatch):
    class Usage:
        free = 1 * 1024**3

    monkeypatch.setattr(tools.shutil, "disk_usage", lambda p: Usage())
    low = tools.disk_status(tmp_path)
    assert low.status == "warn"
    assert low.message == "เหลือ 1 GB"
    Usage.free = 50 * 1024**3
    fine = tools.disk_status(tmp_path)
    assert fine.status == "ok"
    assert fine.message == "เหลือ 50 GB"


def test_output_status(tmp_path):
    assert tools.output_status(tmp_path / "out").status == "ok"
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert tools.output_status(blocker / "sub").status == "error"


def test_output_status_two_checks_at_once_both_ok(tmp_path):
    # หน้าตรวจสุขภาพสองคำขอพร้อมกัน: ไฟล์ทดสอบชื่อไม่ซ้ำกัน จึงไม่ลบของอีกฝั่งจนฟ้องว่าเขียนไม่ได้
    import threading

    out = tmp_path / "out"
    barrier = threading.Barrier(2)
    results: list[str] = []

    def check() -> None:
        for _ in range(100):
            barrier.wait()
            results.append(tools.output_status(out).status)

    threads = [threading.Thread(target=check) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("ok") == 200
    assert list(out.iterdir()) == []


def test_network_status():
    assert tools.network_status(lambda url: 200).status == "ok"

    def boom(url):
        raise urllib.error.URLError("offline")

    assert tools.network_status(boom).status == "error"

    def http_error(url):
        raise urllib.error.HTTPError(url, 405, "Method Not Allowed", {}, None)

    assert tools.network_status(http_error).status == "ok"


def test_network_status_remembers_ok_for_a_minute_but_not_errors(monkeypatch):
    # หน้าตรวจสุขภาพเปิดบ่อย: ต่อยูทูปได้แล้วจำไว้ 60 วินาที ต่อไม่ได้ไม่จำ (เน็ตกลับมาเห็นทันที)
    calls = []
    now = [100.0]
    monkeypatch.setattr(tools, "_network_cache", None)
    monkeypatch.setattr(tools, "_head_status", lambda url: calls.append(url) or 200)

    def clock():
        return now[0]

    assert tools.network_status(clock=clock).status == "ok"
    assert tools.network_status(clock=clock).status == "ok"
    assert len(calls) == 1
    now[0] += tools.NETWORK_CACHE_SECONDS + 1
    assert tools.network_status(clock=clock).status == "ok"
    assert len(calls) == 2

    def boom(url):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(tools, "_network_cache", None)
    monkeypatch.setattr(tools, "_head_status", boom)
    assert tools.network_status(clock=clock).status == "error"
    monkeypatch.setattr(tools, "_head_status", lambda url: 200)
    assert tools.network_status(clock=clock).status == "ok"


def test_collect_health_offline_never_touches_the_network(paths, fake_platform, monkeypatch):
    # โหมดข้อมูลปลอม: ไม่ต่อยูทูปและไม่ต่อ PyPI
    monkeypatch.setenv("YT_TOOLKIT_FFMPEG_PATH_LOOKUP", "0")

    def forbidden(*args, **kwargs):
        raise AssertionError("offline health must not use the network")

    monkeypatch.setattr(tools, "_head_status", forbidden)
    monkeypatch.setattr(tools, "_fetch_latest_ytdlp", forbidden)
    monkeypatch.setattr(tools, "_network_cache", None)
    health = tools.collect_health(paths, fake_platform, paths.data_root / "out", offline=True)
    assert health["network"]["status"] == "ok"
    assert health["tools"]["ytdlp"]["name"] == "yt-dlp"


def test_collect_health_shape(paths, fake_platform, monkeypatch):
    monkeypatch.setenv("YT_TOOLKIT_FFMPEG_PATH_LOOKUP", "0")
    health = tools.collect_health(
        paths, fake_platform, paths.data_root / "out", network=lambda: ToolStatus("ok", name="network")
    )
    assert set(health) == {"tools", "disk", "output", "network"}
    assert set(health["tools"]) == {"ffmpeg", "ytdlp", "jsRuntime", "impersonation"}
    assert health["tools"]["impersonation"]["name"] == "curl_cffi"
    assert health["tools"]["ffmpeg"]["status"] == "error"
    assert health["network"] == {"status": "ok", "name": "network", "version": None, "message": None, "path": None}


def test_run_version_survives_undecodable_output(tmp_path, fake_platform):  # final fix item 8
    # ffmpeg หรือ deno บางรุ่นพิมพ์ byte แปลก ๆ ต้องไม่ทำให้หน้าตรวจสุขภาพพัง
    script = tmp_path / "odd_version.py"
    script.write_text(r"import sys; sys.stdout.buffer.write(b'odd \x81\xff\xfe 1.0\n')", encoding="utf-8")
    line = tools._run_version(sys.executable, fake_platform, str(script))
    assert line is not None
    assert line.startswith("odd ") and line.endswith(" 1.0")
    assert "�" in line


# ---------- PRD 6.6: core/ ไม่ import api หรือ platform ตอนรันจริง (final review) ----------


def _runtime_imports(path):
    """ชื่อโมดูลที่ import ตอนรันจริง (ไม่นับที่อยู่ใน if TYPE_CHECKING:) แปลง import แบบจุดเป็นชื่อเต็ม"""
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    skip: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and "TYPE_CHECKING" in ast.unparse(node.test):
            skip.update(id(child) for stmt in node.body for child in ast.walk(stmt))
    names = []
    for node in ast.walk(tree):
        if id(node) in skip:
            continue
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # from ..platform import X ใน yttoolkit/core/*.py = yttoolkit.platform
                base = ["yttoolkit", "core"][: 2 - (node.level - 1)]
                names.append(".".join([*base, *([node.module] if node.module else [])]))
            else:
                names.append(node.module or "")
    return names


def test_runtime_import_helper_resolves_relative_and_skips_type_checking(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text(
        "from typing import TYPE_CHECKING\n"
        "from ..platform import Platform\n"
        "from .db import Database\n"
        "if TYPE_CHECKING:\n"
        "    from ..api import errors\n",
        encoding="utf-8",
    )
    assert _runtime_imports(sample) == ["typing", "yttoolkit.platform", "yttoolkit.core.db"]


def test_core_does_not_import_api_or_platform_at_runtime():
    core = Path(tools.__file__).parent
    offenders = {
        path.name: name
        for path in sorted(core.glob("*.py"))
        for name in _runtime_imports(path)
        if name.split(".")[:2] in (["yttoolkit", "api"], ["yttoolkit", "platform"])
    }
    assert offenders == {}


# ---------- owner round 3: แถว "ทำงานแบบเบราว์เซอร์ (curl_cffi)" ----------


def test_impersonation_status_ok_shows_the_curl_cffi_version():
    status = tools.impersonation_status(lambda: (True, "0.16.3"))
    assert status == ToolStatus("ok", name="curl_cffi", version="0.16.3")


def test_impersonation_status_missing_package_is_a_warning():
    status = tools.impersonation_status(lambda: (False, None))
    assert status.status == "warn"
    assert status.version is None
    assert "ไม่มี curl_cffi" in (status.message or "")


def test_impersonation_status_unsupported_version_is_a_warning():
    status = tools.impersonation_status(lambda: (False, "0.17.0"))
    assert (status.status, status.version) == ("warn", "0.17.0")
    assert "ใช้ไม่ได้" in (status.message or "")


def test_impersonation_status_survives_a_broken_check():
    def boom():
        raise RuntimeError("yt-dlp changed")

    assert tools.impersonation_status(boom).status == "warn"


def test_impersonation_status_real_check_runs_offline():
    # curl_cffi เป็น dependency แล้ว (yt-dlp[curl-cffi]) ตรวจจริงต้องพร้อม และไม่มีอะไรเกี่ยวกับคุกกี้ในผล
    status = tools.impersonation_status()
    assert status.status == "ok"
    assert status.version
    assert "cookie" not in repr(status).lower()
