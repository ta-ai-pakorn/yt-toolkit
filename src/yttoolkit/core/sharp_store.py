"""ภาพคมใน cache ของแอพ (M5 รอบ B spec 5): หนึ่งชุดต่อคลิป สลับชุดแบบ atomic

โครง: <cache_root>/<video_id>/sharp/{index.json, f_0000.jpg, ...}
index.json = {"origin": "manual"|"auto", "intervalMs": int|null, "frames": [{"index","tMs","file"}], "createdAt"}
สร้างใน sharp.tmp-<jobId>/ ก่อน แล้วสลับ: sharp/ -> sharp.old-<jobId>/ · tmp -> sharp/ · ลบ old
ยกเลิกหรือดับก่อนสลับ = ชุดเดิมอยู่ครบ · ดับระหว่างสองขั้น = sweep_sharp_leftovers คืนชุดเดิมตอนเปิดโปรแกรม
ล้าง cache 30 วัน (db.purge_stale_cache) ลบทั้งโฟลเดอร์ของคลิปอยู่แล้ว · ไม่ import api/platform ไม่แตะเครือข่าย
"""

from __future__ import annotations

import errno
import json
import logging
import re
import shutil
import threading
import time
from collections.abc import Sequence
from pathlib import Path

from .inputs import VIDEO_ID
from .storyboard import frame_file_name
from .yterrors import YtError

log = logging.getLogger("yttoolkit")

FOLDER = "sharp"
INDEX = "index.json"
TMP_PREFIX = "sharp.tmp-"
OLD_PREFIX = "sharp.old-"
ORIGINS = ("manual", "auto")
# Windows: เปลี่ยนชื่อโฟลเดอร์ไม่ได้ชั่วครู่ระหว่างที่เบราว์เซอร์ยังอ่านภาพในโฟลเดอร์อยู่ ลองซ้ำได้ราว 2 วินาที
RENAME_ATTEMPTS = 20
RENAME_WAIT_S = 0.1
_JOB_ID = re.compile(r"[A-Za-z0-9-]{1,64}")
_FRAME_FILE = re.compile(r"f_\d{4,}\.jpg")

_guard = threading.Lock()
_locks: dict[str, threading.Lock] = {}


class ManualSetKept(Exception):
    """commit_sharp(keep_manual=True) เจอชุดที่ผู้ใช้ขอเองอยู่ในที่: ไม่สลับ ทิ้งชุดที่เตรียมไว้ (ขั้นอัตโนมัติ D6)"""


def _lock_for(video_id: str) -> threading.Lock:
    with _guard:
        return _locks.setdefault(video_id, threading.Lock())


def _clip_dir(cache_root: Path, video_id: str) -> Path:
    if not VIDEO_ID.fullmatch(video_id):
        raise ValueError(f"bad video id: {video_id!r}")
    return Path(cache_root) / video_id


def _valid(data: object, folder: Path) -> bool:
    if not isinstance(data, dict) or data.get("origin") not in ORIGINS or not isinstance(data.get("createdAt"), str):
        return False
    interval = data.get("intervalMs")
    if interval is not None and (type(interval) is not int or interval <= 0):
        return False
    frames = data.get("frames")
    if not isinstance(frames, list) or not frames:
        return False
    for frame in frames:
        if not isinstance(frame, dict):
            return False
        name = frame.get("file")
        if type(frame.get("index")) is not int or type(frame.get("tMs")) is not int or frame["tMs"] < 0:
            return False
        if not (isinstance(name, str) and _FRAME_FILE.fullmatch(name) and (folder / name).is_file()):
            return False
    return True


