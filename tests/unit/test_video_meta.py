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
    # Me at the zoo ยาว 19 วินาที: รายการแรก (0-190 ms คนกดเล่น) ไม่นับ ยอดถัดมาอยู่ต้นคลิป
    # ยอดช่วงกลาง (10-12 วินาที) ต่ำกว่าครึ่งของยอดสูงสุด จึงไม่นับ (review I-2)
    assert to_video_info(load(ZOO))["mostReplayed"] == [{"startMs": 190, "endMs": 570}]


def test_owner_thai_fixture_drops_the_low_opening_plateau() -> None:
    # รุ่นก่อนเลือกที่ราบเตี้ย ๆ 0-16.8 วินาทีด้วย ตอนนี้เหลือแค่ยอดจริง
    owner = json.loads((FIXTURES / "OWNERTHSUB1.json").read_text(encoding="utf-8"))
    assert to_video_info(owner)["mostReplayed"] == [
        {"startMs": 28800, "endMs": 31200},
        {"startMs": 122400, "endMs": 127200},
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
    # พื้นราบ 0.1 ต่ำกว่าครึ่งของยอดสูงสุด จึงไม่เป็นช่วงที่สอง (รุ่นก่อนได้ 24-40 วินาที, review I-2)
    assert most_replayed(heat) == [{"startMs": 10000, "endMs": 14000}]


def test_merge_stops_before_reaching_another_pick() -> None:
    heat = flat(40, value=0.0)
    heat[5]["value"] = 1.0
    for i in range(10, 30):
        heat[i]["value"] = 0.8  # ที่ราบยาว: รวมได้แต่ห้ามเข้าใกล้ช่วงแรกไม่ถึง 10 วินาที
    picks = most_replayed(heat)
    assert picks[0] == {"startMs": 5000, "endMs": 6000}
    # ที่ราบ 0.8 เริ่มได้ที่ 16 วินาที (ห่างช่วงแรก 10 วินาที) และกว้างได้ไม่เกิน 10 วินาที (คลิป 40 วินาที: 2% < 10)
    assert picks[1] == {"startMs": 16000, "endMs": 26000}
    assert len(picks) == 2  # ที่ราบที่เหลือ (26-30) ห่างช่วงที่สองไม่ถึง 10 วินาที


def test_at_most_three_and_ties_go_to_the_earlier() -> None:
    heat = [entry(i * 20, i * 20 + 1, 0.7) for i in range(6)]
    # รายการแรก (0 วินาที) ไม่นับ
    assert most_replayed(heat) == [
        {"startMs": 20000, "endMs": 21000},
        {"startMs": 40000, "endMs": 41000},
        {"startMs": 60000, "endMs": 61000},
    ]


def test_unsorted_and_malformed_entries() -> None:
    heat = [entry(30, 31, 1.0), "x", {"start_time": True, "end_time": 2, "value": 1}, entry(0, 1, 0.5), entry(9, 10, 0.6)]
    # เรียงตามเวลาก่อน แล้วรายการแรก (0-1) ไม่นับ
    assert most_replayed(heat) == [{"startMs": 9000, "endMs": 10000}, {"startMs": 30000, "endMs": 31000}]


def test_ms_are_rounded_ints() -> None:
    (pick,) = most_replayed([entry(0, 1.2346, 0.1), entry(1.2346, 2.0006, 1.0)])
    assert pick == {"startMs": 1235, "endMs": 2001}
    assert all(type(v) is int for v in pick.values())


def test_first_entry_is_ignored_even_when_it_is_the_highest() -> None:
    # ค่าพุ่งตอนเริ่มคลิป (คนกดเล่น) ไม่ใช่การดูซ้ำ และต้องไม่ทำให้ยอดอื่นตกเกณฑ์ครึ่งหนึ่ง
    heat = flat(60)
    heat[0]["value"] = 1.0
    heat[30]["value"] = 0.4
    assert most_replayed(heat) == [{"startMs": 30000, "endMs": 31000}]


def test_peaks_below_half_of_the_top_are_dropped() -> None:
    heat = flat(60, value=0.0)
    heat[10]["value"] = 1.0
    heat[30]["value"] = 0.5  # ครึ่งพอดี = นับ
    heat[50]["value"] = 0.49  # ต่ำกว่าครึ่ง = ไม่นับ
    assert most_replayed(heat) == [{"startMs": 10000, "endMs": 11000}, {"startMs": 30000, "endMs": 31000}]


def test_merge_width_is_capped_at_two_percent_of_a_long_clip() -> None:
    # คลิป 1,000 วินาที: กว้างได้ max(10, 20) = 20 วินาที แม้ที่ราบจะยาวกว่านั้น
    heat = flat(100, step=10.0, value=0.0)
    for i in range(40, 60):
        heat[i]["value"] = 0.95
    heat[50]["value"] = 1.0
    picks = most_replayed(heat, 1000)
    peak = next(p for p in picks if p["startMs"] <= 500000 < p["endMs"])
    assert peak["endMs"] - peak["startMs"] == 20000
    assert all(p["endMs"] - p["startMs"] <= 20000 for p in picks)
    # ไม่ส่งความยาว (ใช้ปลาย heatmap 1,000 วินาที) ได้ผลเท่ากัน
    assert most_replayed(heat) == picks


def test_merge_grows_towards_the_higher_neighbour_first() -> None:
    heat = flat(40, value=0.0)
    heat[19]["value"] = 0.91
    heat[20]["value"] = 1.0
    heat[21]["value"] = 0.99
    heat[22]["value"] = 0.98
    # ขวาสูงกว่าซ้ายจึงโตไปทางขวาก่อน ทุกอันผ่านเกณฑ์ 90% และไม่เกิน 10 วินาที จึงได้ครบ 19-23
    assert most_replayed(heat) == [{"startMs": 19000, "endMs": 23000}]


def test_duration_falls_back_to_the_end_of_the_heatmap() -> None:
    heat = flat(1000, value=0.0)
    for i in range(400, 460):
        heat[i]["value"] = 1.0
    # ไม่ส่งความยาวคลิป: ใช้ปลาย heatmap (1,000 วินาที) กว้างได้ 20 วินาที
    picks = most_replayed(heat)
    assert picks[0] == {"startMs": 400000, "endMs": 420000}
    # ส่งความยาวสั้นกว่า (100 วินาที): กว้างได้แค่ 10 วินาที
    assert most_replayed(heat, 100)[0] == {"startMs": 400000, "endMs": 410000}


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
