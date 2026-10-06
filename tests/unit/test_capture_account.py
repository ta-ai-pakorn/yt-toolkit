"""ถ่ายภาพคมตรงจุดกับบัญชียูทูปชั่วคราว (M5 รอบ C spec 2.4 "B2 capture"): ถ่ายแบบไม่ใช้บัญชีก่อน แล้วถ่ายใหม่ทั้งครั้งด้วยบัญชี"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from helpers_capture import BBB, MEDIA, FakeVideos, FixtureFetcher, StubQueue, StubSettings, clip_info

from yttoolkit.core.account_scope import current_jar
from yttoolkit.core.capture import CaptureService
from yttoolkit.core.media import FakeMediaTools
from yttoolkit.core.yterrors import ACCOUNT_TRIED_MESSAGE, YtError

JAR = object()


class Gate:
    def __init__(self, jar: Any | None = JAR) -> None:
        self._jar = jar
        self.used: list[str | None] = []

    def jar(self) -> Any | None:
        return self._jar

    def mark_used(self, job_id: str | None) -> None:
        self.used.append(job_id)


class RestrictedVideos(FakeVideos):
    """อ่านข้อมูลคลิปได้เฉพาะใต้บัญชี (คลิปจำกัดอายุ)"""

    def get(self, video_id: str, refresh: bool = False, peek: bool = False) -> dict:
        if current_jar() is None:
            raise YtError("E_AGE_RESTRICTED", "fake: needs the account")
        return super().get(video_id, refresh, peek)


class RecordingFetcher(FixtureFetcher):
    def __init__(self, code_without_account: str | None = None) -> None:
        super().__init__()
        self.code = code_without_account
        self.jars: list[Any] = []

    def fetch_frame_piece(self, video_id: str, t_ms: int, max_short_side: int | None, dest: Path):  # type: ignore[override]
        self.jars.append(current_jar())
        if self.code is not None and current_jar() is None:
            raise YtError(self.code, "fake: needs the account")
        return super().fetch_frame_piece(video_id, t_ms, max_short_side, dest)


def _service(tmp_path: Path, videos: FakeVideos, fetcher: FixtureFetcher, gate: Gate | None) -> CaptureService:
    return CaptureService(videos, fetcher, FakeMediaTools(MEDIA), tmp_path / "cache", StubSettings(tmp_path / "out"),
                          StubQueue(), work_root=tmp_path / "work", now=lambda: datetime(2026, 10, 6, 3, tzinfo=UTC),
                          accounts=gate)  # fmt: skip


def test_a_restricted_clip_is_captured_with_the_account(tmp_path: Path) -> None:
    gate, fetcher = Gate(), RecordingFetcher()
    service = _service(tmp_path, RestrictedVideos({BBB: clip_info()}), fetcher, gate)
    capture, created = service.capture(BBB, 2_000)
    assert created and capture.id == "c_2000"
    assert fetcher.jars == [JAR]  # อ่านข้อมูลคลิปและโหลดชิ้นภาพใต้บัญชีเดียวกัน
    assert gate.used == [None]  # ใช้แบบโต้ตอบ ไม่นับเข้ากฎคิวว่าง


def test_a_piece_that_needs_the_account_retries_the_whole_capture(tmp_path: Path) -> None:
    gate, fetcher = Gate(), RecordingFetcher("E_VIDEO_PRIVATE")
    service = _service(tmp_path, FakeVideos({BBB: clip_info()}), fetcher, gate)
    capture, created = service.capture(BBB, 3_000)
    assert created and fetcher.jars == [None, JAR]
    assert not list((tmp_path / "work").glob("capture-*"))


def test_without_an_account_the_capture_fails_plainly(tmp_path: Path) -> None:
    service = _service(tmp_path, RestrictedVideos({BBB: clip_info()}), RecordingFetcher(), None)
    with pytest.raises(YtError) as info:
        service.capture(BBB, 2_000)
    assert info.value.code == "E_AGE_RESTRICTED" and info.value.account_tried is False


def test_an_account_without_access_gets_the_tried_copy(tmp_path: Path) -> None:
    fetcher = RecordingFetcher()
    fetcher.error = YtError("E_VIDEO_PRIVATE", "fake: private for everyone")
    service = _service(tmp_path, FakeVideos({BBB: clip_info()}), fetcher, Gate())
    with pytest.raises(YtError) as info:
        service.capture(BBB, 2_000)
    assert info.value.message == ACCOUNT_TRIED_MESSAGE
    assert fetcher.jars == [None, JAR]


def test_a_bot_check_is_never_retried_with_the_account(tmp_path: Path) -> None:
    gate, fetcher = Gate(), RecordingFetcher()
    fetcher.error = YtError("E_BOT_CHECK", "fake")
    service = _service(tmp_path, FakeVideos({BBB: clip_info()}), fetcher, gate)
    with pytest.raises(YtError) as info:
        service.capture(BBB, 2_000)
    assert info.value.code == "E_BOT_CHECK"
    assert fetcher.jars == [None] and gate.used == []
