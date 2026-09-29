import sys
import urllib.error
from datetime import date
from pathlib import Path

from yttoolkit.core import tools
from yttoolkit.core.tools import ToolStatus
from yttoolkit.platform import current


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

    def fake_run(cmd, **kwargs):
        captured.update(kwargs)

        class Out:
            stdout = "x 1"
            stderr = ""

        return Out()

    monkeypatch.setattr(tools.subprocess, "run", fake_run)
    fake_platform.popen_flags = 0x1234
    assert tools._run_version("exe", fake_platform) == "x 1"
    assert captured["creationflags"] == 0x1234


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
    assert status.message == "ไม่พบตัวช่วยของ yt-dlp (deno)"


def test_ytdlp_status_age():
    fresh = tools.ytdlp_status(version="2026.09.20", today=date(2026, 9, 28))
    assert fresh.status == "ok"
    assert "8 วัน" in (fresh.message or "")
    old = tools.ytdlp_status(version="2026.08.01", today=date(2026, 9, 28))
    assert old.status == "warn"
    assert old.message == "อัปเดตล่าสุด 58 วันก่อน ถ้าโหลดคลิปไม่ได้ ให้ปิดแล้วเปิดใหม่ด้วย start.bat เพื่อรับเวอร์ชันล่าสุด"


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


def test_network_status():
    assert tools.network_status(lambda url: 200).status == "ok"

    def boom(url):
        raise urllib.error.URLError("offline")

    assert tools.network_status(boom).status == "error"

    def http_error(url):
        raise urllib.error.HTTPError(url, 405, "Method Not Allowed", {}, None)

    assert tools.network_status(http_error).status == "ok"


def test_collect_health_shape(paths, fake_platform, monkeypatch):
    monkeypatch.setenv("YT_TOOLKIT_FFMPEG_PATH_LOOKUP", "0")
    health = tools.collect_health(
        paths, fake_platform, paths.data_root / "out", network=lambda: ToolStatus("ok", name="network")
    )
    assert set(health) == {"tools", "disk", "output", "network"}
    assert set(health["tools"]) == {"ffmpeg", "ytdlp", "jsRuntime"}
    assert health["tools"]["ffmpeg"]["status"] == "error"
    assert health["network"] == {"status": "ok", "name": "network", "version": None, "message": None, "path": None}
