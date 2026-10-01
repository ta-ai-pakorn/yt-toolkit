"""ตัวช่วยเทสที่ใช้ ffmpeg จริง (ข้ามเมื่อเครื่องไม่มี ffmpeg)"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest


def find_test_ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


requires_ffmpeg = pytest.mark.skipif(find_test_ffmpeg() is None, reason="ต้องมี ffmpeg ในเครื่อง")


def ffprobe_json(path: Path) -> dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    ffmpeg = find_test_ffmpeg()
    if ffprobe is None and ffmpeg is not None:
        exe = Path(ffmpeg)
        candidate = exe.with_name(exe.name.replace("ffmpeg", "ffprobe"))
        ffprobe = str(candidate) if candidate.exists() else None
    assert ffprobe is not None, "ไม่พบ ffprobe"
    out = subprocess.run(
        [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True,
        check=True,
    ).stdout
    return json.loads(out.decode("utf-8"))
