"""ป้องกันไม่ให้เว็บอื่นหรือเครื่องอื่นสั่งงานแอพ (NFR-SEC-1..3)"""

from __future__ import annotations

import json
import secrets
from collections.abc import Iterable

from .errors import error_body

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
FORBIDDEN_MESSAGE = "คำขอนี้ไม่ได้รับอนุญาต ลองรีเฟรชหน้าเว็บ"


class LocalOnlyMiddleware:
    def __init__(self, app, *, port: int, token: str, extra_origins: Iterable[str] = ()) -> None:
        self.app = app
        self._token = token.encode("latin-1")
        self._hosts = frozenset({f"127.0.0.1:{port}", f"localhost:{port}"})
        self._origins = frozenset({f"http://{h}" for h in self._hosts} | set(extra_origins))

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        if headers.get("host") not in self._hosts:
            await _send_json(send, 421)
            return
        if scope["method"] not in SAFE_METHODS:
            origin_ok = headers.get("origin") in self._origins
            token_ok = secrets.compare_digest(headers.get("x-toolkit-token", "").encode("latin-1"), self._token)
            if not (origin_ok and token_ok):
                await _send_json(send, 403)
                return
        await self.app(scope, receive, send)


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
