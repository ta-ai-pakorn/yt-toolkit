"""โน้ต .md สำหรับ Obsidian (C-A3): YAML escape, ความยาวคลิป, หัวข้อที่ไม่มีข้อมูลถูกข้าม"""

from __future__ import annotations

import pytest
import yaml

from yttoolkit.core.note import build_note, hms, yaml_str
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
        "tags": ["a", "b: c"],
        "views": 10,
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
        {"stats": {"likes": 3}},
        {"stats": {"views": True}},
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
