"""โน้ต .md สำหรับ Obsidian (C-A3): YAML escape, ความยาวคลิป, หัวข้อที่ไม่มีข้อมูลถูกข้าม"""

from __future__ import annotations

import pytest
import yaml

from yttoolkit.core.note import build_note, hms, note_tags, obsidian_tag, yaml_str
from yttoolkit.core.srt_builder import Token, md_sections, to_md

VID = "jNQXAC9IVRw"


def _front(text: str) -> dict:
    head, sep, _ = text[4:].partition("\n---\n")
    assert text.startswith("---\n") and sep
    return yaml.safe_load(head)


# ---------- yaml_str ----------


@pytest.mark.parametrize(
    "value",
    [
        "plain",
        "",
        'quote " inside',
        "colon: value",
        "- dash first",
        "# hash first",
        "key: [a, b] {c}",
        "back\\slash \\n literal",
        "ไทย ภาษา ที่ น้ำ",
        "line one\nline two\r\nthree\rfour",
        "tab\there",
        "nul\0bell\a esc\x1b del\x7f",
        "nel\x85 ls  ps  bom﻿",
        "emoji 😀 and astral 𝄞",
        "  padded  ",
        "yes",
        "null",
        "123",
        "'single'",
        "@at `tick` %pct &amp *star !bang |pipe >gt",
        "\ud800 lone surrogate",
    ],
)
def test_yaml_str_round_trips(value: str) -> None:
    quoted = yaml_str(value)
    assert quoted.startswith('"') and quoted.endswith('"')
    assert "\n" not in quoted and "\r" not in quoted
    if "\ud800" in value:
        assert "\\uD800" in quoted  # PyYAML ไม่ยอมอ่าน surrogate เดี่ยว แค่ต้องไม่ทำไฟล์เสีย
        return
    assert yaml.safe_load(f"k: {quoted}") == {"k": value}


def test_yaml_flow_list_round_trips() -> None:
    tags = ['a, b', 'c"d', "e]f", "ไทย"]
    line = "tags: [" + ", ".join(yaml_str(t) for t in tags) + "]"
    assert yaml.safe_load(line) == {"tags": tags}


@pytest.mark.parametrize(("seconds", "text"), [(0, "0:00:00"), (19, "0:00:19"), (372, "0:06:12"), (3720, "1:02:00"), (360000, "100:00:00")])
def test_hms(seconds: int, text: str) -> None:
    assert hms(seconds) == text


# ---------- build_note ----------

INFO = {
    "videoId": VID,
    "title": 'Title: "with" quotes\nand a newline',
    "channel": "ช่อง: ทดสอบ",
    "durationS": 372,
    "publishedAt": "2025-05-20",
    "description": "line 1\r\nline 2\r\n\r\n## not a real heading\n\n\n",
    "chapters": [
        {"startS": 65.5, "endS": 70, "title": "  Second\tchapter "},
        {"startS": 0, "endS": 65.5, "title": "First"},
    ],
    "tags": ["a", "b: c"],
    "stats": {"views": 10, "likes": 2},
}


def test_full_note_layout() -> None:
    tokens = [Token("hello", 0, 500), Token(" world", 500, 900), Token("later", 66_000, 67_000)]
    transcript = md_sections(tokens, [(0, "First"), (65_500, "  Second\tchapter ")], level=3)
    text = build_note(INFO, VID, transcript)
    assert "\r" not in text and text.endswith("\n") and not text.endswith("\n\n")
    assert _front(text) == {
        "title": INFO["title"],
        "url": f"https://www.youtube.com/watch?v={VID}",
        "channel": "ช่อง: ทดสอบ",
        "published": yaml.safe_load("d: 2025-05-20")["d"],
        "duration": "0:06:12",
        "tags": ["a", "b-c"],  # แท็กแบบ Obsidian (review M-5)
        "views": 10,
        "likes": 2,
        "source": "YT Toolkit",
    }
    body = text.split("\n---\n", 1)[1]
    assert body == (
        "\n"
        '# Title: "with" quotes and a newline\n'
        "\n"
        "## คำอธิบาย\n"
        "line 1\n"
        "line 2\n"
        "\n"
        "## not a real heading\n"
        "\n"
        "## Chapter\n"
        "- [00:00] First\n"
        "- [01:05] Second chapter\n"
        "\n"
        "## ทรานสคริปต์\n"
        "\n"
        "### [00:00] First\n"
        "\n"
        "hello world\n"
        "\n"
        "### [01:05] Second chapter\n"
        "\n"
        "later\n"
    )


def test_minimal_note_omits_every_empty_section() -> None:
    text = build_note({"videoId": VID, "title": "", "durationS": 0, "chapters": []}, VID, None)
    assert text == (
        "---\n"
        'title: ""\n'
        f"url: https://www.youtube.com/watch?v={VID}\n"
        "source: YT Toolkit\n"
        "---\n"
        "\n"
        f"# {VID}\n"
    )


@pytest.mark.parametrize(
    "extra",
    [
        {"publishedAt": "2025-5-1"},
        {"description": "  \n "},
        {"tags": []},
        {"stats": {"views": True, "likes": True, "comments": "5", "channelFollowers": None}},
        {"durationS": True},
        {"channel": ""},
    ],
)
def test_unusable_values_are_left_out(extra: dict) -> None:
    text = build_note({"videoId": VID, "title": "t", **extra}, VID, [])
    front = _front(text)
    assert set(front) == {"title", "url", "source"}
    assert "## " not in text


def test_chapter_with_empty_title_has_no_trailing_space() -> None:
    text = build_note({"title": "t", "chapters": [{"startS": 3725, "title": " "}]}, VID, None)
    assert "\n- [1:02:05]\n" in text