def _read_folder(folder: Path) -> dict | None:
    """index ของโฟลเดอร์ชุดภาพคม ถ้าอ่านได้และผ่าน _valid · ไม่งั้น None (กฎเดียวกับ read_sharp และตอนกู้ชุดเดิม)"""
    try:
        data = json.loads((folder / INDEX).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if _valid(data, folder) else None


def read_sharp(cache_root: Path, video_id: str) -> dict | None:
    """ชุดภาพคมของคลิป ไม่มี / index เสีย / ไฟล์ภาพหาย / id ผิดรูปแบบ = None"""
    if not VIDEO_ID.fullmatch(video_id):
        return None
    return _read_folder(Path(cache_root) / video_id / FOLDER)


def prepare_sharp(
    cache_root: Path,
    video_id: str,
    job_id: str,
    frames: Sequence[tuple[int, Path]],
    *,
    origin: str,
    interval_ms: int | None,
    created_at: str,
) -> Path:
    """คัดลอกภาพ (tMs, ไฟล์) เป็น f_0000.jpg ... พร้อม index.json ลง sharp.tmp-<jobId>/ (ยังไม่มีใครเห็น)"""
    if not frames:
        raise ValueError("no frames")
    if origin not in ORIGINS:
        raise ValueError(f"bad origin: {origin!r}")
    if not _JOB_ID.fullmatch(job_id):
        raise ValueError(f"bad job id: {job_id!r}")
    # กฎเดียวกับ _valid: ชุดที่อ่านกลับไม่ได้ต้องไม่เคยถูกสลับเข้าไปแทนชุดเดิม
    if interval_ms is not None and (type(interval_ms) is not int or interval_ms <= 0):
        raise ValueError(f"bad interval: {interval_ms!r}")
    if not isinstance(created_at, str):
        raise ValueError("bad createdAt")
    if any(type(t_ms) is not int or t_ms < 0 for t_ms, _src in frames):
        raise ValueError("bad frame time")
    staged = _clip_dir(cache_root, video_id) / f"{TMP_PREFIX}{job_id}"
    shutil.rmtree(staged, ignore_errors=True)
    try:
        staged.mkdir(parents=True)
        entries = []
        for index, (t_ms, src) in enumerate(frames):
            name = frame_file_name(index)
            shutil.copyfile(src, staged / name)
            entries.append({"index": index, "tMs": int(t_ms), "file": name})
        doc = {"origin": origin, "intervalMs": interval_ms, "frames": entries, "createdAt": created_at}
        (staged / INDEX).write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    except OSError as err:
        shutil.rmtree(staged, ignore_errors=True)
        code = "E_DISK_FULL" if err.errno == errno.ENOSPC else "E_UNKNOWN"
        raise YtError(code, f"prepare sharp set: {type(err).__name__}") from err
    except BaseException:
        shutil.rmtree(staged, ignore_errors=True)
        raise
    return staged


def _rename(src: Path, dst: Path) -> None:
    for attempt in range(RENAME_ATTEMPTS):
        try:
            src.rename(dst)
            return
        except PermissionError:
            if attempt == RENAME_ATTEMPTS - 1:
                raise
            time.sleep(RENAME_WAIT_S)


def commit_sharp(cache_root: Path, video_id: str, staged: Path, *, keep_manual: bool = False) -> dict:
    """สลับชุดที่เตรียมไว้เข้าที่ (แทนชุดเดิม D5) พลาด = คืนชุดเดิม ทิ้งชุดใหม่ แล้ว E_UNKNOWN
    keep_manual=True (ขั้นอัตโนมัติ): ชุดในที่เป็นของผู้ใช้ (origin "manual") = ทิ้งชุดใหม่แล้ว ManualSetKept
    เช็กใต้ล็อกเดียวกับการสลับ งานมือที่สลับเข้ามาระหว่างขั้นอัตโนมัติกำลังดึงภาพจึงไม่ถูกแทน"""
    clip = _clip_dir(cache_root, video_id)
    staged = Path(staged)
    if staged.parent != clip or not staged.name.startswith(TMP_PREFIX):
        raise ValueError(f"not a staged sharp set: {staged.name}")
    try:
        staged_ok = _valid(json.loads((staged / INDEX).read_text(encoding="utf-8")), staged)
    except (OSError, ValueError):
        staged_ok = False
    if not staged_ok:
        discard_sharp(staged)
        raise YtError("E_UNKNOWN", "staged sharp set is not valid")
    target = clip / FOLDER
    old = clip / f"{OLD_PREFIX}{staged.name[len(TMP_PREFIX):]}"
    with _lock_for(video_id):
        if keep_manual and (current := read_sharp(cache_root, video_id)) is not None and current["origin"] == "manual":
            discard_sharp(staged)
            raise ManualSetKept(video_id)
        moved_old = False
        try:
            if target.exists():
                _rename(target, old)
                moved_old = True
            _rename(staged, target)
        except OSError as exc:
            if moved_old and not target.exists():
                try:
                    _rename(old, target)
                except OSError as back:
                    log.warning("คืนชุดภาพคมเดิมไม่ได้ (%s) รอให้เปิดโปรแกรมรอบหน้าคืนให้", type(back).__name__)
            discard_sharp(staged)
            raise YtError("E_UNKNOWN", f"swap sharp set: {type(exc).__name__}") from exc
        if moved_old:
            shutil.rmtree(old, ignore_errors=True)
    index = read_sharp(cache_root, video_id)
    if index is None:
        raise YtError("E_UNKNOWN", "sharp set unreadable after the swap")
    return index


def discard_sharp(staged: Path) -> None:
    shutil.rmtree(staged, ignore_errors=True)


def sweep_sharp_leftovers(cache_root: Path) -> int:
    """ตอนเปิดโปรแกรม (ยังไม่มีงานรัน): ลบ sharp.tmp-* · sharp.old-* คืนเป็น sharp/ ถ้า sharp/ หายไป (ดับกลางการสลับ)
    และชุดนั้นผ่าน _valid (กฎเดียวกับตอนอ่าน) ตัวที่ใช้ไม่ได้ถูกลบแล้วลองตัวถัดไป ไม่งั้นลบ · คืนจำนวนโฟลเดอร์ที่จัดการ"""
    try:
        clips = [p for p in Path(cache_root).iterdir() if p.is_dir()]
    except OSError:
        return 0
    count = 0
    for clip in clips:
        try:
            children = sorted(p for p in clip.iterdir() if p.is_dir())
        except OSError:
            continue
        target = clip / FOLDER
        for child in children:
            if child.name.startswith(TMP_PREFIX):
                shutil.rmtree(child, ignore_errors=True)
                count += 1
            elif child.name.startswith(OLD_PREFIX):
                if not target.exists() and _read_folder(child) is not None:
                    try:
                        child.rename(target)
                        count += 1
                        continue
                    except OSError:
                        pass
                shutil.rmtree(child, ignore_errors=True)
                count += 1
    return count
