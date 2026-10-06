"""API บัญชียูทูปชั่วคราว (api/account.py · M5 รอบ C spec 2.5) + แถวบัญชีใน /health + ข่าว SSE "account"

ใช้ AccountService ตัวจริงกับตัวอ่าน cookies.txt ตัวจริง (core/extractor.parse_account_cookies) ไม่ต่อเน็ต
"""

from __future__ import annotations

from pathlib import Path

import pytest

from yttoolkit.api.errors import redact_home
from yttoolkit.api.events import format_event
from yttoolkit.core.account_session import MAX_IMPORT_BYTES, AccountService
from yttoolkit.core.db import Database
from yttoolkit.core.events import Event, EventBus
from yttoolkit.core.extractor import parse_account_cookies
from yttoolkit.core.jobs import JobStore
from yttoolkit.core.media import FakeMediaTools
from yttoolkit.core.queue import QueueRunner
from yttoolkit.core.settings import SettingsStore
from yttoolkit.core.yterrors import MESSAGES

BASE = "http://127.0.0.1:8787"
AUTH = {"X-Toolkit-Token": "test-token", "Origin": BASE}
CANARY = "canary-api-9c1e"
GOOD = (
    "# Netscape HTTP Cookie File\n"
    f".youtube.com\tTRUE\t/\tTRUE\t1999999999\tSAPISID\t{CANARY}\n"
    f".youtube.com\tTRUE\t/\tTRUE\t1999999999\tLOGIN_INFO\t{CANARY}\n"
)
MEDIA_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "media"
HEALTH = {"tools": {}, "disk": {}, "output": {}, "network": {}}


@pytest.fixture
def bus():
    events = EventBus()
    yield events
    events.close()


@pytest.fixture
def service(bus):
    return AccountService(parse_account_cookies, publish=bus.publish)


@pytest.fixture
def client(make_client, service):
    return make_client(accounts=service, health=lambda: dict(HEALTH))


def _no_secret(text: str) -> None:
    assert CANARY not in text
    assert "SAPISID" not in text and "LOGIN_INFO" not in text


def test_status_starts_inactive(client) -> None:
    assert client.get("/api/cookies").json() == {"active": False, "used": False}


def test_no_router_without_the_service(make_client) -> None:
    assert make_client().get("/api/cookies").status_code == 404


def test_import_then_status_then_delete(client, service) -> None:
    resp = client.post("/api/cookies/import", json={"text": GOOD, "acceptWarning": True}, headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"active", "importedAt", "expiresAt", "used"} and body["active"] is True
    _no_secret(resp.text)
    assert client.get("/api/cookies").json() == body
    assert service.jar() is not None
    gone = client.delete("/api/cookies", headers=AUTH)
    assert gone.status_code == 200 and gone.json() == {"active": False, "used": False}
    assert service.jar() is None


def test_changes_need_the_token(client, service) -> None:
    assert client.post("/api/cookies/import", json={"text": GOOD, "acceptWarning": True}).status_code == 403
    assert client.delete("/api/cookies").status_code == 403
    assert service.jar() is None


def test_import_without_accepting_the_warning_is_409(client, service) -> None:
    for body in ({"text": GOOD}, {"text": GOOD, "acceptWarning": False}, {"text": GOOD, "acceptWarning": "yes"}):
        resp = client.post("/api/cookies/import", json=body, headers=AUTH)
        assert resp.status_code == 409 and resp.json()["error"]["code"] == "E_BAD_REQUEST"
        _no_secret(resp.text)
    assert service.jar() is None


@pytest.mark.parametrize(
    "body",
    [[GOOD], {"text": 5, "acceptWarning": True}, {"text": GOOD, "acceptWarning": True, "cookies": GOOD}, {}],
)
def test_a_malformed_body_is_422_without_echoing_it(client, body) -> None:
    resp = client.post("/api/cookies/import", json=body, headers=AUTH)
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "E_BAD_REQUEST"
    _no_secret(resp.text)


