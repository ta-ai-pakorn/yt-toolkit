"""กฎลองซ้ำด้วยบัญชียูทูปชั่วคราว (core/account_scope.with_account_retry · M5 รอบ C spec 2.4)

ทุกจุดเรียกยูทูป (probe ของหน้า W2, งานในคิว, ถ่ายภาพคม) ใช้ตัวนี้ตัวเดียว เทสที่นี่ครอบกฎ เทสของแต่ละจุดเรียกอยู่ใน
test_videos_account.py, test_handlers_account.py, test_capture_account.py และ tests/api/test_videos_api.py
"""

from __future__ import annotations

from typing import Any

import pytest

from yttoolkit.core.account_scope import current_jar, signed_in, with_account_retry
from yttoolkit.core.yterrors import ACCOUNT_TRIED_MESSAGE, MESSAGES, YtError

JAR = object()
MARKER = "MARKER-DETAIL"  # แทนข้อความดิบของ yt-dlp (ห้ามมีชื่อคุกกี้ใน detail ของ error แม้แต่ในเทส)


class Gate:
    def __init__(self, jar: Any | None = JAR) -> None:
        self._jar = jar
        self.used: list[str | None] = []

    def jar(self) -> Any | None:
        return self._jar

    def mark_used(self, job_id: str | None) -> None:
        self.used.append(job_id)


class Call:
    """จำลองคำขอ: anonymous / signed = รหัส error ของแต่ละแบบ (None = สำเร็จ) และจดว่ารอบไหนใช้ jar อะไร"""

    def __init__(self, anonymous: str | None, signed: str | None = None) -> None:
        self.anonymous = anonymous
        self.signed = signed
        self.jars: list[Any] = []

    def __call__(self) -> str:
        jar = current_jar()
        self.jars.append(jar)
        code = self.anonymous if jar is None else self.signed
        if code is not None:
            raise YtError(code, f"ERROR: [youtube] x: raw yt-dlp text {MARKER} ({code})")
        return "ok"


@pytest.mark.parametrize("code", ["E_AGE_RESTRICTED", "E_VIDEO_PRIVATE"])
def test_account_codes_retry_once_signed_in(code: str) -> None:
    gate, call = Gate(), Call(anonymous=code)
    assert with_account_retry(gate, call, job_id="job-1") == "ok"
    assert call.jars == [None, JAR]
    assert gate.used == ["job-1"]
    assert current_jar() is None  # ขอบเขตจบพร้อมงาน


def test_success_needs_no_account() -> None:
    gate, call = Gate(), Call(anonymous=None)
    assert with_account_retry(gate, call) == "ok"
    assert call.jars == [None] and gate.used == []


@pytest.mark.parametrize("code", ["E_BOT_CHECK", "E_NETWORK", "E_GEO_BLOCKED", "E_LIVE_NOT_READY", "E_VIDEO_UNAVAILABLE"])
def test_other_codes_never_use_the_account(code: str) -> None:
    gate, call = Gate(), Call(anonymous=code)
    with pytest.raises(YtError) as info:
        with_account_retry(gate, call)
    assert info.value.code == code and info.value.account_tried is False
    assert call.jars == [None] and gate.used == []


def test_no_account_held_keeps_the_plain_error() -> None:
    call = Call(anonymous="E_AGE_RESTRICTED")
    for gate in (None, Gate(jar=None)):
        with pytest.raises(YtError) as info:
            with_account_retry(gate, call)
        assert info.value.message == MESSAGES["E_AGE_RESTRICTED"]
        assert MARKER in info.value.detail  # ข้อความดิบของรอบไม่ใช้บัญชีคงเดิม (ไม่มีคุกกี้ในรอบนี้)


@pytest.mark.parametrize("code", ["E_AGE_RESTRICTED", "E_VIDEO_PRIVATE"])
def test_signed_in_failure_with_the_same_code_uses_the_tried_copy(code: str) -> None:
    gate, call = Gate(), Call(anonymous=code, signed=code)
    with pytest.raises(YtError) as info:
        with_account_retry(gate, call)
    err = info.value
    assert err.code == code and err.account_tried is True and err.message == ACCOUNT_TRIED_MESSAGE
    assert err.detail == f"signed-in retry failed ({code})"
    assert err.__cause__ is None and err.__suppress_context__ is True  # ไม่มีข้อความดิบของรอบที่ใช้บัญชีหลุดไป log
    assert gate.jar() is JAR  # บัญชียังอยู่ (อาจแค่ไม่มีสิทธิ์ดูคลิปนี้)


def test_signed_in_bot_check_keeps_its_code_for_the_queue_brake() -> None:
    gate, call = Gate(), Call(anonymous="E_AGE_RESTRICTED", signed="E_BOT_CHECK")
    with pytest.raises(YtError) as info:
        with_account_retry(gate, call)
    assert info.value.code == "E_BOT_CHECK" and info.value.account_tried is False
    assert MARKER not in str(info.value)


def test_inside_a_signed_in_scope_there_is_no_second_retry() -> None:
    gate, call = Gate(), Call(anonymous="E_AGE_RESTRICTED", signed="E_AGE_RESTRICTED")
    other = object()
    with signed_in(other):
        with pytest.raises(YtError) as info:
            with_account_retry(gate, call)
    assert call.jars == [other] and gate.used == []
    assert info.value.account_tried is False  # รอบนอก (ผู้เปิดขอบเขต) เป็นคนตัดสินข้อความ


def test_interactive_use_is_marked_without_a_job_id() -> None:
    gate = Gate()
    with_account_retry(gate, Call(anonymous="E_VIDEO_PRIVATE"))
    assert gate.used == [None]
