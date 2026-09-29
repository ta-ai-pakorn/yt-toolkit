"""เสิร์ฟหน้าเว็บที่ build แล้ว (web/dist) และฝัง token ลงใน index.html"""

from __future__ import annotations

import html
import os
from pathlib import Path, PurePosixPath

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse


def inject_token(index_html: str, token: str) -> str:
    meta = f'<meta name="yt-token" content="{html.escape(token, quote=True)}">'
    return index_html.replace("</head>", f"{meta}</head>", 1)


def _safe_parts(full_path: str) -> tuple[str, ...] | None:
    """ตรวจ path แบบไม่แตะดิสก์ คืน None ถ้าอาจหลุดออกนอก dist

    ห้ามส่ง path ที่ผู้ใช้ส่งมาเข้า resolve()/is_file() ตรงๆ เพราะบน Windows
    path แบบ UNC (ขึ้นต้นด้วย backslash สองตัว) จะทำให้เครื่องไปต่อ SMB และหลุด NTLM hash
    """
    if any(ch in full_path for ch in ("\\", ":", "\x00")) or full_path.startswith("/"):
        return None
    parts = tuple(p for p in PurePosixPath(full_path).parts if p not in ("", "."))
    if not parts or ".." in parts:
        return None
    return parts


def _same_file(a: Path, b: Path) -> bool:
    """บน Windows ชื่ออย่าง "index.html." หรือชื่อย่อ 8.3 ก็ชี้ไปที่ index.html ได้ ต้องเทียบที่ตัวไฟล์"""
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def mount_web(app: FastAPI, dist: Path, token: str) -> None:
    root = dist.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        index = root / "index.html"
        if not index.is_file():
            return PlainTextResponse("ยังไม่ได้ build หน้าเว็บ (web/dist)", status_code=503)
        parts = _safe_parts(full_path)
        # index.html ตัวดิบไม่มี token ต้องเสิร์ฟตัวที่ฝัง token แล้วเสมอ
        if parts and [p.lower() for p in parts] != ["index.html"]:
            candidate = root.joinpath(*parts)
            if candidate.is_file() and not _same_file(candidate, index):
                return FileResponse(candidate)
        page = inject_token(index.read_text(encoding="utf-8"), token)
        return HTMLResponse(page, headers={"Cache-Control": "no-store"})
