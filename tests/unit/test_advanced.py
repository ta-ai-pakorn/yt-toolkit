"""คณิตของตัวเลือกขั้นสูง (M5 รอบ A): ช่วงที่เก็บไว้ ช่วงของ chapter และส่วนต่อท้ายชื่อไฟล์"""

from __future__ import annotations

import pytest

from yttoolkit.core.advanced import (
    ADS_SUFFIX,
    MIN_PIECE_MS,
    ChapterPart,
    chapter_parts,
    keep_intervals,
    kept_ms,
    merge_intervals,
    range_suffix,
)


@pytest.mark.parametrize(
    ("start", "end", "suffix"),
    [
        (90_000, 300_000, " (01.30-05.00)"),
        (0, 59_000, " (00.00-00.59)"),
        (3_750_000, 3_900_000, " (1.02.30-1.05.00)"),
        (0, 3_600_000, " (0.00.00-1.00.00)"),
        (59 * 60_000, 3_661_000, " (0.59.00-1.01.01)"),
        (36_000_000, 36_300_000, " (10.00.00-10.05.00)"),
    ],
)
def test_range_suffix(start, end, suffix):
    assert range_suffix(start, end) == suffix
    assert not set('\\/:*?"<>|') & set(suffix)


def test_ads_suffix_is_the_spec_text():
    assert ADS_SUFFIX == " (ตัดโฆษณา)" and MIN_PIECE_MS == 1000


def test_merge_intervals_sorts_joins_and_drops_empty():
    assert merge_intervals([(50, 60), (0, 10), (5, 20), (20, 30), (40, 40)]) == [(0, 30), (50, 60)]


def test_keep_without_ads_is_the_span():
    assert keep_intervals((0, 635_000), []) == [(0, 635_000)]


def test_keep_removes_ads_and_clips_them_to_the_span():
    ads = [(60_000, 90_000), (0, 12_000), (600_000, 700_000)]
    assert keep_intervals((0, 635_000), ads) == [(12_000, 60_000), (90_000, 600_000)]


def test_keep_inside_a_range():
    assert keep_intervals((30_000, 120_000), [(60_000, 90_000), (200_000, 210_000)]) == [
        (30_000, 60_000), (90_000, 120_000)]


def test_keep_drops_pieces_shorter_than_one_second():
    # left pieces (0, 500) and (50_000, 50_900) are both shorter than 1 s
    assert keep_intervals((0, 100_000), [(500, 50_000), (50_900, 100_000)]) == []
    assert keep_intervals((0, 100_000), [(1_000, 50_000)]) == [(0, 1_000), (50_000, 100_000)]


def test_keep_everything_cut_is_empty():
    assert keep_intervals((0, 10_000), [(0, 10_000)]) == []


def test_kept_ms():
    assert kept_ms([(0, 1_000), (5_000, 7_500)]) == 3_500


ZOO = [
    {"startS": 0, "endS": 5, "title": "Intro"},
    {"startS": 5, "endS": 17, "title": "The cool thing"},
    {"startS": 17, "endS": 19, "title": "End"},
]


def test_chapter_parts_of_the_zoo_clip():
    assert chapter_parts(ZOO, 19_000) == [
        ChapterPart(1, 3, 0, 5_000, "Intro"),
        ChapterPart(2, 3, 5_000, 17_000, "The cool thing"),
        ChapterPart(3, 3, 17_000, 19_000, "End"),
    ]


def test_chapter_parts_clip_the_last_end_and_strip_titles():
    parts = chapter_parts([{"startS": 0, "endS": 10.5, "title": "  a  "}, {"startS": 10.5, "endS": 99, "title": ""}], 20_000)
    assert parts == [ChapterPart(1, 2, 0, 10_500, "a"), ChapterPart(2, 2, 10_500, 20_000, "")]


def test_chapter_parts_need_two_usable_chapters():
    assert chapter_parts([], 10_000) == []
    assert chapter_parts(ZOO[:1], 19_000) == []
    assert chapter_parts([{"startS": 0, "endS": 5, "title": "a"}, {"startS": 25, "endS": 30, "title": "b"}], 19_000) == []
    assert chapter_parts([{"startS": None, "endS": 5}, {"startS": "x", "endS": 9}], 19_000) == []
