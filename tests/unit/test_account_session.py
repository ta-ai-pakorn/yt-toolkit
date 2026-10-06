"""บัญชียูทูปชั่วคราว (core/account_session.py · M5 รอบ C spec 2.1-2.2): สถานะ เวลาลบเอง และ grace ของคิว

ใช้นาฬิกาและตัวตั้งเวลาปลอม (ไม่รอเวลาจริง) และตัวอ่านไฟล์ปลอม (ไม่แตะ yt-dlp)
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from yttoolkit.core.account_session import EXPIRY_S, GRACE_S, MAX_IMPORT_BYTES, AccountService
from yttoolkit.core.yterrors import YtError

T0 = datetime(2026, 10, 6, 3, 0, tzinfo=UTC)
GOOD = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSAPISID\tvalue-1\n"


class FakeJar:
    def __init__(self, text: str) -> None:
        self.text = text


def fake_parse(text: str) -> FakeJar:
    if "bad" in text:
        raise YtError("E_COOKIES_INVALID", "line 1: expected 7 tab-separated fields")
    return FakeJar(text)


class Clock:
    """นาฬิกาปลอม + ตัวตั้งเวลาปลอม: advance(s) เดินเวลาแล้วเรียกงานที่ถึงเวลาตามลำดับ"""

    def __init__(self) -> None:
        self.now = T0
        self.timers: list[tuple[datetime, Callable[[], None]]] = []

    def __call__(self) -> datetime:
        return self.now

    def schedule(self, delay: float, fn: Callable[[], None]) -> None:
        self.timers.append((self.now + timedelta(seconds=delay), fn))

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)
        due = sorted((t for t in self.timers if t[0] <= self.now), key=lambda t: t[0])
        self.timers = [t for t in self.timers if t[0] > self.now]
        for _, fn in due:
            fn()


class Env:
    def __init__(self) -> None:
        self.clock = Clock()
        self.events: list[tuple[str, dict]] = []
        self.busy = False
        self.cleared = 0

        def on_clear() -> None:
            self.cleared += 1

        self.service = AccountService(
            fake_parse,
            publish=lambda name, data: self.events.append((name, data)),
            busy=lambda: self.busy,
            on_clear=on_clear,
            now=self.clock,
            schedule=self.clock.schedule,
        )

    def last(self) -> dict:
        name, data = self.events[-1]
        assert name == "account"
        return data


@pytest.fixture
def env() -> Env:
    return Env()


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def test_nothing_held_at_start(env: Env) -> None:
    assert env.service.status() == {"active": False, "used": False}
    assert env.service.jar() is None


def test_import_holds_the_jar_and_reports_times_only(env: Env) -> None:
    status = env.service.import_text(GOOD)
    expires = _iso(T0 + timedelta(seconds=EXPIRY_S))
    assert status == {"active": True, "importedAt": _iso(T0), "expiresAt": expires, "used": False}
    assert env.service.status() == status
    assert isinstance(env.service.jar(), FakeJar)
    assert env.events == [("account", {"active": True, "expiresAt": expires})]
    assert "value-1" not in repr(status) and "SAPISID" not in repr(env.events)


def test_oversize_text_is_rejected_before_parsing(env: Env) -> None:
    calls: list[str] = []
    service = AccountService(lambda text: calls.append(text) or FakeJar(text))
    with pytest.raises(YtError) as info:
        service.import_text("#" * (MAX_IMPORT_BYTES + 1))
    assert info.value.code == "E_COOKIES_INVALID"
    assert calls == [] and service.jar() is None


def test_a_bad_file_keeps_the_held_account(env: Env) -> None:
    env.service.import_text(GOOD)
    held = env.service.jar()
    with pytest.raises(YtError) as info:
        env.service.import_text("bad file")
    assert info.value.code == "E_COOKIES_INVALID"
    assert env.service.jar() is held
    assert len(env.events) == 1


def test_expires_two_hours_after_import(env: Env) -> None:
    env.service.import_text(GOOD)
    env.clock.advance(EXPIRY_S - 1)
    assert env.service.status()["active"] is True
    env.clock.advance(1)
    assert env.service.status() == {"active": False, "used": False}
    assert env.last() == {"active": False, "reason": "expired"}
    assert env.cleared == 1


def test_reimport_replaces_the_account_and_restarts_the_clock(env: Env) -> None:
    env.service.import_text(GOOD)
    env.clock.advance(3600)
    env.service.import_text(GOOD + "\n")
    assert env.cleared == 1  # ข้อมูลที่ได้มาด้วยบัญชีเดิมถูกทิ้ง
    env.clock.advance(3601)  # ครบ 2 ชม. ของรอบแรกแล้ว แต่รอบแรกถูกแทนไป
    assert env.service.status()["active"] is True
    env.clock.advance(EXPIRY_S - 3601)
    assert env.service.status()["active"] is False
    assert env.last()["reason"] == "expired"


def test_grace_starts_when_a_job_that_used_the_account_ends_and_the_queue_is_idle(env: Env) -> None:
    env.service.import_text(GOOD)
    env.service.mark_used("job-1")
    env.clock.advance(60)
    env.service.job_ended("job-1")
    grace_end = _iso(env.clock.now + timedelta(seconds=GRACE_S))
    assert env.service.status()["expiresAt"] == grace_end
    assert env.service.status()["used"] is True
    assert env.last() == {"active": True, "expiresAt": grace_end}
    env.clock.advance(GRACE_S)
    assert env.service.status()["active"] is False
    assert env.last() == {"active": False, "reason": "queue_done"}


def test_no_grace_while_the_queue_still_has_work(env: Env) -> None:
    env.service.import_text(GOOD)
    env.service.mark_used("job-1")
    env.busy = True  # มีงานรอคิว (รวมคิวที่พักเพราะยูทูปขอตรวจสอบ) หรือกำลังทำอยู่
    env.service.job_ended("job-1")
    env.clock.advance(GRACE_S + 1)
    assert env.service.status()["active"] is True
    env.busy = False
    env.service.job_ended("job-2")  # งานสุดท้ายจบ (ไม่ได้ใช้บัญชี) คิวว่างแล้ว
    env.clock.advance(GRACE_S)
    assert env.service.status()["active"] is False


def test_a_new_job_cancels_the_grace(env: Env) -> None:
    env.service.import_text(GOOD)
    env.service.mark_used("job-1")
    env.service.job_ended("job-1")
    env.clock.advance(GRACE_S - 1)
    env.service.job_queued()
    assert env.last() == {"active": True, "expiresAt": _iso(T0 + timedelta(seconds=EXPIRY_S))}
    env.clock.advance(5)
    assert env.service.status()["active"] is True
    env.service.job_ended("job-2")  # งานใหม่จบ คิวว่างอีกครั้ง: นับ grace ใหม่
    env.clock.advance(GRACE_S)
    assert env.service.status()["active"] is False


def test_interactive_use_never_starts_the_grace(env: Env) -> None:
    env.service.import_text(GOOD)
    env.service.mark_used(None)  # หน้า W2 หรือถ่ายภาพคมใช้บัญชี
    env.service.job_ended("job-1")  # งานอื่นที่ไม่ได้ใช้บัญชีจบ
    env.clock.advance(GRACE_S + 1)
    status = env.service.status()
    assert status["active"] is True and status["used"] is True


def test_a_job_that_did_not_use_the_account_does_not_start_the_grace(env: Env) -> None:
    env.service.import_text(GOOD)
    env.service.job_ended("job-1")
    env.clock.advance(GRACE_S + 1)
    assert env.service.status()["active"] is True


def test_manual_clear_and_shutdown(env: Env) -> None:
    env.service.import_text(GOOD)
    env.service.mark_used("job-1")
    assert env.service.clear("manual") == {"active": False, "used": False}
    assert env.last() == {"active": False, "reason": "manual"}
    env.service.job_ended("job-1")  # งานที่ใช้บัญชีเก่าจบหลังลบ: ไม่มีอะไรเกิดขึ้น
    assert env.service.jar() is None
    env.service.import_text(GOOD)
    env.service.clear("shutdown")
    assert env.last() == {"active": False, "reason": "shutdown"}
    assert env.cleared == 2


def test_clear_without_an_account_is_silent(env: Env) -> None:
    assert env.service.clear("manual") == {"active": False, "used": False}
    assert env.events == [] and env.cleared == 0
    with pytest.raises(ValueError):
        env.service.clear("because")


def test_stale_timers_after_clear_do_nothing(env: Env) -> None:
    env.service.import_text(GOOD)
    env.service.mark_used("job-1")
    env.service.job_ended("job-1")
    env.service.clear("manual")
    env.service.import_text(GOOD)
    env.clock.advance(GRACE_S)  # grace ของบัญชีก่อนหน้าครบเวลา
    assert env.service.status()["active"] is True


def test_listener_errors_never_break_the_service() -> None:
    def boom(*_args: object) -> None:
        raise RuntimeError("bus closed")

    service = AccountService(fake_parse, publish=boom, on_clear=boom)
    assert service.import_text(GOOD)["active"] is True
    assert service.clear("manual")["active"] is False
