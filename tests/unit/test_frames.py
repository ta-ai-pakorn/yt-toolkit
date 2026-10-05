from __future__ import annotations

import io
import logging
import math
import unicodedata
import zipfile
from itertools import pairwise
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw, ImageFont, features

from yttoolkit.core import frames
from yttoolkit.core.extractor import FakeExtractor
from yttoolkit.core.frames import (
    CELL_H,
    CELL_W,
    GUTTER,
    HEADER_H,
    MAX_SHEET_FRAMES,
    contact_sheet,
    file_timecode,
    frame_file_names,
    frames_zip,
    timecode,
)
from yttoolkit.core.storyboard import build
from yttoolkit.core.yterrors import YtError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
BBB = "aqz-KE-bpKQ"
THAI_TITLE = "ทดสอบภาษาไทย ผู้ใหญ่ ปั๊มน้ำ ที่นี่"
BG = (0x0E, 0x0F, 0x11)


def make_frame(path: Path, color: tuple[int, int, int], size=(CELL_W, CELL_H)) -> Path:
    Image.new("RGB", size, color).save(path, "JPEG", quality=95)
    return path


@pytest.fixture
def white(tmp_path: Path) -> Path:
    return make_frame(tmp_path / "white.jpg", (255, 255, 255))


def items(path: Path, count: int, step_ms: int = 5000) -> list[tuple[int, Path]]:
    return [(i * step_ms, path) for i in range(count)]


def decode(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    image.load()
    return image


def cell_origin(index: int, columns: int = 5) -> tuple[int, int]:
    row, col = divmod(index, columns)
    return (
        GUTTER + col * (CELL_W + GUTTER),
        HEADER_H + GUTTER + row * (CELL_H + GUTTER),
    )


def close(pixel, expected, tolerance=12) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(pixel, expected, strict=True))


# ---------- timecode ----------


@pytest.mark.parametrize(
    ("ms", "expected"),
    [
        (0, "00:00:00"),
        (999, "00:00:00"),
        (1000, "00:00:01"),
        (4961, "00:00:04"),
        (61_000, "00:01:01"),
        (3_661_999, "01:01:01"),
        (127 * 4961, "00:10:30"),
        (100 * 3_600_000, "100:00:00"),
        (-5, "00:00:00"),
    ],
)
def test_timecode_floors_and_always_shows_hours(ms: int, expected: str) -> None:
    assert timecode(ms) == expected


def test_file_timecode_uses_dashes() -> None:
    assert file_timecode(3_661_999) == "01-01-01"
    assert file_timecode(0) == "00-00-00"


# ---------- fonts ----------


def test_fonts_are_bundled_with_licence() -> None:
    fonts = Path(frames.__file__).resolve().parents[1] / "assets" / "fonts"
    for name in (
        "IBMPlexSansThai-Regular.ttf",
        "IBMPlexSansThai-SemiBold.ttf",
        "OFL.txt",
    ):
        assert (fonts / name).is_file(), name


def test_font_is_loaded_once_per_weight_and_size() -> None:
    assert frames.load_font("regular", 14) is frames.load_font("regular", 14)
    assert frames.load_font("regular", 14) is not frames.load_font("semibold", 14)


@pytest.mark.parametrize("weight", ["regular", "semibold"])
def test_thai_title_has_no_tofu(weight: str) -> None:
    font = frames.load_font(weight, 28)
    notdef = font.getmask("￿")
    for char in THAI_TITLE.replace(" ", ""):
        mask = font.getmask(char)
        assert mask.getbbox() is not None, f"{char!r} has no glyph"
        assert (mask.size, bytes(mask)) != (notdef.size, bytes(notdef)), (
            f"{char!r} draws as the notdef box"
        )
    assert font.getmask("ก").size != (0, 0)
    assert bytes(font.getmask("ก")) != bytes(notdef)


