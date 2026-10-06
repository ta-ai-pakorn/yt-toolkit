"""VideoService กับบัญชียูทูปชั่วคราว (M5 รอบ C spec 2.4 "Cache"): probe ที่ใช้บัญชีอยู่ในหน่วยความจำ ไม่ลงฐานข้อมูล"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from yttoolkit.core.account_scope import signed_in
from yttoolkit.core.db import Database
from yttoolkit.core.extractor import FakeExtractor
from yttoolkit.core.videos import VideoService
from yttoolkit.core.yterrors import YtError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
AGE = "ACCOUNTAGE1"
BBB = "aqz-KE-bpKQ"


@pytest.fixture
def env(tmp_path: Path):
    db = Database(tmp_path / "app.db")
    db.migrate()
    fake = FakeExtractor(FIXTURES)
    videos = VideoService(db, fake, now=lambda: datetime(2026, 10, 6, 3, tzinfo=UTC))
    yield db, fake, videos
    db.close()


def _rows(db: Database, video_id: str) -> list:
    return db.execute("SELECT video_id FROM videos WHERE video_id = ?", (video_id,))


def _probes(fake: FakeExtractor) -> int:
    return sum(1 for name, _ in fake.calls if name == "probe")


def test_signed_in_probe_is_never_written_to_the_database(env) -> None:
    db, fake, videos = env
    with signed_in(object()):
        info = videos.get(AGE)
    assert info["videoId"] == AGE and info["title"] == "คลิปจำกัดอายุ"
    assert _rows(db, AGE) == []
    assert videos.recent(10, scope="all") == ([], 0)


def test_the_kept_copy_serves_later_reads_without_the_account(env) -> None:
    db, fake, videos = env
    with signed_in(object()):
        videos.get(AGE, peek=True)
    before = _probes(fake)
    assert videos.get(AGE)["title"] == "คลิปจำกัดอายุ"  # หน้า W2 แท็บอื่น / ตัวทำงานในคิว อ่านซ้ำได้
    assert videos.raw(AGE)["id"] == AGE  # storyboard / ภาพคมอ่านข้อมูลดิบที่ตัดแล้ว
    assert _probes(fake) == before
    assert _rows(db, AGE) == []


def test_forget_signed_in_drops_every_kept_copy(env) -> None:
    db, fake, videos = env
    with signed_in(object()):
        videos.get(AGE)
    videos.forget_signed_in()
    with pytest.raises(YtError) as info:
        videos.get(AGE)  # ไม่มีบัญชีแล้ว: probe แบบไม่ใช้บัญชี ได้ error เดิม
    assert info.value.code == "E_AGE_RESTRICTED"


def test_raw_inside_a_scope_probes_signed_in(env) -> None:
    db, fake, videos = env
    with signed_in(object()):
        assert videos.raw(AGE)["id"] == AGE
    assert _rows(db, AGE) == []


def test_kept_copies_are_independent(env) -> None:
    db, fake, videos = env
    with signed_in(object()):
        videos.get(AGE)
    videos.raw(AGE)["title"] = "เปลี่ยน"
    assert videos.get(AGE)["title"] == "คลิปจำกัดอายุ"


def test_public_clips_still_use_the_database_cache(env) -> None:
    db, fake, videos = env
    videos.get(BBB)
    assert len(_rows(db, BBB)) == 1
    with signed_in(object()):
        assert videos.get(BBB)["videoId"] == BBB  # มี cache อยู่แล้ว ไม่ probe ใหม่ด้วยบัญชี
    assert _probes(fake) == 1
