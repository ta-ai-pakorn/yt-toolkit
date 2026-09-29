import asyncio

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from yttoolkit.api.security import LocalOnlyMiddleware

PORT = 8787
BASE = f"http://127.0.0.1:{PORT}"
TOKEN = "secret-token"
WS_URL = f"ws://127.0.0.1:{PORT}/ws"  # TestClient ใช้ host "testserver" ถ้าไม่ใส่ URL เต็ม


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


def _ws_client(extra_origins=()) -> TestClient:
    app = FastAPI()

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept()
        await websocket.send_text("hi")
        await websocket.close()

    app.add_middleware(LocalOnlyMiddleware, port=PORT, token=TOKEN, extra_origins=extra_origins)
    return TestClient(app, base_url=BASE)


def _assert_ws_rejected(headers: dict) -> None:
    with pytest.raises(WebSocketDisconnect) as info, _ws_client().websocket_connect(WS_URL, headers=headers):
        pass
    assert info.value.code == 1008


def test_websocket_with_allowed_host_and_origin_accepted():
    with _ws_client().websocket_connect(WS_URL, headers={"origin": BASE}) as ws:
        assert ws.receive_text() == "hi"


def test_websocket_without_origin_rejected():
    _assert_ws_rejected({})


def test_websocket_with_foreign_origin_rejected():
    _assert_ws_rejected({"origin": "https://evil.example"})


def test_websocket_with_foreign_host_rejected():
    _assert_ws_rejected({"origin": BASE, "host": "evil.example:8787"})


def _call_raw(scope: dict) -> tuple[list, list]:
    """เรียก middleware ตรง ๆ คืน (ข้อความที่ส่งออก, scope ที่ถึง app)"""
    sent, reached = [], []

    async def app(scope, receive, send):
        reached.append(scope)

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        sent.append(message)

    asyncio.run(LocalOnlyMiddleware(app, port=PORT, token=TOKEN)(scope, receive, send))
    return sent, reached


def test_websocket_rejection_never_calls_app():
    scope = {"type": "websocket", "headers": [(b"host", b"127.0.0.1:8787"), (b"origin", b"https://evil.example")]}
    sent, reached = _call_raw(scope)
    assert reached == []
    assert sent == [{"type": "websocket.close", "code": 1008}]


def test_lifespan_scope_passes_through():
    scope = {"type": "lifespan"}
    sent, reached = _call_raw(scope)
    assert reached == [scope]
    assert sent == []


def _post_scope(headers: list[tuple[bytes, bytes]]) -> dict:
    return {"type": "http", "method": "POST", "headers": headers}


HOST = (b"host", b"127.0.0.1:8787")
ORIGIN = (b"origin", BASE.encode())
GOOD_TOKEN = (b"x-toolkit-token", TOKEN.encode())


def test_raw_post_with_single_headers_allowed():
    sent, reached = _call_raw(_post_scope([HOST, ORIGIN, GOOD_TOKEN]))
    assert sent == [] and len(reached) == 1


def test_duplicate_host_rejected_with_421():
    sent, reached = _call_raw(_post_scope([(b"host", b"evil.example"), HOST, ORIGIN, GOOD_TOKEN]))
    assert reached == []
    assert sent[0]["status"] == 421


def test_duplicate_origin_rejected_with_403():
    sent, reached = _call_raw(_post_scope([HOST, (b"origin", b"https://evil.example"), ORIGIN, GOOD_TOKEN]))
    assert reached == []
    assert sent[0]["status"] == 403


def test_duplicate_token_rejected_with_403():
    sent, reached = _call_raw(_post_scope([HOST, ORIGIN, (b"x-toolkit-token", b"guess"), GOOD_TOKEN]))
    assert reached == []
    assert sent[0]["status"] == 403


def test_duplicate_origin_rejected_even_on_get():
    scope = {"type": "http", "method": "GET", "headers": [HOST, ORIGIN, ORIGIN]}
    sent, reached = _call_raw(scope)
    assert reached == []
    assert sent[0]["status"] == 403
