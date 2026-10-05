"""ซับตามช่วงเวลา (C5, AC-SUB-10): กรองคำตามจุดกึ่งกลาง เลื่อนให้เริ่มที่ 0 ตัดปลายซับไม่ให้เกินความยาวช่วง

ไฟล์ range-cases.json / range-golden.json ใช้ร่วมกับ web/src/lib/srt-range.test.ts (ต้องตรงกันทุกไบต์ AC-SUB-06)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from yttoolkit.core.db import Database
from yttoolkit.core.extractor import FakeExtractor
from yttoolkit.core.srt_builder import PRESETS, Cue, Token, build_cues, clamp_cues, options_from_dict, range_tokens, to_srt
from yttoolkit.core.subtitles import SubtitleService
from yttoolkit.core.videos import VideoService

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SUBS = FIXTURES / "subs"
CASES = json.loads((SUBS / "range-cases.json").read_text(encoding="utf-8"))["cases"]
GOLDEN_RANGE = (90_000, 210_000)


def _tokens(raw: list[dict]) -> list[Token]:
    return [Token(t["t"], t["s"], t["e"]) for t in raw]


def _srt(tokens: list[Token], start: int, end: int, opts) -> str:
    return to_srt(clamp_cues(build_cues(range_tokens(tokens, start, end), opts), end - start))


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_range_cases(case):
    ranged = range_tokens(_tokens(case["tokens"]), case["startMs"], case["endMs"])
    assert [{"t": t.t, "s": t.s, "e": t.e} for t in ranged] == case["ranged"]
    assert _srt(_tokens(case["tokens"]), case["startMs"], case["endMs"], options_from_dict(case["options"])) == case["srt"]


@pytest.mark.parametrize("name", ["th-asr", "en-asr"])
def test_real_tokens_match_the_range_golden(name):
    golden = json.loads((SUBS / "range-golden.json").read_text(encoding="utf-8"))
    doc = json.loads((SUBS / "tokens" / f"{name}.json").read_text(encoding="utf-8"))
    assert _srt(_tokens(doc["tokens"]), *GOLDEN_RANGE, PRESETS["medium"]) == golden[f"{name}.medium.90000-210000"]


def test_ac_sub_10_cues_stay_inside_the_range():
    doc = json.loads((SUBS / "tokens" / "th-asr.json").read_text(encoding="utf-8"))
    cues = clamp_cues(build_cues(range_tokens(_tokens(doc["tokens"]), 90_000, 300_000), PRESETS["medium"]), 210_000)
    assert cues and cues[0].start_ms >= 0 and cues[-1].end_ms <= 210_000


def test_clamp_cues_only_shortens_ends():
    cues = [Cue(0, 1000, ("a",)), Cue(1000, 5000, ("b",))]
    assert clamp_cues(cues, 3000) == [Cue(0, 1000, ("a",)), Cue(1000, 3000, ("b",))]


def test_export_with_a_range(tmp_path):
    db = Database(tmp_path / "app.db")
    db.migrate()
    fake = FakeExtractor(FIXTURES)
    subs = SubtitleService(VideoService(db, fake), fake.fetch_subtitle, tmp_path / "cache")
    try:
        full = subs.export("88o5Sk8_m1Y", "a.th-orig", "srt", PRESETS["medium"])
        ranged = subs.export("88o5Sk8_m1Y", "a.th-orig", "srt", PRESETS["medium"], (10_000, 40_000))
        txt = subs.export("88o5Sk8_m1Y", "a.th-orig", "txt", PRESETS["medium"], (10_000, 40_000))
        assert ranged.data == txt.data and ranged.data != full.data
        ends = [int(h) * 3_600_000 + int(m) * 60_000 + int(s) * 1000 + int(ms)
                for h, m, s, ms in re.findall(r"--> (\d\d):(\d\d):(\d\d),(\d\d\d)", ranged.data.decode("utf-8"))]
        assert ends and max(ends) <= 30_000
        with pytest.raises(ValueError):
            subs.export("88o5Sk8_m1Y", "a.th-orig", "md", PRESETS["medium"], (10_000, 40_000))
    finally:
        db.close()
