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
    "theme",
    "filenameStyle",
    "cookies",
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
