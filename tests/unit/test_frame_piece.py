"""ภาพคมตรงจุด (M5 รอบ B2 spec 3.1): อ่าน sidx (v0/v1, กล่องเลย 64 KB, รอยต่อ, เลยท้าย) เลือก format และประกอบชิ้น"""

from __future__ import annotations

import ast
import struct
from pathlib import Path

import pytest

from yttoolkit.core import frame_piece
from yttoolkit.core.frame_piece import (
    HEAD_BYTES,
    MAX_INDEX_BYTES,
    MAX_SEGMENT_BYTES,
    PieceInfo,
    SidxIndex,
    SidxRef,
    fetch_piece,
    max_short_side,
    parse_sidx,
    pick_capture_format,
    piece_info,
    read_index,
    segment_for,
    short_side,
    write_piece,
)
from yttoolkit.core.yterrors import YtError

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "capture" / "piece.mp4"


def _box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def _sidx(version: int, timescale: int, earliest: int, first: int, refs: list[tuple[int, int]]) -> bytes:
    body = struct.pack(">B3xII", version, 1, timescale)
    body += struct.pack(">II", earliest, first) if version == 0 else struct.pack(">QQ", earliest, first)
    body += struct.pack(">HH", 0, len(refs))
    for size, duration in refs:
        body += struct.pack(">III", size, duration, 0x9000_0000)
    return _box(b"sidx", body)


def _file(moov_payload: int = 100, version: int = 1, refs: list[tuple[int, int]] | None = None, earliest: int = 0) -> bytes:
    refs = refs or [(1000, 5000), (1200, 5000), (800, 4000)]
    head = _box(b"ftyp", b"isom\x00\x00\x02\x00") + _box(b"moov", b"\x00" * moov_payload)
    head += _sidx(version, 1000, earliest, 0, refs)
    segments = b"".join(bytes([i + 1]) * size for i, (size, _d) in enumerate(refs))
    return head + segments


class Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.calls: list[tuple[int, int]] = []

    def __call__(self, first: int, last: int) -> bytes:
        self.calls.append((first, last))
        return self.data[first : last + 1]


@pytest.mark.parametrize("version", [0, 1])
def test_parse_sidx_gives_offsets_and_times(version: int) -> None:
    box = _sidx(version, 90_000, 9000, 16, [(500, 450_000), (700, 450_000)])
    index = parse_sidx(box, 1000)
    first = 1000 + len(box) + 16
    assert index == SidxIndex(90_000, (SidxRef(first, 500, 9000, 450_000), SidxRef(first + 500, 700, 459_000, 450_000)))
    assert index.to_ms(9000) == 100 and index.end_ms == 10_100


@pytest.mark.parametrize(
    "box",
    [
        _box(b"sidx", b"\x00" * 10),  # too short
        _box(b"free", b"\x00" * 40),  # not sidx
        _sidx(2, 1000, 0, 0, [(10, 10)]),  # unknown version
        _sidx(0, 0, 0, 0, [(10, 10)]),  # timescale 0
        _sidx(0, 1000, 0, 0, [(0x8000_0010, 10)]),  # reference to another sidx
        _sidx(0, 1000, 0, 0, [(0, 10)]),  # empty segment
        _sidx(0, 1000, 0, 0, [(10, 10), (MAX_SEGMENT_BYTES + 1, 10)]),  # segment bigger than 64 MB
        struct.pack(">I4sQ", 1, b"sidx", 48) + b"\x00" * 32,  # 64-bit box size header
    ],
)
def test_bad_sidx_is_unsupported(box: bytes) -> None:
    with pytest.raises(YtError) as info:
        parse_sidx(box, 0)
    assert info.value.code == "E_CAPTURE_UNSUPPORTED"


def test_read_index_walks_ftyp_and_moov_in_one_request() -> None:
    data = _file()
    reader = Reader(data)
    index = read_index(reader)
    assert reader.calls == [(0, HEAD_BYTES - 1)]
    sidx_end = len(data) - 3000
    assert index.init == data[:sidx_end]
    assert [r.offset for r in index.sidx.refs] == [sidx_end, sidx_end + 1000, sidx_end + 2200]
    assert [index.sidx.to_ms(r.start) for r in index.sidx.refs] == [0, 5000, 10_000]


def test_a_sidx_crossing_64_kb_fetches_the_rest_of_the_box() -> None:
    data = _file(moov_payload=HEAD_BYTES - 60)  # sidx เริ่มก่อน 64 KB นิดเดียว ท้ายกล่องอยู่เลย 64 KB
    reader = Reader(data)
    index = read_index(reader)
    sidx_end = len(data) - 3000
    assert reader.calls == [(0, HEAD_BYTES - 1), (HEAD_BYTES, sidx_end - 1)]
    assert len(index.sidx.refs) == 3


def test_a_box_header_past_64_kb_is_fetched_too() -> None:
    data = _file(moov_payload=HEAD_BYTES + 100)
    index = read_index(Reader(data))
    assert index.sidx.end_ms == 14_000


