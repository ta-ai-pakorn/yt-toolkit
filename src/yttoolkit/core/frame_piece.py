"""ภาพคมตรงจุด (M5 รอบ B2 spec 3.1) ส่วนที่ไม่ต่อเน็ต: อ่าน sidx ของ mp4 แบบแบ่งท่อน เลือก format และประกอบไฟล์ชิ้นเล็ก

ไฟล์ DASH ของยูทูปเรียงกล่องเป็น ftyp, moov, sidx แล้วตามด้วย moof+mdat ทีละท่อน (ราว 5 วินาทีต่อท่อน)
sidx บอกว่าแต่ละท่อนเริ่มที่ไบต์ไหน ยาวกี่ไบต์ และกินเวลาเท่าไร จึงโหลดแค่ส่วนหัว (init) กับท่อนเดียวที่มีเวลาที่ต้องการ
โมดูลนี้ไม่ใช้ yt-dlp และไม่ต่อเน็ต: ตัวจริง (extractor.py) ส่ง read_range ที่ยิงคำขอแบบ Range
ตัวปลอมส่ง read_range ที่ตัดจากไฟล์ใน tests/fixtures/capture/
"""

from __future__ import annotations

import errno
import math
import struct
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .yterrors import YtError

HEAD_BYTES = 65_536  # คำขอแรก: ftyp + moov + sidx ของยูทูปอยู่ในช่วงนี้แทบทุกคลิป
MAX_INDEX_BYTES = 1_048_576  # เลยจากนี้ยังไม่เจอ sidx = ไม่ใช่ไฟล์แบบที่รองรับ
MAX_TOP_BOXES = 64
MAX_SEGMENT_BYTES = 64 * 1024 * 1024  # ท่อนที่ sidx บอกว่าใหญ่กว่านี้ = ไฟล์แปลก ไม่โหลดทั้งท่อน
# ค่าตั้ง captureQuality -> ด้านสั้นสูงสุด ("สูงสุดที่มี" = สูงสุดถึง 4K ตาม spec E2 ด้านสั้น 2160 จึงรวม 4K แนวตั้ง ตัด 8K)
CAPTURE_SHORT_SIDES: dict[str, int | None] = {"max": 2160, "1080": 1080, "720": 720}

ReadRange = Callable[[int, int], bytes]  # (ไบต์แรก, ไบต์สุดท้ายแบบนับรวม) -> ข้อมูล (สั้นกว่าที่ขอได้ถ้าถึงท้ายไฟล์)


@dataclass(frozen=True)
class SidxRef:
    """ท่อนหนึ่งของไฟล์: ไบต์แรก ขนาด และเวลาเริ่ม/ความยาวในหน่วย timescale"""

    offset: int
    size: int
    start: int
    duration: int


@dataclass(frozen=True)
class SidxIndex:
    timescale: int
    refs: tuple[SidxRef, ...]

    def to_ms(self, units: int) -> int:
        return units * 1000 // self.timescale

    @property
    def end_ms(self) -> int:
        last = self.refs[-1]
        return self.to_ms(last.start + last.duration)


@dataclass(frozen=True)
class MediaIndex:
    init: bytes  # ไบต์ 0 ถึงท้ายกล่อง sidx (ftyp + moov + sidx) ffmpeg ต้องใช้ส่วนนี้ถอดรหัสท่อนใดก็ได้
    sidx: SidxIndex


@dataclass(frozen=True)
class PieceInfo:
    """ไฟล์ชิ้นเล็ก (init + หนึ่งท่อน) ที่เขียนแล้ว · segment_start_ms = เวลาของคลิปที่ท่อนนี้เริ่ม
    segment_duration_ms = ความยาวของท่อน (None = ไม่รู้) ใช้ถอยมาท้ายท่อนเมื่อเวลาที่ขอเลยท่อนสุดท้าย"""

    path: Path
    segment_start_ms: int
    width: int | None
    height: int | None
    format_id: str
    dynamic_range: str | None  # None = SDR (แบบเดียวกับ MediaTools.extract_frame)
    segment_duration_ms: int | None = None


def _unsupported(why: str) -> YtError:
    return YtError("E_CAPTURE_UNSUPPORTED", why)


