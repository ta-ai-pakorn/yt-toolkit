from __future__ import annotations

import io
import json
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from yttoolkit.core import storyboard
from yttoolkit.core.db import Database
from yttoolkit.core.extractor import FakeExtractor
from yttoolkit.core.storyboard import (
    build,
    get_storyboard,
    pick_storyboard,
    plan_frames,
)
from yttoolkit.core.videos import VideoService
from yttoolkit.core.yterrors import YtError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
BBB = "aqz-KE-bpKQ"
VID = "abcdefghijk"
CW, CH = 64, 36  # ขนาดช่องของกริดสังเคราะห์ (เล็กเพื่อให้เทสเร็ว)

COLORS = [
    (230, 30, 30), (30, 200, 30), (30, 30, 230),
    (230, 230, 30), (30, 230, 230), (230, 30, 230),
    (250, 140, 20), (120, 20, 200), (20, 120, 100),
]  # fmt: skip


def make_grid(
    cells: int, rows: int = 3, columns: int = 3, offset: int = 0, fmt: str = "JPEG"
) -> bytes:
    """กริดสีล้วนช่องละสี + เลขช่องวาดที่มุมซ้ายบน (ตำแหน่งกลางช่องยังเป็นสีล้วน)"""
    per_row = min(cells, columns)
    used_rows = -(-cells // columns)
    image = Image.new("RGB", (per_row * CW, min(used_rows, rows) * CH), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    for cell in range(cells):
        x, y = (cell % columns) * CW, (cell // columns) * CH
        draw.rectangle((x, y, x + CW - 1, y + CH - 1), fill=COLORS[(cell + offset) % 9])
        draw.text((x + 2, y + 2), str(cell), fill=(255, 255, 255))
    out = io.BytesIO()
    image.save(out, fmt)
    return out.getvalue()


def make_sb(fragment_durations: list[float], fps: float = 0.25, **extra) -> dict:
    return {
        "format_id": "sb0",
        "format_note": "storyboard",
        "width": CW,
        "height": CH,
        "rows": 3,
        "columns": 3,
        "fps": fps,
        "fragments": [
            {"url": f"https://x.invalid/M{n}.jpg", "duration": d}
            for n, d in enumerate(fragment_durations)
        ],
        **extra,
    }


def make_raw(sb: dict | list[dict], duration: float = 100) -> dict:
    return {
        "id": VID,
        "duration": duration,
        "formats": sb if isinstance(sb, list) else [sb],
    }


def close(pixel: tuple[int, ...], expected: tuple[int, ...], tol: int = 24) -> bool:
    return all(abs(a - b) <= tol for a, b in zip(pixel, expected, strict=True))


# ---------- pick_storyboard ----------


def test_picks_largest_area() -> None:
    small = {**make_sb([10]), "format_id": "sb1", "width": 160, "height": 90}
    big = {**make_sb([10]), "format_id": "sb0", "width": 320, "height": 180}
    assert pick_storyboard(make_raw([small, big]))["format_id"] == "sb0"


def test_tie_breaks_on_lowest_format_number() -> None:
    a = {**make_sb([10]), "format_id": "sb2"}
    b = {**make_sb([10]), "format_id": "sb10"}
    c = {**make_sb([10]), "format_id": "sb1"}
    assert pick_storyboard(make_raw([a, b, c]))["format_id"] == "sb1"


def test_none_without_storyboard_or_fragments() -> None:
    video = {"format_id": "137", "format_note": "1080p", "height": 1080}
    empty = {**make_sb([]), "fragments": []}
    assert pick_storyboard(make_raw([video])) is None
    assert pick_storyboard(make_raw([video, empty])) is None
    assert pick_storyboard({"formats": None}) is None


def test_skips_storyboards_with_missing_geometry() -> None:
    broken = {
        "format_id": "sb0",
        "format_note": "storyboard",
        "fragments": [{"url": "u"}],
    }
    ok = {**make_sb([10]), "format_id": "sb3", "width": 48, "height": 27}
    assert pick_storyboard(make_raw([broken, ok]))["format_id"] == "sb3"


def test_picks_sb0_of_real_bbb_fixture() -> None:
    raw = json.loads((FIXTURES / "probe" / f"{BBB}.json").read_text(encoding="utf-8"))
    sb = pick_storyboard(raw)
    assert (sb["format_id"], sb["width"], sb["height"]) == ("sb0", 320, 180)


# ---------- plan_frames ----------


def test_plan_counts_frames_per_fragment_and_spacing() -> None:
    # fps 0.25 -> ห่าง 4000 ms; แผ่น 36 วิ = 9 เฟรม, แผ่น 8 วิ = 2 เฟรม
    frames = plan_frames(make_sb([36, 8]), duration_s=44)
    assert len(frames) == 11
    assert [f.t_ms for f in frames] == [i * 4000 for i in range(11)]
    assert [f.index for f in frames] == list(range(11))
    assert [(f.fragment, f.cell) for f in frames[8:11]] == [(0, 8), (1, 0), (1, 1)]


def test_plan_drops_frames_past_duration() -> None:
    frames = plan_frames(make_sb([36, 8]), duration_s=17)
    assert [f.t_ms for f in frames] == [0, 4000, 8000, 12000, 16000]


def test_plan_keeps_frame_exactly_at_duration() -> None:
    assert plan_frames(make_sb([36]), duration_s=16)[-1].t_ms == 16000


def test_plan_caps_at_grid_capacity() -> None:
    frames = plan_frames(make_sb([400]), duration_s=1000)
    assert len(frames) == 9


def test_plan_without_duration_keeps_everything() -> None:
    assert len(plan_frames(make_sb([36, 8]), duration_s=None)) == 11


def test_plan_interval_is_rounded_from_fps() -> None:
    frames = plan_frames(make_sb([200], fps=0.2015748031496063), duration_s=635)
    assert frames[1].t_ms == round(1000 / 0.2015748031496063) == 4961


# ---------- build ----------


def fetch_from(grids: dict[str, bytes], calls: list[str] | None = None):
    def fetch(url: str) -> bytes:
        if calls is not None:
            calls.append(url)
        return grids[url]

    return fetch


def test_build_crops_cells_to_right_colours_in_order(tmp_path: Path) -> None:
    # 3 แผ่น: 9 + 9 + 2 ช่อง; แผ่นที่ 2 เลื่อนสีไป 4 ช่องเพื่อแยกแยะจากแผ่นแรก
    sb = make_sb([36, 36, 8])
    grids = {
        "https://x.invalid/M0.jpg": make_grid(9),
        "https://x.invalid/M1.jpg": make_grid(9, offset=4),
        "https://x.invalid/M2.jpg": make_grid(2, offset=1),
    }
    index = build(VID, make_raw(sb, duration=200), tmp_path, fetch_from(grids))
    assert index["intervalMs"] == 4000
    assert len(index["frames"]) == 20
    expected = (
        [COLORS[c] for c in range(9)]
        + [COLORS[(c + 4) % 9] for c in range(9)]
        + [COLORS[(c + 1) % 9] for c in range(2)]
    )
    for frame, colour in zip(index["frames"], expected, strict=True):
        with Image.open(tmp_path / "storyboard" / frame["file"]) as image:
            assert image.size == (CW, CH)
            assert image.format == "JPEG"
            assert close(image.getpixel((CW - 6, CH - 6)), colour), frame["index"]


def test_build_index_shape_and_files(tmp_path: Path) -> None:
    sb = make_sb([36])
    build(
        VID,
        make_raw(sb),
        tmp_path,
        fetch_from({"https://x.invalid/M0.jpg": make_grid(9)}),
    )
    folder = tmp_path / "storyboard"
    on_disk = json.loads((folder / "index.json").read_text(encoding="utf-8"))
    assert set(on_disk) == {"intervalMs", "frames"}
    assert on_disk["frames"][3] == {"index": 3, "tMs": 12000, "file": "f_0003.jpg"}
    assert sorted(p.name for p in folder.iterdir()) == sorted(
        ["index.json", *(f"f_{i:04d}.jpg" for i in range(9))]
    )
    assert [p.name for p in tmp_path.iterdir()] == [
        "storyboard"
    ]  # ไม่มีโฟลเดอร์ชั่วคราวเหลือ


def test_build_excludes_cells_past_duration(tmp_path: Path) -> None:
    sb = make_sb([36])
    index = build(
        VID,
        make_raw(sb, duration=10),
        tmp_path,
        fetch_from({"https://x.invalid/M0.jpg": make_grid(9)}),
    )
    assert [f["tMs"] for f in index["frames"]] == [0, 4000, 8000]
    assert len(list((tmp_path / "storyboard").glob("f_*.jpg"))) == 3


def test_build_uses_format_cell_size_for_partial_last_grid(tmp_path: Path) -> None:
    # แผ่นท้ายกว้างแค่ 2 ช่อง ต้องตัดตามขนาดช่องของ format ไม่ใช่ความกว้างแผ่น ÷ columns
    sb = make_sb([36, 8])
    grids = {
        "https://x.invalid/M0.jpg": make_grid(9),
        "https://x.invalid/M1.jpg": make_grid(2),
    }
    index = build(VID, make_raw(sb), tmp_path, fetch_from(grids))
    assert len(index["frames"]) == 11
    with Image.open(tmp_path / "storyboard" / "f_0010.jpg") as image:
        assert image.size == (CW, CH)
        assert close(image.getpixel((CW - 6, CH - 6)), COLORS[1])


def test_build_reads_webp_grids_and_saves_real_jpeg(tmp_path: Path) -> None:
    sb = make_sb([36])
    grids = {"https://x.invalid/M0.jpg": make_grid(9, fmt="WEBP")}
    index = build(VID, make_raw(sb), tmp_path, fetch_from(grids))
    with Image.open(tmp_path / "storyboard" / index["frames"][0]["file"]) as image:
        assert image.format == "JPEG"
        assert image.mode == "RGB"


def test_cache_hit_makes_no_fetch(tmp_path: Path) -> None:
    sb = make_sb([36])
    calls: list[str] = []
    fetch = fetch_from({"https://x.invalid/M0.jpg": make_grid(9)}, calls)
    first = build(VID, make_raw(sb), tmp_path, fetch)
    assert len(calls) == 1

    def boom(url: str) -> bytes:
        raise AssertionError("cache hit ต้องไม่โหลดซ้ำ")

    assert build(VID, make_raw(sb), tmp_path, boom) == first
    assert (
        build(VID, {"formats": []}, tmp_path, boom) == first
    )  # แม้ข้อมูลดิบว่างก็ยังใช้ cache


def test_corrupt_index_is_rebuilt(tmp_path: Path) -> None:
    sb = make_sb([36])
    fetch = fetch_from({"https://x.invalid/M0.jpg": make_grid(9)})
    build(VID, make_raw(sb), tmp_path, fetch)
    (tmp_path / "storyboard" / "index.json").write_text("{not json", encoding="utf-8")
    index = build(VID, make_raw(sb), tmp_path, fetch)
    assert len(index["frames"]) == 9
    assert (
        json.loads((tmp_path / "storyboard" / "index.json").read_text(encoding="utf-8"))
        == index
    )


def test_missing_storyboard_raises_e_no_storyboard(tmp_path: Path) -> None:
    video = {"format_id": "137", "format_note": "1080p", "height": 1080}
    with pytest.raises(YtError) as info:
        build(VID, make_raw(video), tmp_path, fetch_from({}))
    assert info.value.code == "E_NO_STORYBOARD"
    assert not (tmp_path / "storyboard").exists()


def test_invalid_video_id_rejected_before_touching_disk(tmp_path: Path) -> None:
    with pytest.raises(YtError) as info:
        build("../evil", make_raw(make_sb([36])), tmp_path / "x", fetch_from({}))
    assert info.value.code == "E_INVALID_INPUT"
    assert not (tmp_path / "x").exists()


def test_fetch_failure_removes_partial_files_and_propagates(tmp_path: Path) -> None:
    sb = make_sb([36, 36, 36])
    grids = {
        "https://x.invalid/M0.jpg": make_grid(9),
        "https://x.invalid/M2.jpg": make_grid(9),
    }

    def fetch(url: str) -> bytes:
        if url.endswith("M1.jpg"):
            raise YtError("E_NETWORK", "หลุด")
        return grids[url]

    with pytest.raises(YtError) as info:
        build(VID, make_raw(sb, duration=200), tmp_path, fetch, max_workers=1)
    assert info.value.code == "E_NETWORK"
    assert list(tmp_path.iterdir()) == []


def test_undecodable_grid_is_network_error_and_cleans_up(tmp_path: Path) -> None:
    sb = make_sb([36])
    with pytest.raises(YtError) as info:
        build(
            VID,
            make_raw(sb),
            tmp_path,
            fetch_from({"https://x.invalid/M0.jpg": b"<html>403</html>"}),
        )
    assert info.value.code == "E_NETWORK"
    assert list(tmp_path.iterdir()) == []


def test_truncated_grid_is_network_error(tmp_path: Path) -> None:
    sb = make_sb([36])
    small = make_grid(4)  # ต้องการ 9 ช่องแต่ได้ 4
    with pytest.raises(YtError) as info:
        build(
            VID, make_raw(sb), tmp_path, fetch_from({"https://x.invalid/M0.jpg": small})
        )
    assert info.value.code == "E_NETWORK"
    assert list(tmp_path.iterdir()) == []


def test_stale_tmp_dirs_are_swept(tmp_path: Path) -> None:
    stale = tmp_path / "storyboard.tmp-deadbeef"
    stale.mkdir()
    (stale / "f_0000.jpg").write_bytes(b"x")
    build(
        VID,
        make_raw(make_sb([36])),
        tmp_path,
        fetch_from({"https://x.invalid/M0.jpg": make_grid(9)}),
    )
    assert not stale.exists()


def test_concurrent_builds_of_same_video_run_once(tmp_path: Path) -> None:
    sb = make_sb([36, 36])
    grids = {
        "https://x.invalid/M0.jpg": make_grid(9),
        "https://x.invalid/M1.jpg": make_grid(9),
    }
    calls: list[str] = []

    def slow(url: str) -> bytes:
        calls.append(url)
        time.sleep(0.15)
        return grids[url]

    results: list[dict] = []
    errors: list[BaseException] = []

    def work() -> None:
        try:
            results.append(build(VID, make_raw(sb, duration=200), tmp_path, slow))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
    assert not errors
    assert len(results) == 5
    assert all(r == results[0] for r in results)
    assert sorted(calls) == sorted(grids)  # แต่ละแผ่นโหลดแค่ครั้งเดียว


def test_different_videos_build_in_parallel(tmp_path: Path) -> None:
    sb = make_sb([36])
    grid = make_grid(9)
    barrier = threading.Barrier(2, timeout=5)

    def meet(url: str) -> bytes:
        barrier.wait()  # ผ่านได้ก็ต่อเมื่อทั้งสองคลิปกำลังโหลดพร้อมกัน
        return grid

    errors: list[BaseException] = []

    def work(video_id: str) -> None:
        try:
            build(video_id, make_raw(sb), tmp_path / video_id, meet)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [
        threading.Thread(target=work, args=(v,)) for v in ("abcdefghijk", "kjihgfedcba")
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
    assert not errors


# ---------- ข้อมูลจริง (BBB) ----------


def bbb_raw() -> dict:
    return json.loads((FIXTURES / "probe" / f"{BBB}.json").read_text(encoding="utf-8"))


def test_real_bbb_fixture_gives_128_frames(tmp_path: Path) -> None:
    raw = bbb_raw()
    sb = pick_storyboard(raw)
    fake = FakeExtractor(FIXTURES)
    index = build(BBB, raw, tmp_path, fake.fetch)
    assert len(index["frames"]) == 128
    assert index["intervalMs"] == round(1000 / sb["fps"]) == 4961
    assert index["frames"][1]["tMs"] == 4961
    assert index["frames"][-1]["tMs"] == 127 * 4961 <= 635000
    assert sum(1 for c in fake.calls if c[0] == "fetch") == 15
    with Image.open(tmp_path / "storyboard" / "f_0127.jpg") as image:
        assert (image.size, image.format) == ((320, 180), "JPEG")


def test_real_bbb_build_is_fast_without_network(tmp_path: Path) -> None:
    raw = bbb_raw()
    fake = FakeExtractor(FIXTURES)
    sb = pick_storyboard(raw)
    preloaded = {
        f["url"]: fake.fetch(f["url"]) for f in sb["fragments"]
    }  # ไม่นับเวลาโหลด
    started = time.perf_counter()
    build(BBB, raw, tmp_path, preloaded.__getitem__)
    assert time.perf_counter() - started < 2.0


# ---------- get_storyboard ----------


@pytest.fixture
def videos(tmp_path: Path):
    db = Database(tmp_path / "app.db")
    db.migrate()
    fake = FakeExtractor(FIXTURES)
    service = VideoService(db, fake, now=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC))
    service.fake = fake  # type: ignore[attr-defined]
    yield service
    db.close()


def test_get_storyboard_builds_from_video_service(
    tmp_path: Path, videos: VideoService
) -> None:
    index = get_storyboard(BBB, videos, tmp_path / "cache", videos.fake.fetch)  # type: ignore[attr-defined]
    assert len(index["frames"]) == 128
    assert (tmp_path / "cache" / BBB / "storyboard" / "index.json").is_file()


def test_get_storyboard_refreshes_probe_once_on_network_error(
    tmp_path: Path, videos: VideoService
) -> None:
    fake = videos.fake  # type: ignore[attr-defined]
    videos.get(BBB)
    probes_before = sum(1 for c in fake.calls if c[0] == "probe")
    state = {"failed": False}

    def flaky(url: str) -> bytes:
        if not state["failed"]:
            state["failed"] = True
            raise YtError("E_NETWORK", "ลิงก์หมดอายุ")
        return fake.fetch(url)

    index = get_storyboard(BBB, videos, tmp_path / "cache", flaky)
    assert len(index["frames"]) == 128
    assert sum(1 for c in fake.calls if c[0] == "probe") == probes_before + 1


def test_get_storyboard_does_not_loop_on_repeated_network_error(
    tmp_path: Path, videos: VideoService
) -> None:
    fake = videos.fake  # type: ignore[attr-defined]
    videos.get(BBB)
    probes_before = sum(1 for c in fake.calls if c[0] == "probe")
    attempts: list[str] = []

    def dead(url: str) -> bytes:
        attempts.append(url)
        raise YtError("E_NETWORK", "หลุด")

    with pytest.raises(YtError) as info:
        get_storyboard(BBB, videos, tmp_path / "cache", dead)
    assert info.value.code == "E_NETWORK"
    assert (
        sum(1 for c in fake.calls if c[0] == "probe") == probes_before + 1
    )  # refresh แค่ครั้งเดียว
    assert not (tmp_path / "cache" / BBB / "storyboard").exists()


def test_get_storyboard_does_not_refresh_on_other_errors(
    tmp_path: Path, videos: VideoService
) -> None:
    fake = videos.fake  # type: ignore[attr-defined]
    videos.get("jNQXAC9IVRw")
    probes_before = sum(1 for c in fake.calls if c[0] == "probe")
    with pytest.raises(YtError) as info:
        get_storyboard("jNQXAC9IVRw", videos, tmp_path / "cache", fake.fetch)
    assert info.value.code == "E_NO_STORYBOARD"
    assert sum(1 for c in fake.calls if c[0] == "probe") == probes_before


def test_get_storyboard_rejects_bad_id(tmp_path: Path, videos: VideoService) -> None:
    with pytest.raises(YtError) as info:
        get_storyboard("../x", videos, tmp_path, lambda url: b"")
    assert info.value.code == "E_INVALID_INPUT"


def test_module_does_not_import_api_or_platform() -> None:
    text = Path(storyboard.__file__).read_text(encoding="utf-8")
    assert "yttoolkit.api" not in text
    assert "yttoolkit.platform" not in text
    assert "import yt_dlp" not in text
