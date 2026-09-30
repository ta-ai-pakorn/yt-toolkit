from __future__ import annotations

import dataclasses
import json
import re
import sys
from pathlib import Path

import pytest

from yttoolkit.core import thai_fallback as tf
from yttoolkit.core.srt_builder import Token, cue_text
from yttoolkit.core.subparse import (
    PARSER_VERSION,
    ParsedTrack,
    SubParseError,
    normalize_text,
    parse_json3,
    parse_vtt,
    split_block,
)

SUBS = Path(__file__).resolve().parents[1] / "fixtures" / "subs"
TH_JSON3 = SUBS / "88o5Sk8_m1Y" / "th-orig.json3"
TH_VTT = SUBS / "88o5Sk8_m1Y" / "th-orig.vtt"
EN_ASR = SUBS / "8lpOfyoxcvU" / "en-US-orig.json3"
ZOO_JSON3 = SUBS / "jNQXAC9IVRw" / "en.json3"
ZOO_VTT = SUBS / "jNQXAC9IVRw" / "en.vtt"
OWNER_TH = SUBS / "OWNERTHSUB1" / "th.json3"
ALL_JSON3 = sorted(SUBS.glob("*/*.json3"))


@pytest.fixture(autouse=True)
def _keep_data_dir_out_of_home(tmp_path, monkeypatch):
    # PyThaiNLP creates its data folder on first use; keep it out of ~/.
    monkeypatch.setenv(tf.DATA_ENV, str(tmp_path / "pythainlp-data"))