def parse_sidx(box: bytes, box_offset: int) -> SidxIndex:
    """กล่อง sidx ทั้งกล่อง (version 0 หรือ 1) -> ตำแหน่งไบต์และเวลาของทุกท่อน (ISO 14496-12 8.16.3)

    box_offset = ตำแหน่งของกล่องในไฟล์: ท่อนแรกเริ่มที่ท้ายกล่อง + first_offset
    """
    if len(box) < 32 or box[4:8] != b"sidx":
        raise _unsupported("not a sidx box")
    if box[0:4] == b"\x00\x00\x00\x01":
        raise _unsupported("sidx with a 64-bit box size")
    version = box[8]
    if version not in (0, 1):
        raise _unsupported(f"sidx version {version}")
    if version == 1 and len(box) < 40:
        raise _unsupported("sidx box too short")
    pos = 16  # หัวกล่อง 8 + version/flags 4 + reference_ID 4
    (timescale,) = struct.unpack_from(">I", box, pos)
    pos += 4
    if version == 0:
        earliest, first = struct.unpack_from(">II", box, pos)
        pos += 8
    else:
        earliest, first = struct.unpack_from(">QQ", box, pos)
        pos += 16
    pos += 2  # reserved
    (count,) = struct.unpack_from(">H", box, pos)
    pos += 2
    if timescale == 0 or count == 0 or pos + count * 12 > len(box):
        raise _unsupported("bad sidx")
    offset = box_offset + len(box) + first
    start = earliest
    refs: list[SidxRef] = []
    for _ in range(count):
        word, duration, _sap = struct.unpack_from(">III", box, pos)
        pos += 12
        if word >> 31:
            raise _unsupported("sidx points to another sidx")
        size = word & 0x7FFF_FFFF
        if size == 0 or size > MAX_SEGMENT_BYTES:
            raise _unsupported(f"sidx segment size {size}")
        refs.append(SidxRef(offset, size, start, duration))
        offset += size
        start += duration
    return SidxIndex(timescale, tuple(refs))


class _Head:
    """ไบต์ต้นไฟล์ที่โหลดมาแล้ว ขอเพิ่มต่อท้ายได้จนถึง MAX_INDEX_BYTES"""

    def __init__(self, read_range: ReadRange) -> None:
        self._read = read_range
        self.data = read_range(0, HEAD_BYTES - 1)

    def need(self, end: int) -> None:
        if end <= len(self.data):
            return
        if end > MAX_INDEX_BYTES:
            raise _unsupported("no sidx near the start of the file")
        more = self._read(len(self.data), end - 1)
        if len(more) != end - len(self.data):
            raise YtError("E_NETWORK", "short read")
        self.data += more


def _find_sidx(head: _Head) -> tuple[int, int]:
    """เดินกล่องระดับบนจากต้นไฟล์จนเจอ sidx -> (ตำแหน่ง, ขนาด) · เจอ moof/mdat ก่อน = ไม่มี sidx"""
    pos = 0
    for _ in range(MAX_TOP_BOXES):
        head.need(pos + 8)
        size, kind = struct.unpack_from(">I4s", head.data, pos)
        header = 8
        if size == 1:
            head.need(pos + 16)
            (size,) = struct.unpack_from(">Q", head.data, pos + 8)
            header = 16
        if size < header:  # 0 = กล่องยาวถึงท้ายไฟล์ (ไม่มีอะไรตามหลัง) หรือขนาดเสีย
            raise _unsupported(f"bad box size at {pos}")
        if kind == b"sidx":
            return pos, size
        if kind in (b"moof", b"mdat"):
            raise _unsupported("no sidx before the media")
        pos += size
    raise _unsupported("no sidx")


def read_index(read_range: ReadRange) -> MediaIndex:
    head = _Head(read_range)
    pos, size = _find_sidx(head)
    head.need(pos + size)
    sidx = parse_sidx(head.data[pos : pos + size], pos)
    return MediaIndex(head.data[: pos + size], sidx)


def segment_for(index: SidxIndex, t_ms: int) -> SidxRef | None:
    """ท่อนที่มีเวลา t_ms: ก่อนท่อนแรก = ท่อนแรก · ตรงรอยต่อ = ท่อนหลัง
    เลยท่อนสุดท้ายไม่ถึงความยาวของท่อนนั้น = ท่อนสุดท้าย (ดูจนจบคลิปแล้วกดถ่าย: เวลาของตัวเล่นเลยภาพสุดท้ายได้เล็กน้อย)
    เลยไปกว่านั้น = None · เทียบในหน่วย timescale × 1000 จึงไม่มีเศษปัด"""
    target = t_ms * index.timescale
    for ref in index.refs:
        if target < (ref.start + ref.duration) * 1000:
            return ref
    last = index.refs[-1]
    if target < (last.start + 2 * last.duration) * 1000:
        return last
    return None


