"""ถ่ายภาพคมตรงจุดที่ตัวเล่นอยู่ (M5 รอบ B2 spec 3.2): ไม่ผ่านคิว ถ่ายได้ครั้งละภาพทั้งแอพ

ไฟล์ของคลิปหนึ่ง:
- cache ของแอพ: <cache>/<id>/captures/c_<tMs>.jpg และ captures/index.json = {"captures": [entry, ...]}
  entry = {"id", "tMs", "width", "height", "file", "outputRoot", "outputRel", "createdAt"}
- โฟลเดอร์ผลลัพธ์: <output>/<โฟลเดอร์ของคลิป>/ภาพที่ถ่าย/frame_HH-MM-SS.jpg (วินาทีเดียวกัน _2, _3 ...)
ลำดับการเขียน: ไฟล์ใน cache → ไฟล์ในโฟลเดอร์ → แถวใน index (แถวมาหลังสุด: ไม่มีแถวไหนชี้ไฟล์ที่ยังไม่มี)
ไฟล์ชั่วคราวอยู่ใน work/capture-<uuid>/ ลบทุกครั้งที่จบ (ดับกลางทาง = ตัวกวาด work/ ตอนเปิดโปรแกรมลบให้)
log บอกแค่ id คลิป รหัส error และชนิด error (ไม่มี path ลิงก์ หรือ outputRoot) · core ไม่ import api/platform
detail ของ error จากงานไฟล์ = ชื่อชนิดของ error เดิมเท่านั้น และตัด error เดิมออกจากสาย (from None):
API log ทั้ง detail และ traceback ของ error 500 ซึ่งข้อความของ OSError/Pillow/ffmpeg มี path
"""

from __future__ import annotations

import errno
import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from PIL import Image, UnidentifiedImageError

from .account_scope import AccountGate, with_account_retry
from .cancel import JobCancelled
from .files import PATH_LIMIT, ensure_output_root, plan_output
from .frame_piece import PieceInfo, max_short_side
from .frames import file_timecode
from .inputs import VIDEO_ID
from .yterrors import YtError

log = logging.getLogger("yttoolkit")

CAPTURE_FOLDER = "captures"
CAPTURE_INDEX = "index.json"
OUTPUT_DIR = "ภาพที่ถ่าย"
CAPTURE_ID = re.compile(r"c_(\d{1,9})")
NO_FRAME_RETRY_MS = 100  # spec 4: เวลาเศษท้ายคลิปที่ไม่มีภาพ ลองถอยหลัง 100 ms อีกครั้งเดียว
# ดูจนจบคลิปแล้วกดถ่าย: เวลาของตัวเล่นเท่ากับหรือเลยความยาวที่ปัดเป็นวินาทีได้ (durationS ปัดขึ้นหรือลง)
# เวลาไม่ถึง ความยาว + END_SLACK_MS จึงไม่ปฏิเสธ แต่ถ่ายที่เวลาไม่เกิน ความยาว - END_STEP_MS
END_SLACK_MS = 1000
END_STEP_MS = 100
MAX_SAME_SECOND = 99
FFMPEG_DEADLINE_S = 60  # ffmpeg ของภาพหนึ่งภาพ (รวมรอบถอย 100 ms) นานกว่านี้ = ค้าง ยกเลิกแล้วปล่อยล็อก
_OUTPUT_NAME = re.compile(r"frame_\d{2,}-\d{2}-\d{2}(?:_\d{1,2})?\.jpg")
_LONGEST_NAME = "frame_000-00-00_99.jpg"
_BANGKOK = timezone(timedelta(hours=7))


class PieceFetcher(Protocol):
    def fetch_frame_piece(self, video_id: str, t_ms: int, max_short_side: int | None, dest: Path) -> PieceInfo: ...


class VideoLookup(Protocol):
    def get(self, video_id: str, refresh: bool = False, peek: bool = False) -> dict: ...
    def peek_cached(self, video_id: str) -> dict | None: ...


class FrameExtractor(Protocol):
    def available(self) -> bool: ...
    def extract_frame(self, src: Path, dst: Path, t_ms: int, *, long_side: int | None, dynamic_range: str | None,
                      cancel: Callable[[], bool]) -> bool: ...  # fmt: skip


