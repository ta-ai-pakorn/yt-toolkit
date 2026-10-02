"""ตรวจและเตรียมเครื่องมือภายนอกที่แอพต้องใช้ (ffmpeg, JS runtime, yt-dlp)"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sysconfig
import threading
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import httpx

from ..config import Paths, env_flag

if TYPE_CHECKING:  # ใช้แค่เป็นชนิดของพารามิเตอร์ ผู้เรียกส่ง Platform เข้ามา (core ไม่ import platform, PRD 6.6)
    from ..platform import Platform

Status = Literal["ok", "warn", "error"]

YTDLP_MAX_AGE_DAYS = 30
YTDLP_UPDATE_GRACE_DAYS = 7  # bot อัปเดต uv.lock ทุกวัน ให้เวลามันทำงานก่อนเตือนเรื่องเวอร์ชันใหม่
FFMPEG_INSTALLING_MESSAGE = "กำลังโหลด ffmpeg อาจใช้เวลา 1-3 นาที"
MIN_FREE_BYTES = 2 * 1024**3
PYPI_YTDLP_URL = "https://pypi.org/pypi/yt-dlp/json"
LATEST_YTDLP_CACHE_SECONDS = 3600

_latest_ytdlp_cache: tuple[float, str] | None = None  # (เวลาที่เช็ก, เวอร์ชัน)


@dataclass(frozen=True)
class ToolStatus:
    status: Status
    name: str | None = None
    version: str | None = None
    message: str | None = None
    path: str | None = None


class ToolInstallError(RuntimeError):
    pass


def _run_version(exe: Path | str, plat: Platform, arg: str = "--version") -> str | None:
    try:
        out = subprocess.run(
            [str(exe), arg],
            capture_output=True,
            text=True,
            errors="replace",  # byte แปลก ๆ จาก ffmpeg หรือ deno ต้องไม่ทำให้หน้าตรวจสุขภาพพัง
            timeout=10,
            creationflags=plat.popen_flags,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (out.stdout or out.stderr or "").strip()
    return text.splitlines()[0] if text else None


def scripts_dir() -> Path:
    return Path(sysconfig.get_path("scripts"))


def find_ffmpeg(paths: Paths, plat: Platform) -> Path | None:
    local = paths.bin / plat.exe_name("ffmpeg")
    if local.is_file():
        return local
    if env_flag("YT_TOOLKIT_FFMPEG_PATH_LOOKUP", True):
        found = shutil.which(plat.exe_name("ffmpeg"))
        if found:
            return Path(found)
    return None


def parse_ffmpeg_version(line: str | None) -> str | None:
    if not line:
        return None
    match = re.match(r"ffmpeg version (\S+)", line)
    return match.group(1) if match else None


def ffmpeg_status(paths: Paths, plat: Platform) -> ToolStatus:
    if _ffmpeg_installing.is_set():
        return ToolStatus("warn", name="ffmpeg", message=FFMPEG_INSTALLING_MESSAGE)
    exe = find_ffmpeg(paths, plat)
    if exe is None:
        return ToolStatus("error", name="ffmpeg", message="ยังไม่มีโปรแกรมแปลงไฟล์ (ffmpeg)")
    version = parse_ffmpeg_version(_run_version(exe, plat, "-version"))
    if version is None:
        return ToolStatus("error", name="ffmpeg", path=str(exe), message="มี ffmpeg แต่เรียกใช้งานไม่ได้")
    return ToolStatus("ok", name="ffmpeg", version=version, path=str(exe))


def find_js_runtime(plat: Platform) -> ToolStatus:
    bundled = scripts_dir() / plat.exe_name("deno")
    candidates = [
        ("deno", str(bundled) if bundled.is_file() else shutil.which("deno")),
        ("node", shutil.which("node")),
    ]
    for name, exe in candidates:
        if not exe:
            continue
        line = _run_version(exe, plat)
        if line is None:
            continue
        if name == "deno":
            parts = line.split()
            version = parts[1] if len(parts) > 1 else line
            return ToolStatus("ok", name="deno", version=version, path=exe)
        return ToolStatus("warn", name="node", version=line.lstrip("v"), path=exe, message="ใช้ node แทน deno")
    return ToolStatus("warn", name=None, message="ไม่พบตัวช่วยของ yt-dlp (deno)")


def _fetch_latest_ytdlp() -> str:
    response = httpx.get(PYPI_YTDLP_URL, timeout=3)
    response.raise_for_status()
    return str(response.json()["info"]["version"])


def latest_ytdlp_version(
    fetch: Callable[[], str] | None = None, *, clock: Callable[[], float] = time.monotonic
) -> str | None:
    """เวอร์ชันเสถียรล่าสุดของ yt-dlp บน PyPI (จำไว้ 1 ชั่วโมง) คืน None ถ้าเช็กไม่ได้"""
    global _latest_ytdlp_cache
    now = clock()
    if _latest_ytdlp_cache is not None and now - _latest_ytdlp_cache[0] < LATEST_YTDLP_CACHE_SECONDS:
        return _latest_ytdlp_cache[1]
    try:
        latest = (fetch or _fetch_latest_ytdlp)()
    except (httpx.HTTPError, OSError, ValueError, KeyError, TypeError):
        return None  # ไม่จำความล้มเหลว เน็ตกลับมาเมื่อไรก็เช็กได้ทันที
    _latest_ytdlp_cache = (now, latest)
    return latest


def _version_key(version: str) -> tuple[int, ...] | None:
    """yt-dlp ใช้เวอร์ชันแบบวันที่ (2026.08.19 หรือ 2026.8.19.123456) เทียบเป็นตัวเลขทีละส่วน"""
    parts = version.split(".")
    if len(parts) < 3 or not all(p.isdigit() for p in parts[:3]):
        return None
    return tuple(int(p) for p in parts if p.isdigit())


def ytdlp_status(
    version: str | None = None, today: date | None = None, fetch_latest: Callable[[], str] | None = None
) -> ToolStatus:
    if version is None:
        from .extractor import ytdlp_version

        version = ytdlp_version()
    today = today or date.today()
    try:
        released = datetime.strptime(version[:10], "%Y.%m.%d").date()
    except ValueError:
        return ToolStatus("ok", name="yt-dlp", version=version)
    age = (today - released).days
    latest = latest_ytdlp_version(fetch_latest)
    installed_key, latest_key = _version_key(version), _version_key(latest) if latest else None
    if installed_key is not None and latest_key is not None:
        # อายุมากแต่เป็นตัวล่าสุดแล้ว ไม่ต้องเตือน เพราะผู้ใช้ทำอะไรเพิ่มไม่ได้
        if installed_key >= latest_key:
            return ToolStatus("ok", name="yt-dlp", version=version, message=f"อัปเดตล่าสุด {age} วันก่อน (เป็นเวอร์ชันล่าสุด)")
        if age <= YTDLP_UPDATE_GRACE_DAYS:
            return ToolStatus("ok", name="yt-dlp", version=version, message=f"อัปเดตล่าสุด {age} วันก่อน")
        return ToolStatus(
            "warn", name="yt-dlp", version=version,
            message=f"มีเวอร์ชันใหม่ {latest} ถ้าโหลดคลิปไม่ได้ ให้ปิดแล้วเปิดใหม่ด้วย start.bat เพื่อรับเวอร์ชันล่าสุด",
        )
    # เช็ก PyPI ไม่ได้ ใช้กฎอายุแบบเดิม
    if age > YTDLP_MAX_AGE_DAYS:
        return ToolStatus(
            "warn", name="yt-dlp", version=version, message=f"อัปเดตล่าสุด {age} วันก่อน ถ้าโหลดคลิปไม่ได้ ให้ปิดแล้วเปิดใหม่ด้วย start.bat เพื่อรับเวอร์ชันล่าสุด",
        )
    return ToolStatus("ok", name="yt-dlp", version=version, message=f"อัปเดตล่าสุด {age} วันก่อน")


def impersonation_status(info: Callable[[], tuple[bool, str | None]] | None = None) -> ToolStatus:
    """yt-dlp ทำตัวเป็นเบราว์เซอร์ได้ไหม (curl_cffi) ใช้ตอนโหลดซับ ไม่มีก็ยังโหลดซับได้แบบคำขอธรรมดา จึงแค่เตือน

    ไม่ต่อเน็ต และไม่มีข้อมูลคุกกี้หรือเซสชันใด ๆ ในผลนี้
    """
    if info is None:
        from .extractor import impersonation_info

        info = impersonation_info
    try:
        available, version = info()
    except Exception:
        available, version = False, None
    if available:
        return ToolStatus("ok", name="curl_cffi", version=version)
    message = "ไม่มี curl_cffi โหลดซับแบบคำขอธรรมดาแทน" if version is None else "curl_cffi รุ่นนี้ yt-dlp ใช้ไม่ได้ โหลดซับแบบคำขอธรรมดาแทน"
    return ToolStatus("warn", name="curl_cffi", version=version, message=message)


def disk_status(path: Path) -> ToolStatus:
    free = shutil.disk_usage(path).free
    message = f"เหลือ {free / 1024**3:.0f} GB"
    if free < MIN_FREE_BYTES:
        return ToolStatus("warn", name="disk", message=message)
    return ToolStatus("ok", name="disk", message=message)


def output_status(output_dir: Path) -> ToolStatus:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        # ชื่อไม่ซ้ำต่อครั้ง: หน้าตรวจสุขภาพสองคำขอพร้อมกันจะไม่ลบไฟล์ทดสอบของกันและกัน
        probe = output_dir / f".yt-toolkit-write-test-{uuid.uuid4().hex}"
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
    network: Callable[[], ToolStatus] | None = None,
) -> dict:
    return {
        "tools": {
            "ffmpeg": asdict(ffmpeg_status(paths, plat)),
            "ytdlp": asdict(ytdlp_status()),
            "jsRuntime": asdict(find_js_runtime(plat)),
            "impersonation": asdict(impersonation_status()),
        },
        "disk": asdict(disk_status(paths.data_root)),
        "output": asdict(output_status(output_dir)),
        "network": asdict((network or network_status)()),
    }


FFMPEG_RELEASE = "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest"
FFMPEG_WIN_ZIP = "ffmpeg-master-latest-win64-gpl.zip"
_FFMPEG_WIN_FILES = frozenset({"ffmpeg.exe", "ffprobe.exe"})

Downloader = Callable[[str, Path], None]

# ปุ่มในหน้าเว็บกับการติดตั้งอัตโนมัติตอนเปิดแอพอาจเรียกพร้อมกัน ให้โหลดได้ทีละงานเท่านั้น
_ffmpeg_install_lock = threading.Lock()
_ffmpeg_installing = threading.Event()


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as response, dest.open("wb") as out:
        shutil.copyfileobj(response, out, 1024 * 1024)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_checksums(text: str, filename: str) -> str | None:
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == filename:
            return parts[0].lower()
    return None


def _unlink_quietly(path: Path) -> None:
    """ลบไฟล์ชั่วคราว ถ้าลบไม่ได้ (เช่นไฟล์ถูกล็อกบน Windows) ก็ปล่อยไว้ ไม่ให้บังผลจริง"""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def install_ffmpeg_windows(paths: Paths, download: Downloader = _download) -> Path:
    zip_path = paths.work / FFMPEG_WIN_ZIP
    sums_path = paths.work / "ffmpeg-checksums.sha256"
    temps: dict[str, Path] = {}
    try:
        download(f"{FFMPEG_RELEASE}/checksums.sha256", sums_path)
        expected = parse_checksums(sums_path.read_text(encoding="utf-8"), FFMPEG_WIN_ZIP)
        if expected is None:
            raise ToolInstallError("ไม่พบ checksum ของ ffmpeg ในรีลีส")
        download(f"{FFMPEG_RELEASE}/{FFMPEG_WIN_ZIP}", zip_path)
        if sha256_file(zip_path) != expected:
            raise ToolInstallError("checksum ของ ffmpeg ไม่ตรง")
        paths.bin.mkdir(parents=True, exist_ok=True)
        # แตกไฟล์ลงชื่อชั่วคราวก่อน ครบแล้วค่อย os.replace เข้าที่ ไฟล์ที่เขียนค้างครึ่งเดียวจะไม่ถูกใช้
        with zipfile.ZipFile(zip_path) as archive:
            for member in archive.namelist():
                base = member.rsplit("/", 1)[-1]
                if base in _FFMPEG_WIN_FILES and "/bin/" in member:
                    temp = paths.bin / f"{base}.part"
                    temps[base] = temp
                    temp.write_bytes(archive.read(member))
        if set(temps) != _FFMPEG_WIN_FILES:
            raise ToolInstallError("ไฟล์ ffmpeg ใน zip ไม่ครบ")
        # วาง ffprobe ก่อน ffmpeg เป็นตัวสุดท้าย เพราะแอพถือว่ามี ffmpeg = ติดตั้งครบแล้ว
        for base in ("ffprobe.exe", "ffmpeg.exe"):
            os.replace(temps[base], paths.bin / base)
    except (OSError, zipfile.BadZipFile) as error:
        raise ToolInstallError(f"โหลด ffmpeg ไม่สำเร็จ: {error}") from error
    finally:
        for temp in temps.values():
            _unlink_quietly(temp)
        _unlink_quietly(zip_path)
        _unlink_quietly(sums_path)
    return paths.bin / "ffmpeg.exe"


def install_ffmpeg(paths: Paths, plat: Platform, download: Downloader = _download) -> Path:
    with _ffmpeg_install_lock:
        # ไฟล์ .part ที่ค้างจากรอบก่อน (เช่นปิดแอพกลางคัน) ลบทิ้งได้ เพราะตอนนี้ไม่มีงานอื่นเขียนอยู่
        for leftover in paths.bin.glob("*.part"):
            _unlink_quietly(leftover)
        current = ffmpeg_status(paths, plat)
        if current.status == "ok" and current.path:
            return Path(current.path)  # อีกงานเพิ่งติดตั้งเสร็จระหว่างที่รอ lock
        if not plat.ffmpeg_auto_install:
            raise ToolInstallError("ยังไม่รองรับการโหลด ffmpeg อัตโนมัติบนระบบนี้")
        _ffmpeg_installing.set()
        try:
            return install_ffmpeg_windows(paths, download)
        finally:
            _ffmpeg_installing.clear()
