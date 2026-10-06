"""งานในคิวกับบัญชียูทูปชั่วคราว (M5 รอบ C spec 2.4): ทั้งงานลองแบบไม่ใช้บัญชีก่อน แล้วทำใหม่ทั้งงานด้วยบัญชีครั้งเดียว

ใช้ FakeExtractor ตัวจริง (คลิป ACCOUNTAGE1 ต้องใช้บัญชี · PRIVATEVID1 ส่วนตัวเสมอ) FakeMediaTools และฐานข้อมูลชั่วคราว
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from yttoolkit.core.account_scope import current_jar
from yttoolkit.core.cancel import JobCancelled
from yttoolkit.core.db import Database
from yttoolkit.core.extractor import FakeExtractor
from yttoolkit.core.handlers import HandlerDeps, build_handlers
from yttoolkit.core.jobs import Job
from yttoolkit.core.media import FakeMediaTools
from yttoolkit.core.subtitles import SubtitleService
from yttoolkit.core.videos import VideoService
from yttoolkit.core.yterrors import ACCOUNT_TRIED_MESSAGE, YtError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
AGE = "ACCOUNTAGE1"
PRIVATE = FakeExtractor.PRIVATE_ID
JAR = object()


class Gate:
    def __init__(self, jar: Any | None = JAR) -> None:
        self._jar = jar
        self.used: list[str | None] = []

    def jar(self) -> Any | None:
        return self._jar

    def mark_used(self, job_id: str | None) -> None:
        self.used.append(job_id)


class Ctx:
    def __init__(self, workdir: Path, output_root: Path) -> None:
        self.job_id = "01900000-0000-7000-8000-00000000000c"
        self.workdir = workdir
        self.output_root = output_root
        self.stages: list[str] = []

    def stage(self, stage: str) -> None:
        self.stages.append(stage)

    def progress(self, fraction: float | None, speed_bps: int | None = None, eta_s: int | None = None) -> None:
        pass

    def set_title(self, title: str) -> None:
        pass

    def cancelled(self) -> bool:
        return False

    def check_cancelled(self) -> None:
        if self.cancelled():
            raise JobCancelled()

    def wait(self, seconds: float) -> None:
        pass


class SpyExtractor(FakeExtractor):
    """FakeExtractor ที่จดว่า download แต่ละครั้งรันใต้บัญชีไหม"""

    def __init__(self, root: Path, behaviors: Path) -> None:
        super().__init__(root, behaviors=behaviors)
        self.download_jars: list[Any] = []

    def download(self, video_id, choose, workdir, hooks):  # type: ignore[override]
        self.download_jars.append(current_jar())
        return super().download(video_id, choose, workdir, hooks)


@pytest.fixture
def env(tmp_path: Path):
    doc = json.loads((FIXTURES / "downloads" / "behaviors.json").read_text(encoding="utf-8"))
    for entry in [doc["default"], *doc["videos"].values()]:
        entry["stepMs"] = 0
    behaviors = tmp_path / "behaviors.json"
    behaviors.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    db = Database(tmp_path / "app.db")
    db.migrate()
    fake = SpyExtractor(FIXTURES, behaviors)
    videos = VideoService(db, fake)
    deps = HandlerDeps(
        videos=videos,
        downloader=fake,  # type: ignore[arg-type]
        media=FakeMediaTools(FIXTURES / "media"),
        subtitles=SubtitleService(videos, fake.fetch_subtitle, tmp_path / "cache"),
        cache_root=tmp_path / "cache",
    )
    yield deps, fake, db, tmp_path
    db.close()


def _job(video_id: str, kind: str = "video", params: dict | None = None) -> Job:
    base = {"maxQuality": False, "splitChapters": False, "noAudio": False, "audioLanguage": "original"}
    return Job(
        id=f"job-{video_id}", video_id=video_id, title="", kind=kind, params=base if params is None else params,
        status="running", stage=None, progress=None, speed_bps=None, eta_s=None, attempt=0, bot_checks=0, position=1,
        error_code=None, error_message=None, error_detail=None, notes=(), outputs=(),
        created_at="2026-10-06T03:00:00.000000+00:00", started_at="2026-10-06T03:00:01.000000+00:00", finished_at=None,
    )  # fmt: skip


def _run(env, job: Job):
    deps, fake, db, tmp = env
    work = tmp / "work" / job.id
    work.mkdir(parents=True, exist_ok=True)
    return build_handlers(deps)[job.kind](job, Ctx(work, tmp / "out"))


def test_restricted_video_job_retries_the_whole_job_with_the_account(env) -> None:
    deps, fake, db, tmp = env
    deps.accounts = gate = Gate()
    result = _run(env, _job(AGE))
    (output,) = result.outputs
    assert (tmp / "out" / output.rel).is_file()
    assert fake.download_jars == [JAR]  # รอบแรกพลาดตั้งแต่ probe จึงไม่ถึงขั้นโหลด · รอบสองโหลดด้วยบัญชี
    assert gate.used == [f"job-{AGE}"]
    assert db.execute("SELECT video_id FROM videos WHERE video_id = ?", (AGE,)) == []


def test_without_an_account_the_job_fails_with_the_plain_copy(env) -> None:
    deps, fake, db, tmp = env
    with pytest.raises(YtError) as info:
        _run(env, _job(AGE))
    assert info.value.code == "E_AGE_RESTRICTED" and info.value.account_tried is False


def test_an_account_without_access_fails_with_the_tried_copy(env) -> None:
    deps, fake, db, tmp = env
    deps.accounts = Gate()
    with pytest.raises(YtError) as info:
        _run(env, _job(PRIVATE))
    assert info.value.code == "E_VIDEO_PRIVATE"
    assert info.value.message == ACCOUNT_TRIED_MESSAGE


@pytest.mark.parametrize(
    ("kind", "params"),
    [
        ("audio", {"format": "m4a", "splitChapters": False, "audioLanguage": "original"}),
        ("subtitle", {"format": "srt", "options": {"maxChars": 25, "lines": 1, "minMs": 1200, "maxMs": 5000}}),
        ("frames_sharp", {}),
    ],
)
def test_every_youtube_job_kind_uses_the_same_rule(env, kind: str, params: dict) -> None:
    deps, fake, db, tmp = env
    deps.accounts = gate = Gate()
    result = _run(env, _job(AGE, kind, params))
    assert result.outputs or result.notes  # ซับ: คลิปนี้ไม่มีซับ = จบแบบมีโน้ต NO_SUBTITLES (ไม่ใช่ error)
    assert gate.used == [f"job-{AGE}"]
