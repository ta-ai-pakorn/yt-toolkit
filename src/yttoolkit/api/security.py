"""ป้องกันไม่ให้เว็บอื่นหรือเครื่องอื่นสั่งงานแอพ (NFR-SEC-1..3)"""

from __future__ import annotations

import json
import secrets
from collections.abc import Iterable

from .errors import error_body

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
FORBIDDEN_MESSAGE = "คำขอนี้ไม่ได้รับอนุญาต ลองรีเฟรชหน้าเว็บ"
_CHECKED_HEADERS = ("host", "origin", "x-toolkit-token")
_FETCH_SITE = "sec-fetch-site"
# เบราว์เซอร์บอกว่าคำขอมาจากเว็บอื่น (เช่น <img src=".../api/videos/...?refresh=1">) GET ของ /api
# บางตัวมีผลข้างเคียง (probe ยูทูป เขียนประวัติ ทำภาพ) จึงปฏิเสธทุก method
# ไม่มี header นี้ (curl, CLI, เบราว์เซอร์เก่า) หรือเป็น same-origin / none (พิมพ์ URL เอง) ผ่านได้
_FOREIGN_FETCH_SITES = frozenset({"cross-site", "same-site"})
WS_POLICY_VIOLATION = 1008


class LocalOnlyMiddleware:
    def __init__(self, app, *, port: int, token: str, extra_origins: Iterable[str] = ()) -> None:
        self.app = app
        self._token = token.encode("latin-1")
        self._hosts = frozenset({f"127.0.0.1:{port}", f"localhost:{port}"})
        self._origins = frozenset({f"http://{h}" for h in self._hosts} | set(extra_origins))

    async def __call__(self, scope, receive, send) -> None:
        kind = scope["type"]
        if kind not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        status = self._reject_status(scope)
        if status is None:
            await self.app(scope, receive, send)
        elif kind == "websocket":
            # ปิดก่อน accept เซิร์ฟเวอร์จะตอบ handshake เป็น 403 และ app ไม่ถูกเรียกเลย
            await send({"type": "websocket.close", "code": WS_POLICY_VIOLATION})
        else:
            await _send_json(send, status)

    def _reject_status(self, scope) -> int | None:
        """คืน status ที่ต้องปฏิเสธ หรือ None ถ้าผ่าน"""
        headers = _collect_headers(scope["headers"])
        # header ซ้ำอาจทำให้ส่วนต่าง ๆ อ่านคนละค่ากัน จึงปฏิเสธเลย ไม่ใช้ค่าสุดท้าย
        host = headers.get("host", [])
        if len(host) != 1 or host[0] not in self._hosts:
            return 421
        if any(len(headers.get(name, [])) > 1 for name in _CHECKED_HEADERS):
            return 403
        if scope["type"] == "http" and _is_api_path(scope.get("path", "")):
            fetch_site = headers.get(_FETCH_SITE, [])
            if len(fetch_site) > 1 or (fetch_site and fetch_site[0].strip().lower() in _FOREIGN_FETCH_SITES):
                return 403
        origin = headers.get("origin", [None])[0]
        if scope["type"] == "websocket":
            return None if origin in self._origins else 403
        if scope["method"] not in SAFE_METHODS:
            origin_ok = origin in self._origins
            token = headers.get("x-toolkit-token", [""])[0]
            token_ok = secrets.compare_digest(token.encode("latin-1"), self._token)
            if not (origin_ok and token_ok):
                return 403
        return None


def _is_api_path(path: str) -> bool:
    return path == "/api" or path.startswith("/api/")


def _collect_headers(raw: Iterable[tuple[bytes, bytes]]) -> dict[str, list[str]]:
    headers: dict[str, list[str]] = {}
    for key, value in raw:
        name = key.decode("latin-1").lower()
        if name in _CHECKED_HEADERS or name == _FETCH_SITE:
            headers.setdefault(name, []).append(value.decode("latin-1"))
    return headers


async def _send_json(send, status: int) -> None:
    body = json.dumps(error_body("E_FORBIDDEN", FORBIDDEN_MESSAGE), ensure_ascii=False).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
