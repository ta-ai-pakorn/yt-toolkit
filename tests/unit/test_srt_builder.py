from __future__ import annotations

import ast
import json
import random
import re
from dataclasses import replace
from pathlib import Path

import pytest

from yttoolkit.core import srt_builder
from yttoolkit.core.srt_builder import (
    LIMITS,
    MERGE_LIMIT_FACTOR,
    PRESETS,
    Cue,
    SubOptions,
    Token,
    build_cues,
    cue_text,
    display_len,
    is_punct_only,
    options_from_dict,
    to_md,
    to_srt,
    to_txt,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CASES = json.loads((FIXTURES / "subs" / "builder-cases.json").read_text(encoding="utf-8"))["cases"]


def _tokens(raw: list[dict]) -> list[Token]:
    return [Token(t["t"], t["s"], t["e"]) for t in raw]


def _cue_dicts(cues: list[Cue]) -> list[dict]:
    return [{"startMs": c.start_ms, "endMs": c.end_ms, "lines": list(c.lines)} for c in cues]


# ---------- shared cases (the same file drives the TS port in T9) ----------


def test_cases_file_shape() -> None:
    names = [c["name"] for c in CASES]
    assert len(names) == len(set(names))
    for required in (
        "english-char-limit", "thai-display-len", "silence-gap", "max-duration", "tokens-mode",
        "single-long-token", "min-extend-adjacent", "min-merge", "merge-refused-over-limit",
        "two-lines-middle", "two-lines-fits-one", "whitespace-collapse", "over-one-hour", "empty",
        "txt-paragraphs", "md-chapters", "md-two-minute-sections",
        "two-lines-per-line-cap", "two-lines-thai-no-space", "two-lines-long-token-alone",
        "two-lines-merge-refused-per-line", "word-preset-english", "word-preset-thai",
        "word-preset-punctuation", "word-preset-leading-punctuation-and-gap",
        "tokens-mode-punctuation-two-lines", "short-preset-punctuation-unchanged",
    ):
        assert required in names
    raw = (FIXTURES / "subs" / "builder-cases.json").read_bytes()
    assert b"\r" not in raw  # CRLF only appears as JSON escapes


@pytest.mark.parametrize("name", ["short", "medium", "long", "word"])
def test_every_preset_passes_api_validation(name: str) -> None:
    # หน้าเว็บส่งค่าของ preset ไปที่ /export ตรง ๆ ทุก preset จึงต้องผ่าน LIMITS
    p = PRESETS[name]
    d = {"maxChars": p.max_chars, "lines": p.lines, "minMs": p.min_ms, "maxMs": p.max_ms, "mode": p.mode}
    if p.tokens_per_cue is not None:
        d["tokensPerCue"] = p.tokens_per_cue
    assert options_from_dict(d) == p


def test_word_preset_gives_one_token_per_cue() -> None:
    # ทุกซับมี token เดียว รวมถึงคำที่ยาวเกิน max_chars และคำที่สั้นกว่าเวลาขั้นต่ำ (ไม่ถูกรวมกับคำถัดไป)
    toks = [Token("a", 0, 100), Token(" b", 100, 200), Token(" " + "x" * 40, 200, 300), Token(" c", 5000, 5100)]
    cues = build_cues(toks, PRESETS["word"])
    assert [c.lines for c in cues] == [("a",), ("b",), ("x" * 40,), ("c",)]
    assert [(c.start_ms, c.end_ms) for c in cues] == [(0, 100), (100, 200), (200, 1000), (5000, 5800)]


def _case_options(o: dict) -> SubOptions:
    # Not options_from_dict: a case may sit outside the UI LIMITS on purpose
    # (thai-display-len uses maxChars 3), and the builder itself does not validate ranges.
    return SubOptions(
        max_chars=o["maxChars"], lines=o["lines"], min_ms=o["minMs"], max_ms=o["maxMs"],
        mode=o.get("mode", "chars"), tokens_per_cue=o.get("tokensPerCue"),
    )


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_shared_case(case: dict) -> None:
    opts = _case_options(case["options"])
    tokens = _tokens(case["tokens"])
    cues = build_cues(tokens, opts)
    assert _cue_dicts(cues) == case["cues"]
    assert to_srt(cues) == case["srt"]
    assert to_txt(tokens) == case["txt"]
    if "md" in case:
        md = case["md"]
        chapters = [(c["startMs"], c["title"]) for c in md["chapters"]]
        assert to_md(tokens, title=md["title"], video_id=md["videoId"], chapters=chapters) == md["out"]


# ---------- helpers ----------


def test_display_len_thai_marks_not_counted() -> None:
    assert display_len("ที่") == 1
    assert display_len("น้ำ") == 2  # SARA AM (U+0E33) is a spacing vowel
    assert display_len("ดี") == 1
    assert display_len("กัน") == 2  # MAI HAN-AKAT U+0E31
    marks = "ั" + "".join(chr(c) for c in range(0x0E34, 0x0E3B)) + "".join(
        chr(c) for c in range(0x0E47, 0x0E4F)
    )
    assert display_len("ก" + marks) == 1
    # neighbours of the excluded ranges count
    assert display_len("ะาำ฿ๆ๏") == 6
    assert display_len("Hello world") == 11
    assert display_len("😀") == 1  # code points, not UTF-16 units
    assert display_len("") == 0


def test_cue_text_collapses_ascii_spaces_only() -> None:
    toks = [Token("  a  ", 0, 1), Token(" b", 1, 2), Token("c   ", 2, 3)]
    assert cue_text(toks) == "a bc"
    assert cue_text([]) == ""


def test_constants() -> None:
    assert MERGE_LIMIT_FACTOR == 1.0  # Q3 = ก
    assert PRESETS == {
        "short": SubOptions(max_chars=15, lines=1, min_ms=800, max_ms=3000),
        "medium": SubOptions(max_chars=25, lines=1, min_ms=1200, max_ms=5000),
        "long": SubOptions(max_chars=42, lines=2, min_ms=1500, max_ms=7000),
        "word": SubOptions(max_chars=15, lines=1, min_ms=800, max_ms=3000, mode="tokens", tokens_per_cue=1),
    }
    assert list(PRESETS) == ["short", "medium", "long", "word"]  # ลำดับเดียวกับปุ่มในหน้าเว็บ
    chars = [p for name, p in PRESETS.items() if name != "word"]
    assert all(p.mode == "chars" and p.tokens_per_cue is None for p in chars)
    assert LIMITS == {
        "maxChars": (10, 60),
        "lines": (1, 2),
        "minMs": (300, 3000),
        "maxMs": (1000, 10000),
        "tokensPerCue": (1, 20),
    }


def test_srt_timestamp_floor_and_wide_hours() -> None:
    cues = [Cue(0, 999, ("x",)), Cue(3723004, 3723005, ("y",)), Cue(360000000, 360000001, ("z",))]
    assert to_srt(cues) == (
        "1\r\n00:00:00,000 --> 00:00:00,999\r\nx\r\n\r\n"
        "2\r\n01:02:03,004 --> 01:02:03,005\r\ny\r\n\r\n"
        "3\r\n100:00:00,000 --> 100:00:00,001\r\nz\r\n"
    )


def test_md_section_time_floor_seconds() -> None:
    toks = [Token("a", 59999, 60000)]
    out = to_md(toks, title="t", video_id="v", chapters=[(59999, "c")])
    assert "## [00:59] c\r\n" in out


def test_module_is_pure() -> None:
    tree = ast.parse(Path(srt_builder.__file__).read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "no relative (app) imports"
            mods.add(node.module or "")
    assert mods <= {"__future__", "dataclasses", "typing", "re", "unicodedata", "collections.abc"}


# ---------- options_from_dict ----------

GOOD = {"maxChars": 25, "lines": 1, "minMs": 1200, "maxMs": 5000, "mode": "chars"}


def test_options_from_dict_ok() -> None:
    assert options_from_dict(GOOD) == PRESETS["medium"]
    assert options_from_dict({k: v for k, v in GOOD.items() if k != "mode"}) == PRESETS["medium"]
    tok = options_from_dict({**GOOD, "mode": "tokens", "tokensPerCue": 3})
    assert tok == SubOptions(max_chars=25, lines=1, min_ms=1200, max_ms=5000, mode="tokens", tokens_per_cue=3)
    # tokensPerCue is ignored (not even validated) in chars mode
    assert options_from_dict({**GOOD, "tokensPerCue": 99}).tokens_per_cue is None
    # unknown keys (e.g. an export "format") are ignored
    assert options_from_dict({**GOOD, "format": "srt"}) == PRESETS["medium"]
    # both ends of every range are accepted
    options_from_dict({"maxChars": 10, "lines": 2, "minMs": 300, "maxMs": 1000})
    options_from_dict({"maxChars": 60, "lines": 1, "minMs": 3000, "maxMs": 10000, "mode": "tokens", "tokensPerCue": 20})
    options_from_dict({**GOOD, "mode": "tokens", "tokensPerCue": 1})


@pytest.mark.parametrize(
    "bad",
    [
        {**GOOD, "maxChars": 9},
        {**GOOD, "maxChars": 61},
        {**GOOD, "lines": 0},
        {**GOOD, "lines": 3},
        {**GOOD, "minMs": 299},
        {**GOOD, "minMs": 3001},
        {**GOOD, "maxMs": 999},
        {**GOOD, "maxMs": 10001},
        {**GOOD, "minMs": 3000, "maxMs": 3000},
        {**GOOD, "minMs": 2000, "maxMs": 1000},
        {**GOOD, "mode": "tokens"},
        {**GOOD, "mode": "tokens", "tokensPerCue": None},
        {**GOOD, "mode": "tokens", "tokensPerCue": 0},
        {**GOOD, "mode": "tokens", "tokensPerCue": 21},
        {**GOOD, "mode": "words"},
        {**GOOD, "maxChars": 25.0},
        {**GOOD, "maxChars": "25"},
        {**GOOD, "lines": True},
        {k: v for k, v in GOOD.items() if k != "maxMs"},
    ],
)
def test_options_from_dict_rejects(bad: dict) -> None:
    with pytest.raises(ValueError):
        options_from_dict(bad)


# ---------- properties over random token lists ----------

WORDS = [
    "a", "I", "ok", "the", "hello", "world", "subtitle", "extraordinary", "ที่", "น้ำ", "ดี", "กัน",
    "สวัสดีครับ", "ประเทศไทย", "ภาษาไทยนั้นไม่มีช่องว่างระหว่างคำ", "😀", "x" * 50, "y" * 90, ".", ",", "?!", "…", "♪", "--",
]


def _random_tokens(rng: random.Random) -> list[Token]:
    n = rng.choice([0, 1, 2, 3, rng.randint(4, 30), rng.randint(30, 120)])
    toks: list[Token] = []
    t = rng.randint(0, 5000)
    for _ in range(n):
        dur = rng.choice([0, rng.randint(1, 150), rng.randint(150, 900), rng.randint(900, 4000)])
        word = rng.choice(WORDS)
        text = rng.choice(["", " ", " ", "  "]) + word + rng.choice(["", "", " ", "  "])
        toks.append(Token(text, t, t + dur))
        t += dur + rng.choice([0, 0, 0, rng.randint(1, 999), 1000, rng.randint(1000, 2500), 2000, 1999])
    return toks


def _random_options(rng: random.Random) -> list[SubOptions]:
    out = list(PRESETS.values())
    tpc = rng.randint(1, 5)
    out.append(replace(PRESETS["medium"], mode="tokens", tokens_per_cue=tpc))
    out.append(replace(PRESETS["long"], mode="tokens", tokens_per_cue=tpc))
    return out


def _no_space(s: str) -> str:
    return s.replace(" ", "")


def _partition(tokens: list[Token], cues: list[Cue]) -> list[list[Token]]:
    """Walks the tokens in order and assigns each cue its run of tokens (fails if impossible)."""
    groups: list[list[Token]] = []
    i = 0
    for c in cues:
        want = _no_space("".join(c.lines))
        got = ""
        group: list[Token] = []
        while got != want:
            assert i < len(tokens), "cue text is not made of the remaining tokens"
            group.append(tokens[i])
            got += _no_space(tokens[i].t)
            i += 1
            assert want.startswith(got), "tokens out of order or text changed"
        assert group, "empty cue"
        groups.append(group)
    assert i == len(tokens), "tokens left over"
    return groups


SRT_BLOCK = re.compile(r"(\d+)\r\n(\d{2,}):(\d\d):(\d\d),(\d{3}) --> (\d{2,}):(\d\d):(\d\d),(\d{3})\r\n")


def _check(tokens: list[Token], opts: SubOptions) -> None:
    cues = build_cues(tokens, opts)
    groups = _partition(tokens, cues)

    for c, g in zip(cues, groups, strict=True):
        assert c.start_ms == g[0].s
        assert c.end_ms >= g[-1].e
        assert 1 <= len(c.lines) <= opts.lines
        assert all(line and line == line.strip(" ") and "  " not in line for line in c.lines)
        # owner ruling: no line ever exceeds maxChars; only a cue that is one single token is exempt
        # (FR-SUB-9: never cut inside a word). Stricter than "single-token lines exempt".
        punct = [opts.mode == "tokens" and is_punct_only(t) for t in g]
        if len(g) > 1:
            # โหมดนับคำ: เครื่องหมายที่เกาะมาไม่นับเป็นคำ และยกเว้นกฎความยาวบรรทัดเหมือนคำเดียวที่ยาวเกิน
            if not any(punct):
                assert all(display_len(line) <= opts.max_chars for line in c.lines), (c, opts)
            if opts.mode == "tokens":
                assert punct.count(False) <= opts.tokens_per_cue
        if len(c.lines) == 2:
            assert display_len(" ".join(c.lines)) > opts.max_chars

    # ซับที่มีแต่เครื่องหมาย (โหมดนับคำ) เกิดได้เฉพาะเมื่อเงียบ >= 1 วินาทีทั้งก่อนและหลัง
    for idx, g in enumerate(groups):
        if opts.mode == "tokens" and all(is_punct_only(t) for t in g):
            assert idx == 0 or g[0].s - groups[idx - 1][-1].e >= 1000, g
            assert idx == len(groups) - 1 or groups[idx + 1][0].s - g[-1].e >= 1000, g

    for idx, c in enumerate(cues):
        nxt = cues[idx + 1] if idx + 1 < len(cues) else None
        if nxt is not None:
            assert c.end_ms <= nxt.start_ms
        if c.start_ms == c.end_ms:  # only zero-duration input squeezed against the next cue
            assert nxt is not None and nxt.start_ms == c.start_ms
            assert all(t.s == t.e == c.start_ms for t in groups[idx])
        assert c.start_ms <= c.end_ms
        if c.end_ms - c.start_ms < opts.min_ms:  # AC-SUB-05
            assert nxt is not None and c.end_ms == nxt.start_ms

    srt = to_srt(cues)
    txt = to_txt(tokens)
    for out in (srt, txt):
        assert "\n" not in out.replace("\r\n", "")  # AC-SUB-08
        assert "\r" not in out.replace("\r\n", "")
    nums = [int(m.group(1)) for m in SRT_BLOCK.finditer(srt)]
    assert nums == list(range(1, len(cues) + 1))
    assert (srt == "") == (not cues)


def test_properties_random() -> None:
    rng = random.Random(3)
    for _ in range(200):
        tokens = _random_tokens(rng)
        for opts in _random_options(rng):
            _check(tokens, opts)


def test_properties_md_crlf() -> None:
    rng = random.Random(3)
    for _ in range(50):
        tokens = _random_tokens(rng)
        chapters = [(rng.randint(0, 200000), rng.choice(["Intro", "  a\tb ", "ส่วนที่ 2"])) for _ in range(rng.randint(0, 4))]
        out = to_md(tokens, title="T\nx", video_id="v", chapters=chapters)
        assert "\n" not in out.replace("\r\n", "")
        assert out.endswith("\r\n") and not out.endswith("\r\n\r\n")
        body = [line for line in out.split("\r\n")[4:] if line and not line.startswith("## [")]
        assert _no_space("".join(body)) == _no_space("".join(t.t for t in tokens))


def test_two_line_fit_rule_and_balanced_split() -> None:
    toks = [Token("a" * 10, 0, 100), Token(" " + "b" * 10, 100, 200), Token(" " + "c" * 14, 200, 300)]
    opts = SubOptions(max_chars=20, lines=2, min_ms=300, max_ms=5000)
    # greedy: "a b" = 21 > 20 needs a split (10|10 ok); "a b c" = 36: k=1 10|25 bad, k=2 21|14 bad -> close
    assert [c.lines for c in build_cues(toks, opts)] == [("a" * 10, "b" * 10), ("c" * 14,)]
    long_opts = SubOptions(max_chars=25, lines=2, min_ms=300, max_ms=5000)
    # "a b c" = 36 > 25: k=1 10|25 ok, k=2 21|14 ok -> most balanced = k=2
    assert [c.lines for c in build_cues(toks, long_opts)] == [("a" * 10 + " " + "b" * 10, "c" * 14)]


def test_has_split_matches_full_scan() -> None:
    # _has_split is a binary-search shortcut; it must agree with scanning every k (C6 says "some k")
    rng = random.Random(3)
    for _ in range(2000):
        toks = [Token(rng.choice(["", " ", "  "]) + rng.choice(WORDS[:16]) + rng.choice(["", " "]), 0, 0)
                for _ in range(rng.randint(2, 12))]
        cap = rng.randint(1, 60)
        naive = [
            k for k in range(1, len(toks))
            if display_len(cue_text(toks[:k])) <= cap and display_len(cue_text(toks[k:])) <= cap
        ]
        assert [k for k, _, _ in srt_builder._splits(toks, cap)] == naive
        assert srt_builder._has_split(toks, cap) == bool(naive)


def test_build_cues_tokens_mode_without_count_raises() -> None:
    with pytest.raises(ValueError):
        build_cues([Token("a", 0, 1)], SubOptions(max_chars=25, lines=1, min_ms=300, max_ms=5000, mode="tokens"))


def test_single_token_longer_than_limit_stays_whole() -> None:
    long = "x" * 100
    cues = build_cues([Token(long, 0, 2000)], PRESETS["long"])
    assert cues == [Cue(0, 2000, (long,))]


def test_empty_inputs() -> None:
    assert build_cues([], PRESETS["medium"]) == []
    assert to_srt([]) == ""
    assert to_txt([]) == ""