def test_more_than_1_mb_is_413(client, service) -> None:
    text = GOOD + "#" * MAX_IMPORT_BYTES
    resp = client.post("/api/cookies/import", json={"text": text, "acceptWarning": True}, headers=AUTH)
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "E_COOKIES_INVALID"
    assert resp.json()["error"]["message"] == MESSAGES["E_COOKIES_INVALID"]
    assert service.jar() is None


def test_an_invalid_file_is_422_and_keeps_the_held_account(client, service) -> None:
    client.post("/api/cookies/import", json={"text": GOOD, "acceptWarning": True}, headers=AUTH)
    held = service.jar()
    bad = f"# Netscape HTTP Cookie File\nnot a cookie line {CANARY}\n"
    resp = client.post("/api/cookies/import", json={"text": bad, "acceptWarning": True}, headers=AUTH)
    assert resp.status_code == 422
    assert resp.json()["error"] == {
        "code": "E_COOKIES_INVALID",
        "message": MESSAGES["E_COOKIES_INVALID"],
        "detail": "line 2: expected 7 tab-separated fields",
    }
    assert service.jar() is held


def test_import_and_delete_are_announced_on_the_event_stream(client, bus) -> None:
    sub = bus.subscribe()
    client.post("/api/cookies/import", json={"text": GOOD, "acceptWarning": True}, headers=AUTH)
    client.delete("/api/cookies", headers=AUTH)
    first, second = sub.get(1), sub.get(1)
    assert isinstance(first, Event) and first.name == "account"
    assert set(first.data) == {"active", "expiresAt"} and first.data["active"] is True
    assert isinstance(second, Event) and second.data == {"active": False, "reason": "manual"}
    wire = format_event(first) + format_event(second)
    assert wire.startswith("event: account\n")
    _no_secret(wire)


def test_health_has_the_account_row_with_status_only(client) -> None:
    assert client.get("/api/health").json()["account"] == {"status": "ok", "active": False, "importedAt": None}
    client.post("/api/cookies/import", json={"text": GOOD, "acceptWarning": True}, headers=AUTH)
    resp = client.get("/api/health")
    row = resp.json()["account"]
    assert row["status"] == "ok" and row["active"] is True and row["importedAt"]
    _no_secret(resp.text)


def test_health_without_the_service_has_no_account_row(make_client) -> None:
    assert "account" not in make_client(health=lambda: dict(HEALTH)).get("/api/health").json()


def test_jobs_refuse_use_cookies_in_otherwise_normal_params(make_client, tmp_path) -> None:
    # useCookies ใน POST /jobs ยังได้ 422 (C9: ไม่มี checkbox ต่อคลิป) API ใหม่ไม่เปิดทางอื่นให้ส่งคุกกี้ไปกับงาน
    db = Database(tmp_path / "app.db")
    db.migrate()
    bus = EventBus()
    settings = SettingsStore(db, tmp_path / "out")
    runner = QueueRunner(
        JobStore(db), bus, {}, settings=settings, work_root=tmp_path / "work", spawn=lambda fn: None, redact=redact_home
    )
    try:
        client = make_client(queue=runner, events=bus, settings=settings, media=FakeMediaTools(MEDIA_FIXTURES))
        normal = {"maxQuality": False, "splitChapters": False, "noAudio": False, "audioLanguage": "original"}

        def post(params: dict):
            item = {"videoId": "aqz-KE-bpKQ", "kind": "video", "params": params}
            return client.post("/api/jobs", json={"items": [item]}, headers=AUTH)

        resp = post({**normal, "useCookies": True})
        assert resp.status_code == 422 and resp.json()["error"]["code"] == "E_BAD_REQUEST"
        assert runner.store.pending_count() == 0
        assert post(normal).status_code == 200  # ตัวควบคุม: ค่าเดียวกันที่ไม่มี useCookies ผ่าน
    finally:
        runner.shutdown(timeout=0.1)
        bus.close()
        db.close()
