"""เซสชันผู้ชมแบบไม่ระบุตัวตน (owner round 3): สร้าง, อายุ, ล็อก, บันทึกแบบ replace, ล้างเมื่อเกิน 30 วัน

ใช้ MozillaCookieJar ของ Python แทน YoutubeDLCookieJar (รูปแบบไฟล์เดียวกัน) ไม่มีเน็ต ไม่มี yt-dlp
"""

from __future__ import annotations

import json
import logging
import os
import threading
from http.cookiejar import Cookie, MozillaCookieJar
from pathlib import Path

import pytest

from yttoolkit.core.visitor_session import (
    MAX_AGE_S,
    META_FILE,
    MIN_TRANSLATION_AGE_S,
    SESSION_FILE,
    VISITOR_COOKIE,
    VisitorSession,
)

SECRET = "visitor-value-must-never-be-logged"


class Clock:
    def __init__(self, now: float = 1_800_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def cookie(name: str, value: str, domain: str = ".youtube.com") -> Cookie:
    return Cookie(
        version=0,
        name=name,
        value=value,
        port=None,
        port_specified=False,
        domain=domain,
        domain_specified=True,
        domain_initial_dot=domain.startswith("."),
        path="/",
        path_specified=True,
        secure=True,
        expires=2_000_000_000,
        discard=False,
        comment=None,
        comment_url=None,
        rest={},
    )


def make(tmp_path: Path, clock: Clock | None = None, **kwargs) -> VisitorSession:
    return VisitorSession(tmp_path, MozillaCookieJar, clock=clock or Clock(), **kwargs)


def visit(session: VisitorSession, value: str = SECRET) -> None:
    """เหมือน probe หนึ่งครั้ง: ยูทูปออกคุกกี้ผู้เข้าชมให้ แล้ว YoutubeDL ปิด (บันทึก)"""
    session.jar().set_cookie(cookie(VISITOR_COOKIE, value))
    session.save()


def test_files_live_in_the_given_folder(tmp_path: Path) -> None:
    session = make(tmp_path)
    assert session.path == tmp_path / SESSION_FILE == tmp_path / "visitor-session.txt"
    assert session.meta_path == tmp_path / META_FILE == tmp_path / "visitor-session.json"


def test_new_session_has_no_age_until_youtube_issues_a_visitor_cookie(tmp_path: Path) -> None:
    session = make(tmp_path)
    assert session.age() is None
    assert session.wait_seconds() is None
    # คุกกี้ความยินยอมที่ yt-dlp ตั้งเองก่อนต่อเน็ต ยังไม่นับเป็นเซสชัน
    session.jar().set_cookie(cookie("SOCS", "consent"))
    session.save()
    assert session.age() is None
    assert session.path.is_file()
    assert not session.meta_path.exists()


def test_clock_starts_when_the_visitor_cookie_first_appears(tmp_path: Path) -> None:
    clock = Clock()
    session = make(tmp_path, clock)
    visit(session)
    assert session.age() == 0
    assert session.wait_seconds() == MIN_TRANSLATION_AGE_S == 75
    clock.now += 30.2
    assert session.wait_seconds() == 45  # ปัดขึ้น
    clock.now += 44.5
    assert session.wait_seconds() == 1  # เหลือ 0.3 วินาทีก็ยังต้องรอ 1
    clock.now += 0.3
    assert session.wait_seconds() == 0
    meta = json.loads(session.meta_path.read_text(encoding="utf-8"))
    assert meta == {"createdAt": 1_800_000_000.0}


def test_age_survives_a_restart(tmp_path: Path) -> None:
    clock = Clock()
    visit(make(tmp_path, clock))
    clock.now += 100
    again = make(tmp_path, clock)
    assert again.age() == 100
    assert again.wait_seconds() == 0
    names = {c.name for c in again.jar()}
    assert VISITOR_COOKIE in names


def test_saving_again_does_not_restart_the_clock(tmp_path: Path) -> None:
    clock = Clock()
    session = make(tmp_path, clock)
    visit(session)
    clock.now += 50
    session.jar().set_cookie(cookie("YSC", "other"))
    session.save()
    assert session.age() == 50


def test_new_visitor_value_restarts_the_clock(tmp_path: Path) -> None:
    clock = Clock()
    session = make(tmp_path, clock)
    visit(session, "first")
    clock.now += 500
    visit(session, "second")
    assert session.age() == 0


def test_visitor_change_after_restart_also_restarts_the_clock(tmp_path: Path) -> None:
    clock = Clock()
    visit(make(tmp_path, clock), "first")
    clock.now += 500
    again = make(tmp_path, clock)
    assert again.age() == 500
    visit(again, "second")
    assert again.age() == 0


def test_older_than_30_days_is_recreated(tmp_path: Path) -> None:
    clock = Clock()
    session = make(tmp_path, clock)
    visit(session)
    clock.now += MAX_AGE_S + 1
    assert session.age() is None  # ล้างทิ้ง นาฬิกาเริ่มใหม่
    assert not session.path.exists()
    assert not session.meta_path.exists()
    assert list(session.jar()) == []
    visit(session, "fresh")
    assert session.age() == 0


def test_older_than_30_days_on_disk_is_recreated_at_load(tmp_path: Path) -> None:
    clock = Clock()
    visit(make(tmp_path, clock))
    clock.now += MAX_AGE_S + 1
    again = make(tmp_path, clock)
    assert again.age() is None
    assert not again.path.exists()


def test_exactly_30_days_is_still_valid(tmp_path: Path) -> None:
    clock = Clock()
    session = make(tmp_path, clock)
    visit(session)
    clock.now += MAX_AGE_S
    assert session.age() == MAX_AGE_S


@pytest.mark.parametrize("meta", [None, "not json", '{"createdAt": "x"}', '{"createdAt": true}', "[]"])
def test_cookie_file_without_a_usable_birth_time_starts_over(tmp_path: Path, meta: str | None) -> None:
    clock = Clock()
    visit(make(tmp_path, clock))
    if meta is None:
        (tmp_path / META_FILE).unlink()
    else:
        (tmp_path / META_FILE).write_text(meta, encoding="utf-8")
    again = make(tmp_path, clock)
    assert again.age() is None
    assert list(again.jar()) == []
    assert not again.path.exists()


def test_birth_time_in_the_future_is_not_trusted(tmp_path: Path) -> None:
    clock = Clock()
    visit(make(tmp_path, clock))
    (tmp_path / META_FILE).write_text(json.dumps({"createdAt": clock.now + 3600}), encoding="utf-8")
    assert make(tmp_path, clock).age() is None


def test_meta_without_a_cookie_file_starts_over(tmp_path: Path) -> None:
    clock = Clock()
    visit(make(tmp_path, clock))
    (tmp_path / SESSION_FILE).unlink()
    again = make(tmp_path, clock)
    assert again.age() is None
    assert not (tmp_path / META_FILE).exists()


def test_corrupt_cookie_file_starts_over(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    (tmp_path / SESSION_FILE).write_text("not a cookie file at all\n", encoding="utf-8")
    (tmp_path / META_FILE).write_text(json.dumps({"createdAt": 1.0}), encoding="utf-8")
    with caplog.at_level(logging.INFO, logger="yttoolkit"):
        session = make(tmp_path)
        assert session.age() is None
    assert list(session.jar()) == []


def test_jar_is_loaded_once_and_shared(tmp_path: Path) -> None:
    loads = []

    def factory(filename: str) -> MozillaCookieJar:
        jar = MozillaCookieJar(filename)
        loads.append(jar)
        return jar

    clock = Clock()
    visit(VisitorSession(tmp_path, factory, clock=clock))
    loads.clear()
    session = VisitorSession(tmp_path, factory, clock=clock)
    first = session.jar()
    assert session.jar() is first
    session.age()
    session.save()
    assert loads == [first]


def test_save_merges_cookies_from_another_jar(tmp_path: Path) -> None:
    # yt-dlp รุ่นที่ใส่ jar ก้อนกลางไม่ได้จะโหลด jar ของตัวเอง: save(jar นั้น) ต้องรวมเข้าก้อนกลาง
    session = make(tmp_path)
    other = MozillaCookieJar()
    other.set_cookie(cookie(VISITOR_COOKIE, SECRET))
    session.save(other)
    assert {c.name for c in session.jar()} == {VISITOR_COOKIE}
    assert session.age() == 0
    assert VISITOR_COOKIE in session.path.read_text(encoding="utf-8")


def test_save_replaces_the_file_atomically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session = make(tmp_path)
    visit(session)
    before = session.path.read_bytes()
    replaced = []
    real_replace = os.replace

    def spy(src, dst):
        replaced.append((Path(src).name, Path(dst).name))
        return real_replace(src, dst)

    monkeypatch.setattr("yttoolkit.core.visitor_session.os.replace", spy)
    session.jar().set_cookie(cookie("YSC", "x"))
    session.save()
    # เขียนลงไฟล์ชั่วคราวในโฟลเดอร์เดียวกันก่อน แล้ว replace ทับ (ไม่มีช่วงที่ไฟล์จริงว่างหรือครึ่ง ๆ)
    cookie_moves = [move for move in replaced if move[1] == SESSION_FILE]
    assert len(cookie_moves) == 1
    assert cookie_moves[0][0].startswith(f".{SESSION_FILE}.") and cookie_moves[0][0].endswith(".tmp")
    assert session.path.read_bytes() != before
    assert not list(tmp_path.glob("*.tmp"))


def test_failed_write_keeps_the_old_file_and_logs_no_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    session = make(tmp_path)
    visit(session)
    before = session.path.read_bytes()

    def broken(src, dst):
        raise PermissionError(f"locked {SECRET}")

    monkeypatch.setattr("yttoolkit.core.visitor_session.os.replace", broken)
    with caplog.at_level(logging.DEBUG, logger="yttoolkit"):
        session.save()  # ไม่โยน
    assert session.path.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))
    assert SECRET not in caplog.text