def test_media_before_any_sidx_is_unsupported() -> None:
    data = _box(b"ftyp", b"isom") + _box(b"moov", b"\x00" * 8) + _box(b"moof", b"\x00" * 8) + _box(b"mdat", b"x")
    with pytest.raises(YtError) as info:
        read_index(Reader(data))
    assert info.value.code == "E_CAPTURE_UNSUPPORTED"


def test_a_sidx_too_far_into_the_file_is_unsupported() -> None:
    data = _file(moov_payload=MAX_INDEX_BYTES)
    with pytest.raises(YtError) as info:
        read_index(Reader(data))
    assert info.value.code == "E_CAPTURE_UNSUPPORTED"


def test_a_bad_box_size_is_unsupported() -> None:
    data = struct.pack(">I4s", 4, b"ftyp") + b"\x00" * 100
    with pytest.raises(YtError) as info:
        read_index(Reader(data))
    assert info.value.code == "E_CAPTURE_UNSUPPORTED"


def test_a_segment_of_exactly_64_mb_is_still_fine() -> None:
    index = parse_sidx(_sidx(0, 1000, 0, 0, [(MAX_SEGMENT_BYTES, 10)]), 0)
    assert index.refs[0].size == MAX_SEGMENT_BYTES


def test_a_top_box_with_a_64_bit_size_is_walked_over() -> None:
    data = _file()
    large = struct.pack(">I4sQ", 1, b"free", 16 + 20) + b"\x00" * 20
    ftyp_end = struct.unpack_from(">I", data, 0)[0]
    data = data[:ftyp_end] + large + data[ftyp_end:]
    index = read_index(Reader(data))
    assert index.init == data[: len(data) - 3000]
    assert [r.offset for r in index.sidx.refs][0] == len(data) - 3000


def test_a_zero_size_box_is_unsupported() -> None:
    data = struct.pack(">I4s", 0, b"free") + b"\x00" * 100
    with pytest.raises(YtError) as info:
        read_index(Reader(data))
    assert info.value.code == "E_CAPTURE_UNSUPPORTED"


def test_a_short_read_is_a_network_error() -> None:
    data = _file(moov_payload=HEAD_BYTES - 60)
    with pytest.raises(YtError) as info:
        read_index(lambda first, last: data[first : min(last + 1, HEAD_BYTES + 4)])
    assert info.value.code == "E_NETWORK"


def test_segment_for_boundaries_before_and_past() -> None:
    index = SidxIndex(1000, (SidxRef(0, 10, 200, 1000), SidxRef(10, 10, 1200, 1000)))
    assert segment_for(index, 0) == index.refs[0]  # ก่อนท่อนแรก (earliest 0.2 s) = ท่อนแรก
    assert segment_for(index, 1199) == index.refs[0]
    assert segment_for(index, 1200) == index.refs[1]  # ตรงรอยต่อ = ท่อนหลัง
    assert segment_for(index, 2199) == index.refs[1]
    assert segment_for(index, 2200) is None


def test_segment_for_uses_exact_timescale_maths() -> None:
    index = SidxIndex(90_000, (SidxRef(0, 1, 0, 450_001), SidxRef(1, 1, 450_001, 450_000)))
    assert segment_for(index, 5000) == index.refs[0]  # 5000 ms = 450_000 หน่วย ยังอยู่ท่อนแรก (ยาว 450_001)
    assert segment_for(index, 5001) == index.refs[1]


def test_fetch_piece_is_init_plus_one_segment() -> None:
    data = _file()
    reader = Reader(data)
    index = read_index(reader)
    piece, ref = fetch_piece(reader, index, 7_500)
    assert ref == index.sidx.refs[1]
    assert piece == index.init + b"\x02" * 1200
    assert reader.calls[-1] == (ref.offset, ref.offset + 1199)
    with pytest.raises(YtError) as past:
        fetch_piece(reader, index, 14_000)
    assert past.value.code == "E_UNKNOWN"
    with pytest.raises(YtError) as short:
        fetch_piece(lambda first, last: data[first:last], index, 0)
    assert short.value.code == "E_NETWORK"


def test_the_committed_fixture_is_a_four_second_dash_file() -> None:
    data = FIXTURE.read_bytes()
    reader = Reader(data)
    index = read_index(reader)
    assert reader.calls == [(0, HEAD_BYTES - 1)]
    assert index.sidx.timescale == 10_240 and len(index.sidx.refs) == 4 and index.sidx.end_ms == 4000
    assert [index.sidx.to_ms(r.start) for r in index.sidx.refs] == [0, 1000, 2000, 3000]
    assert index.sidx.refs[-1].offset + index.sidx.refs[-1].size <= len(data)
    piece, ref = fetch_piece(reader, index, 2550)
    assert index.sidx.to_ms(ref.start) == 2000 and len(piece) == len(index.init) + ref.size


def test_write_piece_creates_the_folder(tmp_path: Path) -> None:
    dest = tmp_path / "work" / "piece.mp4"
    write_piece(dest, b"abc")
    assert dest.read_bytes() == b"abc"


