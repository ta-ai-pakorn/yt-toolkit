"""ทุกตัวอ่าน cache ต้องทนโฟลเดอร์ data/cache/<id>/ ที่หายไป (M6 รอบ A spec 3.3: หลังกด "ล้างข้อมูลชั่วคราว")

หนึ่งเทสต่อหนึ่งแถวของตาราง spec 3.3 (แถว api/videos._cache_target อยู่ที่ tests/api/test_storage_api.py)
FakeExtractor ไม่แตะเครือข่าย
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from helpers_capture import BBB as CAPTURE_CLIP
from helpers_capture import MEDIA, FakeVideos, FixtureFetcher, StubQueue, StubSettings, clip_info

from yttoolkit.core.capture import CaptureService
from yttoolkit.core.comments import PinnedCommentService
from yttoolkit.core.db import Database, purge_stale_cache
from yttoolkit.core.extractor import FakeExtractor
from yttoolkit.core.media import FakeMediaTools
from yttoolkit.core.sharp_store import read_sharp, sweep_sharp_leftovers
from yttoolkit.core.storyboard import get_storyboard
from yttoolkit.core.subtitles import SubtitleService
from yttoolkit.core.videos import VideoService

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
BBB = "aqz-KE-bpKQ"
THAI = "88o5Sk8_m1Y"
NOW = datetime(2026, 10, 14, 5, 0, tzinfo=UTC)
TRASH = ".clear-" + "f" * 32


@pytest.fixture
def env(tmp_path: Path):
    db = Database(tmp_path / "app.db")
    db.migrate()
    fake = FakeExtractor(FIXTURES)
    videos = VideoService(db, fake, now=lambda: NOW)
    yield db, fake, videos, tmp_path / "cache"
    db.close()


def _cleared(cache: Path, video_id: str) -> None:
    shutil.rmtree(cache / video_id, ignore_errors=True)
    assert not (cache / video_id).exists()


def test_storyboard_rebuilds_after_the_clip_cache_is_gone(env):
    _, fake, videos, cache = env
    first = get_storyboard(BBB, videos, cache, fake.fetch)
    _cleared(cache, BBB)
    again = get_storyboard(BBB, videos, cache, fake.fetch)
    assert len(again["frames"]) == len(first["frames"]) == 128
    assert (cache / BBB / "storyboard" / "index.json").is_file()


def test_read_sharp_is_none_after_the_clip_cache_is_gone(env):
    _, _, _, cache = env
    (cache / BBB / "sharp").mkdir(parents=True)
    _cleared(cache, BBB)
    assert read_sharp(cache, BBB) is None


def test_the_capture_strip_is_empty_after_the_clip_cache_is_gone(tmp_path):
    service = CaptureService(FakeVideos({CAPTURE_CLIP: clip_info()}), FixtureFetcher(), FakeMediaTools(MEDIA),
                             tmp_path / "cache", StubSettings(tmp_path / "out"), StubQueue(),
                             work_root=tmp_path / "work", now=lambda: NOW)  # fmt: skip
    capture, _ = service.capture(CAPTURE_CLIP, 1_000)
    copies = list((tmp_path / "out").rglob("*.jpg"))
    assert service.list(CAPTURE_CLIP) and copies
    _cleared(tmp_path / "cache", CAPTURE_CLIP)
    assert service.list(CAPTURE_CLIP) == []
    assert all(p.is_file() for p in copies)  # สำเนาใน "ภาพที่ถ่าย/" ยังอยู่


def test_subtitle_tokens_download_again_after_the_clip_cache_is_gone(env):
    _, fake, videos, cache = env
    subtitles = SubtitleService(videos, fake.fetch_subtitle, cache)
    first = subtitles.tokens(THAI, "a.th-orig")
    _cleared(cache, THAI)
    again = subtitles.tokens(THAI, "a.th-orig")
    assert [t.t for t in again.tokens] == [t.t for t in first.tokens]
    assert (cache / THAI / "subs").is_dir()


def test_the_pinned_comment_is_fetched_again_after_the_clip_cache_is_gone(env):
    _, fake, videos, cache = env
    calls: list[str] = []

    def pinned(video_id: str) -> dict | None:
        calls.append(video_id)
        return {"text": "ปักหมุด", "likes": 1, "byUploader": True}

    service = PinnedCommentService(videos, pinned, cache, now=lambda: NOW)
    assert service.get(THAI) == {"text": "ปักหมุด", "likes": 1, "byUploader": True}
    _cleared(cache, THAI)
    assert service.get(THAI) == {"text": "ปักหมุด", "likes": 1, "byUploader": True}
    assert calls == [THAI, THAI]


def test_startup_sweeps_ignore_a_clear_trash_folder(env):
    db, _, _, cache = env
    trash = cache / TRASH / BBB / "storyboard"
    trash.mkdir(parents=True)
    (trash / "f.jpg").write_bytes(b"x")
    assert sweep_sharp_leftovers(cache) == 0
    assert purge_stale_cache(db, cache, NOW) == 0
    assert (trash / "f.jpg").is_file()  # ของ .clear-* ลบโดย sweep_clear_leftovers เท่านั้น