def test_layout_engine_choice_is_logged_once(caplog: pytest.LogCaptureFixture) -> None:
    frames._layout_engine.cache_clear()
    with caplog.at_level(logging.INFO, logger="yttoolkit"):
        first = frames._layout_engine()
        second = frames._layout_engine()
    assert first == second
    assert first in (ImageFont.Layout.RAQM, ImageFont.Layout.BASIC)
    assert len([r for r in caplog.records if "raqm" in r.getMessage().lower()]) == 1


# ---------- contact sheet: layout (AC-FRAME-05) ----------


def test_sheet_width_is_five_columns_plus_gutters(white: Path) -> None:
    image = decode(contact_sheet(items(white, 3), "x", 60))
    assert image.format == "JPEG"
    assert image.width == 5 * CELL_W + 6 * GUTTER == 1648


@pytest.mark.parametrize("count", [1, 5, 6, 11, 12, 128])
def test_sheet_rows_are_ceil_n_over_5(white: Path, count: int) -> None:
    image = decode(contact_sheet(items(white, count), "x", 60))
    rows = math.ceil(count / 5)
    assert image.height == HEADER_H + rows * (CELL_H + GUTTER) + GUTTER


def test_sheet_honours_custom_columns(white: Path) -> None:
    image = decode(contact_sheet(items(white, 7), "x", 60, columns=3))
    assert image.width == 3 * CELL_W + 4 * GUTTER
    assert image.height == HEADER_H + 3 * (CELL_H + GUTTER) + GUTTER


def test_sheet_places_each_frame_in_reading_order(tmp_path: Path) -> None:
    colors = [(230, 30, 30), (30, 200, 30), (30, 30, 230), (230, 230, 30)]
    paths = [make_frame(tmp_path / f"c{i}.jpg", c) for i, c in enumerate(colors)]
    data = contact_sheet(
        [(i * 1000, p) for i, p in enumerate(paths)], "x", 10, columns=2
    )
    image = decode(data)
    for i, color in enumerate(colors):
        x, y = cell_origin(i, columns=2)
        assert close(image.getpixel((x + 40, y + 40)), color), i


