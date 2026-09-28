"""เสิร์ฟหน้าเว็บที่ build แล้ว (web/dist) และฝัง token ลงใน index.html"""

from __future__ import annotations

import html
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse


def inject_token(index_html: str, token: str) -> str:
    meta = f'<meta name="yt-token" content="{html.escape(token, quote=True)}">'
    return index_html.replace("</head>", f"{meta}</head>", 1)


def mount_web(app: FastAPI, dist: Path, token: str) -> None:
    root = dist.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        index = root / "index.html"
        if not index.is_file():
            return PlainTextResponse("ยังไม่ได้ build หน้าเว็บ (web/dist)", status_code=503)
        if full_path:
            candidate = (root / full_path).resolve()
            if candidate.is_relative_to(root) and candidate.is_file():
                return FileResponse(candidate)
        page = inject_token(index.read_text(encoding="utf-8"), token)
        return HTMLResponse(page, headers={"Cache-Control": "no-store"})
