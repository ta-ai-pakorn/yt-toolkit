"""ภาพเฟรมโหมดเร็ว: เลือก storyboard ที่ใหญ่สุดของยูทูป โหลดแผ่น grid พร้อมกัน แล้วตัดเป็นเฟรมเดี่ยว
พร้อม timecode และเก็บ cache ไว้ต่อคลิป (PRD FR-FRAME, AC-FRAME-01/02)

ไม่ import api/platform (PRD 6.6) และไม่แตะเครือข่ายเอง: ผู้เรียกส่งฟังก์ชัน `fetch` เข้ามา
โครงโฟลเดอร์: <cache_root>/<video_id>/storyboard/{index.json, f_0000.jpg, ...}
"""

from __future__ import annotations

import io
import json
import re
import shutil
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image

from .inputs import VIDEO_ID
from .yterrors import YtError

if TYPE_CHECKING:
    from .videos import VideoService

FOLDER = "storyboard"
INDEX = "index.json"
JPEG_QUALITY = 90
_STORYBOARD = "storyboard"
_TRAILING_NUMBER = re.compile(r"(\d+)$")
_FRAME_FILE = re.compile(r"f_\d{4,}\.jpg")

Fetch = Callable[[str], bytes]


@dataclass(frozen=True)
class FrameSpec:
    index: int
    fragment: int  # ลำดับแผ่น grid ใน sb["fragments"]
    cell: int  # ลำดับช่องในแผ่น (นับจากซ้ายบน ไล่ทีละแถว)
    t_ms: int


def _positive(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and value > 0


def _usable(fmt: Any) -> bool:
    return (
        isinstance(fmt, dict)
        and fmt.get("format_note") == _STORYBOARD
        and bool(fmt.get("fragments"))
        and all(
            _positive(fmt.get(k)) for k in ("width", "height", "rows", "columns", "fps")
        )
    )


def _format_number(fmt: dict) -> int:
    found = _TRAILING_NUMBER.search(str(fmt.get("format_id") or ""))
    return int(found.group(1)) if found else 10**9


def pick_storyboard(raw: dict) -> dict | None:
    """storyboard ที่ width × height ใหญ่สุด เท่ากันเลือก format_id เลขน้อยสุด (sb0)"""
    candidates = [f for f in (raw.get("formats") or []) if _usable(f)]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda f: (
            -(f["width"] * f["height"]),
            _format_number(f),
            str(f.get("format_id")),
        ),
    )


def interval_ms(sb: dict) -> int:
    return round(1000 / sb["fps"])


def plan_frames(sb: dict, duration_s: float | None) -> list[FrameSpec]:
    """เฟรมทั้งหมดที่ควรมี: เฟรมที่ i อยู่ที่ i × ช่วงห่าง และตัดช่องว่างท้าย grid ที่เกินความยาวคลิป"""
    step = interval_ms(sb)
    capacity = int(sb["rows"]) * int(sb["columns"])
    limit_ms = duration_s * 1000 if _positive(duration_s) else None
    frames: list[FrameSpec] = []
    for fragment_no, fragment in enumerate(sb["fragments"]):
        length = fragment.get("duration")
        count = round(length * sb["fps"]) if _positive(length) else capacity
        for cell in range(min(capacity, count)):
            index = len(frames)
            t_ms = index * step
            if limit_ms is not None and t_ms > limit_ms:
                return frames
            frames.append(FrameSpec(index, fragment_no, cell, t_ms))
    return frames


# ---------- สร้างและเก็บ cache ----------

# ล็อกนี้ใช้ได้ในโปรเซสเดียวเท่านั้น: ดีไซน์นี้สมมติว่ามีแอพรันอยู่โปรเซสเดียวต่อโฟลเดอร์ cache
# (ถ้ามีสองโปรเซสสร้างพร้อมกัน ตัวที่เปลี่ยนชื่อทีหลังจะเห็นผลของตัวแรกแล้วใช้ต่อ ดู build)
_guard = threading.Lock()
_locks: dict[Path, threading.Lock] = {}


