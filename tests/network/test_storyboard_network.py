"""AC-FRAME-01 (N): ต่อยูทูปจริง ได้ข้อมูลคลิปและภาพเฟรมครบ ค่ามัธยฐานของ 5 ครั้งไม่เกิน 5 วินาที
รันเองด้วย: uv run pytest -m network -q tests/network/test_storyboard_network.py -s"""

from __future__ import annotations

import shutil
import statistics
import time
from pathlib import Path

import pytest

from yttoolkit.core import storyboard
from yttoolkit.core.db import Database
from yttoolkit.core.extractor import YtDlpExtractor, ytdlp_version
from yttoolkit.core.videos import VideoService

pytestmark = pytest.mark.network

BBB = "aqz-KE-bpKQ"  # Big Buck Bunny (Blender Foundation, CC BY 3.0)
LIMIT_SECONDS = 5
ATTEMPTS = 5


def test_median_of_5_video_and_storyboard_within_5_seconds(tmp_path: Path) -> None:
    # import yt_dlp ก่อน: ครั้งแรกหลังติดตั้งหรืออัปเดต yt-dlp ไม่นับตาม AC-FRAME-01
    # เวลา import จึงไม่ควรปนเข้าไปในเวลาที่วัด (แอพจริงเปิดค้างไว้ก่อนกดวิเคราะห์อยู่แล้ว)
    ytdlp_version()
    db = Database(tmp_path / "app.db")
    db.migrate()
    extractor = YtDlpExtractor()
    cache_root = tmp_path / "cache"
    times: list[float] = []
    try:
        videos = VideoService(db, extractor)
        for _ in range(ATTEMPTS):
            # ล้าง cache ของภาพเฟรมทุกรอบ และ probe ใหม่ด้วย refresh=True (ไม่อาศัย cache ข้อมูลคลิป)
            # ทุกรอบจึงเป็นการโหลดสดจากเน็ตจริง ๆ เหมือนกดวิเคราะห์คลิปใหม่
            shutil.rmtree(cache_root, ignore_errors=True)
            start = time.monotonic()
            info = videos.get(BBB, refresh=True)
            index = storyboard.get_storyboard(BBB, videos, cache_root, extractor.fetch)
            times.append(time.monotonic() - start)
            assert info["videoId"] == BBB
            frames = index["frames"]
            assert len(frames) == 128
            folder = cache_root / BBB / storyboard.FOLDER
            assert all((folder / f["file"]).is_file() for f in frames)
    finally:
        extractor.close()
        db.close()
    median = statistics.median(times)
    print(
        f"probe + storyboard median {median:.2f}s of {ATTEMPTS}: "
        + ", ".join(f"{t:.2f}s" for t in times)
    )
    assert median <= LIMIT_SECONDS, f"ค่ามัธยฐาน {median:.2f} วินาที ({times})"
