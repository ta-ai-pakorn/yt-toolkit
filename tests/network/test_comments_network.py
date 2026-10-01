"""คอมเมนต์ปักหมุดจากยูทูปจริง (byUploader = true สำหรับคลิปที่เจ้าของช่องปักหมุดเอง) (C-A2, owner round 2)

รันเองด้วย: uv run pytest -m network -q tests/network/test_comments_network.py -s
id ของคลิปอยู่ใน tests/network_videos.toml ([comments]) ยิงยูทูปครั้งเดียว (~2 คำขอ innertube "next")
ยูทูปตอบ 429 หรือขอยืนยันว่าไม่ใช่บอท (E_BOT_CHECK) = เทสตก ให้รายงานผล ห้ามลองซ้ำเป็นลูป
"""

from __future__ import annotations

import time
import tomllib
from pathlib import Path

import pytest

from yttoolkit.core import extractor as extractor_mod
from yttoolkit.core.extractor import YtDlpExtractor, ytdlp_version

pytestmark = pytest.mark.network

_TOML = Path(__file__).resolve().parents[1] / "network_videos.toml"
PINNED = tomllib.loads(_TOML.read_text(encoding="utf-8"))["comments"]["uploader_pinned"]


def test_uploader_pinned_comment_via_the_cheap_path(monkeypatch: pytest.MonkeyPatch) -> None:
    ytdlp_version()  # ไม่นับเวลา import
    fallback_used: list[str] = []
    original = extractor_mod._first_comment_public

    def record(ydl: object, video_id: str) -> dict | None:
        fallback_used.append(video_id)
        return original(ydl, video_id)

    first_flags: list[dict] = []
    direct = extractor_mod._first_comment_direct

    def peek(ydl: object, video_id: str) -> dict | None:
        # บันทึกแค่ธงของคอมเมนต์แรก (ไม่เก็บข้อความ/ผู้เขียน) ไว้ดูว่าทำไมได้ None
        first = direct(ydl, video_id)
        first_flags.append(
            {k: first.get(k) for k in ("is_pinned", "author_is_uploader")} if first else {"first": None}
        )
        return first

    monkeypatch.setattr(extractor_mod, "_first_comment_public", record)
    monkeypatch.setattr(extractor_mod, "_first_comment_direct", peek)
    ex = YtDlpExtractor()
    start = time.monotonic()
    try:
        comment = ex.pinned_comment(PINNED)
    finally:
        ex.close()
    elapsed = time.monotonic() - start
    print(
        f"pinned comment {PINNED}: {elapsed:.2f}s, fallback={bool(fallback_used)}, "
        f"found={comment is not None}, byUploader={comment.get('byUploader') if comment else None}, "
        f"keys={sorted(comment) if comment else None}, chars={len(comment['text']) if comment else 0}, "
        f"first={first_flags}"
    )
    assert not fallback_used, "ทางหลัก (API ภายในของ yt-dlp) ใช้ไม่ได้แล้ว ต้องถอยไป probe"
    assert comment is not None, "ไม่พบคอมเมนต์ปักหมุดของเจ้าของช่อง (คลิปอาจเลิกปักหมุดแล้ว เลือกคลิปใหม่)"
    assert set(comment) <= {"text", "likes", "publishedText", "byUploader"}
    assert comment["byUploader"] is True, "คลิป uploader_pinned ต้องเป็นปักหมุดของเจ้าของช่อง"
    assert comment["text"].strip()
