"""M5 รอบ B2 กับยูทูปจริง: ถ่ายภาพคมตรงจุดด้วย YtDlpExtractor.fetch_frame_piece + ffmpeg จริง (spec 5, E6)

ต้องได้รับอนุญาตจากพิธก่อนรัน (ยังไม่เคยรัน): โหลดลง temp แล้วลบทิ้งทุกครั้งที่จบ (ทั้งผ่านและตก)
  - ชิ้นวิดีโอ (หนึ่งท่อน ไม่ใช่ทั้งคลิป) 1080p และ 4K รวมราว 2-8 MB
  - เทสเทียบรอยต่อท่อน: ชิ้น 360p อีก 2 ชิ้น (ราว 1 MB) และ **ไฟล์ 360p ทั้งไฟล์ของ format เดียวกัน** (BBB 635 วินาที
    ราว 15-40 MB, เพดาน 150 MB) เพื่อเทียบภาพที่ตัดจากชิ้นกับภาพที่ตัดจากไฟล์เต็ม
รันเองด้วย: uv run pytest -m network -q tests/network/test_capture_network.py -s
id ของคลิปอยู่ใน tests/network_videos.toml ([capture]) · ยูทูปตอบ 429 หรือขอยืนยันว่าไม่ใช่บอท = เทสตก ให้รายงานผล ห้ามแก้เทสให้หลวมลง
"""

from __future__ import annotations

import shutil
import time
import tempfile
import tomllib
from collections.abc import Iterator
from pathlib import Path

import pytest
from helpers_ffmpeg import find_test_ffmpeg, requires_ffmpeg
from PIL import Image

from yttoolkit.core.extractor import YtDlpExtractor
from yttoolkit.core.frame_piece import PieceInfo
from yttoolkit.core.media import FfmpegTools

pytestmark = [pytest.mark.network, requires_ffmpeg]

_TOML = Path(__file__).resolve().parents[1] / "network_videos.toml"
CLIPS: dict[str, str] = tomllib.loads(_TOML.read_text(encoding="utf-8"))["capture"]
AT_MS = 120_500
GAP_S = 2  # เว้นช่วงระหว่างคำขอไปยูทูป (แบบเดียวกับ network test อื่น)
MAX_PIECE_BYTES = 15_000_000  # หนึ่งท่อน (ราว 5 วินาที) ไม่ใช่ทั้งคลิป: BBB 4K ทั้งคลิปราว 700 MB
MAX_WHOLE_BYTES = 150_000_000  # เพดานของไฟล์ 360p ทั้งไฟล์ (เทสรอยต่อ) เกินนี้ yt-dlp หยุดโหลด
BOUNDARY_CAP = 360  # เทสรอยต่อใช้ 360p: ไฟล์ทั้งไฟล์เล็กพอโหลดได้
# ภาพจากชิ้นกับภาพจากไฟล์เต็มที่เวลาเดียวกัน ย่อเหลือ 160x90 สีเทา: ผลต่างพิกเซลเฉลี่ย (0-255) ต้องไม่เกินค่านี้
# avc1 จริงมี B-frame และ edit list จึงอาจต่างกันเล็กน้อย (ตัวถอดรหัสเลือกเฟรมข้างเคียง) แต่ภาพคนละเฟรมจากเวลาอื่นต่างกว่านี้มาก
MAX_MEAN_DIFF = 6.0


@pytest.fixture
def work() -> Iterator[Path]:
    """โฟลเดอร์ชั่วคราวของเทสนี้ ทุกอย่างที่โหลดอยู่ที่นี่ และถูกลบทิ้งเสมอ (ผ่านหรือตก)"""
    folder = Path(tempfile.mkdtemp(prefix="yt-capture-network-"))
    try:
        yield folder
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def _tools() -> FfmpegTools:
    ffmpeg = find_test_ffmpeg()
    assert ffmpeg is not None
    return FfmpegTools(lambda: Path(ffmpeg))


def _cut(src: Path, out: Path, t_ms: int, piece: PieceInfo | None) -> tuple[int, int]:
    """ตัดภาพที่ t_ms ของคลิป: จากชิ้น (เวลาในไฟล์ = t_ms - เวลาเริ่มท่อน) หรือจากไฟล์เต็ม (piece=None)"""
    local = t_ms if piece is None else t_ms - piece.segment_start_ms
    dynamic_range = None if piece is None else piece.dynamic_range
    assert _tools().extract_frame(src, out, local, long_side=None, dynamic_range=dynamic_range, cancel=lambda: False)
    with Image.open(out) as img:
        return img.size