def fetch_piece(read_range: ReadRange, index: MediaIndex, t_ms: int) -> tuple[bytes, SidxRef]:
    """init + ท่อนเดียวที่มี t_ms (ไฟล์ mp4 ที่ ffmpeg เปิดได้ เวลาของไฟล์เริ่มที่เวลาของท่อน)"""
    ref = segment_for(index.sidx, t_ms)
    if ref is None:
        raise YtError("E_UNKNOWN", "time past the end of the index")
    body = read_range(ref.offset, ref.offset + ref.size - 1)
    if len(body) != ref.size:
        raise YtError("E_NETWORK", "short read")
    return index.init + body, ref


def write_piece(dest: Path, data: bytes) -> None:
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    except OSError as err:
        code = "E_DISK_FULL" if err.errno == errno.ENOSPC else "E_UNKNOWN"
        # ไม่ผูก OSError เดิม: ข้อความมี path ของไฟล์ทำงาน และ log ของ 500 พิมพ์สายโซ่ exception
        raise YtError(code, type(err).__name__) from None


def max_short_side(quality: str) -> int | None:
    if quality not in CAPTURE_SHORT_SIDES:
        raise ValueError(f"unknown capture quality: {quality!r}")
    return CAPTURE_SHORT_SIDES[quality]


def _positive(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        return None
    return int(value) if value > 0 else None


def short_side(fmt: Mapping[str, Any]) -> int:
    width, height = _positive(fmt.get("width")), _positive(fmt.get("height"))
    if width and height:
        return min(width, height)
    return height or 0


def _is_sdr(fmt: Mapping[str, Any]) -> bool:
    value = fmt.get("dynamic_range")
    return value is None or str(value).strip().upper() in ("", "SDR")


def _codec_rank(fmt: Mapping[str, Any]) -> int:
    vcodec = str(fmt.get("vcodec") or "").lower()
    if vcodec.startswith("avc1"):
        return 0
    if vcodec.startswith("av01"):
        return 1
    return 2


def _is_candidate(fmt: object) -> bool:
    """mp4 ภาพอย่างเดียวที่โหลดผ่าน https ตรง ๆ (ไฟล์แบบนี้ของยูทูปมี sidx) และรู้ขนาดภาพ"""
    if not isinstance(fmt, Mapping):
        return False
    vcodec = fmt.get("vcodec")
    url = fmt.get("url")
    return (
        fmt.get("ext") == "mp4"
        and fmt.get("protocol") == "https"
        and isinstance(vcodec, str)
        and vcodec not in ("", "none")
        and fmt.get("acodec") in (None, "none")
        and isinstance(url, str)
        and url != ""
        and short_side(fmt) > 0
    )


def _rank(fmt: Mapping[str, Any]) -> tuple:
    size = _positive(fmt.get("filesize")) or _positive(fmt.get("filesize_approx"))
    return (-short_side(fmt), not _is_sdr(fmt), _codec_rank(fmt), size is None, size or 0, str(fmt.get("format_id")))


def pick_capture_format(info: Mapping[str, Any], max_short_side: int | None) -> dict | None:
    """format ที่ใช้ถ่ายภาพ (spec 3.1 ข้อ 2): ด้านสั้นมากสุดที่ไม่เกินเพดาน > SDR > avc1 > av01 > ไฟล์เล็กสุด
    ไม่มีตัวที่ไม่เกินเพดาน = ตัวที่ด้านสั้นเล็กที่สุดเหนือเพดาน · ไม่มี mp4 ภาพอย่างเดียวผ่าน https เลย = None"""
    candidates = [dict(f) for f in (info.get("formats") or []) if _is_candidate(f)]
    if not candidates:
        return None
    pool = [f for f in candidates if max_short_side is None or short_side(f) <= max_short_side]
    if not pool:
        smallest = min(short_side(f) for f in candidates)
        pool = [f for f in candidates if short_side(f) == smallest]
    return min(pool, key=_rank)


def piece_info(fmt: Mapping[str, Any], path: Path, index: SidxIndex, ref: SidxRef) -> PieceInfo:
    start_ms = index.to_ms(ref.start)
    return PieceInfo(
        path=path,
        segment_start_ms=start_ms,
        width=_positive(fmt.get("width")),
        height=_positive(fmt.get("height")),
        format_id=str(fmt.get("format_id") or ""),
        dynamic_range=None if _is_sdr(fmt) else str(fmt.get("dynamic_range")),
        segment_duration_ms=index.to_ms(ref.start + ref.duration) - start_ms,
    )