def _raw_events(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8-sig"))["events"]


def _kept_events(path: Path) -> list[dict]:
    """Events the parser keeps: not aAppend, with segs, and some non-blank text."""
    out = []
    for ev in _raw_events(path):
        if ev.get("aAppend") or not ev.get("segs"):
            continue
        if "".join(normalize_text(seg.get("utf8", "")) for seg in ev["segs"]).strip():
            out.append(ev)
    return out


def _no_spaces(tokens) -> str:
    return "".join(t.t for t in tokens).replace(" ", "")


def _assert_c6(tokens: tuple[Token, ...]) -> None:
    """The parser guarantees of contract C6 (the SRT builder relies on them)."""
    for i, tok in enumerate(tokens):
        assert tok.t.strip(" "), f"blank token {i}"
        assert not re.search(r"[^\S ]", tok.t), f"non-space whitespace in {tok.t!r}"
        assert "  " not in tok.t
        assert 0 <= tok.s <= tok.e
        if i + 1 < len(tokens):
            assert tok.s <= tokens[i + 1].s
            assert tok.e <= tokens[i + 1].s


# normalize_text


def test_normalize_text_removes_zero_width_and_maps_whitespace():
    assert normalize_text("a​b‌c‍d﻿e") == "abcde"
    assert normalize_text("a\nb c\td　e") == "a b c d e"
    assert normalize_text("a \n b") == "a   b"  # no collapsing


def test_normalize_text_covers_every_isspace_character():
    # The translate table stops at U+3000; nothing above it is whitespace.
    assert not any(chr(cp).isspace() for cp in range(0x3001, sys.maxunicode + 1))
    spaces = "".join(chr(cp) for cp in range(0x3001) if chr(cp).isspace())
    assert normalize_text(spaces) == " " * len(spaces)


# split_block


def test_split_block_latin_words_keep_leading_space_and_trailing_space_glued():
    toks = split_block("one  two three ", 0, 1000)
    assert [t.t for t in toks] == ["one", " two", " three "]


def test_split_block_spreads_time_by_display_len_in_integer_ms():
    # lens 3, 4, 6 (total 13) over 1000 ms
    toks = split_block("one two three", 100, 1100)
    assert [(t.s, t.e) for t in toks] == [(100, 330), (330, 638), (638, 1100)]


def test_split_block_blank_text_gives_nothing():
    assert split_block("  \n ", 0, 1000) == []


def test_split_block_zero_display_len_puts_every_token_at_start():
    # Thai non-spacing marks only: display_len is 0 for both "words".
    toks = split_block("่ ้", 500, 900)
    assert [t.s for t in toks] == [500, 500]
    assert toks[-1].e == 900


def test_split_block_thai_60_chars_no_spaces_ac_sub_09():
    text = "ร้านกาแฟเล็กๆแถวบ้านขายดีมากเพราะเจ้าของใส่ใจลูกค้าทุกคนเสมอ"
    assert len(text) == 60 and " " not in text
    toks = split_block(text, 2000, 7000)
    assert len(toks) >= 4
    assert [t.t for t in toks] == tf.split_words(text)
    assert sum(t.e - t.s for t in toks) == 5000
    assert toks[0].s == 2000 and toks[-1].e == 7000
    assert all(a.e == b.s for a, b in zip(toks, toks[1:], strict=False))


# json3: word-timed (auto captions)


def test_thai_asr_json3_one_token_per_seg_ac_sub_03():
    track = parse_json3(TH_JSON3.read_bytes())
    assert isinstance(track, ParsedTrack)
    assert track.source == "json3"
    assert track.has_word_timing is True
    toks = track.tokens
    assert all(t.t.strip() and "\n" not in t.t for t in toks)
    expected = sum(
        1 for ev in _kept_events(TH_JSON3) for seg in ev["segs"] if normalize_text(seg["utf8"]).strip()
    )
    assert len(toks) == expected
    _assert_c6(toks)
    assert toks[0] == Token("สวัสดี", 120, 1120)


def test_thai_asr_json3_keeps_every_character_ac_sub_04():
    track = parse_json3(TH_JSON3.read_bytes())
    source = "".join(normalize_text(seg["utf8"]) for ev in _kept_events(TH_JSON3) for seg in ev["segs"])
    assert _no_spaces(track.tokens) == source.replace(" ", "")


def test_thai_asr_json3_keeps_youtube_word_boundaries():
    track = parse_json3(TH_JSON3.read_bytes())
    # One of the real segs is " 7:00 " with spaces; it stays one token.
    assert " 7:00 " in [t.t for t in track.tokens]


def test_english_asr_json3_keeps_leading_spaces():
    track = parse_json3(EN_ASR.read_bytes())
    assert track.has_word_timing
    texts = [t.t for t in track.tokens]
    assert " the" in texts
    first5 = cue_text(track.tokens[:5])
    assert first5 == "In the 1956 era."
    assert re.fullmatch(r"[A-Za-z0-9.]+( [A-Za-z0-9.]+)*", first5)
    _assert_c6(track.tokens)


def test_timed_json3_glues_whitespace_seg_onto_next_seg():
    doc = {
        "events": [
            {"tStartMs": 1000, "dDurationMs": 2000, "segs": [
                {"utf8": "a"},
                {"utf8": "\n", "tOffsetMs": 300},
                {"utf8": "b", "tOffsetMs": 600},
                {"utf8": " ", "tOffsetMs": 900},
            ]},
        ]
    }
    track = parse_json3(json.dumps(doc).encode())
    assert track.tokens == (Token("a", 1000, 1600), Token(" b", 1600, 3000))


def test_timed_json3_clamps_overlapping_events():
    doc = {
        "events": [
            {"tStartMs": 0, "dDurationMs": 5000, "segs": [{"utf8": "a"}, {"utf8": " b", "tOffsetMs": 1000}]},
            {"tStartMs": 3000, "dDurationMs": 1000, "segs": [{"utf8": " c"}]},
            {"tStartMs": 4000, "dDurationMs": 1000, "aAppend": 1, "segs": [{"utf8": "\n"}]},
        ]
    }
    track = parse_json3(json.dumps(doc).encode())
    assert track.has_word_timing  # one event has 2 segs
    assert track.tokens == (Token("a", 0, 1000), Token(" b", 1000, 3000), Token(" c", 3000, 4000))


def test_single_seg_with_offset_counts_as_word_timing():
    doc = {"events": [{"tStartMs": 0, "dDurationMs": 900, "segs": [{"utf8": "one two", "tOffsetMs": 100}]}]}
    track = parse_json3(json.dumps(doc).encode())
    assert track.has_word_timing
    assert track.tokens == (Token("one two", 100, 900),)  # never split further


# json3: untimed (owner subtitles)


def test_owner_english_json3_is_untimed_blocks():
    track = parse_json3(ZOO_JSON3.read_bytes())
    assert track.has_word_timing is False
    toks = track.tokens
    assert toks[0].t == "All" and toks[0].s == 1200
    block2 = [t for t in toks if 5318 <= t.s < 7974]
    assert block2 and all(t.t.startswith(" ") for t in block2)
    assert cue_text(block2) == "the cool thing about these guys is that they have really..."
    _assert_c6(toks)


def test_owner_thai_json3_uses_newmm_words_per_block():
    track = parse_json3(OWNER_TH.read_bytes())
    assert track.has_word_timing is False
    events = _kept_events(OWNER_TH)
    source = "".join(seg["utf8"] for ev in events for seg in ev["segs"])
    assert _no_spaces(track.tokens) == re.sub(r"\s", "", source)

    toks = list(track.tokens)
    pos = 0
    for n, ev in enumerate(events):
        text = re.sub(" {2,}", " ", normalize_text("".join(seg["utf8"] for seg in ev["segs"])))
        words = tf.split_words(text)
        if n and not words[0].startswith(" "):
            words[0] = " " + words[0]
        block = toks[pos : pos + len(words)]
        pos += len(words)
        # Every token boundary is a newmm word boundary (never inside a word).
        assert [t.t for t in block] == words
        start, end = ev["tStartMs"], ev["tStartMs"] + ev["dDurationMs"]
        assert block[0].s == start and block[-1].e == end
        assert all(a.s <= b.s and a.e == b.s for a, b in zip(block, block[1:], strict=False))
    assert pos == len(toks)
    _assert_c6(track.tokens)


def test_owner_thai_json3_line_break_becomes_a_word_boundary():
    track = parse_json3(OWNER_TH.read_bytes())
    texts = [t.t for t in track.tokens]
    assert all("\n" not in t for t in texts)
    # "...เรื่อง\nการทำ..." in block 2: the line break is a space before the next word.
    assert any(t.startswith(" การ") for t in texts)


def test_untimed_json3_skips_repeated_block_and_prefixes_space():
    doc = {
        "events": [
            {"tStartMs": 0, "dDurationMs": 2000, "segs": [{"utf8": "Hello  there"}]},
            {"tStartMs": 1500, "dDurationMs": 2000, "segs": [{"utf8": "Hello there "}]},  # repeat
            {"tStartMs": 3000, "dDurationMs": 1000, "segs": [{"utf8": "Bye"}]},
            {"tStartMs": 4000, "dDurationMs": 1000, "segs": [{"utf8": "Bye"}]},  # after the end: kept
            {"tStartMs": 5000, "dDurationMs": 1000, "segs": [{"utf8": " \n "}]},  # blank
        ]
    }
    track = parse_json3(json.dumps(doc).encode())
    assert track.has_word_timing is False
    assert [t.t for t in track.tokens] == ["Hello", " there", " Bye", " Bye"]
    assert [(t.s, t.e) for t in track.tokens] == [(0, 909), (909, 2000), (3000, 4000), (4000, 5000)]


def test_all_json3_fixtures_meet_the_c6_guarantees():
    for path in ALL_JSON3:
        if path.name == "broken.json3":
            continue
        track = parse_json3(path.read_bytes())
        assert track.tokens, path
        _assert_c6(track.tokens)


# vtt


def test_thai_asr_vtt_matches_json3_ac_sub_11():
    """Rolling vtt: only the last line of each cue is new, 10 ms repeat cues are skipped.

    The real 88o5 vtt and json3 agree token for token on text and start time,
    so no YouTube-side difference needs tolerating here.
    """
    vtt = parse_vtt(TH_VTT.read_bytes())
    js = parse_json3(TH_JSON3.read_bytes())
    assert vtt.source == "vtt"
    assert vtt.has_word_timing is True
    assert _no_spaces(vtt.tokens) == _no_spaces(js.tokens)
    assert [(t.t, t.s) for t in vtt.tokens] == [(t.t, t.s) for t in js.tokens]
    assert vtt.tokens[0].t == "สวัสดี" and vtt.tokens[0].s == 120
    assert vtt.tokens[1].t == "ครับ" and vtt.tokens[1].s == 1120
    _assert_c6(vtt.tokens)


def test_owner_vtt_matches_owner_json3():
    vtt = parse_vtt(ZOO_VTT.read_bytes())
    js = parse_json3(ZOO_JSON3.read_bytes())
    assert vtt.has_word_timing is False
    assert cue_text(vtt.tokens) == cue_text(js.tokens)
    assert vtt.tokens == js.tokens


def test_vtt_timed_tags_entities_and_short_cues():
    data = (
        "﻿WEBVTT\r\nKind: captions\r\n\r\n"
        "NOTE a comment\r\n\r\n"
        "cue-1\r\n"
        "00:00:01.000 --> 00:00:03.000 align:start position:0%\r\n"
        " \r\n"
        "Tom<00:00:01.500><c.colorE5E5E5> &amp;</c><00:00:02.000><c> Jerry&nbsp;</c>\r\n"
        "\r\n"
        "00:00:03.000 --> 00:00:03.010\r\n"
        "Tom & Jerry\r\n"
        " \r\n"
        "\r\n"
        "00:00:03.010 --> 00:00:04.000\r\n"
        "Tom & Jerry\r\n"
        "<00:00:03.200><c>end</c>\r\n"
    ).encode()
    track = parse_vtt(data)
    assert track.has_word_timing
    assert track.tokens == (
        Token("Tom", 1000, 1500),
        Token(" &", 1500, 2000),
        Token(" Jerry ", 2000, 3000),  # &nbsp; becomes a plain space
        Token("end", 3200, 4000),  # the 10 ms repeat cue is skipped
    )


def test_vtt_cue_times_with_long_hours():
    data = b"WEBVTT\n\n100:00:00.005 --> 100:00:01.000\nlate\n"
    track = parse_vtt(data)
    assert track.tokens == (Token("late", 360_000_005, 360_001_000),)


def test_vtt_untimed_joins_lines_and_strips_tags():
    data = (
        "WEBVTT\n\n"
        "1\n00:01.000 --> 00:02.000\n<i>Hello</i>\nworld &lt;3\n\n"
        "2\n00:02.000 --> 00:03.000\n<v Bob>Again</v>\n"
    ).encode()
    track = parse_vtt(data)
    assert track.has_word_timing is False
    assert [t.t for t in track.tokens] == ["Hello", " world", " <3", " Again"]
    assert track.tokens[0].s == 1000 and track.tokens[-1].e == 3000


# errors and constants


@pytest.mark.parametrize(
    "data",
    [
        (SUBS / "VTTFALLBAK1" / "broken.json3").read_bytes(),
        b"{}",
        b"[]",
        b'{"events": {}}',
        b"\xff\xfe not utf-8",
        b'{"events": [{"tStartMs": "x", "segs": [{"utf8": "a"}]}]}',
        b'{"events": [{"tStartMs": 0, "segs": [{"utf8": 5}]}]}',
        b'{"events": ["nope"]}',
    ],
    ids=["truncated", "no-events", "list", "events-not-list", "not-utf8", "bad-start", "bad-utf8", "bad-event"],
)
def test_json3_errors(data):
    with pytest.raises(SubParseError):
        parse_json3(data)


@pytest.mark.parametrize(
    "data",
    [b"not a vtt", b"", b"\xff\xfeWEBVTT", TH_JSON3.read_bytes()],
    ids=["text", "empty", "not-utf8", "json3"],
)
def test_vtt_errors(data):
    with pytest.raises(SubParseError):
        parse_vtt(data)


def test_subparse_error_is_value_error_and_track_is_frozen():
    assert issubclass(SubParseError, ValueError)
    assert PARSER_VERSION == 1
    track = parse_json3(ZOO_JSON3.read_bytes())
    assert isinstance(track.tokens, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        track.source = "vtt"  # type: ignore[misc]
