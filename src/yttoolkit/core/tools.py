"""ตรวจและเตรียมเครื่องมือภายนอกที่แอพต้องใช้ (ffmpeg, JS runtime, yt-dlp)"""

from __future__ import annotations

import re
import shutil
import subprocess
import sysconfig
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from ..config import Paths, env_flag
from ..platform import Platform

Status = Literal["ok", "warn", "error"]

YTDLP_MAX_AGE_DAYS = 30
MIN_FREE_BYTES = 2 * 1024**3
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass(frozen=True)
class ToolStatus:
    status: Status
    name: str | None = None
    version: str | None = None
    message: str | None = None
    path: str | None = None


class ToolInstallError(RuntimeError):
    pass


def _run_version(exe: Path | str, arg: str = "--version") -> str | None:
    try:
        out = subprocess.run(
            [str(exe), arg], capture_output=True, text=True, timeout=10, creationflags=_NO_WINDOW
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (out.stdout or out.stderr or "").strip()
    return text.splitlines()[0] if text else None


def scripts_dir() -> Path:
    return Path(sysconfig.get_path("scripts"))


def find_ffmpeg(paths: Paths, plat: Platform) -> Path | None:
    local = paths.bin / plat.ffmpeg_exe
    if local.is_file():
        return local
    if env_flag("YT_TOOLKIT_FFMPEG_PATH_LOOKUP", True):
        found = shutil.which("ffmpeg")
        if found:
            return Path(found)
    return None


def parse_ffmpeg_version(line: str | None) -> str | None:
    if not line:
        return None
    match = re.match(r"ffmpeg version (\S+)", line)
    return match.group(1) if match else None


def ffmpeg_status(paths: Paths, plat: Platform) -> ToolStatus:
    exe = find_ffmpeg(paths, plat)
    if exe is None:
        return ToolStatus("error", name="ffmpeg", message="ยังไม่มีโปรแกรมแปลงไฟล์ (ffmpeg)")
    version = parse_ffmpeg_version(_run_version(exe, "-version"))
    if version is None:
        return ToolStatus("error", name="ffmpeg", path=str(exe), message="มี ffmpeg แต่เรียกใช้งานไม่ได้")
    return ToolStatus("ok", name="ffmpeg", version=version, path=str(exe))


def find_js_runtime() -> ToolStatus:
    scripts = scripts_dir()
    # Try bundled deno with both .exe and no extension (works cross-platform)
    bundled_paths = [scripts / "deno.exe", scripts / "deno"]
    bundled = next((p for p in bundled_paths if p.is_file()), None)
    candidates = [
        ("deno", str(bundled) if bundled else shutil.which("deno")),
        ("node", shutil.which("node")),
    ]
    for name, exe in candidates:
        if not exe:
            continue
        line = _run_version(exe)
        if line is None:
            continue
        if name == "deno":
            parts = line.split()
            version = parts[1] if len(parts) > 1 else line
            return ToolStatus("ok", name="deno", version=version, path=exe)
        return ToolStatus("warn", name="node", version=line.lstrip("v"), path=exe, message="ใช้ node แทน deno")
    return ToolStatus(
        "warn", message="บางคุณภาพอาจไม่แสดง เพราะเครื่องยังไม่มีตัวช่วยที่ yt-dlp ต้องใช้"
    )


def ytdlp_status(version: str | None = None, today: date | None = None) -> ToolStatus:
    if version is None:
        from yt_dlp.version import __version__ as version
    today = today or date.today()
    try:
        released = datetime.strptime(version[:10], "%Y.%m.%d").date()
    except ValueError:
        return ToolStatus("ok", name="yt-dlp", version=version)
    age = (today - released).days
    if age > YTDLP_MAX_AGE_DAYS:
        return ToolStatus(
            "warn", name="yt-dlp", version=version, message=f"อัปเดตล่าสุด {age} วันก่อน ลองกดตรวจหาอัปเดต"
        )
    return ToolStatus("ok", name="yt-dlp", version=version, message=f"อัปเดตล่าสุด {age} วันก่อน")


def disk_status(path: Path) -> ToolStatus:
    free = shutil.disk_usage(path).free
    gb = free / 1024**3
    if free < MIN_FREE_BYTES:
        return ToolStatus("warn", name="disk", message=f"เหลือ {gb:.1f} GB")
    return ToolStatus("ok", name="disk", message=f"เหลือ {gb:.0f} GB")


def output_status(output_dir: Path) -> ToolStatus:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        probe = output_dir / ".yt-toolkit-write-test"
        probe.write_bytes(b"")
        probe.unlink()
    except OSError:
        return ToolStatus("error", name="output", path=str(output_dir), message="บันทึกลงโฟลเดอร์นี้ไม่ได้")
    return ToolStatus("ok", name="output", path=str(output_dir))


def _head_status(url: str) -> int:
    request = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status


def network_status(opener: Callable[[str], int] | None = None) -> ToolStatus:
    try:
        code = (opener or _head_status)("https://www.youtube.com/")
    except urllib.error.HTTPError:
        return ToolStatus("ok", name="network")  # ได้คำตอบกลับมา แปลว่าต่อถึง
    except OSError:
        return ToolStatus("error", name="network", message="ต่อยูทูปไม่ได้ ตรวจเน็ตอีกครั้ง")
    return ToolStatus("ok" if code < 500 else "warn", name="network")


def collect_health(
    paths: Paths,
    plat: Platform,
    output_dir: Path,
    *,
    network: Callable[[], ToolStatus] = network_status,
) -> dict:
    return {
        "tools": {
            "ffmpeg": asdict(ffmpeg_status(paths, plat)),
            "ytdlp": asdict(ytdlp_status()),
            "jsRuntime": asdict(find_js_runtime()),
        },
        "disk": asdict(disk_status(paths.data_root)),
        "output": asdict(output_status(output_dir)),
        "network": asdict(network()),
    }
