"""Turn YouTube subtitle files (json3 or vtt) into timed tokens for the SRT builder.

A token is a piece of text with a start and end time in ms (``srt_builder.Token``).

- **Word-timed files** (auto captions): YouTube already cut the text into
  words with their own times. We keep YouTube's words exactly as they are
  and never split them further (FR-SUB-9).
- **Untimed files** (owner subtitles): each subtitle line is one block with
  only a start and an end. We cut the block into words (Thai through
  PyThaiNLP's ``newmm``, other languages at spaces) and share the block's
  time between the words by their on-screen length.

The output always satisfies the parser guarantees of contract C6: tokens are
sorted by start, ``s <= e <= next.s``, every token has a non-space character,
and the only whitespace inside a token is the ASCII space.

``SubParseError`` means the file is unusable; the service then falls back to
the vtt version of the same track.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from yttoolkit.core.srt_builder import Token, display_len
from yttoolkit.core.thai_fallback import has_thai, split_words

PARSER_VERSION = 1

# Python's str.isspace() is true for no code point above U+3000 (a unit test
# checks this), so the table covers every whitespace character.
_NORMALIZE = {cp: " " for cp in range(0x3001) if chr(cp).isspace()}
_NORMALIZE.update({0x200B: None, 0x200C: None, 0x200D: None, 0xFEFF: None})

_SPACE_RUN = re.compile(" {2,}")
_LATIN_WORD = re.compile(r" ?[^ ]+")

_VTT_TIMING = re.compile(
    r"(?:(\d+):)?(\d{2}):(\d{2})\.(\d{3}) --> (?:(\d+):)?(\d{2}):(\d{2})\.(\d{3})"
)
_VTT_WORD_TIMING = re.compile(r"<\d{2}:\d{2}:\d{2}\.\d{3}>")
_VTT_TIME_TAG = re.compile(r"<(?:(\d+):)?(\d{2}):(\d{2})\.(\d{3})>")
_VTT_TAG = re.compile(r"<[^>]*>")
_VTT_ENTITY = re.compile(r"&(amp|lt|gt|nbsp|lrm|rlm);")
_VTT_ENTITIES = {
    "amp": "&",
    "lt": "<",
    "gt": ">",
    "nbsp": " ",
    "lrm": "‎",
    "rlm": "‏",
}
_VTT_MIN_CUE_MS = 50  # rolling vtt puts a 10 ms repeat cue between real cues


class SubParseError(ValueError):
    """The subtitle data is not usable (triggers the vtt fallback)."""


@dataclass(frozen=True)
class ParsedTrack:
    tokens: tuple[Token, ...]
    has_word_timing: bool
    source: str  # "json3" | "vtt"


def normalize_text(s: str) -> str:
    """Remove zero-width characters and turn every other whitespace into " ".

    Removed: U+200B, U+200C, U+200D, U+FEFF. Every ``str.isspace()`` character
    (``\\n``, tab, NBSP, ...) becomes one ASCII space. Runs are not collapsed.
    """
    return s.translate(_NORMALIZE)


def _collapse(s: str) -> str:
    return _SPACE_RUN.sub(" ", s)


def split_block(text: str, start_ms: int, end_ms: int) -> list[Token]:
    """Cut one untimed block into word tokens and share its time between them.

    Thai text is cut by ``newmm``; other text at spaces, a space staying on
    the front of the word after it. Each word gets a share of the time equal
    to its share of ``display_len``, in integer ms; the last word ends at
    ``end_ms``. Blank text gives [].
    """
    text = _collapse(normalize_text(text))
    if has_thai(text):
        words = split_words(text)
    else:
        words = _LATIN_WORD.findall(text)
        if words and text.endswith(" "):
            words[-1] += " "
    if not words:
        return []

    end_ms = max(end_ms, start_ms)
    dur = end_ms - start_ms
    lens = [display_len(w) for w in words]
    total = sum(lens)
    starts: list[int] = []
    cum = 0
    for n in lens:
        starts.append(start_ms + (dur * cum) // total if total else start_ms)
        cum += n
    ends = [*starts[1:], end_ms]
    return [Token(w, s, e) for w, s, e in zip(words, starts, ends, strict=True)]


def _blocks_to_tokens(blocks: list[tuple[str, int, int]]) -> list[Token]:
    """Untimed rule shared by json3 and vtt: one block per subtitle line.

    A block that repeats the block right before it (same text, starting before
    that one ends) is skipped. Every kept block after the first starts with a
    space, because owner lines are sentences.

    Each kept block is spread over [start, min(end, next kept block's start)]
    (never below start), so overlapping blocks cannot interleave their words
    in the final sort.
    """
    kept: list[tuple[str, int, int]] = []
    prev: tuple[str, int] | None = None  # (collapsed text, end) of the block before
    for text, start, end in blocks:
        key = _collapse(text).strip(" ")
        if not key:
            continue
        repeat = prev is not None and key == prev[0] and start < prev[1]
        prev = (key, end)
        if not repeat:
            kept.append((text, start, end))

    tokens: list[Token] = []
    for i, (text, start, end) in enumerate(kept):
        if i + 1 < len(kept):
            end = max(min(end, kept[i + 1][1]), start)
        block = split_block(text, start, end)
        if tokens and block and not block[0].t.startswith(" "):
            first = block[0]
            block[0] = Token(" " + first.t, first.s, first.e)
        tokens.extend(block)
    return tokens


def _finish(tokens: list[Token]) -> tuple[Token, ...]:
    """Final pass for both formats: sort, clamp times, collapse, drop blanks."""
    ordered = sorted(tokens, key=lambda tok: tok.s)  # sorted() is stable
    out: list[Token] = []
    pending = ""
    for i, tok in enumerate(ordered):
        s = max(tok.s, 0)
        e = tok.e
        if i + 1 < len(ordered):
            e = min(e, max(ordered[i + 1].s, 0))
        e = max(e, s)
        t = _collapse(tok.t)
        if not t.strip(" "):
            pending += t
            continue
        if pending:
            t = _collapse(pending + t)
            pending = ""
        out.append(Token(t, s, e))
    return tuple(out)


# json3


def _int_field(obj: dict[str, Any], key: str, default: int | None = None) -> int:
    value = obj.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise SubParseError(f"json3: {key} is not an integer")
    return value


def _seg_text(seg: Any) -> str:
    if not isinstance(seg, dict):
        raise SubParseError("json3: seg is not an object")
    text = seg.get("utf8", "")
    if not isinstance(text, str):
        raise SubParseError("json3: seg utf8 is not a string")
    return normalize_text(text)


def parse_json3(data: bytes) -> ParsedTrack:
    """Parse YouTube's json3 subtitle format (see the json3 rules in the M3 plan, Task 7)."""
    try:
        doc = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise SubParseError(f"json3: {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("events"), list):
        raise SubParseError("json3: no events list")

    kept: list[tuple[int, int, list[tuple[str, int]]]] = []
    has_timing = False
    for ev in doc["events"]:
        if not isinstance(ev, dict):
            raise SubParseError("json3: event is not an object")
        segs = ev.get("segs")
        if ev.get("aAppend") or not segs:
            continue
        if not isinstance(segs, list):
            raise SubParseError("json3: segs is not a list")
        texts = [(_seg_text(seg), _int_field(seg, "tOffsetMs", 0)) for seg in segs]
        if not "".join(t for t, _ in texts).strip(" "):
            continue
        start = _int_field(ev, "tStartMs")
        dur = _int_field(ev, "dDurationMs", 0)
        kept.append((start, start + dur, texts))
        has_timing = has_timing or len(segs) >= 2 or any("tOffsetMs" in seg for seg in segs)

    tokens: list[Token] = []
    if has_timing:
        for start, end, texts in kept:
            words: list[tuple[str, int]] = []
            pending = ""
            for text, offset in texts:
                if not text.strip(" "):
                    pending += text
                    continue
                words.append((pending + text, start + offset))
                pending = ""
            for i, (text, s) in enumerate(words):
                e = words[i + 1][1] if i + 1 < len(words) else end
                tokens.append(Token(text, s, e))
    else:
        blocks = [("".join(t for t, _ in texts), start, end) for start, end, texts in kept]
        tokens = _blocks_to_tokens(blocks)
    return ParsedTrack(_finish(tokens), has_timing, "json3")


# vtt


def _ms(h: str | None, m: str, s: str, ms: str) -> int:
    return ((int(h or 0) * 60 + int(m)) * 60 + int(s)) * 1000 + int(ms)


def _vtt_clean(text: str) -> str:
    text = _VTT_TAG.sub("", text)
    text = _VTT_ENTITY.sub(lambda m: _VTT_ENTITIES[m.group(1)], text)
    return normalize_text(text)


def _vtt_cues(text: str) -> list[tuple[int, int, list[str]]]:
    """Split a WEBVTT body into (start, end, text lines). Headers, ids and notes are skipped."""
    cues: list[tuple[int, int, list[str]]] = []
    current: list[str] | None = None
    for line in text.split("\n")[1:]:
        m = _VTT_TIMING.match(line)
        if m:
            g = m.groups()
            current = []
            cues.append((_ms(*g[:4]), _ms(*g[4:]), current))
        elif line == "":
            current = None
        elif current is not None:
            current.append(line)
    return cues


def _vtt_word_tokens(line: str, start: int, end: int) -> list[Token]:
    """One rolling-vtt line: text before the first time tag starts at the cue start."""
    pieces: list[tuple[str, int]] = []
    pos = 0
    at = start
    for m in _VTT_TIME_TAG.finditer(line):
        pieces.append((line[pos : m.start()], at))
        at = _ms(*m.groups())
        pos = m.end()
    pieces.append((line[pos:], at))
    words = [(_vtt_clean(raw), s) for raw, s in pieces]
    words = [(t, s) for t, s in words if t]
    return [
        Token(t, s, words[i + 1][1] if i + 1 < len(words) else end)
        for i, (t, s) in enumerate(words)
    ]


def parse_vtt(data: bytes) -> ParsedTrack:
    """Parse WebVTT, including YouTube's rolling auto-caption layout."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SubParseError(f"vtt: {exc}") from exc
    if not text.startswith("WEBVTT"):
        raise SubParseError("vtt: missing WEBVTT header")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    cues = _vtt_cues(text)
    has_timing = any(_VTT_WORD_TIMING.search(line) for _, _, lines in cues for line in lines)

    tokens: list[Token] = []
    if has_timing:
        for start, end, lines in cues:
            if end - start < _VTT_MIN_CUE_MS:
                continue
            filled = [line for line in lines if _vtt_clean(line).strip(" ")]
            if filled:
                tokens.extend(_vtt_word_tokens(filled[-1], start, end))
    else:
        blocks = [
            (" ".join(_vtt_clean(line) for line in lines), start, end)
            for start, end, lines in cues
        ]
        tokens = _blocks_to_tokens(blocks)
    return ParsedTrack(_finish(tokens), has_timing, "vtt")