def test_sheet_letterboxes_frames_of_other_sizes(tmp_path: Path) -> None:
    tall = make_frame(tmp_path / "tall.jpg", (200, 40, 40), size=(90, 160))
    image = decode(contact_sheet([(0, tall)], "x", 10))
    x, y = cell_origin(0)
    assert close(image.getpixel((x + CELL_W // 2, y + 40)), (200, 40, 40))
    assert close(image.getpixel((x + 5, y + 40)), (0, 0, 0))  # แถบดำข้างภาพแนวตั้ง


def test_sheet_draws_timecode_badge_bottom_right(white: Path) -> None:
    image = decode(contact_sheet([(3_661_000, white)], "x", 4000))
    x, y = cell_origin(0)
    # ต้นฉบับขาวล้วน: มุมขวาล่างในป้ายถูกทับด้วยดำโปร่ง 65% จึงต้องคล้ำลงชัดเจน
    corner = image.getpixel((x + CELL_W - 8, y + CELL_H - 8))
    assert sum(corner) / 3 < 140
    # ส่วนอื่นของช่องยังขาว
    assert close(image.getpixel((x + 20, y + 20)), (255, 255, 255))


def test_sheet_header_uses_dark_band_with_light_text(white: Path) -> None:
    image = decode(contact_sheet(items(white, 2), THAI_TITLE, 635))
    assert close(image.getpixel((3, 3)), BG, tolerance=4)
    header = image.crop((0, 0, image.width, HEADER_H)).convert("L")
    assert header.getextrema()[1] > 200  # มีตัวหนังสือสว่าง


def test_sheet_title_actually_renders_in_header(white: Path) -> None:
    blank = decode(contact_sheet(items(white, 1), "", 635))
    titled = decode(contact_sheet(items(white, 1), THAI_TITLE, 635))
    box = (0, 0, titled.width, 56)
    assert blank.crop(box).tobytes() != titled.crop(box).tobytes()


def test_sheet_is_jpeg_quality_88(white: Path) -> None:
    image = decode(contact_sheet(items(white, 1), "x", 1))
    reference = io.BytesIO()
    Image.new("RGB", (16, 16)).save(reference, "JPEG", quality=88)
    assert image.quantization[0] == decode(reference.getvalue()).quantization[0]


def test_sheet_rejects_empty_and_bad_columns(white: Path) -> None:
    with pytest.raises(ValueError):
        contact_sheet([], "x", 1)
    with pytest.raises(ValueError):
        contact_sheet(items(white, 1), "x", 1, columns=0)


# ---------- contact sheet: title and cap ----------


def test_short_title_is_kept_and_long_title_truncated_with_ellipsis() -> None:
    font = frames.load_font("semibold", 28)
    assert frames.fit_text(font, "สั้น ๆ", 1000) == "สั้น ๆ"
    long = "ชื่อคลิปที่ยาวมากมาก " * 30
    fitted = frames.fit_text(font, long, 600)
    assert fitted.endswith("…")
    assert fitted != long
    assert font.getlength(fitted) <= 600


def test_truncation_never_splits_a_thai_vowel_or_tone_mark_from_its_base() -> None:
    font = frames.load_font("semibold", 28)
    title = "ปั๊มน้ำ" * 40
    for width in range(200, 420, 7):
        fitted = frames.fit_text(font, title, width)
        kept = fitted.removesuffix("…")
        assert title.startswith(kept)
        if len(kept) < len(title):
            assert unicodedata.category(title[len(kept)]) != "Mn", width


def test_title_whitespace_and_newlines_are_collapsed() -> None:
    font = frames.load_font("semibold", 28)
    assert frames.fit_text(font, " a\n b\t\tc  ", 1000) == "a b c"


def test_summary_line_states_duration_and_count() -> None:
    assert frames.summary_line(635, 128, 128) == "ความยาว 00:10:35 · 128 เฟรม"
    assert frames.LABEL_DURATION == "ความยาว"
    assert frames.LABEL_FRAMES == "เฟรม"
    assert frames.LABEL_SAMPLED == "แสดง {shown} จาก {total} เฟรม"


def test_summary_line_says_sampled_when_capped() -> None:
    assert (
        frames.summary_line(7200, 400, 1451)
        == "ความยาว 02:00:00 · แสดง 400 จาก 1451 เฟรม"
    )


def test_sample_keeps_everything_up_to_cap(white: Path) -> None:
    full = items(white, MAX_SHEET_FRAMES)
    assert frames.sample_frames(full) == full


def test_sample_spreads_evenly_and_keeps_first_and_last(white: Path) -> None:
    many = items(white, 1500, step_ms=1000)
    picked = frames.sample_frames(many)
    assert len(picked) == MAX_SHEET_FRAMES == 400
    assert picked[0] == many[0]
    assert picked[-1] == many[-1]
    times = [t for t, _ in picked]
    assert times == sorted(set(times))
    gaps = {b - a for a, b in pairwise(times)}
    assert max(gaps) - min(gaps) <= 1000  # ห่างเกือบเท่ากันทุกช่วง


def test_sheet_caps_long_videos_at_400_frames(white: Path) -> None:
    data = contact_sheet(items(white, 1500), "คลิปยาว", 7200)
    image = decode(data)
    assert image.height == HEADER_H + 80 * (CELL_H + GUTTER) + GUTTER


# ---------- real data ----------


def test_real_bbb_frames_make_a_full_sheet(tmp_path: Path) -> None:
    raw = FakeExtractor(FIXTURES).probe(BBB)
    fake = FakeExtractor(FIXTURES)
    index = build(BBB, raw, tmp_path, fake.fetch)
    folder = tmp_path / "storyboard"
    listed = [(f["tMs"], folder / f["file"]) for f in index["frames"]]
    image = decode(contact_sheet(listed, raw["title"], int(raw["duration"])))
    assert image.width == 1648
    assert image.height == HEADER_H + math.ceil(128 / 5) * (CELL_H + GUTTER) + GUTTER


# ---------- zip (AC-FRAME-06) ----------


def unzip(data: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(data))


def test_zip_has_one_named_entry_per_frame(tmp_path: Path) -> None:
    paths = [make_frame(tmp_path / f"{i}.jpg", (i * 20, 0, 0)) for i in range(3)]
    data = frames_zip([(0, paths[0]), (61_000, paths[1]), (3_661_000, paths[2])])
    with unzip(data) as archive:
        assert archive.namelist() == [
            "frame_00-00-00.jpg",
            "frame_00-01-01.jpg",
            "frame_01-01-01.jpg",
        ]
        assert archive.read("frame_00-01-01.jpg") == paths[1].read_bytes()
        assert archive.testzip() is None


def test_zip_suffixes_duplicate_names(white: Path) -> None:
    same_second = [(4000, white), (4100, white), (4999, white), (5000, white)]
    with unzip(frames_zip(same_second)) as archive:
        assert archive.namelist() == [
            "frame_00-00-04.jpg",
            "frame_00-00-04_2.jpg",
            "frame_00-00-04_3.jpg",
            "frame_00-00-05.jpg",
        ]


def test_zip_keeps_the_given_frame_order(white: Path) -> None:
    with unzip(frames_zip([(9000, white), (1000, white)])) as archive:
        assert archive.namelist() == ["frame_00-00-09.jpg", "frame_00-00-01.jpg"]


def test_zip_is_stored_and_deterministic(white: Path) -> None:
    given = items(white, 4)
    first, second = frames_zip(given), frames_zip(given)
    assert first == second
    with unzip(first) as archive:
        for info in archive.infolist():
            assert info.compress_type == zipfile.ZIP_STORED
            assert info.date_time == (1980, 1, 1, 0, 0, 0)


def test_zip_count_matches_a_real_128_frame_set(tmp_path: Path) -> None:
    raw = FakeExtractor(FIXTURES).probe(BBB)
    fake = FakeExtractor(FIXTURES)
    index = build(BBB, raw, tmp_path, fake.fetch)
    folder = tmp_path / "storyboard"
    listed = [(f["tMs"], folder / f["file"]) for f in index["frames"]]
    with unzip(frames_zip(listed)) as archive:
        names = archive.namelist()
    assert len(names) == 128
    assert len(set(names)) == 128
    assert all(n.startswith("frame_") and n.endswith(".jpg") for n in names)


def test_zip_rejects_empty(white: Path) -> None:
    with pytest.raises(ValueError):
        frames_zip([])


# ---------- ไฟล์เฟรมหาย/เสีย ----------


def test_sheet_maps_missing_frame_to_no_storyboard(tmp_path: Path) -> None:
    with pytest.raises(YtError) as caught:
        contact_sheet([(0, tmp_path / "nope.jpg")], "x", 1)
    assert caught.value.code == "E_NO_STORYBOARD"
    assert "nope.jpg" in caught.value.detail
    assert caught.value.detail.startswith(frames.FRAME_FILE_BAD)


def test_sheet_maps_corrupt_frame_to_no_storyboard(tmp_path: Path) -> None:
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"not a jpeg at all")
    with pytest.raises(YtError) as caught:
        contact_sheet([(0, bad)], "x", 1)
    assert caught.value.code == "E_NO_STORYBOARD"


def test_sheet_maps_truncated_frame_to_no_storyboard(
    tmp_path: Path, white: Path
) -> None:
    cut = tmp_path / "cut.jpg"
    cut.write_bytes(white.read_bytes()[:200])
    with pytest.raises(YtError) as caught:
        contact_sheet([(0, cut)], "x", 1)
    assert caught.value.code == "E_NO_STORYBOARD"


def test_zip_maps_missing_frame_to_no_storyboard(tmp_path: Path, white: Path) -> None:
    with pytest.raises(YtError) as caught:
        frames_zip([(0, white), (1000, tmp_path / "gone.jpg")])
    assert caught.value.code == "E_NO_STORYBOARD"
    assert "gone.jpg" in caught.value.detail


# ---------- วางสระ/วรรณยุกต์ไทย (ไม่มี raqm) ----------

needs_basic = pytest.mark.skipif(
    features.check("raqm"), reason="มี raqm: Pillow จัดวางเอง ไม่ใช้ตัวช่วยวาดของเรา"
)
CANVAS = (700, 300)
ORIGIN = (60, 200)  # จุดวาง (x, เส้นบรรทัด)


def render(text: str, *, plain: bool = False, weight: str = "semibold") -> Image.Image:
    font = frames.load_font(weight, 64)
    image = Image.new("L", CANVAS, 0)
    draw = ImageDraw.Draw(image)
    if plain:
        draw.text(ORIGIN, text, font=font, fill=255, anchor="ls")
    else:
        frames.draw_text(draw, ORIGIN, text, font, (255,))
    return image


def added(full: str, part: str) -> tuple[int, int, int, int]:
    """กรอบหมึกที่ full มีเพิ่มจาก part (ใช้แยกหมึกของเครื่องหมายออกจากตัวอักษรหลัก)"""
    box = ImageChops.subtract(render(full), render(part)).getbbox()
    assert box is not None, f"{full!r} adds no ink over {part!r}"
    return box


def column_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    return max(0, min(a[2], b[2]) - max(a[0], b[0]))


def ascender_box(char: str) -> tuple[int, int, int, int]:
    plain_top = render("ก").getbbox()[1]
    box = render(char).crop((0, 0, CANVAS[0], plain_top)).getbbox()
    assert box is not None
    return box


@needs_basic
def test_tone_mark_sits_strictly_above_upper_vowel() -> None:
    tone = added("ที่", "ที")
    vowel = added("ที", "ท")
    assert tone[3] < vowel[1]


@needs_basic
def test_tone_and_vowel_stay_clear_of_the_pho_pla_ascender() -> None:
    ascender = ascender_box("ป")
    vowel = added("ปั", "ป")
    tone = added("ปั๊", "ปั")
    assert tone[3] < vowel[1]  # ๊ อยู่เหนือ ั
    assert column_overlap(vowel, ascender) <= 2
    assert column_overlap(tone, ascender) <= 2


@needs_basic
def test_plain_pillow_layout_does_collide_which_is_why_we_fix_it() -> None:
    ascender = ascender_box("ป")
    plain = ImageChops.subtract(render("ปั๊", plain=True), render("ป", plain=True))
    assert column_overlap(plain.getbbox(), ascender) > 2


@needs_basic
@pytest.mark.parametrize("base", ["น", "ป", "ฟ"])
def test_sara_am_tone_mark_is_above_the_nikhahit_ring(base: str) -> None:
    tone = added(f"{base}้ำ", f"{base}ำ")
    ring = added(f"{base}ํ", base)
    assert tone[3] < ring[1]


@needs_basic
def test_sara_am_is_drawn_as_ring_plus_sara_aa() -> None:
    together = render("นำ")
    assert together.tobytes() == render("นํา").tobytes()


@needs_basic
@pytest.mark.parametrize("base", ["ฎ", "ฏ"])
@pytest.mark.parametrize("vowel", ["ุ", "ู"])
def test_lower_vowel_is_below_the_descender_tail(base: str, vowel: str) -> None:
    tail = render(base).getbbox()
    assert added(base + vowel, base)[1] >= tail[3]


@needs_basic
@pytest.mark.parametrize("text", ["ก้", "ก็", "กุ", "ผู", "ญุ", "ฐู"])
def test_marks_without_a_collision_keep_their_default_place(text: str) -> None:
    assert render(text).tobytes() == render(text, plain=True).tobytes()


@needs_basic
def test_tone_mark_without_upper_vowel_keeps_default_position() -> None:
    assert render("ก้").tobytes() == render("ก้", plain=True).tobytes()


@pytest.mark.parametrize("text", ["ทดสอบ ภาษา 123 Abc", "กขค ง", "", "Hello"])
def test_text_without_marks_is_identical_to_plain_draw(text: str) -> None:
    assert render(text).tobytes() == render(text, plain=True).tobytes()


def test_raqm_path_is_left_to_pillow(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(frames, "_layout_engine", lambda: ImageFont.Layout.RAQM)
    assert render("ปั๊ม น้ำ ที่").tobytes() == render("ปั๊ม น้ำ ที่", plain=True).tobytes()


@needs_basic
def test_marked_text_keeps_the_same_advance_width_after_the_cluster() -> None:
    font = frames.load_font("semibold", 64)
    # ตัวอักษรหลังกลุ่มที่มีเครื่องหมายต้องเริ่มที่เดิม: เทียบกับ ก ที่วางต่อท้าย
    for word in ("ที่", "น้ำ", "ปั๊ม"):
        tail = added(word + "ก", word)
        assert tail[0] >= ORIGIN[0] + font.getlength(word) - 6


# ---------- fit_text: ำ ติดกับตัวหน้า และหมึกไม่เกินความกว้าง ----------

SARA_AM_TITLE = "ทดสอบน้ำมันรถยนต์ทุกชนิด"


def test_truncation_never_separates_sara_am_from_its_tone_mark() -> None:
    font = frames.load_font("semibold", 28)
    seen = set()
    for width in range(100, 320):
        fitted = frames.fit_text(font, SARA_AM_TITLE, width)
        kept = fitted.removesuffix("…")
        assert SARA_AM_TITLE.startswith(kept)
        if kept.startswith("ทดสอบ"):
            seen.add(fitted)
            if len(kept) < len(SARA_AM_TITLE):
                assert SARA_AM_TITLE[len(kept)] != "ำ", width
            assert not kept.endswith("้"), width  # ไม้โท ค้างโดยไม่มี ำ
    assert "ทดสอบน้ำ…" in seen
    assert "ทดสอบน้…" not in seen
    assert "ทดสอบ…" in seen


@pytest.mark.parametrize("weight", ["semibold", "regular"])
def test_rendered_title_ink_stays_within_max_width(weight: str) -> None:
    font = frames.load_font(weight, 28)
    title = "ปั๊มน้ำที่บ้านผู้ใหญ่ก็ซ่อมได้ " * 6
    for width in range(150, 700, 23):
        fitted = frames.fit_text(font, title, width)
        image = Image.new("L", (1000, 120), 0)
        frames.draw_text(ImageDraw.Draw(image), (0, 80), fitted, font, (255,))
        box = image.getbbox()
        assert box is not None
        assert box[0] >= 0
        assert box[2] <= width, (width, fitted)


def test_frame_file_names_match_the_zip_names() -> None:
    times = [4000, 4100, 4999, 5000, 3_661_000]
    assert frame_file_names(times) == [
        "frame_00-00-04.jpg", "frame_00-00-04_2.jpg", "frame_00-00-04_3.jpg", "frame_00-00-05.jpg", "frame_01-01-01.jpg",
    ]  # fmt: skip


def test_missing_code_can_name_the_sharp_set(tmp_path: Path) -> None:
    for build_it in (
        lambda: contact_sheet([(0, tmp_path / "nope.jpg")], "x", 1, missing_code="E_NO_SHARP_FRAMES"),
        lambda: frames_zip([(0, tmp_path / "nope.jpg")], missing_code="E_NO_SHARP_FRAMES"),
    ):
        with pytest.raises(YtError) as caught:
            build_it()
        assert caught.value.code == "E_NO_SHARP_FRAMES"


def _cell_row(sheet: Image.Image) -> list[int]:
    """แถวความสว่าง (0-255) กลางช่องแรกของภาพรวม"""
    gray = sheet.convert("L")
    y = HEADER_H + GUTTER + CELL_H // 2
    return [gray.getpixel((GUTTER + x, y)) for x in range(CELL_W)]


def _hairline(path: Path, width: int, line_px: int) -> Path:
    """ภาพ 16:9 สีดำล้วน มีเส้นขาวตั้งตรงกลางกว้าง line_px (ฉากเดียวกัน ถ่ายที่ความละเอียดต่างกัน)"""
    image = Image.new("RGB", (width, width * 9 // 16), (0, 0, 0))
    ImageDraw.Draw(image).rectangle((width // 2, 0, width // 2 + line_px - 1, image.height), fill=(255, 255, 255))
    image.save(path, "JPEG", quality=95)
    return path


def test_sharp_sized_frames_are_downscaled_into_the_cell(tmp_path: Path) -> None:
    big = make_frame(tmp_path / "big.jpg", (200, 30, 30), size=(1280, 720))
    tall = make_frame(tmp_path / "tall.jpg", (30, 200, 30), size=(720, 1280))
    data = contact_sheet([(0, big), (60_000, tall)], "ภาพคม", 120)
    with Image.open(io.BytesIO(data)) as sheet:
        assert sheet.width == 5 * CELL_W + 6 * 8
        rgb = sheet.convert("RGB")
    y = HEADER_H + GUTTER + CELL_H // 2
    wide = [rgb.getpixel((GUTTER + x, y)) for x in (2, CELL_W // 2, CELL_W - 3)]
    assert all(r > 150 and g < 80 for r, g, _ in wide)  # 16:9 เต็มช่อง ไม่ถูกตัดขอบ ไม่มีแถบดำ
    left = GUTTER + CELL_W + GUTTER  # ช่องที่สอง: ภาพแนวตั้งย่อให้พอดีความสูง เหลือแถบดำสองข้าง
    tall_cell = [rgb.getpixel((left + x, y)) for x in (2, CELL_W // 2, CELL_W - 3)]
    assert max(tall_cell[0]) < 12 and max(tall_cell[2]) < 12
    assert tall_cell[1][1] > 150 and tall_cell[1][0] < 80


def test_sharp_downscale_keeps_a_hairline_crisp_but_an_upscaled_frame_blurs_it(tmp_path: Path) -> None:
    """เส้นขาวบางในภาพคม 1280 กว้างย่อเหลือราว 1 พิกเซลในช่อง 320 ส่วนฉากเดียวกันที่ถ่าย 160 กว้างแล้วขยายขึ้นจะเบลอเป็นหลายพิกเซล
    (ถ้าย่อผิดวิธี เส้นจะหายหรือแตก ค่าสองฝั่งนี้จะเปลี่ยน)"""
    sharp = _hairline(tmp_path / "sharp.jpg", 1280, 4)
    small = _hairline(tmp_path / "small.jpg", 160, 1)
    with Image.open(io.BytesIO(contact_sheet([(0, sharp)], "x", 1))) as sheet:
        sharp_row = _cell_row(sheet)
    with Image.open(io.BytesIO(contact_sheet([(0, small)], "x", 1))) as sheet:
        small_row = _cell_row(sheet)
    assert max(sharp_row) > 180 and sum(v > 40 for v in sharp_row) <= 2  # เส้นยังคมและบาง
    assert max(small_row) > 180 and sum(v > 40 for v in small_row) >= 3  # ภาพที่ขยายขึ้นเบลอเป็นแถบกว้างกว่า
