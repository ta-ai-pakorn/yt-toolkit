"""สถิติของฉัน (M6 รอบ C spec §1, BRD FR-STAT-1..4, PRD :625)

คำนวณจากตาราง jobs ในเครื่องทุกครั้งที่เรียก ไม่มี network ไม่แตะไฟล์ (C1)
ผลมีแค่ตัวเลข ชนิด เดือน และเวลาเริ่มนับ ไม่มีชื่อคลิปหรือ path (C2) · แถวเสียข้ามเงียบ ๆ (C6)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .db import Database

# เวลาไทยคงที่ (ไม่มี DST) ใช้จัดเดือน ไม่ขึ้นกับเขตเวลาของเครื่อง (C5, AC-STAT-01)
THAI = timezone(timedelta(hours=7))

# ชนิดผลลัพธ์ (core/jobs.OutputFile.kind) → 4 กลุ่มของ BRD (Pete Q1 = A) · ชนิดอื่นไม่นับ
KIND_GROUP = {
    "video": "video",
    "audio": "audio",
    "subtitle": "subtitle",
    "note": "subtitle",
    "image": "image",
    "archive": "image",
    "folder": "image",  # โฟลเดอร์ภาพคม = 1 ไฟล์ ขนาดทั้งโฟลเดอร์
}
GROUP_ORDER = ("video", "audio", "subtitle", "image")
MONTHS = 12


def _parse(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    aware = parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    try:  # ปี 9999 / ปี 1 แปลงเขตเวลาแล้วล้นได้ = ถือเป็นเวลาที่อ่านไม่ได้ (C6)
        aware.astimezone(THAI)
        aware.astimezone(UTC)
    except (OverflowError, ValueError):
        return None
    return aware


def _outputs(raw: object) -> list[tuple[str, int]]:
    """(กลุ่ม, ไบต์) ของแต่ละผลลัพธ์ที่นับได้ · JSON เสีย/ไม่ใช่ list = ไม่มีไฟล์"""
    if not isinstance(raw, str):
        return []
    try:
        items = json.loads(raw)
    except ValueError:
        return []
    if not isinstance(items, list):
        return []
    counted: list[tuple[str, int]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        group = KIND_GROUP.get(kind) if isinstance(kind, str) else None
        if group is None:
            continue
        size = item.get("sizeBytes")
        ok = isinstance(size, int) and not isinstance(size, bool) and size >= 0
        counted.append((group, size if ok else 0))  # type: ignore[arg-type]
    return counted


def _month_key(moment: datetime) -> str:
    local = moment.astimezone(THAI)
    return f"{local.year:04d}-{local.month:02d}"


def _window(now: datetime) -> list[str]:
    local = now.astimezone(THAI)
    year, month = local.year, local.month
    keys: list[str] = []
    for _ in range(MONTHS):
        keys.append(f"{year:04d}-{month:02d}")
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    return keys


def compute(db: Database, since: object, now: datetime) -> dict[str, Any]:
    start = _parse(since)
    rows = db.execute("SELECT video_id, finished_at, outputs_json FROM jobs WHERE status = 'done'")
    clips: set[str] = set()
    files = 0
    total = 0
    kinds: dict[str, list[int]] = {}
    months: dict[str, dict[str, Any]] = {}
    window = set(_window(now))
    for row in rows:
        finished = _parse(row["finished_at"])
        if finished is None or (start is not None and finished < start):
            continue
        video = str(row["video_id"])
        outputs = _outputs(row["outputs_json"])
        clips.add(video)
        files += len(outputs)
        total += sum(size for _, size in outputs)
        for group, size in outputs:
            entry = kinds.setdefault(group, [0, 0])
            entry[0] += 1
            entry[1] += size
        key = _month_key(finished)
        if key in window:
            month = months.setdefault(key, {"clips": set(), "files": 0, "bytes": 0})
            month["clips"].add(video)
            month["files"] += len(outputs)
            month["bytes"] += sum(size for _, size in outputs)
    by_kind = sorted(
        ({"kind": k, "files": v[0], "bytes": v[1]} for k, v in kinds.items()),
        key=lambda item: (-item["files"], -item["bytes"], GROUP_ORDER.index(item["kind"])),
    )
    by_month = [
        {"month": key, "clips": len(m["clips"]), "files": m["files"], "bytes": m["bytes"]}
        for key, m in sorted(months.items(), reverse=True)
    ]
    return {
        "since": since if start is not None else None,
        "clips": len(clips),
        "files": files,
        "totalBytes": total,
        "byKind": by_kind,
        "byMonth": by_month,
    }