# ---------- md_sections ----------


@pytest.mark.parametrize("chapters", [[], [(0, "A"), (3000, "B")]])
def test_md_sections_is_the_body_of_to_md(chapters: list) -> None:
    tokens = [Token("a", 0, 100), Token("b", 2500, 2600), Token("c", 130_000, 130_500)]
    full = to_md(tokens, title="T", video_id=VID, chapters=chapters)
    header = f"# T\r\n\r\nhttps://www.youtube.com/watch?v={VID}"
    assert full == header + "\r\n".join(["", *md_sections(tokens, chapters)]) + "\r\n"
    level3 = md_sections(tokens, chapters, level=3)
    assert [line for line in level3 if line.startswith("#")] == [
        "#" + line for line in md_sections(tokens, chapters) if line.startswith("#")
    ]


# ---------- แท็กแบบ Obsidian (review M-5) ----------


@pytest.mark.parametrize(
    ("raw", "slug"),
    [
        ("me at the zoo", "me-at-the-zoo"),
        ("  spaced   out  ", "spaced-out"),
        ("การตลาด ออนไลน์", "การตลาด-ออนไลน์"),
        ("น้ำใจ", "น้ำใจ"),
        ("C++ #tips", "C-tips"),
        ("a, b: c", "a-b-c"),
        ("nested/tag", "nested/tag"),
        ("/edge/", "edge"),
        ("snake_case", "snake_case"),
        ("2026", ""),
        ("2026 ๒๕๖๙", ""),
        ("y2k", "y2k"),
        ("!!!", ""),
        ("   ", ""),
        ("-- a -- b --", "a-b"),
    ],
)
def test_obsidian_tag(raw: str, slug: str) -> None:
    assert obsidian_tag(raw) == slug


def test_purely_numeric_after_slugify_is_dropped() -> None:
    assert obsidian_tag("2026") == ""
    assert obsidian_tag("12 34") == ""  # "12-34" ยังเป็นเลขกับขีด ไม่มีตัวอักษร
    assert obsidian_tag("12-34a") == "12-34a"


def test_note_tags_drop_empty_and_duplicates_keep_order() -> None:
    assert note_tags(["Zoo", "me at the zoo", "zoo", "!!!", "2026", 5, None, "Me at the zoo"]) == [
        "Zoo",
        "me-at-the-zoo",
    ]
    assert note_tags(None) == []


def test_note_front_matter_uses_obsidian_tags() -> None:
    text = build_note({"videoId": VID, "title": "t", "tags": ["me at the zoo", "2026", "!!"]}, VID, [])
    assert _front(text)["tags"] == ["me-at-the-zoo"]
    only_bad = build_note({"videoId": VID, "title": "t", "tags": ["2026", "!!"]}, VID, [])
    assert "tags" not in _front(only_bad)


# ---------- C-A3 v2: ฟิลด์ใหม่ + คอมเมนต์ปักหมุด ----------


def test_front_matter_has_the_stats_in_order_before_source() -> None:
    info = {"videoId": VID, "title": "t", "stats": {"views": 1, "likes": 2, "comments": 0, "channelFollowers": 4000}}
    text = build_note(info, VID, None)
    head = text.split("\n---\n", 1)[0].splitlines()
    assert head[-5:] == ["views: 1", "likes: 2", "comments: 0", "channel_followers: 4000", "source: YT Toolkit"]
    front = _front(text)
    assert front["comments"] == 0 and type(front["channel_followers"]) is int


def test_each_missing_stat_is_omitted_on_its_own() -> None:
    info = {"videoId": VID, "title": "t", "stats": {"likes": 7, "channelFollowers": 12}}
    front = _front(build_note(info, VID, None))
    assert front["likes"] == 7 and front["channel_followers"] == 12
    assert "views" not in front and "comments" not in front


@pytest.mark.parametrize(("by_uploader", "who"), [(True, "เจ้าของช่อง"), (False, "ผู้ชม")])
def test_pinned_section_sits_after_chapter_and_before_transcript(by_uploader: bool, who: str) -> None:
    pinned = {"text": "บรรทัดหนึ่ง\r\nบรรทัดสอง\n\n", "likes": 3, "byUploader": by_uploader}
    text = build_note(INFO, VID, ["### [00:00]", "", "hi"], pinned)
    assert "\r" not in text and text.endswith("\n")
    block = f"\n## คอมเมนต์ปักหมุด ({who})\nบรรทัดหนึ่ง\nบรรทัดสอง\n"
    assert block in text
    assert text.index("## Chapter") < text.index(block) < text.index("## ทรานสคริปต์\n")
    other = "ผู้ชม" if by_uploader else "เจ้าของช่อง"
    assert f"({other})" not in text


@pytest.mark.parametrize("pinned", [None, {}, {"text": "  "}, {"text": None}, {"byUploader": True}])
def test_pinned_section_is_omitted_without_text(pinned: dict | None) -> None:
    assert "คอมเมนต์ปักหมุด" not in build_note(INFO, VID, None, pinned)


def test_pinned_without_by_uploader_is_labelled_as_viewer() -> None:
    assert "## คอมเมนต์ปักหมุด (ผู้ชม)\nสวัสดี\n" in build_note(INFO, VID, None, {"text": "สวัสดี"})


def test_pinned_text_starting_with_a_heading_stays_inside_its_section() -> None:
    text = build_note(INFO, VID, None, {"text": "## fake\nbody", "byUploader": True})
    assert text.endswith("## คอมเมนต์ปักหมุด (เจ้าของช่อง)\n## fake\nbody\n")
