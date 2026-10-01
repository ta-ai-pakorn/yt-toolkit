"""ข้อมูลคลิป (C-A1, owner round 2): stats, tags, categories, mostReplayed ใน VideoInfo"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from yttoolkit.core.videos import TAGS_MAX, most_replayed, to_video_info, trim_probe

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "probe"
THAI = "88o5Sk8_m1Y"
ZOO = "jNQXAC9IVRw"
BBB = "aqz-KE-bpKQ"


def load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def entry(start: float, end: float, value: float) -> dict:
    return {"start_time": start, "end_time": end, "value": value}


def flat(n: int, step: float = 1.0, value: float = 0.1) -> list[dict]:
    return [entry(i * step, (i + 1) * step, value) for i in range(n)]


# ---------- stats ----------


def test_real_stats_of_the_thai_clip() -> None:
    info = to_video_info(load(THAI))
    assert info["stats"] == {"views": 38764, "likes": 1970, "comments": 120, "channelFollowers": 11700}
    assert info["categories"] == ["Education"]
    assert len(info["tags"]) == 10
    assert "mostReplayed" not in info  # heatmap ของคลิปนี้เป็น null จริง


def test_missing_metadata_is_omitted() -> None:
    info = to_video_info(load("VTTFALLBAK1"))
    for key in ("stats", "tags", "categories", "mostReplayed"):
        assert key not in info


@pytest.mark.parametrize("bad", [True, False, -1, 1.5, "12", None, float("nan"), [3]])
def test_bad_counts_are_dropped(bad: object) -> None:
    info = to_video_info({"id": BBB, "view_count": bad, "like_count": 7})
    assert info["stats"] == {"likes": 7}


def test_integer_floats_and_zero_are_kept() -> None:
    info = to_video_info({"id": BBB, "view_count": 12.0, "comment_count": 0})
    assert info["stats"] == {"views": 12, "comments": 0}
    assert type(info["stats"]["views"]) is int


# ---------- tags / categories ----------


def test_tags_are_trimmed_deduped_and_empty_dropped() -> None:
    raw = {"id": BBB, "tags": ["  a  ", "", "   ", "b", "a", 5, None, "ไทย"], "categories": [" Education ", ""]}
    info = to_video_info(raw)
    assert info["tags"] == ["a", "b", "ไทย"]
    assert info["categories"] == ["Education"]


def test_tags_are_capped_at_50() -> None:
    info = to_video_info(load("LONGTHAI1hr"))
    assert TAGS_MAX == 50
    assert info["tags"] == [f"แท็กที่ {n}" for n in range(1, 51)]


@pytest.mark.parametrize("bad", ["tag", {"a": 1}, 3, None])
def test_non_list_tags_are_ignored(bad: object) -> None:
    assert "tags" not in to_video_info({"id": BBB, "tags": bad, "categories": bad})


def test_empty_tag_list_is_omitted() -> None:
    info = to_video_info(load("NOORIGSUB01"))
    assert "tags" not in info
    assert info["stats"]["comments"] == 0


# ---------- mostReplayed ----------


def test_no_heatmap_means_nothing() -> None:
    for value in (None, [], "x", [{"start_time": 1}], [entry(5, 5, 1.0)], [entry(1, 2, 0)]):
        assert most_replayed(value) == []


def test_real_heatmap_of_a_short_clip() -> None:
    # Me at the zoo ยาว 19 วินาที: ช่วงที่ห่างกัน 10 วินาทีได้แค่ 2 ช่วง
    assert to_video_info(load(ZOO))["mostReplayed"] == [
        {"startMs": 0, "endMs": 190},
        {"startMs": 10260, "endMs": 12160},
    ]


def test_three_peaks_sorted_by_start() -> None:
    assert to_video_info(load(BBB))["mostReplayed"] == [
        {"startMs": 76200, "endMs": 82550},
        {"startMs": 304800, "endMs": 317500},
        {"startMs": 514350, "endMs": 527050},
    ]


def test_greedy_skips_segments_within_ten_seconds() -> None:
    heat = flat(60)
    heat[20]["value"] = 1.0
    heat[25]["value"] = 0.95  # ห่างจากช่วงแรก 4 วินาที -> ข้าม
    heat[31]["value"] = 0.9  # ห่าง 10 วินาทีพอดี -> เลือกได้
    heat[50]["value"] = 0.5
    heat[55]["value"] = 0.4  # ห่างจากช่วง 50 ไม่ถึง 10 วินาที
    assert most_replayed(heat) == [
        {"startMs": 20000, "endMs": 21000},
        {"startMs": 31000, "endMs": 32000},
        {"startMs": 50000, "endMs": 51000},
    ]


def test_merge_takes_neighbours_at_or_above_ninety_percent() -> None:
    heat = flat(40)
    for i, value in ((9, 0.89), (10, 0.9), (11, 0.95), (12, 1.0), (13, 0.92), (14, 0.5)):
        heat[i]["value"] = value
    # ช่วงที่สอง = พื้นราบ 0.1 อันแรกที่ห่าง 10 วินาที รวมไปจนสุดคลิป (ที่ราบมีค่าเท่ากัน)
    assert most_replayed(heat) == [{"startMs": 10000, "endMs": 14000}, {"startMs": 24000, "endMs": 40000}]


def test_merge_stops_before_reaching_another_pick() -> None:
    heat = flat(40, value=0.0)
    heat[5]["value"] = 1.0
    for i in range(10, 30):
        heat[i]["value"] = 0.8  # ที่ราบยาว: รวมได้แต่ห้ามเข้าใกล้ช่วงแรกไม่ถึง 10 วินาที
    picks = most_replayed(heat)
    assert picks[0] == {"startMs": 5000, "endMs": 6000}
    assert picks[1] == {"startMs": 16000, "endMs": 30000}
    assert len(picks) == 2


def test_at_most_three_and_ties_go_to_the_earlier() -> None:
    heat = [entry(i * 20, i * 20 + 1, 0.7) for i in range(6)]
    assert most_replayed(heat) == [
        {"startMs": 0, "endMs": 1000},
        {"startMs": 20000, "endMs": 21000},
        {"startMs": 40000, "endMs": 41000},
    ]


def test_unsorted_and_malformed_entries() -> None:
    heat = [entry(30, 31, 1.0), "x", {"start_time": True, "end_time": 2, "value": 1}, entry(0, 1, 0.5)]
    assert most_replayed(heat) == [{"startMs": 0, "endMs": 1000}, {"startMs": 30000, "endMs": 31000}]


def test_ms_are_rounded_ints() -> None:
    (pick,) = most_replayed([entry(1.2346, 2.0006, 1.0)])
    assert pick == {"startMs": 1235, "endMs": 2001}
    assert all(type(v) is int for v in pick.values())


# ---------- trim_probe ----------


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.json")), ids=lambda p: p.stem)
def test_trimmed_and_raw_give_the_same_info(path: Path) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert to_video_info(trim_probe(raw)) == to_video_info(raw)


def test_trim_keeps_clean_values_but_not_the_raw_heatmap() -> None:
    raw = load(BBB)
    raw["tags"] = [" x ", "", "x"]
    trimmed = trim_probe(raw)
    assert "heatmap" not in trimmed
    assert trimmed["mostReplayed"] == to_video_info(raw)["mostReplayed"]
    assert trimmed["tags"] == ["x"]
    assert trimmed["view_count"] == 1234567


def test_stored_most_replayed_that_is_broken_falls_back_to_heatmap() -> None:
    raw = load(BBB)
    expected = to_video_info(raw)["mostReplayed"]
    for broken in ([{"startMs": 5, "endMs": 1}], [{"startMs": 1.5, "endMs": 3}], "x", [1]):
        assert to_video_info({**raw, "mostReplayed": broken})["mostReplayed"] == expected
    assert "mostReplayed" not in to_video_info({"id": BBB, "mostReplayed": [{"startMs": True, "endMs": 4}]})
