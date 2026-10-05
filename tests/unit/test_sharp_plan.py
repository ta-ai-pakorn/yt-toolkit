"""แผนเวลาภาพคม (M5 รอบ B spec 3.2) ฝั่ง Python · เคสร่วมกับ web/src/lib/sharp-frames.test.ts ห้ามแก้ fixture ให้เทสผ่าน"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from yttoolkit.core.extractor import FakeExtractor
from yttoolkit.core.sharp import (
    MAX_SHARP_FRAMES,
    SharpPlan,
    custom_times,
    default_interval_s,
    fast_times,
    plan_sharp,
    raised_interval_s,
)
from yttoolkit.core.storyboard import build

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CASES = json.loads((FIXTURES / "sharp" / "plan-cases.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_golden_plan_cases(case: dict) -> None:
    fast = case["fast"]
    times = [i * fast["stepMs"] for i in range(fast["count"])] if fast else None
    plan = plan_sharp(case["durationS"], interval_s=case["intervalS"], fast_times=times)
    want = case["expect"]
    assert len(plan.times_ms) == want["count"] <= MAX_SHARP_FRAMES
    assert plan.times_ms[0] == want["first"] and plan.times_ms[-1] == want["last"]
    assert plan.interval_s == want["intervalS"] and plan.raised is want["raised"]
    if "times" in want:
        assert list(plan.times_ms) == want["times"]
    assert list(plan.times_ms) == sorted(set(plan.times_ms))


def test_helpers() -> None:
    assert default_interval_s(19) == 1 and default_interval_s(635) == 7 and default_interval_s(36000) == 360
    assert raised_interval_s(635) == 4 and raised_interval_s(200) == 1
    assert custom_times(3, 10) == [0, 3000, 6000, 9000]
    assert plan_sharp(19, interval_s=None, fast_times=None) == SharpPlan(tuple(range(0, 19_000, 1000)), 1, False)


@pytest.mark.parametrize(
    ("duration_s", "interval_s", "fast"),
    [(0, None, None), (-5, 2, None), (10, 0, None), (10, 3601, None), (10, True, None), (10, None, [])],
)
def test_bad_input_is_a_value_error(duration_s, interval_s, fast) -> None:
    with pytest.raises(ValueError):
        plan_sharp(duration_s, interval_s=interval_s, fast_times=fast)


def test_fast_times_equal_the_storyboard_index_without_fetching(tmp_path: Path) -> None:
    fake = FakeExtractor(FIXTURES)
    raw = fake.probe("aqz-KE-bpKQ")
    planned = fast_times(raw)
    assert fake.calls == [("probe", "aqz-KE-bpKQ")]  # ไม่โหลดแผ่น storyboard
    index = build("aqz-KE-bpKQ", raw, tmp_path / "aqz-KE-bpKQ", fake.fetch)
    assert planned == [frame["tMs"] for frame in index["frames"]]
    assert len(planned) == 128


def test_fast_times_without_a_storyboard_is_none() -> None:
    assert fast_times(FakeExtractor(FIXTURES).probe("jNQXAC9IVRw")) is None
