from __future__ import annotations

import pytest

from yttoolkit.core.db import Database
from yttoolkit.core.settings import SettingsStore

AUTH = {"X-Toolkit-Token": "test-token", "Origin": "http://127.0.0.1:8787"}

SETTING_KEYS = {
    "outputDir",
    "videoDefault",
    "audioDefault",
    "audioLanguage",
    "mp3Kbps",
    "subPreset",
    "subCustom",
    "concurrency",
    "sponsorblockDefault",
    "autoSharpFrames",
    "captureQuality",
    "theme",
    "filenameStyle",
    "statsResetAt",
    "lastUsed",
}


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "app.db")
    database.migrate()
    yield database
    database.close()


@pytest.fixture
def client(make_client, db, tmp_path):
    return make_client(settings=SettingsStore(db, tmp_path / "out"))


def test_get_returns_the_full_shape(client, tmp_path):
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == SETTING_KEYS
    assert body["outputDir"] == str(tmp_path / "out")
    assert body["concurrency"] == 2


def test_no_settings_router_without_a_store(make_client):
    assert make_client().get("/api/settings").status_code == 404


def test_patch_persists(client, db, tmp_path):
    resp = client.patch("/api/settings", json={"concurrency": 3, "audioDefault": "mp3"}, headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["concurrency"] == 3
    assert client.get("/api/settings").json()["audioDefault"] == "mp3"
    assert SettingsStore(db, tmp_path / "out").concurrency() == 3


def test_patch_requires_the_token(client):
    assert client.patch("/api/settings", json={"concurrency": 3}).status_code == 403
    assert client.get("/api/settings").json()["concurrency"] == 2


@pytest.mark.parametrize(
    "body",
    [{"concurrency": 4}, {"nope": 1}, {"cookies": {}}, {"outputDir": "relative"}],
)
def test_invalid_patch_is_422_with_the_envelope(client, body):
    resp = client.patch("/api/settings", json={"theme": "dark", **body}, headers=AUTH)
    assert resp.status_code == 422
    error = resp.json()["error"]
    assert error["code"] == "E_BAD_REQUEST"
    assert error["message"]
    assert client.get("/api/settings").json()["theme"] == "system"


def test_bad_output_dir_uses_the_full_path_hint(client):
    resp = client.patch("/api/settings", json={"outputDir": "relative"}, headers=AUTH)
    assert resp.status_code == 422
    error = resp.json()["error"]
    assert error["code"] == "E_BAD_REQUEST"
    assert error["message"] == "ใส่ที่อยู่โฟลเดอร์แบบเต็ม เช่น C:\\Users\\ชื่อ\\Videos"


def test_nul_in_output_dir_is_422_not_500(client):
    resp = client.patch("/api/settings", json={"outputDir": "C:\\a\x00b"}, headers=AUTH)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "E_BAD_REQUEST"


def test_non_finite_last_used_does_not_poison_settings(client):
    resp = client.patch(
        "/api/settings", content='{"lastUsed": {"x": NaN}}', headers={**AUTH, "Content-Type": "application/json"}
    )
    assert resp.status_code == 422
    assert client.get("/api/settings").status_code == 200


def test_float_enum_values_are_422(client):
    resp = client.patch("/api/settings", json={"concurrency": 2.0}, headers=AUTH)
    assert resp.status_code == 422
    assert client.get("/api/settings").json()["concurrency"] == 2


def test_patch_with_a_non_object_body_is_422(client):
    resp = client.patch("/api/settings", json=[1, 2], headers=AUTH)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "E_BAD_REQUEST"


def test_unwritable_output_dir_is_422(client, tmp_path):
    a_file = tmp_path / "file.txt"
    a_file.write_text("x")
    resp = client.patch("/api/settings", json={"outputDir": str(a_file)}, headers=AUTH)
    assert resp.status_code == 422
    error = resp.json()["error"]
    assert error["code"] == "E_OUTPUT_NOT_WRITABLE"
    assert "บันทึกลงโฟลเดอร์นี้ไม่ได้" in error["message"]


def test_open_output_uses_the_override(make_client, db, tmp_path, fake_platform):
    opened = []
    client = make_client(settings=SettingsStore(db, tmp_path / "out"), open_folder=opened.append)
    resp = client.post("/api/settings/open-output", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert opened == [tmp_path / "out"]
    assert (tmp_path / "out").is_dir()
    assert fake_platform.opened == []


def test_open_output_falls_back_to_the_platform(client, tmp_path, fake_platform):
    assert client.post("/api/settings/open-output", headers=AUTH).status_code == 200
    assert fake_platform.opened == [tmp_path / "out"]


def test_open_output_requires_the_token(client, fake_platform):
    assert client.post("/api/settings/open-output").status_code == 403
    assert fake_platform.opened == []


def test_open_output_not_writable_is_422(make_client, db, tmp_path, fake_platform):
    store = SettingsStore(db, tmp_path / "blocked")
    (tmp_path / "blocked").write_text("x")  # มีไฟล์ชื่อเดียวกับโฟลเดอร์ปลายทาง
    resp = make_client(settings=store).post("/api/settings/open-output", headers=AUTH)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "E_OUTPUT_NOT_WRITABLE"
    assert fake_platform.opened == []


def test_health_reports_the_settings_folder(make_client, db, tmp_path):
    store = SettingsStore(db, tmp_path / "chosen")
    body = make_client(settings=store).get("/api/health").json()
    assert body["output"]["path"] == str(tmp_path / "chosen")
    store.patch({"outputDir": str(tmp_path / "moved")})
    assert make_client(settings=store).get("/api/health").json()["output"]["path"] == str(tmp_path / "moved")


def test_capture_quality_round_trips(client):
    resp = client.patch("/api/settings", json={"captureQuality": "720"}, headers=AUTH)
    assert resp.status_code == 200 and resp.json()["captureQuality"] == "720"
    bad = client.patch("/api/settings", json={"captureQuality": "480"}, headers=AUTH)
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "E_BAD_REQUEST"
    assert client.get("/api/settings").json()["captureQuality"] == "720"



# ---------- M6 รอบ A: สำรอง / นำเข้าค่าตั้ง (spec 4, AC-SET-09 / AC-SET-10) ----------

import json  # noqa: E402
import re  # noqa: E402
from datetime import datetime  # noqa: E402

from yttoolkit.api import settings as settings_api  # noqa: E402
from yttoolkit.core.yterrors import MESSAGES  # noqa: E402

INVALID = MESSAGES["E_SETTINGS_INVALID"]


def _rows(db) -> list[tuple[str, str]]:
    return [(r["key"], r["value_json"]) for r in db.execute("SELECT key, value_json FROM settings ORDER BY key")]


def _import(client, content: bytes | str, headers: dict | None = None):
    data = content.encode("utf-8") if isinstance(content, str) else content
    return client.post("/api/settings/import", content=data,
                       headers={**AUTH, "Content-Type": "application/json", **(headers or {})})  # fmt: skip


def test_export_is_a_dated_attachment_without_read_only_keys(client):
    client.patch("/api/settings", json={"theme": "dark"}, headers=AUTH)
    resp = client.get("/api/settings/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/json"
    assert resp.headers["cache-control"] == "no-store"
    name = f"yt-toolkit-settings-{datetime.now().astimezone():%Y-%m-%d}.json"
    assert resp.headers["content-disposition"] == f"attachment; filename=\"{name}\"; filename*=UTF-8''{name}"
    assert resp.content.endswith(b"}\n") and not resp.content.startswith(b"\xef\xbb\xbf") and b"\r" not in resp.content
    doc = resp.json()
    assert list(doc) == ["app", "schema", "exportedAt", "settings"]
    assert (doc["app"], doc["schema"]) == ("yt-toolkit", 1)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00", doc["exportedAt"])
    assert set(doc["settings"]) == SETTING_KEYS - {"statsResetAt"}
    assert doc["settings"]["theme"] == "dark"


def test_export_needs_no_token(client):
    assert client.get("/api/settings/export", headers={"Origin": "http://127.0.0.1:8787"}).status_code == 200


def test_import_round_trip_on_a_fresh_data_folder(client, make_client, tmp_path):
    client.patch("/api/settings", json={"concurrency": 3, "filenameStyle": "title-quality"}, headers=AUTH)
    exported = client.get("/api/settings/export")
    fresh_db = Database(tmp_path / "fresh.db")
    fresh_db.migrate()
    try:
        fresh = make_client(settings=SettingsStore(fresh_db, tmp_path / "elsewhere"))
        resp = _import(fresh, exported.content)
        assert resp.status_code == 200
        body = resp.json()
        assert body["warnings"] == []
        after = fresh.get("/api/settings").json()
        for key, value in exported.json()["settings"].items():
            assert after[key] == value, key
        assert body["settings"] == after
    finally:
        fresh_db.close()


def test_import_with_a_bom_is_accepted(client):
    doc = {"app": "yt-toolkit", "schema": 1, "settings": {"theme": "light"}}
    resp = _import(client, b"\xef\xbb\xbf" + json.dumps(doc).encode("utf-8"))
    assert resp.status_code == 200 and resp.json()["settings"]["theme"] == "light"


def test_import_keeps_an_unusable_output_dir_and_warns(client, tmp_path):
    old = client.get("/api/settings").json()["outputDir"]
    doc = {"app": "yt-toolkit", "schema": 1, "settings": {"outputDir": "relative\\folder", "theme": "dark"}}
    resp = _import(client, json.dumps(doc))
    assert resp.status_code == 200
    assert resp.json()["warnings"] == ["outputDir"]
    assert resp.json()["settings"]["outputDir"] == old and resp.json()["settings"]["theme"] == "dark"


@pytest.mark.parametrize(
    ("content", "detail"),
    [
        (b"not json at all", "not JSON"),
        (b"\xff\xfe\x00garbage", "not UTF-8"),
        (b'{"app": "yt-toolkit", "schema": 1, "settings": {"concurrency": NaN}}', "not JSON"),
        (b'{"app": "other", "schema": 1, "settings": {}}', "app invalid"),
        (b'{"app": "yt-toolkit", "schema": 2, "settings": {}}', "schema invalid"),
        (b"[" * 100_000, "not JSON"),
        (b'{"app": "yt-toolkit", "schema": 1, "settings": {"theme": "SECRET-VALUE-123"}}', "theme: invalid value"),
        (b'{"app": "yt-toolkit", "schema": 1, "settings": {"outputDir": 7}}', "outputDir: invalid value"),
    ],
    ids=["not-json", "not-utf8", "nan", "other-app", "newer-schema", "deep-nesting", "bad-value", "output-dir-type"],
)
def test_import_of_a_bad_file_is_422_and_changes_nothing(client, db, content, detail):
    client.patch("/api/settings", json={"concurrency": 3}, headers=AUTH)
    before = _rows(db)
    resp = _import(client, content)
    assert resp.status_code == 422
    assert resp.json()["error"] == {"code": "E_SETTINGS_INVALID", "message": INVALID, "detail": detail}
    assert b"SECRET-VALUE-123" not in resp.content  # 422 ไม่ยกค่าในไฟล์กลับ
    assert _rows(db) == before


def test_import_above_one_megabyte_is_413_with_or_without_content_length(client, db):
    big = b'{"app": "yt-toolkit", "schema": 1, "settings": {}, "pad": "' + b"x" * 1_048_576 + b'"}'
    before = _rows(db)
    resp = _import(client, big)
    assert resp.status_code == 413
    assert resp.json()["error"] == {"code": "E_SETTINGS_INVALID", "message": INVALID,
                                    "detail": "file larger than 1048576 bytes"}  # fmt: skip

    def chunks():
        yield big[:600_000]
        yield big[600_000:]

    streamed = client.post("/api/settings/import", content=chunks(),
                           headers={**AUTH, "Content-Type": "application/json"})  # fmt: skip
    assert streamed.status_code == 413
    assert _rows(db) == before


def test_exactly_one_megabyte_is_still_read(client):
    doc = b'{"app": "yt-toolkit", "schema": 1, "settings": {}, "pad": "'
    body = doc + b"x" * (settings_api.MAX_SETTINGS_IMPORT_BYTES - len(doc) - 2) + b'"}'
    assert len(body) == settings_api.MAX_SETTINGS_IMPORT_BYTES
    assert _import(client, body).status_code == 200


def test_import_requires_the_token_and_our_origin(client):
    doc = json.dumps({"app": "yt-toolkit", "schema": 1, "settings": {}})
    no_token = client.post("/api/settings/import", content=doc, headers={"Origin": "http://127.0.0.1:8787"})
    foreign = client.post("/api/settings/import", content=doc, headers={**AUTH, "Origin": "https://evil.example"})
    assert no_token.status_code == 403 and foreign.status_code == 403
    assert no_token.json()["error"]["code"] == "E_FORBIDDEN"


def test_import_body_never_reaches_the_log(client, caplog):
    import logging

    with caplog.at_level(logging.DEBUG, logger="yttoolkit"):
        _import(client, b'{"app": "yt-toolkit", "schema": 1, "settings": {"theme": "SECRET-VALUE-123"}}')
    assert "SECRET-VALUE-123" not in caplog.text