def _gray(path: Path) -> list[int]:
    with Image.open(path) as img:
        return list(img.convert("L").resize((160, 90)).getdata())


def _mean_diff(a: Path, b: Path) -> float:
    pa, pb = _gray(a), _gray(b)
    assert len(pa) == len(pb)
    return sum(abs(x - y) for x, y in zip(pa, pb, strict=True)) / len(pa)


@pytest.mark.parametrize(("cap", "short_side"), [(1080, 1080), (None, 2160)])
def test_one_segment_gives_a_source_size_frame(work: Path, cap: int | None, short_side: int) -> None:
    started = time.monotonic()
    piece = YtDlpExtractor().fetch_frame_piece(CLIPS["landscape"], AT_MS, cap, work / "piece.mp4")
    elapsed = time.monotonic() - started
    size = piece.path.stat().st_size
    assert size < MAX_PIECE_BYTES
    assert 0 <= AT_MS - piece.segment_start_ms < 15_000
    width, height = _cut(piece.path, work / "frame.jpg", AT_MS, piece)
    assert min(width, height) == short_side
    assert (width, height) == (piece.width, piece.height)
    print(f"cap={cap} format={piece.format_id} {width}x{height} piece={size / 1e6:.1f} MB in {elapsed:.1f} s")
    time.sleep(GAP_S)


def _download_whole(video_id: str, format_id: str, folder: Path) -> Path:
    """ไฟล์เต็มของ format เดียวกับชิ้น (ไว้เทียบภาพเท่านั้น) · เกิน MAX_WHOLE_BYTES = yt-dlp ไม่โหลด เทสตก"""
    import yt_dlp

    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "format": format_id,
        "outtmpl": {"default": "whole.%(ext)s"},
        "paths": {"home": str(folder), "temp": str(folder)},
        "max_filesize": MAX_WHOLE_BYTES,
        "retries": 3,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    (whole,) = [p for p in folder.glob("whole.*") if not p.name.endswith((".part", ".ytdl"))]
    return whole


def test_frame_from_the_piece_matches_the_whole_file_near_a_segment_boundary(work: Path) -> None:
    """avc1 จริงมี B-frame และ edit list: ภาพจากชิ้น (init + ท่อนเดียว) ต้องเป็นเฟรมเดียวกับภาพจากไฟล์เต็ม
    ที่รอยต่อท่อน: ต้นท่อน (S และ S+100 ms) และท้ายท่อนก่อนหน้า (S-100 ms) ยอมให้ต่างกันเล็กน้อย (MAX_MEAN_DIFF)"""
    extractor = YtDlpExtractor()
    video_id = CLIPS["landscape"]
    piece = extractor.fetch_frame_piece(video_id, AT_MS, BOUNDARY_CAP, work / "piece.mp4")
    start = piece.segment_start_ms
    assert start > 0, "ท่อนแรกของคลิปไม่มีรอยต่อให้ตรวจ"
    time.sleep(GAP_S)
    before = extractor.fetch_frame_piece(video_id, start - 100, BOUNDARY_CAP, work / "before.mp4")
    assert before.format_id == piece.format_id
    assert before.segment_start_ms < start <= before.segment_start_ms + 15_000
    time.sleep(GAP_S)

    whole = _download_whole(video_id, piece.format_id, work)
    cases = [
        ("start", start, piece),
        ("start+100ms", start + 100, piece),
        ("end-of-previous-segment", start - 100, before),
    ]
    for name, t_ms, src in cases:
        from_piece = work / f"piece-{name}.jpg"
        from_whole = work / f"whole-{name}.jpg"
        piece_size = _cut(src.path, from_piece, t_ms, src)
        whole_size = _cut(whole, from_whole, t_ms, None)
        assert piece_size == whole_size, name
        diff = _mean_diff(from_piece, from_whole)
        print(f"{name}: t={t_ms} ms {piece_size[0]}x{piece_size[1]} mean diff {diff:.2f}")
        assert diff <= MAX_MEAN_DIFF, f"{name}: ภาพจากชิ้นไม่ใช่เฟรมเดียวกับไฟล์เต็ม (ต่าง {diff:.2f})"
    assert not any(work.glob("*.part"))
