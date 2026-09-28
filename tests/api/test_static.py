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