class CaptureSettings(Protocol):
    def get(self) -> dict: ...
    def output_dir(self) -> Path: ...


class QueueBrake(Protocol):
    def pause_state(self) -> Any: ...  # PauseState(until, reason) | None
    def brake(self, reason: str = "E_BOT_CHECK") -> None: ...


class CaptureRejected(Exception):
    """คำขอที่ถ่ายไม่ได้เพราะตัวคำขอเอง (คลิปสด ไม่รู้ความยาว เวลานอกคลิป) API ตอบ 422 E_BAD_REQUEST"""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True)
class Capture:
    id: str
    t_ms: int
    width: int
    height: int
    file: str


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _u16(text: str) -> int:
    return len(text.encode("utf-16-le", errors="surrogatepass")) // 2


def _clock(moment: datetime) -> str:
    """เวลาแบบนาฬิกา HH:MM ของประเทศไทย (ข้อความ "ลองใหม่หลัง {time}")"""
    return moment.astimezone(_BANGKOK).strftime("%H:%M")


def _write_error(err: OSError) -> YtError:
    return YtError("E_DISK_FULL" if err.errno == errno.ENOSPC else "E_OUTPUT_NOT_WRITABLE", type(err).__name__)


def _entry_ok(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    match = CAPTURE_ID.fullmatch(str(entry.get("id")))
    t_ms = entry.get("tMs")
    return (
        match is not None
        and type(t_ms) is int
        and int(match.group(1)) == t_ms
        and entry.get("file") == f"c_{t_ms}.jpg"
        and all(type(entry.get(k)) is int and entry[k] > 0 for k in ("width", "height"))
        and all(isinstance(entry.get(k), str) for k in ("outputRoot", "outputRel", "createdAt"))
    )


def _to_capture(entry: Mapping[str, Any]) -> Capture:
    return Capture(str(entry["id"]), int(entry["tMs"]), int(entry["width"]), int(entry["height"]), str(entry["file"]))


def _is_link(path: Path) -> bool:
    try:
        return path.is_symlink() or path.is_junction()
    except OSError:
        return True


def _exact_name(folder: Path, name: str) -> bool:
    try:
        with os.scandir(folder) as entries:
            return any(entry.name == name for entry in entries)
    except OSError:
        return False


def recorded_output(root_text: str, rel: str) -> Path | None:
    """ไฟล์ในโฟลเดอร์ผลลัพธ์ตามที่บันทึกไว้ ถ้ายังเป็นไฟล์เดิมจริง: อยู่ใต้ root ที่บันทึก ชื่อตรงเป๊ะ ไม่ผ่านลิงก์ใด ๆ
    ไม่ผ่านเกณฑ์หรือไม่มีไฟล์แล้ว = None (ห้ามลบ/เปิดอย่างอื่น)
    root เป็นโฟลเดอร์ในเครือข่าย (\\\\server\\share) ได้: ค่าตั้งรับไว้ และ root มาจากที่แอพบันทึกเอง ไม่ใช่จากผู้ใช้
    การตรวจลิงก์และการอยู่ใต้ root ยังใช้เหมือนเดิมทุกข้อ"""
    if not root_text or "\x00" in root_text or "\x00" in rel or "\\" in rel or ":" in rel:
        return None
    root = Path(root_text)
    parts = PurePosixPath(rel).parts
    if not root.is_absolute() or PurePosixPath(rel).is_absolute() or any(p in ("", ".", "..") for p in parts):
        return None
    if len(parts) < 3 or parts[-2] != OUTPUT_DIR or not _OUTPUT_NAME.fullmatch(parts[-1]):
        return None
    current = root
    for part in parts:
        current = current / part
        if _is_link(current):
            return None
    try:
        real_root = root.resolve(strict=True)
        real = current.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if not real.is_relative_to(real_root) or not current.is_file() or not _exact_name(current.parent, parts[-1]):
        return None
    return current


class CaptureService:
    """C7: ถ่าย (capture) ดูรายการ (list) ลบ (delete) และหาโฟลเดอร์ที่ต้องเปิด (reveal_dir)"""

    def __init__(
        self,
        videos: VideoLookup,
        extractor: PieceFetcher,
        media: FrameExtractor,
        cache_root: Path,
        settings: CaptureSettings,
        queue: QueueBrake,
        *,
        work_root: Path,
        now: Callable[[], datetime] = _utcnow,
        accounts: AccountGate | None = None,
    ) -> None:
        self._videos = videos
        self._extractor = extractor
        self._media = media
        self._cache_root = Path(cache_root)
        self._settings = settings
        self._queue = queue
        self._work_root = Path(work_root)
        self._now = now
        self._accounts = accounts  # M5 รอบ C: ลองซ้ำด้วยบัญชีชั่วคราว (ทั้งการอ่านคลิปและการโหลดชิ้นภาพ)
        self._busy = threading.Lock()  # ถ่ายได้ครั้งละภาพทั้งแอพ (ไม่รอ: ถือไว้อยู่ = E_CAPTURE_BUSY)
        self._guard = threading.Lock()
        self._clip_locks: dict[str, threading.Lock] = {}

    # ---------- ที่เก็บ ----------

    def _clip_lock(self, video_id: str) -> threading.Lock:
        with self._guard:
            return self._clip_locks.setdefault(video_id, threading.Lock())

    def _folder(self, video_id: str) -> Path:
        return self._cache_root / video_id / CAPTURE_FOLDER

    def cache_path(self, video_id: str, capture: Capture) -> Path:
        return self._folder(video_id) / capture.file

    def _read_entries(self, video_id: str) -> list[dict]:
        try:
            data = json.loads((self._folder(video_id) / CAPTURE_INDEX).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        items = data.get("captures") if isinstance(data, dict) else None
        return [entry for entry in items if _entry_ok(entry)] if isinstance(items, list) else []

    def _write_entries(self, video_id: str, entries: list[dict]) -> None:
        folder = self._folder(video_id)
        folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / f".{CAPTURE_INDEX}.{uuid.uuid4().hex}.tmp"
        try:
            tmp.write_text(json.dumps({"captures": sorted(entries, key=lambda e: e["tMs"])}, ensure_ascii=False),
                           encoding="utf-8")  # fmt: skip
            os.replace(tmp, folder / CAPTURE_INDEX)
        finally:
            tmp.unlink(missing_ok=True)

    def _existing(self, video_id: str, t_ms: int) -> Capture | None:
        with self._clip_lock(video_id):
            for entry in self._read_entries(video_id):
                if entry["tMs"] == t_ms and (self._folder(video_id) / entry["file"]).is_file():
                    return _to_capture(entry)
        return None

    # ---------- ถ่ายภาพ ----------

    def _brake_on_bot_check(self, exc: YtError) -> None:
        if exc.code == "E_BOT_CHECK":
            self._queue.brake("E_BOT_CHECK")

    def capture(self, video_id: str, t_ms: int) -> tuple[Capture, bool]:
        """ถ่ายภาพที่เวลา t_ms คืน (ภาพ, ถ่ายใหม่ไหม) · เวลาเดิมที่ถ่ายไว้แล้ว = คืนภาพเดิมโดยไม่โหลดอะไร"""
        if not VIDEO_ID.fullmatch(video_id):
            raise YtError("E_INVALID_INPUT", f"video id ไม่ถูกรูปแบบ: {video_id!r}")
        if isinstance(t_ms, bool) or not isinstance(t_ms, int):
            raise CaptureRejected("tMs must be an integer")
        # M5 รอบ C spec 2.4: ถ่ายแบบไม่ใช้บัญชีก่อน จำกัดอายุ/ส่วนตัว + ถือบัญชีอยู่ = ถ่ายใหม่ทั้งครั้งด้วยบัญชี (ไม่นับเข้ากฎคิว)
        return with_account_retry(self._accounts, lambda: self._capture_once(video_id, t_ms))

    def _capture_once(self, video_id: str, t_ms: int) -> tuple[Capture, bool]:
        try:
            info = self._videos.get(video_id, peek=True)  # ไม่มีในที่เก็บ = probe ใหม่ (ติดบอทได้)
        except YtError as exc:
            self._brake_on_bot_check(exc)
            log.warning("ถ่ายภาพคม %s ไม่สำเร็จ (%s)", video_id, exc.code)
            raise
        duration_ms = int(info.get("durationS") or 0) * 1000
        if info.get("isLive"):
            raise CaptureRejected("live clip")
        if duration_ms <= 0:
            raise CaptureRejected("duration unknown")
        if not 0 <= t_ms < duration_ms + END_SLACK_MS:
            raise CaptureRejected(f"tMs {t_ms} outside 0..{duration_ms}")
        t_ms = min(t_ms, max(0, duration_ms - END_STEP_MS))  # ท้ายคลิป: ถ่ายภาพก่อนจบ 100 ms
        existing = self._existing(video_id, t_ms)
        if existing is not None:
            return existing, False
        pause = self._queue.pause_state()
        if pause is not None:
            raise YtError("E_QUEUE_PAUSED", "queue paused by a bot check", params={"time": _clock(pause.until)})
        if not self._media.available():
            raise YtError("E_FFMPEG_MISSING")
        if not self._busy.acquire(blocking=False):
            raise YtError("E_CAPTURE_BUSY", "another capture is running")
        try:
            existing = self._existing(video_id, t_ms)
            if existing is not None:
                return existing, False
            return self._capture_locked(video_id, str(info.get("title") or ""), t_ms), True
        except YtError as exc:
            self._brake_on_bot_check(exc)
            log.warning("ถ่ายภาพคม %s ไม่สำเร็จ (%s)", video_id, exc.code)
            raise
        finally:
            self._busy.release()

    def _capture_locked(self, video_id: str, title: str, t_ms: int) -> Capture:
        tmp = self._work_root / f"capture-{uuid.uuid4().hex}"
        try:
            try:
                tmp.mkdir(parents=True)
            except OSError as err:
                raise YtError("E_DISK_FULL" if err.errno == errno.ENOSPC else "E_UNKNOWN", type(err).__name__) from None
            try:
                cap = max_short_side(str(self._settings.get().get("captureQuality", "max")))
            except ValueError:
                cap = max_short_side("max")  # ค่าตั้งเสีย (ไม่ควรเกิด SettingsStore ตรวจแล้ว) = สูงสุดที่มี
            piece = self._extractor.fetch_frame_piece(video_id, t_ms, cap, tmp / "piece.mp4")
            frame = tmp / "frame.jpg"
            self._extract_frame(piece, frame, max(0, t_ms - piece.segment_start_ms))
            width, height = _jpeg_size(frame)
            return self._store(video_id, title, t_ms, frame, width, height)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _extract_frame(self, piece: PieceInfo, frame: Path, offset: int) -> None:
        """ภาพที่ offset ของชิ้น (ไม่มีภาพ = ถอย 100 ms อีกครั้ง) · offset เลยท้ายท่อน (เวลาเลยท่อนสุดท้ายของคลิป)
        แล้วยังไม่มีภาพ = ลองอีกครั้งที่ 100 ms ก่อนท้ายท่อน · ffmpeg ทุกครั้งรวมกันไม่เกิน FFMPEG_DEADLINE_S
        (ค้าง = ล็อกการถ่ายของทั้งแอพค้างตาม) · detail ไม่มีข้อความ stderr ของ ffmpeg (มี path ไฟล์งาน)"""
        deadline = time.monotonic() + FFMPEG_DEADLINE_S

        def expired() -> bool:
            return time.monotonic() >= deadline

        def extract(at_ms: int) -> bool:
            return self._media.extract_frame(piece.path, frame, at_ms, long_side=None,
                                             dynamic_range=piece.dynamic_range, cancel=expired)  # fmt: skip

        attempts = [offset]
        if offset > 0:
            attempts.append(max(0, offset - NO_FRAME_RETRY_MS))
        length = piece.segment_duration_ms
        if length is not None and offset >= length:
            tail = max(0, length - NO_FRAME_RETRY_MS)
            if tail not in attempts:
                attempts.append(tail)
        try:
            if any(extract(at_ms) for at_ms in attempts):
                return
        except JobCancelled:
            raise YtError("E_UNKNOWN", "ffmpeg timeout") from None
        except YtError as exc:
            if exc.code == "E_DISK_FULL":
                raise YtError("E_DISK_FULL", "ffmpeg") from None
            raise
        raise YtError("E_UNKNOWN", "no frame at this time")

    def _drop_stale_output(self, video_id: str, capture_id: str) -> None:
        """แถวเดิมของเวลานี้ที่ไฟล์ใน cache หายไปแล้ว (ถึงตรงนี้ได้เพราะ _existing ไม่นับแถวนั้น): ลบสำเนาในโฟลเดอร์ของแถวเดิม
        ก่อนถ่ายใหม่ ไม่อย่างนั้นแถวใหม่แทนที่แถวเดิมแล้วไฟล์เดิมไม่มีแถวไหนชี้ แอพลบไม่ได้อีกเลย
        ลบเฉพาะไฟล์ที่ยังเป็นไฟล์เดิมจริง (recorded_output) ไม่มีแล้วหรือลบไม่ได้ = ถ่ายต่อตามปกติ"""
        with self._clip_lock(video_id):
            stale = [e for e in self._read_entries(video_id)
                     if e["id"] == capture_id and not (self._folder(video_id) / e["file"]).is_file()]  # fmt: skip
        for entry in stale:
            target = recorded_output(entry["outputRoot"], entry["outputRel"])
            if target is None:
                continue
            try:
                target.unlink(missing_ok=True)
            except OSError as err:
                log.warning("ลบสำเนาเดิมของภาพที่ถ่ายของ %s ไม่ได้ (%s)", video_id, type(err).__name__)

    def _store(self, video_id: str, title: str, t_ms: int, frame: Path, width: int, height: int) -> Capture:
        capture = Capture(f"c_{t_ms}", t_ms, width, height, f"c_{t_ms}.jpg")
        folder = self._folder(video_id)
        cached = folder / capture.file
        self._drop_stale_output(video_id, capture.id)
        try:
            folder.mkdir(parents=True, exist_ok=True)
            part = folder / f".{capture.file}.{uuid.uuid4().hex}.part"
            try:
                shutil.copyfile(frame, part)
                os.replace(part, cached)
            finally:
                part.unlink(missing_ok=True)
        except OSError as err:
            raise YtError("E_DISK_FULL" if err.errno == errno.ENOSPC else "E_UNKNOWN", type(err).__name__) from None
        output: Path | None = None
        try:
            root = self._settings.output_dir()
            output = self._write_output(root, title, video_id, t_ms, frame)
            entry = {
                "id": capture.id, "tMs": t_ms, "width": width, "height": height, "file": capture.file,
                "outputRoot": str(root), "outputRel": output.relative_to(root).as_posix(),
                "createdAt": self._now().astimezone(UTC).isoformat(timespec="seconds"),
            }  # fmt: skip
            with self._clip_lock(video_id):
                entries = [e for e in self._read_entries(video_id) if e["id"] != capture.id]
                try:
                    self._write_entries(video_id, [*entries, entry])
                except OSError as err:
                    raise YtError("E_DISK_FULL" if err.errno == errno.ENOSPC else "E_UNKNOWN", type(err).__name__) from None
        except BaseException:
            cached.unlink(missing_ok=True)
            if output is not None:
                output.unlink(missing_ok=True)
            raise
        return capture

    def _write_output(self, root: Path, title: str, video_id: str, t_ms: int, frame: Path) -> Path:
        """สำเนาในโฟลเดอร์ของคลิป: <clip folder>/ภาพที่ถ่าย/frame_HH-MM-SS.jpg (ชื่อซ้ำ _2 ... _99) จองชื่อแบบ exclusive"""
        try:
            ensure_output_root(root)
        except YtError as err:
            # detail เดิมเป็นข้อความของ OSError ซึ่งมี path ของโฟลเดอร์ผลลัพธ์: เหลือแค่ชื่อชนิดของ error
            cause = type(err.__cause__).__name__ if err.__cause__ is not None else "OSError"
            raise YtError("E_OUTPUT_NOT_WRITABLE", cause) from None
        folder = plan_output(root, title, video_id, "", "jpg").parent / OUTPUT_DIR
        if _u16(str(folder / _LONGEST_NAME)) > PATH_LIMIT:
            raise YtError("E_OUTPUT_NOT_WRITABLE", "path too long")
        stem = f"frame_{file_timecode(t_ms)}"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            for n in range(1, MAX_SAME_SECOND + 1):
                target = folder / (f"{stem}.jpg" if n == 1 else f"{stem}_{n}.jpg")
                try:
                    handle = target.open("xb")
                except FileExistsError:
                    continue
                try:
                    with handle, frame.open("rb") as source:
                        shutil.copyfileobj(source, handle)
                except BaseException:
                    target.unlink(missing_ok=True)
                    raise
                return target
        except OSError as err:
            raise _write_error(err) from None
        raise YtError("E_OUTPUT_NOT_WRITABLE", "no free name in the capture folder")

    # ---------- รายการ ลบ เปิดโฟลเดอร์ ----------

    def list(self, video_id: str) -> list[Capture]:
        """ภาพของคลิปเรียงตามเวลา · แถวที่ไฟล์ใน cache หายไปแล้วถูกลบออกจาก index"""
        if not VIDEO_ID.fullmatch(video_id):
            return []
        with self._clip_lock(video_id):
            entries = self._read_entries(video_id)
            kept = [e for e in entries if (self._folder(video_id) / e["file"]).is_file()]
            if len(kept) != len(entries):
                try:
                    self._write_entries(video_id, kept)
                except OSError as err:
                    log.warning("เขียนรายการภาพที่ถ่ายของ %s ใหม่ไม่ได้ (%s)", video_id, type(err).__name__)
        return [_to_capture(e) for e in sorted(kept, key=lambda e: e["tMs"])]

    def delete(self, video_id: str, capture_id: str) -> None:
        """ลบภาพจากโฟลเดอร์ (เฉพาะไฟล์เดิมที่บันทึกไว้) แล้วจาก cache และ index · ไม่รู้จัก = KeyError
        ไฟล์ในโฟลเดอร์ลบไม่ได้ (เช่นเปิดค้างในโปรแกรมดูภาพ) = E_OUTPUT_NOT_WRITABLE และไม่เปลี่ยนอะไร"""
        if not VIDEO_ID.fullmatch(video_id) or not CAPTURE_ID.fullmatch(capture_id):
            raise KeyError(capture_id)
        with self._clip_lock(video_id):
            entries = self._read_entries(video_id)
            entry = next((e for e in entries if e["id"] == capture_id), None)
            if entry is None:
                raise KeyError(capture_id)
            target = recorded_output(entry["outputRoot"], entry["outputRel"])
            if target is not None:
                try:
                    target.unlink(missing_ok=True)
                except OSError as err:
                    raise YtError("E_OUTPUT_NOT_WRITABLE", type(err).__name__) from None
            try:
                (self._folder(video_id) / entry["file"]).unlink(missing_ok=True)
                self._write_entries(video_id, [e for e in entries if e["id"] != capture_id])
            except OSError as err:
                raise YtError("E_UNKNOWN", type(err).__name__) from None

    def reveal_dir(self, video_id: str) -> Path | None:
        """โฟลเดอร์ ภาพที่ถ่าย ที่จะเปิด: ของภาพล่าสุดที่ไฟล์ยังอยู่ · ไม่มี = โฟลเดอร์ตามค่าตั้งปัจจุบันถ้ามีอยู่ · ไม่มีเลย = None"""
        if not VIDEO_ID.fullmatch(video_id):
            return None
        with self._clip_lock(video_id):
            entries = sorted(self._read_entries(video_id), key=lambda e: e["createdAt"], reverse=True)
        for entry in entries:
            target = recorded_output(entry["outputRoot"], entry["outputRel"])
            if target is not None:
                return target.parent
        info = self._videos.peek_cached(video_id)
        if info is None:
            return None
        try:
            folder = plan_output(self._settings.output_dir(), str(info.get("title") or ""), video_id, "", "jpg").parent
        except YtError:
            return None
        folder = folder / OUTPUT_DIR
        return folder if folder.is_dir() and not _is_link(folder) else None


def _jpeg_size(path: Path) -> tuple[int, int]:
    try:
        with Image.open(path) as img:
            return int(img.width), int(img.height)
    except (OSError, UnidentifiedImageError) as err:
        raise YtError("E_UNKNOWN", f"unreadable frame: {type(err).__name__}") from None
