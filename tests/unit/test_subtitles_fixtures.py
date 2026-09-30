"""เกณฑ์ผ่านของซับ (PRD AC-SUB-03/04/05/08/09/11) ตรวจกับข้อมูลจริงใน tests/fixtures/subs ทุก preset

ต่างจาก test_srt_builder.py ที่ตรวจทีละกรณีที่เขียนเอง ไฟล์นี้เอา parser ต่อกับ builder แล้วรันกับซับจริงทั้งชุด
`88o5Sk8_m1Y/tlang-en.json3` เป็นไฟล์สังเคราะห์ (YouTube ตอบ 429 ตอนเก็บ fixture) เวลาของมันซ้อนกันหลายบรรทัด
จึงใช้เฉพาะเช็กว่าไม่มีคำหายหรือซ้ำ ไม่ได้อยู่ในชุด golden
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from yttoolkit.core import thai_fallback as tf
from yttoolkit.core.srt_builder import PRESETS, Cue, Token, build_cues, cue_text, display_len, to_srt
from yttoolkit.core.subparse import ParsedTrack, parse_json3, parse_vtt

SUBS = Path(__file__).resolve().parents[1] / "fixtures" / "subs"
GOLDEN_DIR = SUBS / "golden"

REAL = {
    "th-asr": (SUBS / "88o5Sk8_m1Y" / "th-orig.json3", parse_json3),
    "th-vtt": (SUBS / "88o5Sk8_m1Y" / "th-orig.vtt", parse_vtt),
    "en-asr": (SUBS / "8lpOfyoxcvU" / "en-US-orig.json3", parse_json3),
    "en-owner": (SUBS / "jNQXAC9IVRw" / "en.json3", parse_json3),
    "th-owner": (SUBS / "OWNERTHSUB1" / "th.json3", parse_json3),
    "th-asr-8lpO": (SUBS / "8lpOfyoxcvU" / "th-orig.json3", parse_json3),
    "en-owner-de": (SUBS / "jNQXAC9IVRw" / "de.json3", parse_json3),
    "tlang-en-synthetic": (SUBS / "88o5Sk8_m1Y" / "tlang-en.json3", parse_json3),
}


@pytest.fixture(autouse=True)
def _keep_data_dir_out_of_home(tmp_path, monkeypatch):
    # PyThaiNLP สร้างโฟลเดอร์ข้อมูลตอนใช้ครั้งแรก เก็บไว้นอก ~/
    monkeypatch.setenv(tf.DATA_ENV, str(tmp_path / "pythainlp-data"))


_PARSED: dict[str, ParsedTrack] = {}


def parsed(name: str) -> ParsedTrack:
    if name not in _PARSED:
        path, parse = REAL[name]
        _PARSED[name] = parse(path.read_bytes())
    return _PARSED[name]


def _nospace(text: str) -> str:
    return text.replace(" ", "")


def cue_full_text(cue: Cue) -> str:
    return " ".join(cue.lines)


def cue_token_counts(tokens: tuple[Token, ...], cues: list[Cue]) -> list[tuple[int, int]]:
    """(index ของ token แรก, จำนวน token) ของแต่ละซับ หาจากการไล่กินตัวอักษรตามลำดับ (builder ไม่คืนรายการ token)"""
    out: list[tuple[int, int]] = []
    pos = 0
    for cue in cues:
        want = _nospace("".join(cue.lines))
        first = pos
        got = ""
        while len(got) < len(want):
            got += _nospace(tokens[pos].t)
            pos += 1
        assert got == want, f"cue text is not a run of whole tokens: {cue.lines!r}"
        out.append((first, pos - first))
    assert pos == len(tokens), "some tokens were dropped"
    return out


PRESET_NAMES = list(PRESETS)
ALL_NAMES = list(REAL)


# ---------- AC-SUB-03: ไม่มีซับซ้ำ ----------


def _assert_no_repeats(cues: list[Cue]) -> None:
    prev: Cue | None = None
    for i, cue in enumerate(cues):
        text = cue_full_text(cue)
        assert text.strip(), f"cue {i + 1} is empty"
        assert all(line.strip() for line in cue.lines), f"cue {i + 1} has an empty line"
        if prev is not None:
            prev_text = cue_full_text(prev)
            assert text != prev_text, f"cue {i + 1} repeats cue {i}"
            # บรรทัดใดบรรทัดหนึ่งเท่ากับซับก่อนหน้าทั้งซับ = ซ้อนแบบ rolling caption
            assert prev_text not in cue.lines, f"cue {i + 1} contains the whole previous cue as a line"
        prev = cue


@pytest.mark.parametrize("preset", PRESET_NAMES)
@pytest.mark.parametrize("name", ["th-asr", "th-vtt"])
def test_ac_sub_03_no_repeated_cues_in_thai_asr(name, preset):
    cues = build_cues(parsed(name).tokens, PRESETS[preset])
    assert cues
    _assert_no_repeats(cues)


# ---------- AC-SUB-04: ไม่มีคำหาย ไม่มีคำซ้ำ ----------


def _assert_text_is_preserved(tokens: tuple[Token, ...], cues: list[Cue]) -> None:
    joined = "".join(_nospace("".join(cue.lines)) for cue in cues)
    assert joined == "".join(_nospace(t.t) for t in tokens)
    for cue, (first, _) in zip(cues, cue_token_counts(tokens, cues), strict=True):
        assert cue.lines[0].startswith(tokens[first].t.strip(" ")), cue.lines


@pytest.mark.parametrize("preset", PRESET_NAMES)
@pytest.mark.parametrize("name", ALL_NAMES)
def test_ac_sub_04_no_text_lost_or_duplicated(name, preset):
    tokens = parsed(name).tokens
    assert tokens
    _assert_text_is_preserved(tokens, build_cues(tokens, PRESETS[preset]))


# ---------- AC-SUB-05: บรรทัดไม่เกินขีดจำกัด และซับสั้นถูกยืดจนชนซับถัดไป ----------


@pytest.mark.parametrize("name", ALL_NAMES)
def test_ac_sub_05_medium_line_length_and_min_duration(name):
    opts = PRESETS["medium"]
    tokens = parsed(name).tokens
    cues = build_cues(tokens, opts)
    counts = cue_token_counts(tokens, cues)
    for i, (cue, (_, n_tokens)) in enumerate(zip(cues, counts, strict=True)):
        if n_tokens > 1:
            for line in cue.lines:
                assert display_len(line) <= opts.max_chars, (i + 1, line)
        if cue.end_ms - cue.start_ms < opts.min_ms and i + 1 < len(cues):
            assert cue.end_ms == cues[i + 1].start_ms, (i + 1, cue)


# ---------- AC-SUB-09: ซับไทยไม่มีช่องว่างและไม่มี word timing ตัดที่ขอบคำ ----------

_THAI_60 = "เราอยากไปเที่ยวทะเลกับครอบครัวช่วงวันหยุดยาวเพราะอยากพักผ่อน"


def test_ac_sub_09_untimed_thai_breaks_at_word_boundaries():
    text = _THAI_60
    assert len(text) == 60 and " " not in text
    assert display_len(text) > 50  # ต้องเกินสองบรรทัดที่ 25 ตัว
    doc = {"events": [{"tStartMs": 0, "dDurationMs": 6000, "segs": [{"utf8": text}]}]}
    track = parse_json3(json.dumps(doc).encode("utf-8"))
    assert track.has_word_timing is False
    cues = build_cues(track.tokens, PRESETS["medium"])
    assert len(cues) >= 3
    word_ends: set[int] = set()
    pos = 0
    for word in tf.split_words(text):
        pos += len(word)
        word_ends.add(pos)
    assert pos == len(text)
    boundary = 0
    for cue in cues:
        boundary += len("".join(cue.lines))
        assert boundary in word_ends, (boundary, cue.lines)
    assert boundary == len(text)


# ---------- AC-SUB-11: vtt ให้ซับเหมือน json3 ----------


@pytest.mark.parametrize("preset", PRESET_NAMES)
def test_ac_sub_11_vtt_cues_match_json3(preset):
    vtt, js = parsed("th-vtt"), parsed("th-asr")
    assert "".join(_nospace(t.t) for t in vtt.tokens) == "".join(_nospace(t.t) for t in js.tokens)
    cues = build_cues(vtt.tokens, PRESETS[preset])
    _assert_no_repeats(cues)
    _assert_text_is_preserved(vtt.tokens, cues)
    # ข้อความหลังรวมทุกซับต้องเท่ากับของ json3
    assert cue_text(vtt.tokens) == cue_text(js.tokens)


# ---------- AC-SUB-08: ไฟล์ .srt ที่ได้ ----------


def _check_srt_bytes(raw: bytes) -> None:
    assert not raw.startswith(b"\xef\xbb\xbf"), "BOM"
    text = raw.decode("utf-8")  # ต้องเป็น UTF-8 ที่ถูกต้อง
    assert text.endswith("\r\n")
    assert "\n" not in text.replace("\r\n", ""), "lone LF"
    assert "\r" not in text.replace("\r\n", ""), "lone CR"
    blocks = text[:-2].split("\r\n\r\n")
    prev_end = -1
    for n, block in enumerate(blocks, start=1):
        lines = block.split("\r\n")
        assert lines[0] == str(n)
        start_s, arrow, end_s = lines[1].partition(" --> ")
        assert arrow
        start, end = _srt_ms(start_s), _srt_ms(end_s)
        assert start <= end
        assert start >= prev_end, f"cue {n} overlaps the previous one"
        assert len(lines) >= 3 and all(lines[2:])
        prev_end = end


def _srt_ms(ts: str) -> int:
    hms, _, ms = ts.partition(",")
    h, m, s = (int(x) for x in hms.split(":"))
    assert len(ms) == 3
    return ((h * 60 + m) * 60 + s) * 1000 + int(ms)


@pytest.mark.parametrize("preset", PRESET_NAMES)
@pytest.mark.parametrize("name", ALL_NAMES)
def test_ac_sub_08_built_srt_is_valid(name, preset):
    _check_srt_bytes(to_srt(build_cues(parsed(name).tokens, PRESETS[preset])).encode("utf-8"))


def test_ac_sub_08_every_golden_srt_is_valid():
    files = sorted(GOLDEN_DIR.glob("*.srt"))
    assert len(files) >= 16
    for path in files:
        _check_srt_bytes(path.read_bytes())
