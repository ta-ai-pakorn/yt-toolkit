import os

from yttoolkit.core import tools
from yttoolkit.core.tools import ToolStatus

# ค่าเดียวกับ tests/api/conftest.py (import conftest ตรง ๆ ไม่ได้)
BASE = "http://127.0.0.1:8787"
AUTH = {"X-Toolkit-Token": "test-token", "Origin": BASE}


def test_ping(make_client):
    body = make_client().get("/api/ping").json()
    assert body == {"ok": True, "pid": os.getpid()}


def test_health_includes_version_and_commit(make_client):
    fake = {"tools": {}, "disk": {}, "output": {}, "network": {}}
    body = make_client(health=lambda: fake).get("/api/health").json()
    assert body["version"] == "0.1.0"
    assert body["commit"] == "abc1234"
    assert set(body) == {"version", "commit", "tools", "disk", "output", "network"}


def test_shutdown_requires_token(make_client):
    assert make_client().post("/api/shutdown", json={}).status_code == 403


def test_shutdown_ok_when_no_pending(make_client):
    client = make_client()
    resp = client.post("/api/shutdown", json={"force": False}, headers=AUTH)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert client.calls["shutdown"] == 1


def test_shutdown_without_body(make_client):
    client = make_client()
    assert client.post("/api/shutdown", headers=AUTH).status_code == 200


def test_shutdown_conflict_when_pending(make_client):
    client = make_client(pending_jobs=lambda: 2)
    resp = client.post("/api/shutdown", json={"force": False}, headers=AUTH)
    assert resp.status_code == 409
    assert resp.json() == {"pendingJobs": 2}
    assert client.calls["shutdown"] == 0


def test_shutdown_force_when_pending(make_client):
    client = make_client(pending_jobs=lambda: 2)
    resp = client.post("/api/shutdown", json={"force": True}, headers=AUTH)
    assert resp.status_code == 200
    assert client.calls["shutdown"] == 1


def test_install_ffmpeg_success(make_client, monkeypatch):
    monkeypatch.setattr(tools, "install_ffmpeg", lambda paths, plat: paths.bin / "ffmpeg.exe")
    monkeypatch.setattr(tools, "ffmpeg_status", lambda paths, plat: ToolStatus("ok", name="ffmpeg", version="8.1"))
    resp = make_client().post("/api/tools/ffmpeg/install", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_install_ffmpeg_failure(make_client, monkeypatch):
    def boom(paths, plat):
        raise tools.ToolInstallError("checksum mismatch")

    monkeypatch.setattr(tools, "install_ffmpeg", boom)
    resp = make_client().post("/api/tools/ffmpeg/install", headers=AUTH)
    assert resp.status_code == 502
    assert resp.json()["error"] == {
        "code": "E_TOOL_INSTALL_FAILED",
        "message": "โหลดโปรแกรมที่ต้องใช้ไม่สำเร็จ ตรวจเน็ตแล้วกดลองใหม่",
        "detail": "checksum mismatch",
    }