def _fmt(fid: str, w: int | None, h: int, **extra: object) -> dict:
    base = {"format_id": fid, "ext": "mp4", "protocol": "https", "vcodec": "avc1.640028", "acodec": "none",
            "url": f"https://media.invalid/{fid}", "width": w, "height": h}  # fmt: skip
    return {**base, **extra}


def test_max_short_side_maps_the_setting() -> None:
    assert [max_short_side(q) for q in ("max", "1080", "720")] == [2160, 1080, 720]
    with pytest.raises(ValueError):
        max_short_side("4k")


def test_short_side_counts_portrait_by_width() -> None:
    assert short_side({"width": 1080, "height": 1920}) == 1080
    assert short_side({"height": 720}) == 720
    assert short_side({"width": 640}) == 0
    assert short_side({"width": float("inf"), "height": float("nan")}) == 0  # ค่าไม่จำกัด/ไม่ใช่ตัวเลข = ไม่รู้ขนาด
    assert short_side({"width": 1920, "height": float("inf")}) == 0


def test_pick_prefers_the_largest_short_side_under_the_cap() -> None:
    formats = [_fmt("137", 1920, 1080), _fmt("136", 1280, 720), _fmt("401", 3840, 2160, vcodec="av01.0.12M.08")]
    assert pick_capture_format({"formats": formats}, None)["format_id"] == "401"
    assert pick_capture_format({"formats": formats}, 1080)["format_id"] == "137"
    assert pick_capture_format({"formats": formats}, 720)["format_id"] == "136"
    portrait = [_fmt("p1080", 1080, 1920), _fmt("p720", 720, 1280)]
    assert pick_capture_format({"formats": portrait}, 1080)["format_id"] == "p1080"  # ด้านสั้น 1080 ไม่เกินเพดาน


def test_max_means_up_to_4k_and_leaves_8k_out() -> None:
    formats = [
        _fmt("8k", 7680, 4320, vcodec="av01.0.17M.08"),
        _fmt("4k", 3840, 2160, vcodec="av01.0.12M.08"),
        _fmt("4k-portrait", 2160, 3840, vcodec="av01.0.12M.08"),
    ]
    cap = max_short_side("max")
    assert pick_capture_format({"formats": formats}, cap)["format_id"] == "4k"
    assert pick_capture_format({"formats": formats[2:]}, cap)["format_id"] == "4k-portrait"
    assert pick_capture_format({"formats": formats[:1]}, cap)["format_id"] == "8k"  # ไม่มีตัวใต้เพดาน = ตัวเล็กสุดที่เหนือเพดาน


def test_pick_order_sdr_then_avc1_then_smallest() -> None:
    same = [
        _fmt("hdr", 1920, 1080, dynamic_range="HDR10"),
        _fmt("av1", 1920, 1080, vcodec="av01.0.08M.08", dynamic_range="SDR", filesize=10),
        _fmt("big", 1920, 1080, filesize=900),
        _fmt("small", 1920, 1080, filesize=500),
    ]
    assert pick_capture_format({"formats": same}, None)["format_id"] == "small"
    assert pick_capture_format({"formats": same[:2]}, None)["format_id"] == "av1"
    assert pick_capture_format({"formats": same[:1]}, None)["format_id"] == "hdr"


def test_pick_skips_everything_that_has_no_sidx_mp4() -> None:
    formats = [
        _fmt("webm", 1920, 1080, ext="webm", vcodec="vp9"),
        _fmt("hls", 1920, 1080, protocol="m3u8_native"),
        _fmt("muxed", 1280, 720, acodec="mp4a.40.2"),
        _fmt("audio", None, 0, vcodec="none", acodec="mp4a.40.2"),
        _fmt("nourl", 1920, 1080, url=""),
        {"format_id": "sb0", "ext": "mhtml", "protocol": "mhtml", "vcodec": "none"},
    ]
    assert pick_capture_format({"formats": formats}, None) is None
    assert pick_capture_format({}, None) is None


def test_nothing_under_the_cap_takes_the_smallest_above() -> None:
    formats = [_fmt("2160", 3840, 2160), _fmt("1440", 2560, 1440)]
    assert pick_capture_format({"formats": formats}, 720)["format_id"] == "1440"


def test_piece_info_reads_the_format_facts(tmp_path: Path) -> None:
    index = SidxIndex(1000, (SidxRef(0, 1, 0, 5000), SidxRef(1, 1, 5000, 5000)))
    sdr = piece_info(_fmt("137", 1920, 1080), tmp_path / "p.mp4", index, index.refs[1])
    assert sdr == PieceInfo(tmp_path / "p.mp4", 5000, 1920, 1080, "137", None)
    hdr = piece_info(_fmt("701", 3840, 2160, dynamic_range="HDR10"), tmp_path / "p.mp4", index, index.refs[0])
    assert hdr.dynamic_range == "HDR10" and hdr.segment_start_ms == 0


def test_the_module_never_imports_yt_dlp() -> None:
    tree = ast.parse(Path(frame_piece.__file__).read_text(encoding="utf-8"))
    names = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    names |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert not any(name.split(".")[0] == "yt_dlp" for name in names)