def test_concurrent_saves_lose_no_cookies(tmp_path: Path) -> None:
    session = make(tmp_path)
    errors: list[BaseException] = []
    start = threading.Barrier(8)

    def worker(n: int) -> None:
        try:
            start.wait()
            for k in range(20):
                session.jar().set_cookie(cookie(f"C{n}_{k}", "v"))
                session.save()
        except BaseException as exc:  # pragma: no cover - รายงานผ่าน errors
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    reloaded = MozillaCookieJar()
    reloaded.load(str(session.path), ignore_discard=True, ignore_expires=True)
    assert len({c.name for c in reloaded}) == 8 * 20


def test_one_lock_serialises_load_and_save(tmp_path: Path) -> None:
    # ระหว่างที่อีก thread ถือล็อกของเซสชันอยู่ jar()/save() ต้องรอ
    session = make(tmp_path)
    entered = threading.Event()
    done = threading.Event()
    with session._lock:
        thread = threading.Thread(target=lambda: (entered.set(), session.save(), done.set()))
        thread.start()
        entered.wait(1)
        assert not done.wait(0.2)
    thread.join(2)
    assert done.is_set()


def test_reset_clears_files_and_clock(tmp_path: Path) -> None:
    session = make(tmp_path)
    visit(session)
    session.reset()
    assert session.age() is None
    assert not session.path.exists()
    assert not session.meta_path.exists()


def test_logs_never_contain_cookie_values(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    clock = Clock()
    with caplog.at_level(logging.DEBUG, logger="yttoolkit"):
        session = make(tmp_path, clock)
        visit(session, SECRET)
        clock.now += 10
        visit(session, SECRET + "2")
        clock.now += MAX_AGE_S + 1
        session.age()
    assert caplog.records  # มี log จริง (เริ่มนาฬิกา, ออกเซสชันใหม่, เกิน 30 วัน)
    assert SECRET not in caplog.text
