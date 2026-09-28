from fastapi import FastAPI
from fastapi.testclient import TestClient

from yttoolkit.api.security import LocalOnlyMiddleware

PORT = 8787
BASE = f"http://127.0.0.1:{PORT}"
TOKEN = "secret-token"


def _client(extra_origins=()) -> TestClient:
    app = FastAPI()

    @app.get("/ping")
    def get_ping():
        return {"ok": True}

    @app.post("/ping")
    def post_ping():
        return {"ok": True}

    app.add_middleware(LocalOnlyMiddleware, port=PORT, token=TOKEN, extra_origins=extra_origins)
    return TestClient(app, base_url=BASE)


def test_get_allowed_on_127():
    assert _client().get("/ping").status_code == 200


def test_get_allowed_on_localhost():
    assert _client().get("/ping", headers={"host": f"localhost:{PORT}"}).status_code == 200


def test_foreign_host_rejected_with_421():  # AC-SEC-02
    resp = _client().get("/ping", headers={"host": "evil.example:8787"})
    assert resp.status_code == 421
    assert resp.json()["error"]["code"] == "E_FORBIDDEN"


def test_wrong_port_in_host_rejected():
    assert _client().get("/ping", headers={"host": "127.0.0.1:9999"}).status_code == 421


def test_post_without_token_rejected():  # AC-SEC-03
    resp = _client().post("/ping", headers={"origin": BASE})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "E_FORBIDDEN"


def test_post_with_token_but_no_origin_rejected():
    assert _client().post("/ping", headers={"x-toolkit-token": TOKEN}).status_code == 403


def test_post_with_wrong_origin_rejected():
    headers = {"x-toolkit-token": TOKEN, "origin": "https://evil.example"}
    assert _client().post("/ping", headers=headers).status_code == 403


def test_post_with_non_ascii_token_rejected_cleanly():
    # เรียก middleware ตรง ๆ เพราะ httpx ไม่ยอมส่ง header ที่ไม่ใช่ ASCII
    import asyncio

    sent = []

    async def app(scope, receive, send):
        raise AssertionError("ต้องไม่ถึง app")

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "headers": [
            (b"host", b"127.0.0.1:8787"),
            (b"origin", BASE.encode()),
            (b"x-toolkit-token", "ไม่ใช่".encode("utf-8")),
        ],
    }
    asyncio.run(LocalOnlyMiddleware(app, port=PORT, token=TOKEN)(scope, receive, send))
    assert sent[0]["status"] == 403


def test_post_with_token_and_origin_allowed():
    headers = {"x-toolkit-token": TOKEN, "origin": BASE}
    assert _client().post("/ping", headers=headers).status_code == 200


def test_extra_origin_allowed_for_dev():
    client = _client(extra_origins=("http://localhost:5173",))
    headers = {"x-toolkit-token": TOKEN, "origin": "http://localhost:5173"}
    assert client.post("/ping", headers=headers).status_code == 200
