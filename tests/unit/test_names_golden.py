"""ชื่อโฟลเดอร์/ไฟล์ตามรูปแบบชื่อไฟล์ (M6 รอบ A spec 2.2 / 2.5, C10): files.plan_names ต้องตรงกับ golden ทุกตัวอักษร

tests/fixtures/names/cases.json = ข้อมูลเข้า (camelCase แบบเดียวกับ NameInput ของเว็บ) เขียนด้วยมือ
tests/fixtures/names/golden.json = ผลที่ถูกต้อง สร้างได้ทางเดียวคือรัน
`YT_UPDATE_GOLDEN=1 uv run pytest tests/unit/test_names_golden.py` (รอบนั้นจบแดงเสมอ ดู test_zz_...)
ฝั่งเว็บ (web/src/lib/filename-parity.test.ts) อ่านสองไฟล์นี้ไปเทียบกับ planNames จึงห้ามแก้ golden เพื่อให้เทสผ่าน
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from yttoolkit.core import files, settings
from yttoolkit.core.yterrors import YtError

NAMES = Path(__file__).resolve().parents[1] / "fixtures" / "names"
CASES_FILE = NAMES / "cases.json"
GOLDEN_FILE = NAMES / "golden.json"
UPDATE = os.environ.get("YT_UPDATE_GOLDEN") == "1"
_REGENERATED = False  # True เมื่อรอบนี้เขียน golden ใหม่ ทำให้เทสสุดท้ายของไฟล์ล้มเหลวโดยตั้งใจ

ID = "dQw4w9WgXcQ"
AC_OUT_01 = 'ทดสอบ: "A/B" <ภาค 1>?'
FORBIDDEN = set('\\/:*?"<>|')


def _cases() -> list[dict]:
    return json.loads(CASES_FILE.read_text(encoding="utf-8"))


def _expected(case: dict) -> dict:
    try:
        folder, file = files.plan_names(
            case["baseLen"], case["title"], case["clipId"], suffix=case["suffix"], ext=case["ext"],
            style=case["style"], uploader=case["uploader"], quality=case["quality"],
        )  # fmt: skip
    except YtError as exc:
        assert exc.code == "E_OUTPUT_NOT_WRITABLE"
        return {"error": exc.detail}
    return {"folder": folder, "file": file}


@pytest.fixture(scope="module", autouse=True)
def _update_golden():
    """YT_UPDATE_GOLDEN=1: เขียน golden ใหม่ก่อนเทสรัน ห้ามใช้เมื่อมี CI และรอบนั้นจบแดงเสมอ (ดู test_zz_...)"""
    global _REGENERATED
    if UPDATE:
        if os.environ.get("CI"):
            pytest.fail("YT_UPDATE_GOLDEN=1 is refused when CI is set: goldens are never regenerated in CI", pytrace=False)
        doc = {case["name"]: _expected(case) for case in _cases()}
        text = json.dumps(doc, ensure_ascii=False, indent=1) + "\n"
        GOLDEN_FILE.write_bytes(text.encode("utf-8"))
        _REGENERATED = True
    yield


def test_case_names_are_unique_and_every_case_has_a_golden():
    names = [case["name"] for case in _cases()]
    assert len(names) == len(set(names))
    assert GOLDEN_FILE.is_file(), "golden.json is missing: run with YT_UPDATE_GOLDEN=1"
    golden = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    assert sorted(golden) == sorted(names)


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["name"])
def test_plan_names_matches_golden(case):
    golden = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    assert _expected(case) == golden[case["name"]]


def test_name_styles_match_the_settings_choices():
    assert files.NAME_STYLES == settings.FILENAME_STYLES


# ---------- กฎที่เทสฝั่ง Python อย่างเดียว ----------


def _legacy_plan_output(root: Path, title: str, video_id: str, suffix: str, ext: str, group: str | None = None) -> Path:
    """สำเนาของ files.plan_output ก่อน M6 (ที่ 344567b) ทุกบรรทัด: ใช้ยืนยันว่าแบบ "title" ไม่เปลี่ยนชื่อของใคร"""
    tail = f"{suffix}.{ext}"
    base = root / files.group_folder_name(group) if group else root
    t = files.safe_component(title, video_id)
    budget = files.PATH_LIMIT - (files._u16(str(base)) + 1) - files._u16(f" [{video_id}]") - 1
    budget -= files.TAIL_RESERVE + files.UNIQUE_RESERVE
    cap = budget // 2
    short = ""
    if cap >= 8:
        short = files.truncate_title(t, min(files.TITLE_MAX, cap))
    if short:
        file_cap = budget - files._u16(short) + files.TAIL_RESERVE - files._u16(tail)
        stem = short if files._u16(short) <= file_cap else files.truncate_title(short, file_cap)
        planned = base / f"{short} [{video_id}]" / f"{stem or video_id}{tail}"
    else:
        planned = base / video_id / f"{video_id}{tail}"
    if files._u16(str(planned)) > files.PATH_LIMIT - files.UNIQUE_RESERVE:
        raise YtError("E_OUTPUT_NOT_WRITABLE", "path too long")
    return planned


def _root_of_length(tmp_path: Path, n: int) -> Path:
    anchor = Path(tmp_path.anchor)
    root = anchor / ("x" * (n - len(str(anchor))))
    assert len(str(root)) == n
    return root


_LEGACY_TITLES = (
    "สั้น", "Hi", "ก" * 300, "😀" * 300, chr(0x0E31) * 300, AC_OUT_01, "CON", "com1.txt", "", "...",
    "Big Buck Bunny 60fps 4K - Official Blender Foundation Short Film", "ชื่อคลิปยาวพอสมควร",
)  # fmt: skip
_LEGACY_TAILS = (
    ("", "mp4"), (" (ไม่มีเสียง)", "mp4"), (".th", "srt"), (" (01.30-05.00).th", "srt"), (".note", "md"),
    (" - contact sheet", "jpg"), (" - frames", "zip"), ("", "wav"), (" - ภาพคม", "jpg"),
    (" (ไม่มีเสียง) (1.02.30-1.05.00) (ตัดโฆษณา)", "mp4"),
)  # fmt: skip


@pytest.mark.parametrize("root_len", [4, 40, 60, 110, 150, 190])
@pytest.mark.parametrize("group", [None, "รวมคลิป ก/ข", "g" * 80])
def test_title_style_gives_exactly_the_names_from_before_m6(tmp_path, root_len, group):
    root = _root_of_length(tmp_path, root_len)
    for title in _LEGACY_TITLES:
        for suffix, ext in _LEGACY_TAILS:
            try:
                before = _legacy_plan_output(root, title, ID, suffix, ext, group)
            except YtError:
                with pytest.raises(YtError):
                    files.plan_output(root, title, ID, suffix, ext, group)
                continue
            assert files.plan_output(root, title, ID, suffix, ext, group) == before
            assert files.plan_output(root, title, ID, suffix, ext, group, style="title", uploader="ช่อง",
                                     quality="1080p") == before  # fmt: skip


@pytest.mark.parametrize("title", [AC_OUT_01, "ก" * 300])
@pytest.mark.parametrize(("ext", "quality"), [("mp4", "1080p"), ("mp3", "mp3 192k")])
def test_ac_out_09_every_style_is_safe_and_keeps_quality_and_extension(tmp_path, title, ext, quality):
    root = _root_of_length(tmp_path, 60)
    folders = set()
    for style in files.NAME_STYLES:
        path = files.plan_output(root, title, ID, "", ext, style=style, uploader="ครัว: บ้าน/เรา", quality=quality)
        assert not FORBIDDEN & set(path.parent.name + path.name)
        assert files._u16(str(path)) + files.UNIQUE_RESERVE <= files.PATH_LIMIT
        assert path.name.endswith(f".{ext}")
        if style == "title-quality":
            assert path.name.endswith(f" ({quality}).{ext}")
        if style == "title-channel":
            assert path.name.endswith(f" - ครัว บ้านเรา.{ext}")
        folders.add(path.parent)
    assert len(folders) == 1  # โฟลเดอร์ของคลิปไม่ขึ้นกับรูปแบบ


def test_long_channel_cuts_the_title_to_eight_before_the_channel():
    folder, file = files.plan_names(150, "ก" * 300, ID, suffix="", ext="mp4", style="title-channel", uploader="ช" * 120)
    stem = file.removesuffix(".mp4")
    title_part, channel_part = stem.split(files.CHANNEL_SEP, 1)
    assert title_part == "ก" * 8 and channel_part and set(channel_part) == {"ช"}
    assert 150 + 1 + files._u16(folder) + 1 + files._u16(file) <= files.PATH_LIMIT - files.UNIQUE_RESERVE


def test_unknown_style_and_bad_quality_are_programming_errors():
    with pytest.raises(ValueError):
        files.plan_names(10, "t", ID, suffix="", ext="mp4", style="channel")
    for bad in ("1080P", "", "x" * 17, "mp3/192k"):
        with pytest.raises(ValueError):
            files.plan_names(10, "t", ID, suffix="", ext="mp4", style="title-quality", quality=bad)


def test_zz_golden_was_not_regenerated():
    """ต้องอยู่ท้ายไฟล์: รอบที่เขียน golden เองเทสอื่นผ่านเพราะเทียบกับไฟล์ที่เพิ่งเขียน จึงต้องจบแดงเสมอ"""
    assert not _REGENERATED, "golden regenerated, review git diff and re-run without YT_UPDATE_GOLDEN"
