import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from yttoolkit.api.static import inject_token, mount_web

BASE = "http://127.0.0.1:8787"
INDEX = "<!doctype html><html><head><title>x</title></head><body></body></html>"


def _client(dist) -> TestClient:
    app = FastAPI()

    @app.get("/api/ping")
    def ping():
        return {"ok": True}

    mount_web(app, dist, token="tok<&>")
    return TestClient(app, base_url=BASE)


def _dist(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX, encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    return dist


def test_inject_token_escapes_value():
    out = inject_token(INDEX, 'a"b')
    assert '<meta name="yt-token" content="a&quot;b"></head>' in out


def test_root_serves_index_with_token(tmp_path):
    resp = _client(_dist(tmp_path)).get("/")
    assert resp.status_code == 200
    assert 'name="yt-token" content="tok&lt;&amp;&gt;"' in resp.text
    assert resp.headers["cache-control"] == "no-store"


def test_spa_route_falls_back_to_index(tmp_path):
    resp = _client(_dist(tmp_path)).get("/settings/health")
    assert resp.status_code == 200
    assert "yt-token" in resp.text


def test_asset_is_served(tmp_path):
    resp = _client(_dist(tmp_path)).get("/assets/app.js")
    assert resp.status_code == 200
    assert resp.text == "console.log(1)"


def test_api_routes_win_and_unknown_api_is_404(tmp_path):
    client = _client(_dist(tmp_path))
    assert client.get("/api/ping").json() == {"ok": True}
    assert client.get("/api/nope").status_code == 404


def test_missing_dist_returns_503(tmp_path):
    resp = _client(tmp_path / "missing").get("/")
    assert resp.status_code == 503


def _record_fs_calls(monkeypatch):
    """บันทึก path ทุกตัวที่ถูกส่งเข้า Path.resolve / Path.is_file"""
    import pathlib

    seen: list[str] = []
    real_resolve = pathlib.Path.resolve
    real_is_file = pathlib.Path.is_file

    def resolve(self, *args, **kwargs):
        seen.append(str(self))
        return real_resolve(self, *args, **kwargs)

    def is_file(self, *args, **kwargs):
        seen.append(str(self))
        return real_is_file(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "resolve", resolve)
    monkeypatch.setattr(pathlib.Path, "is_file", is_file)
    return seen


def test_unc_path_never_touches_filesystem(tmp_path, monkeypatch):
    client = _client(_dist(tmp_path))
    seen = _record_fs_calls(monkeypatch)
    resp = client.get("/%5C%5Cevil%5Cshare%5Cx")
    assert resp.status_code == 200
    assert "yt-token" in resp.text
    assert not any("evil" in p for p in seen), seen


def test_encoded_dotdot_traversal_is_rejected(tmp_path, monkeypatch):
    dist = _dist(tmp_path)
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    client = _client(dist)
    seen = _record_fs_calls(monkeypatch)
    resp = client.get("/assets/%2e%2e/%2e%2e/secret.txt")
    assert resp.status_code == 200
    assert "secret" not in resp.text
    assert "yt-token" in resp.text
    assert not any("secret" in p for p in seen), seen


def test_drive_letter_path_never_touches_filesystem(tmp_path, monkeypatch):
    client = _client(_dist(tmp_path))
    seen = _record_fs_calls(monkeypatch)
    resp = client.get("/C:%5CWindows%5Cwin.ini")
    assert resp.status_code == 200
    assert "yt-token" in resp.text
    assert not any("win.ini" in p for p in seen), seen


def test_index_html_is_served_with_token(tmp_path):
    resp = _client(_dist(tmp_path)).get("/index.html")
    assert resp.status_code == 200
    assert 'name="yt-token"' in resp.text
    assert resp.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", ["/index.html.", "/INDEX.HTML.", "/index.html%20", "/Index.Html"])
def test_index_html_aliases_never_serve_raw_copy(tmp_path, path):
    # บน Windows ชื่อที่มีจุดหรือช่องว่างท้าย และตัวพิมพ์ต่างกัน ชี้ไปที่ไฟล์ index.html เดียวกัน
    resp = _client(_dist(tmp_path)).get(path)
    assert resp.status_code == 200
    assert 'name="yt-token"' in resp.text
    assert resp.headers["cache-control"] == "no-store"


def test_samefile_error_fails_closed_to_token_index(tmp_path, monkeypatch):
    from yttoolkit.api import static

    def broken_samefile(a, b):
        raise OSError("cannot stat")

    monkeypatch.setattr(static.os.path, "samefile", broken_samefile)
    resp = _client(_dist(tmp_path)).get("/assets/app.js")
    assert resp.status_code == 200
    assert 'name="yt-token"' in resp.text
