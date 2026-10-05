"""M5 รอบ B2 กับยูทูปจริง: ถ่ายภาพคมตรงจุดด้วย YtDlpExtractor.fetch_frame_piece + ffmpeg จริง (spec 5, E6)

ต้องได้รับอนุญาตจากพิธก่อนรัน (ยังไม่เคยรัน) ขนาดที่โหลดรวมราว 35-60 MB ลง temp แล้วลบทิ้งทุกครั้งที่จบ (ทั้งผ่านและตก):
  - ชิ้นวิดีโอ (หนึ่งท่อน ไม่ใช่ทั้งคลิป): 1080p ราว 2 MB + 4K ราว 7.5 MB (spike 2026-10-05)
  - เทสรอยต่อท่อน: ชิ้น 360p อีก 2 ชิ้น (ราว 1 MB) และไฟล์ 360p ทั้งไฟล์ของ format เดียวกันผ่านทาง YtDlpExtractor.download
    ประเมิน BBB 635 วินาที × บิตเรตราว 400-600 kbps = ราว 25-50 MB (เทสพิมพ์ขนาดจริงของ format และหยุดถ้าเกิน 150 MB
    ก่อนโหลด)
รันเองด้วย: uv run pytest -m network -q tests/network/test_capture_network.py -s
id ของคลิปอยู่ใน tests/network_videos.toml ([capture]) · ยูทูปตอบ 429 หรือขอยืนยันว่าไม่ใช่บอท = เทสตก ให้รายงานผล ห้ามแก้เทสให้หลวมลง
เคส 4K (av01) ข้ามเองถ้า ffmpeg ในเครื่องไม่มีตัวถอดรหัส AV1
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import tempfile
import time
import tomllib
from collections.abc import Iterator
from fractions import Fraction
from pathlib import Path

import pytest
from helpers_ffmpeg import find_test_ffmpeg, requires_ffmpeg
from PIL import Image

from yttoolkit.core.download import DownloadChoice, DownloadHooks
from yttoolkit.core.extractor import YtDlpExtractor
from yttoolkit.core.frame_piece import PieceInfo
from yttoolkit.core.media import FfmpegTools

pytestmark = [pytest.mark.network, requires_ffmpeg]

_TOML = Path(__file__).resolve().parents[1] / "network_videos.toml"
CLIPS: dict[str, str] = tomllib.loads(_TOML.read_text(encoding="utf-8"))["capture"]
AT_MS = 120_500
GAP_S = 2  # เว้นช่วงระหว่างคำขอไปยูทูป (แบบเดียวกับ network test อื่น)
MAX_PIECE_BYTES = 15_000_000  # หนึ่งท่อน (ราว 5 วินาที) ไม่ใช่ทั้งคลิป: BBB 4K ทั้งคลิปราว 700 MB
MAX_WHOLE_BYTES = 150_000_000  # เพดานของไฟล์ 360p ทั้งไฟล์ (เทสรอยต่อ) ประเมินเกินนี้ = ไม่โหลด เทสตก
BOUNDARY_CAP = 360  # เทสรอยต่อใช้ 360p: ไฟล์ทั้งไฟล์เล็กพอโหลดได้
# ภาพจากชิ้นกับภาพจากไฟล์เต็มที่เวลาเดียวกัน (เทียบสีเทาความละเอียดเต็ม): ต้องเป็นเฟรมเดียวกัน ผลต่างพิกเซลเฉลี่ย (0-255)
# ไม่เกินค่านี้ (แบบเดียวกับ tests/integration/test_capture_ffmpeg.py ที่ใช้กับชิ้นจริง) เฟรมเลื่อนไป 1 เฟรมต้องไม่ผ่าน
SAME_FRAME_MAX_DIFF = 0.1
# ภาพของเฟรมถัดไป (ตัวควบคุมเชิงลบ) ต้องต่างจากภาพจากชิ้นอย่างน้อยเท่านี้ ไม่งั้นฉากนิ่งเกินไปจนเทสจับการเลื่อนไม่ได้
CONTROL_MIN_DIFF = 0.3


@pytest.fixture
def work() -> Iterator[Path]:
    """โฟลเดอร์ชั่วคราวของเทสนี้ ทุกอย่างที่โหลดอยู่ที่นี่ และถูกลบทิ้งเสมอ (ผ่านหรือตก)"""
    folder = Path(tempfile.mkdtemp(prefix="yt-capture-network-"))
    try:
        yield folder
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def _ffmpeg() -> str:
    ffmpeg = find_test_ffmpeg()
    assert ffmpeg is not None
    return ffmpeg


def _ffprobe() -> str:
    """หา ffprobe แบบเดียวกับ tests/helpers_ffmpeg.ffprobe_json: ใน PATH หรือข้างไฟล์ ffmpeg"""
    found = shutil.which("ffprobe")
    if found is None:
        exe = Path(_ffmpeg())
        candidate = exe.with_name(exe.name.replace("ffmpeg", "ffprobe"))
        found = str(candidate) if candidate.exists() else None
    assert found is not None, "ไม่พบ ffprobe"
    return found


def _has_av1_decoder() -> bool:
    """ตัวถอดรหัสซอฟต์แวร์ของ AV1 (libdav1d / libaom): ตัว av1 ในตัวของ ffmpeg ใช้ได้เฉพาะกับการ์ดจอ"""
    out = subprocess.run([_ffmpeg(), "-hide_banner", "-decoders"], capture_output=True, check=True).stdout
    return re.search(rb"\blib(dav1d|aom-av1)\b", out) is not None


def _first_frame(path: Path) -> tuple[float, float]:
    """(เวลาแสดงผลของเฟรมแรกในไฟล์ (วินาที), ความยาวหนึ่งเฟรม (วินาที)) จาก ffprobe"""
    out = subprocess.run(
        [_ffprobe(), "-v", "error", "-select_streams", "v:0", "-read_intervals", "%+#8",
         "-show_entries", "frame=pts_time,pkt_pts_time,best_effort_timestamp_time:stream=avg_frame_rate,r_frame_rate",
         "-of", "json", str(path)],
        capture_output=True,
        check=True,
    ).stdout  # fmt: skip
    doc = json.loads(out)
    times = [
        float(t)
        for f in doc["frames"]
        if (t := f.get("pts_time") or f.get("pkt_pts_time") or f.get("best_effort_timestamp_time")) is not None
    ]
    assert times, "ffprobe ไม่คืนเวลาของเฟรมแรก"
    return min(times), float(1 / _frame_rate(doc["streams"][0]))


def _frame_rate(stream: dict) -> Fraction:
    """อัตราเฟรมของสตรีม: avg_frame_rate ก่อน · ffprobe ตอบ 0/0 ได้ (ชิ้นแบบแบ่งท่อนที่อ่านด้วย -read_intervals) = ใช้ r_frame_rate"""
    for key in ("avg_frame_rate", "r_frame_rate"):
        text = str(stream.get(key) or "0/0")
        num, _, den = text.partition("/")
        if int(num or 0) > 0 and int(den or 1) > 0:
            return Fraction(int(num), int(den or 1))
    raise AssertionError(f"ffprobe ไม่บอกอัตราเฟรม (avg_frame_rate={stream.get('avg_frame_rate')}, r_frame_rate={stream.get('r_frame_rate')})")


def _assert_piece_starts_at_segment(piece: PieceInfo) -> None:
    """ชิ้นต้องมีเฟรมแรกที่เวลาเริ่มท่อนจริง (ภายในหนึ่งเฟรม): ถ้าไม่ใช่ เวลาที่ส่งให้ ffmpeg (t - segment_start) ผิดตำแหน่ง"""
    first, period = _first_frame(piece.path)
    start = piece.segment_start_ms / 1000
    assert abs(first - start) <= period, f"เฟรมแรกของชิ้นอยู่ที่ {first:.3f} s แต่ท่อนเริ่มที่ {start:.3f} s (1 เฟรม = {period:.3f} s)"


def _cut(src: Path, out: Path, t_ms: int, piece: PieceInfo | None) -> tuple[int, int]:
    """ตัดภาพที่ t_ms ของคลิป: จากชิ้น (เวลาในไฟล์ = t_ms - เวลาเริ่มท่อน) หรือจากไฟล์เต็ม (piece=None)"""
    local = t_ms if piece is None else t_ms - piece.segment_start_ms
    dynamic_range = None if piece is None else piece.dynamic_range
    tools = FfmpegTools(lambda: Path(_ffmpeg()))
    assert tools.extract_frame(src, out, local, long_side=None, dynamic_range=dynamic_range, cancel=lambda: False)
    with Image.open(out) as img:
        return img.size


def _gray(path: Path) -> bytes:
    with Image.open(path) as img:
        return img.convert("L").tobytes()


def _mean_diff(a: Path, b: Path) -> float:
    pa, pb = _gray(a), _gray(b)
    assert len(pa) == len(pb)
    return sum(abs(x - y) for x, y in zip(pa, pb, strict=True)) / len(pa)


@pytest.mark.parametrize(("cap", "short_side"), [(1080, 1080), (None, 2160)])
def test_one_segment_gives_a_source_size_frame(work: Path, cap: int | None, short_side: int) -> None:
    if cap is None and not _has_av1_decoder():
        pytest.skip("ffmpeg ในเครื่องไม่มีตัวถอดรหัส AV1 (libdav1d/libaom) ข้ามเคส 4K")
    started = time.monotonic()
    piece = YtDlpExtractor().fetch_frame_piece(CLIPS["landscape"], AT_MS, cap, work / "piece.mp4")
    elapsed = time.monotonic() - started
    size = piece.path.stat().st_size
    assert size < MAX_PIECE_BYTES
    assert 0 <= AT_MS - piece.segment_start_ms < 15_000
    _assert_piece_starts_at_segment(piece)  # โหลดท่อนเดียวพอ: เฟรมแรกของชิ้นคือเวลาเริ่มท่อนตาม sidx
    width, height = _cut(piece.path, work / "frame.jpg", AT_MS, piece)
    assert min(width, height) == short_side
    assert (width, height) == (piece.width, piece.height)
    print(f"cap={cap} format={piece.format_id} {width}x{height} piece={size / 1e6:.1f} MB in {elapsed:.1f} s")
    time.sleep(GAP_S)


def _download_whole(extractor: YtDlpExtractor, video_id: str, format_id: str, folder: Path) -> Path:
    """ไฟล์เต็มของ format เดียวกับชิ้น ผ่านทางโหลดของแอพ (ไว้เทียบภาพเท่านั้น) · ขนาดที่ประเมินเกิน MAX_WHOLE_BYTES = ไม่โหลด"""

    def choose(info: dict) -> DownloadChoice:
        fmt = next(f for f in info["formats"] if f.get("format_id") == format_id)
        size = fmt.get("filesize") or fmt.get("filesize_approx")
        if not size and fmt.get("tbr") and info.get("duration"):
            size = int(fmt["tbr"] * 125 * info["duration"])  # tbr = kbit/s
        assert size, f"ไม่รู้ขนาดของ format {format_id} จึงไม่โหลดทั้งไฟล์"
        print(f"whole file: format={format_id} about {size / 1e6:.1f} MB")
        assert size <= MAX_WHOLE_BYTES, f"format {format_id} ประเมิน {size / 1e6:.0f} MB เกินเพดาน {MAX_WHOLE_BYTES / 1e6:.0f} MB"
        return DownloadChoice(format_spec=format_id, merge_mp4=False, audio_language=None, notes=(), expected_bytes=None)

    hooks = DownloadHooks(on_stage=lambda stage: None, on_progress=lambda *_: None, is_cancelled=lambda: False, ffmpeg_location=None)
    folder.mkdir(parents=True, exist_ok=True)
    return extractor.download(video_id, choose, folder, hooks).path


def test_frame_from_the_piece_matches_the_whole_file_near_a_segment_boundary(work: Path) -> None:
    """avc1 จริงมี B-frame และ edit list: ภาพจากชิ้น (init + ท่อนเดียว) ต้องเป็นเฟรมเดียวกับภาพจากไฟล์เต็มของ format
    เดียวกันที่รอยต่อท่อน: ต้นท่อน (S และ S+100 ms) และท้ายท่อนก่อนหน้า (S-100 ms)
    เกณฑ์เข้ม (SAME_FRAME_MAX_DIFF) จึงจับการเลื่อน 1-3 เฟรมได้ และมีตัวควบคุมเชิงลบ: เฟรมถัดไปต้องต่างอย่างวัดได้"""
    extractor = YtDlpExtractor()
    video_id = CLIPS["landscape"]
    piece = extractor.fetch_frame_piece(video_id, AT_MS, BOUNDARY_CAP, work / "piece.mp4")
    start = piece.segment_start_ms
    assert start > 0, "ท่อนแรกของคลิปไม่มีรอยต่อให้ตรวจ"
    time.sleep(GAP_S)
    before = extractor.fetch_frame_piece(video_id, start - 100, BOUNDARY_CAP, work / "before.mp4")
    assert before.format_id == piece.format_id
    assert before.segment_start_ms < start <= before.segment_start_ms + 15_000
    for each in (piece, before):
        _assert_piece_starts_at_segment(each)
    time.sleep(GAP_S)

    whole = _download_whole(extractor, video_id, piece.format_id, work / "whole")
    _, period = _first_frame(piece.path)
    # ceil: ffmpeg ให้เฟรมแรกที่เวลา >= t จึงต้องเลื่อนเกินช่วงหนึ่งเฟรม (เช่น 33.33 ms) ถึงได้เฟรมอื่นแน่ ๆ (round/floor = 33 อาจได้เฟรมเดิม)
    next_frame_ms = math.ceil(period * 1000)
    cases = [
        ("start", start, piece),
        ("start+100ms", start + 100, piece),
        ("end-of-previous-segment", start - 100, before),
    ]
    for name, t_ms, src in cases:
        from_piece = work / f"piece-{name}.jpg"
        from_whole = work / f"whole-{name}.jpg"
        control = work / f"control-{name}.jpg"
        piece_size = _cut(src.path, from_piece, t_ms, src)
        assert _cut(whole, from_whole, t_ms, None) == piece_size, name
        _cut(whole, control, t_ms + next_frame_ms, None)  # หนึ่งเฟรมถัดไปของไฟล์เต็ม
        same = _mean_diff(from_piece, from_whole)
        other = _mean_diff(from_piece, control)
        print(f"{name}: t={t_ms} ms {piece_size[0]}x{piece_size[1]} same-frame diff {same:.3f} next-frame diff {other:.3f}")
        assert other >= CONTROL_MIN_DIFF, f"{name}: ฉากนิ่งเกินไป (เฟรมถัดไปต่างแค่ {other:.3f}) เปลี่ยน AT_MS ไปฉากที่เคลื่อนไหว"
        assert same <= SAME_FRAME_MAX_DIFF, f"{name}: ภาพจากชิ้นไม่ใช่เฟรมเดียวกับไฟล์เต็ม (ต่าง {same:.3f})"