def _lock_for(target: Path) -> threading.Lock:
    with _guard:
        return _locks.setdefault(target, threading.Lock())


def _check_video_id(video_id: str) -> None:
    if not VIDEO_ID.fullmatch(video_id):
        raise YtError("E_INVALID_INPUT", f"video id ไม่ถูกรูปแบบ: {video_id!r}")


def _read_index(target: Path) -> dict | None:
    """index ที่สมบูรณ์ในโฟลเดอร์ cache หรือ None (ไม่มี/เสีย/ไฟล์เฟรมหายไป = สร้างใหม่)"""
    try:
        data = json.loads((target / INDEX).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not (
        isinstance(data, dict)
        and isinstance(data.get("intervalMs"), int)
        and isinstance(data.get("frames"), list)
    ):
        return None
    for frame in data["frames"]:
        name = frame.get("file") if isinstance(frame, dict) else None
        if not (
            isinstance(name, str)
            and _FRAME_FILE.fullmatch(name)
            and (target / name).is_file()
        ):
            return None
    return data


def _open_grid(data: bytes, url: str) -> Image.Image:
    try:
        grid = Image.open(io.BytesIO(data))
        grid.load()
    except Exception as exc:  # Pillow โยนได้หลายชนิด (OSError, SyntaxError, bomb ฯลฯ)
        raise YtError("E_NETWORK", f"แผ่นภาพเสีย ({type(exc).__name__}): {url}") from exc
    return grid


def _crop_fragment(
    sb: dict,
    fragment_no: int,
    specs: list[FrameSpec],
    fetch: Fetch,
    out_dir: Path,
) -> None:
    url = sb["fragments"][fragment_no]["url"]
    grid = _open_grid(fetch(url), url)
    width, height, columns = int(sb["width"]), int(sb["height"]), int(sb["columns"])
    with grid:
        for spec in specs:
            left = (spec.cell % columns) * width
            top = (spec.cell // columns) * height
            if left + width > grid.width or top + height > grid.height:
                raise YtError(
                    "E_NETWORK",
                    f"แผ่นภาพเล็กกว่าที่ควร ({grid.width}x{grid.height}): {url}",
                )
            cell = grid.crop((left, top, left + width, top + height)).convert("RGB")
            cell.save(out_dir / _file_name(spec.index), "JPEG", quality=JPEG_QUALITY)


def _file_name(index: int) -> str:
    return f"f_{index:04d}.jpg"


def _build_into(
    out_dir: Path, sb: dict, frames: list[FrameSpec], fetch: Fetch, max_workers: int
) -> dict:
    by_fragment: dict[int, list[FrameSpec]] = {}
    for spec in frames:
        by_fragment.setdefault(spec.fragment, []).append(spec)
    executor = ThreadPoolExecutor(max_workers=max(1, max_workers))
    try:
        futures = [
            executor.submit(_crop_fragment, sb, no, specs, fetch, out_dir)
            for no, specs in by_fragment.items()
        ]
        # พลาดแผ่นเดียวก็หยุดทั้งงาน: ไม่รอแผ่นที่เหลือ (finally จะยกเลิกแผ่นที่ยังไม่เริ่ม)
        done, _ = wait(futures, return_when=FIRST_EXCEPTION)
        for future in done:
            error = future.exception()
            if error is not None:
                raise error
    finally:
        # รอให้ worker ที่ทำอยู่หยุดก่อน ไม่งั้นลบโฟลเดอร์ชั่วคราวไม่ได้/มีไฟล์งอกใหม่
        executor.shutdown(wait=True, cancel_futures=True)
    index = {
        "intervalMs": interval_ms(sb),
        "frames": [
            {"index": s.index, "tMs": s.t_ms, "file": _file_name(s.index)}
            for s in frames
        ],
    }
    (out_dir / INDEX).write_text(
        json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    return index


def build(
    video_id: str,
    raw: dict,
    cache_dir: Path,
    fetch: Fetch,
    max_workers: int = 8,
) -> dict:
    """คืน {intervalMs, frames:[{index,tMs,file}]} ของคลิป (สร้างใน <cache_dir>/storyboard/ ถ้ายังไม่มี)

    สร้างในโฟลเดอร์ชั่วคราวข้างกันแล้วเปลี่ยนชื่อ จึงไม่มีวัน "ครึ่ง ๆ กลาง ๆ" ให้ใครเห็น
    เรียกซ้อนกันด้วยคลิปเดียวกัน = สร้างครั้งเดียว (ล็อกต่อคลิป) คนละคลิปสร้างพร้อมกันได้
    """
    _check_video_id(video_id)
    target = Path(cache_dir) / FOLDER
    cached = _read_index(target)
    if cached is not None:
        return cached
    with _lock_for(target):
        cached = _read_index(target)  # คนที่ถือล็อกก่อนหน้าอาจสร้างเสร็จแล้ว
        if cached is not None:
            return cached
        sb = pick_storyboard(raw)
        if sb is None:
            raise YtError("E_NO_STORYBOARD", f"คลิป {video_id} ไม่มี storyboard")
        frames = plan_frames(sb, raw.get("duration"))
        if not frames:
            raise YtError("E_NO_STORYBOARD", f"คลิป {video_id} ไม่มีเฟรมใน storyboard")
        parent = target.parent
        parent.mkdir(parents=True, exist_ok=True)
        for stale in parent.glob(f"{FOLDER}.tmp-*"):  # ซากจากรอบที่โปรเซสตายกลางคัน
            shutil.rmtree(stale, ignore_errors=True)
        tmp = parent / f"{FOLDER}.tmp-{uuid.uuid4().hex}"
        tmp.mkdir()
        try:
            index = _build_into(tmp, sb, frames, fetch, max_workers)
            if target.exists():  # โฟลเดอร์เก่าที่ index เสีย/ไฟล์เฟรมหาย
                try:
                    shutil.rmtree(target)
                except OSError as exc:  # Windows: ไฟล์ถูกเปิดค้างอยู่ ฯลฯ
                    raise YtError(
                        "E_UNKNOWN", f"ลบ cache เก่าไม่ได้ ({type(exc).__name__}): {exc}"
                    ) from exc
            try:
                tmp.rename(target)
            except OSError as exc:
                existing = _read_index(target)
                if existing is None:
                    raise YtError(
                        "E_UNKNOWN",
                        f"เปลี่ยนชื่อโฟลเดอร์ cache ไม่ได้ ({type(exc).__name__}): {exc}",
                    ) from exc
                # มีตัวอื่นสร้างเสร็จก่อนเรา (เช่นโปรเซสที่สอง) ใช้ผลของเขา
                shutil.rmtree(tmp, ignore_errors=True)
                return existing
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        return index


def get_storyboard(
    video_id: str, videos: VideoService, cache_root: Path, fetch: Fetch
) -> dict:
    """build จากข้อมูลดิบใน DB; ถ้าโหลดแผ่นพลาดด้วย E_NETWORK (ลิงก์เซ็นชื่อหมดอายุ)
    probe ใหม่หนึ่งครั้งแล้วลองอีกรอบเดียว ครั้งที่สองพลาดก็โยนต่อ (ไม่วนซ้ำ)"""
    _check_video_id(video_id)
    cache_dir = Path(cache_root) / video_id
    raw = videos.raw(video_id)  # ล้มตรงนี้ (probe ครั้งแรกพลาด) = ไม่ probe ซ้ำ
    try:
        return build(video_id, raw, cache_dir, fetch)
    except YtError as exc:
        if exc.code != "E_NETWORK":
            raise
    videos.get(video_id, refresh=True)
    return build(video_id, videos.raw(video_id), cache_dir, fetch)
