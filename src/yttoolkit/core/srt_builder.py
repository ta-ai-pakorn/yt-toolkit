"""แปลง token (คำพร้อมเวลา) เป็นซับ แล้วเขียนออกเป็น .srt / .txt / .md (PRD FR-SUB, AC-SUB-04/05/08)

อัลกอริทึมตามสัญญา C6 ในแผน M3 ทุกบรรทัด ฝั่ง TypeScript (`web/src/lib/srt-builder.ts`, T9)
ต้องให้ผลตรงกันทุกไบต์ ทั้งสองฝั่งทดสอบด้วยชุดเดียวกันคือ `tests/fixtures/subs/builder-cases.json`
แก้ตรงนี้ต้องแก้ฝั่ง TS และชุดทดสอบไปพร้อมกัน

ตัวอย่าง: token "Hello"(0-400) " world"(400-900) ที่ preset กลาง ได้ซับ 1 ตัว 0-1200 ms "Hello world"
(ยืดให้ครบเวลาขั้นต่ำ 1200 ms เพราะเป็นตัวสุดท้าย)

token มาจาก parser (T7) ซึ่งรับประกันว่า: เรียงตาม s, e >= s, e <= s ของตัวถัดไป, มีตัวที่ไม่ใช่ช่องว่าง
อย่างน้อย 1 ตัว และช่องว่างมีแค่ U+0020

โมดูลนี้ไม่ import อะไรจากแอป ไม่แตะไฟล์หรือเน็ต
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


@dataclass(frozen=True)
class Token:
    t: str
    s: int
    e: int


@dataclass(frozen=True)
class SubOptions:
    max_chars: int
    lines: int
    min_ms: int
    max_ms: int
    mode: str = "chars"
    tokens_per_cue: int | None = None


@dataclass(frozen=True)
class Cue:
    start_ms: int
    end_ms: int
    lines: tuple[str, ...]


# C5: ค่าเดียวกับฝั่ง TS ทุกตัว
PRESETS: dict[str, SubOptions] = {
    "short": SubOptions(max_chars=15, lines=1, min_ms=800, max_ms=3000),
    "medium": SubOptions(max_chars=25, lines=1, min_ms=1200, max_ms=5000),
    "long": SubOptions(max_chars=42, lines=2, min_ms=1500, max_ms=7000),
    # "ทีละคำ" (พิธตัดสิน 2026-10-01): ซับละ 1 token แบบซับคลิปสั้น · token เดียวไม่ถูกตัดอยู่แล้ว
    # และยาวเกิน max_chars ได้ ค่าตัวอักษรกับเวลาจึงเท่ากับ "สั้น" (คำแสดงค้างได้ถึง 0.8 วิ หรือจนคำถัดไปขึ้น)
    "word": SubOptions(max_chars=15, lines=1, min_ms=800, max_ms=3000, mode="tokens", tokens_per_cue=1),
}
LIMITS: dict[str, tuple[int, int]] = {
    "maxChars": (10, 60),
    "lines": (1, 2),
    "minMs": (300, 3000),
    "maxMs": (1000, 10000),
    "tokensPerCue": (1, 20),
}
# Q3 = ก: รวมซับที่สั้นเกินกับตัวถัดไปได้เฉพาะเมื่อไม่เกินขีดจำกัดเลย
MERGE_LIMIT_FACTOR: float = 1.0

GAP_SPLIT_MS = 1000  # เงียบนานเท่านี้ขึ้นไป = ขึ้นซับใหม่
PARAGRAPH_GAP_MS = 2000  # เงียบนานเท่านี้ขึ้นไป = ขึ้นย่อหน้าใหม่ใน .txt / .md
MD_SECTION_MS = 120_000  # ไม่มี chapter: แบ่งหัวข้อ .md ทุก 2 นาที
CRLF = "\r\n"

_SPACE_RUN = re.compile(" {2,}")
# ชุดเดียวกับ \s ของ JavaScript (และสิ่งที่ String.prototype.trim ตัด) ไม่ใช้ \s ของ Python
# เพราะ Python นับ \x1c-\x1f และ \x85 เป็นช่องว่างแต่ไม่นับ U+FEFF ซึ่งจะทำให้ผลไม่ตรงกับฝั่ง TS
# (raw string: ตัว re แปลง \uXXXX เอง ในไฟล์จึงไม่มีตัวอักษรล่องหน)
_JS_WS = r"\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
_WS_RUN = re.compile(f"[{_JS_WS}]+")
_WS_EDGE = re.compile(f"^[{_JS_WS}]+|[{_JS_WS}]+$")


# สระบน สระล่าง วรรณยุกต์ และเครื่องหมายที่ไม่กินที่ (Q7 = ก): U+0E31, U+0E34-0E3A, U+0E47-0E4E
# (ตรงกับตัวอักษรหมวด Mn ในช่วงภาษาไทยพอดี) ใช้ regex เพราะเร็วกว่าไล่ทีละตัวมาก
_THAI_MARKS = re.compile(r"[\u0e31\u0e34-\u0e3a\u0e47-\u0e4e]")


def display_len(text: str) -> int:
    """ความยาวตามที่ตาเห็น: นับ code point ยกเว้นสระบน/ล่างและวรรณยุกต์ไทย ("ที่" = 1, "น้ำ" = 2)"""
    return len(text) - len(_THAI_MARKS.findall(text))


def cue_text(tokens: Sequence[Token]) -> str:
    """ต่อข้อความ token ยุบช่องว่างที่ติดกันเหลือช่องเดียว แล้วตัดช่องว่างหัวท้าย"""
    return _SPACE_RUN.sub(" ", "".join(tok.t for tok in tokens)).strip(" ")


def is_punct_only(token: Token) -> bool:
    """ข้อความที่เห็นของ token (ตัด U+0020 หัวท้าย) เป็นเครื่องหมายล้วน: หมวด Unicode P* หรือ S* ทุกตัว

    เช่น "." "," " ?" "♪" "--" นับ ส่วน "a." "1" ". ." (มีช่องว่างกลาง) ไม่นับ (ฝั่ง TS ใช้ regex หมวด P กับ S แบบ u)
    """
    text = token.t.strip(" ")
    return bool(text) and all(unicodedata.category(ch)[0] in "PS" for ch in text)


# เครื่องหมายเปิดที่เกาะหน้าคำถัดไปเสมอ (fix round 1): ( [ { « “ ‘ ¿ ¡ และ ( [ { แบบเต็มความกว้าง
OPENERS = frozenset("([{\u00ab\u201c\u2018\u00bf\u00a1\uff08\uff3b\uff5b")
# อัญประกาศตรงที่เป็นได้ทั้งเปิดและปิด (" ' และแบบเต็มความกว้าง) ตัดสินจากช่องว่างรอบตัว (_kinds)
STRAIGHT_QUOTES = frozenset("\"'\uff02\uff07")
_WORD, _BACK, _FORWARD = 0, 1, 2


def _only(token: Token, chars: frozenset[str]) -> bool:
    text = token.t.strip(" ")
    return bool(text) and all(ch in chars for ch in text)


def _kinds(tokens: Sequence[Token]) -> list[int]:
    """โหมดนับคำ: คำ (_WORD) / เครื่องหมายที่เกาะคำก่อนหน้า (_BACK) / เครื่องหมายเปิดที่เกาะคำถัดไป (_FORWARD)

    เครื่องหมายเปิดเกาะไปข้างหน้าได้เมื่อถัดไปมี token ที่ห่างไม่ถึง 1 วินาที และเป็นคำหรือเครื่องหมายเปิดอีกตัว
    (ไม่งั้นเกาะคำก่อนหน้าเหมือนเครื่องหมายอื่น เช่นวงเล็บเปิดตัวสุดท้ายของแทร็ก)
    อัญประกาศตรงนับเป็นเครื่องหมายเปิดเมื่อ (1) ข้างหน้ามีช่องว่าง: ตัวมันขึ้นต้นด้วย U+0020, token ก่อนหน้าจบด้วย U+0020,
    token ก่อนหน้าเป็นเครื่องหมายเปิด, เป็น token แรก หรือเงียบ >= 1 วินาทีก่อนหน้า และ (2) token ถัดไปติดกันไม่มีช่องว่าง
    (ตัวมันไม่จบด้วย U+0020 และ token ถัดไปไม่ขึ้นต้นด้วย U+0020) ใช้ได้เพราะ token ของยูทูปเก็บช่องว่างนำหน้าคำไว้
    """
    n = len(tokens)
    kinds = [_WORD] * n
    for i in range(n - 1, -1, -1):
        tok = tokens[i]
        if not is_punct_only(tok):
            continue
        kinds[i] = _BACK
        if i + 1 >= n or kinds[i + 1] == _BACK or tokens[i + 1].s - tok.e >= GAP_SPLIT_MS:
            continue
        if _only(tok, OPENERS):
            kinds[i] = _FORWARD
        elif _only(tok, STRAIGHT_QUOTES):
            prev = tokens[i - 1] if i > 0 else None
            spaced_before = (
                prev is None
                or tok.s - prev.e >= GAP_SPLIT_MS
                or tok.t.startswith(" ")
                or prev.t.endswith(" ")
                or _only(prev, OPENERS)
            )
            glued_after = not tok.t.endswith(" ") and not tokens[i + 1].t.startswith(" ")
            if spaced_before and glued_after:
                kinds[i] = _FORWARD
    return kinds


def _collapse(text: str) -> str:
    # ใช้กับชื่อคลิปและชื่อ chapter เท่านั้น
    return _WS_EDGE.sub("", _WS_RUN.sub(" ", text))


# ---------- options ----------


def _int_in(d: Mapping[str, Any], key: str) -> int:
    if key not in d:
        raise ValueError(f"{key} is required")
    value = d[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    lo, hi = LIMITS[key]
    if not lo <= value <= hi:
        raise ValueError(f"{key} must be between {lo} and {hi}")
    return value


def options_from_dict(d: Mapping[str, Any]) -> SubOptions:
    """รับค่าแบบ camelCase (เหมือนฝั่งเว็บ) ตรวจตาม LIMITS แล้วคืน SubOptions ผิดเงื่อนไข = ValueError

    ช่วงค่าเท่านั้นที่ตรวจ ส่วน step (100 / 500) เป็นเรื่องของ UI ไม่ตรวจที่นี่ key อื่นที่ไม่รู้จักถูกข้าม
    """
    max_chars = _int_in(d, "maxChars")
    lines = _int_in(d, "lines")
    min_ms = _int_in(d, "minMs")
    max_ms = _int_in(d, "maxMs")
    if min_ms >= max_ms:
        raise ValueError("minMs must be less than maxMs")
    mode = d.get("mode", "chars")
    if mode not in ("chars", "tokens"):
        raise ValueError("mode must be 'chars' or 'tokens'")
    tokens_per_cue = _int_in(d, "tokensPerCue") if mode == "tokens" else None
    return SubOptions(
        max_chars=max_chars, lines=lines, min_ms=min_ms, max_ms=max_ms, mode=mode, tokens_per_cue=tokens_per_cue
    )


# ---------- tokens -> cues ----------


@dataclass
class _Draft:
    tokens: list[Token]
    start_ms: int
    end_ms: int


def _draft(tokens: list[Token]) -> _Draft:
    return _Draft(tokens, tokens[0].s, tokens[-1].e)


def _line_len(tokens: Sequence[Token]) -> int:
    return display_len(cue_text(tokens))


def _splits(tokens: Sequence[Token], cap: float) -> list[tuple[int, int, int]]:
    """จุดแบ่ง 2 บรรทัดที่ใช้ได้: (k, ยาวบรรทัดบน, ยาวบรรทัดล่าง) ที่ทั้งสองบรรทัด <= cap"""
    out: list[tuple[int, int, int]] = []
    for k in range(1, len(tokens)):
        left = _line_len(tokens[:k])
        if left > cap:
            break  # บรรทัดบนยาวขึ้นเรื่อย ๆ เมื่อ k โต ที่เหลือใช้ไม่ได้แน่นอน (แค่ทางลัด ผลเท่าเดิม)
        right = _line_len(tokens[k:])
        if right <= cap:
            out.append((k, left, right))
    return out


def _fits(tokens: Sequence[Token], opts: SubOptions, cap: float) -> bool:
    """ซับที่มี token >= 2 ตัว "พอดี" เมื่อทุกบรรทัดยาวไม่เกิน cap (เจ้าของสั่ง: ห้ามบรรทัดไหนเกิน maxChars)

    1 บรรทัด: ทั้งก้อน <= cap / 2 บรรทัด: ทั้งก้อน <= cap หรือมีจุดแบ่งที่ทั้งสองบรรทัด <= cap
    token เดียวไม่ต้องตรวจ: หั่นกลางคำไม่ได้ (FR-SUB-9) แต่ก็ไม่มีคำอื่นมาต่อได้เหมือนกัน
    """
    if len(tokens) < 2:
        return True
    if _line_len(tokens) <= cap:
        return True
    return opts.lines == 2 and _has_split(tokens, cap)


def _has_split(tokens: Sequence[Token], cap: float) -> bool:
    """เหมือน bool(_splits(tokens, cap)) แต่เร็วกว่า (ข้อความยาว 1 ชม. ใช้ตรงนี้หลายหมื่นครั้ง)

    ยาวบรรทัดบนไม่ลดลงเมื่อ k โต และบรรทัดล่างไม่เพิ่มขึ้น จึงหา k ที่น้อยที่สุดที่บรรทัดล่าง <= cap
    ด้วย binary search แล้วดูว่าบรรทัดบนที่ k นั้นยัง <= cap ไหม ผลตรงกับการไล่ทุก k
    """
    lo, hi = 1, len(tokens) - 1
    if _line_len(tokens[hi:]) > cap:
        return False
    while lo < hi:
        mid = (lo + hi) // 2
        if _line_len(tokens[mid:]) <= cap:
            hi = mid
        else:
            lo = mid + 1
    return _line_len(tokens[:lo]) <= cap


def _lines(tokens: list[Token], opts: SubOptions) -> tuple[str, ...]:
    text = cue_text(tokens)
    cands = (
        _splits(tokens, opts.max_chars * MERGE_LIMIT_FACTOR)
        if opts.lines == 2 and len(tokens) >= 2 and display_len(text) > opts.max_chars
        else []
    )
    if cands:
        # ซับที่ผ่าน _fits มีจุดแบ่งอย่างน้อย 1 จุดเสมอ ยกเว้นคำยาวเกินที่มีเครื่องหมายเกาะท้าย (โหมดนับคำ) = บรรทัดเดียว
        best_k, best_diff = cands[0][0], abs(cands[0][1] - cands[0][2])
        for k, left, right in cands[1:]:
            if abs(left - right) < best_diff:  # เท่ากันให้ k ที่น้อยกว่า
                best_k, best_diff = k, abs(left - right)
        return (cue_text(tokens[:best_k]), cue_text(tokens[best_k:]))
    # token เดียวที่ยาวเกินขีดจำกัดก็อยู่ทั้งก้อน ไม่หั่นกลางคำ (FR-SUB-9)
    return (text,)


def build_cues(tokens: Sequence[Token], opts: SubOptions) -> list[Cue]:
    """C6 ขั้น 1-4: จับกลุ่ม, เวลาขั้นต่ำ (ยืด/รวม), กันเวลาทับ, แบ่งบรรทัด

    mode "tokens" แต่ไม่มี tokens_per_cue = ValueError (TS: throw)
    """
    tokens_mode = opts.mode == "tokens"
    if tokens_mode and not opts.tokens_per_cue:
        raise ValueError("tokens mode needs tokens_per_cue")
    per_cue = opts.tokens_per_cue or 0

    # โหมดนับคำ (owner round 3 + fix round 1): token ที่เป็นเครื่องหมายล้วนไม่นับเป็นคำ
    # - เครื่องหมายทั่วไปเกาะซับของคำก่อนหน้า (ไม่ใช้กฎจำนวนคำ แต่ยังต้องไม่เกินตัวอักษร/เวลานานสุด) ตัวแรกสุดเกาะซับถัดไป
    # - เครื่องหมายเปิด ( “ และอัญประกาศตรงที่ทำหน้าที่เปิด เกาะหน้าคำถัดไป (_kinds)
    # ซับที่มีแค่เครื่องหมายจึงเกิดได้เฉพาะเมื่อเงียบ >= 1 วินาที หรือเกาะแล้วจะเกินตัวอักษร/เวลานานสุด (review #1)
    kinds = _kinds(tokens) if tokens_mode else [_WORD] * len(tokens)
    punct = [kind != _WORD for kind in kinds]

    def words(start: int, end: int) -> int:
        return sum(1 for k in range(start, end) if not punct[k])

    def chain_end(start: int) -> int:
        """token แรกหลังเครื่องหมายเปิดที่ต่อกันตั้งแต่ start (คือคำที่เครื่องหมายเปิดเหล่านี้เกาะ)"""
        k = start
        while kinds[k] == _FORWARD:
            k += 1
        return k

    # 1. จับกลุ่มแบบ greedy (cur = token ช่วง [cur_from, i))
    drafts: list[_Draft] = []
    cur: list[Token] = []
    cur_from = 0
    for i, tok in enumerate(tokens):
        if cur:
            gap = tok.s - cur[-1].e >= GAP_SPLIT_MS
            # เครื่องหมายเปิดตัดสินพร้อมคำที่มันเกาะ (ช่วง i..j): ถ้าคำนั้นต้องขึ้นซับใหม่ เครื่องหมายก็ขึ้นไปด้วย
            j = chain_end(i) if kinds[i] == _FORWARD else i
            # ทุก token (รวมเครื่องหมาย) ต้องไม่ทำให้เกินขีดจำกัดตัวอักษร/เวลานานสุด (fix round 2, review #1)
            # เกินเมื่อไรก็ขึ้นซับใหม่ตามปกติ แม้จะได้ซับที่ขึ้นต้นด้วยเครื่องหมาย
            capped = (
                not _fits([*cur, *tokens[i : j + 1]], opts, opts.max_chars)
                or tokens[j].e - cur[0].s > opts.max_ms
            )
            # กฎจำนวนคำใช้กับคำและเครื่องหมายเปิดเท่านั้น: เครื่องหมายที่เกาะคำก่อนหน้า และคำที่มีเครื่องหมายเปิด
            # นำหน้าอยู่แล้ว ไม่ขึ้นซับใหม่เพราะจำนวนคำ (ซับที่มีแต่เครื่องหมายนำหน้ามีคำ 0 จึงไม่ถึงเกณฑ์เอง)
            counted = kinds[i] != _BACK and kinds[i - 1] != _FORWARD
            close = gap or capped or (tokens_mode and counted and words(cur_from, i) >= per_cue)
            if close:
                drafts.append(_draft(cur))
                cur = []
                cur_from = i
        cur.append(tok)
    if cur:
        drafts.append(_draft(cur))
    # ช่วง token ของแต่ละซับ (ใช้นับคำตอนรวมซับในขั้น 2)
    first: list[int] = []
    pos = 0
    for d in drafts:
        first.append(pos)
        pos += len(d.tokens)

    # 2. เวลาขั้นต่ำ: ยืดไปได้ถึงต้นซับถัดไป ถ้ายังสั้นอยู่ลองรวมกับตัวถัดไป แล้วตรวจตัวเดิมซ้ำ
    i = 0
    while i < len(drafts):
        c = drafts[i]
        nxt = drafts[i + 1] if i + 1 < len(drafts) else None
        if c.end_ms - c.start_ms < opts.min_ms:
            want = c.start_ms + opts.min_ms
            c.end_ms = min(want, nxt.start_ms) if nxt is not None else want
            if c.end_ms - c.start_ms < opts.min_ms and nxt is not None:
                merged = c.tokens + nxt.tokens
                start = first[i]
                if (
                    _fits(merged, opts, opts.max_chars * MERGE_LIMIT_FACTOR)
                    and nxt.end_ms - c.start_ms <= opts.max_ms
                    and (not tokens_mode or words(start, start + len(merged)) <= per_cue)
                ):
                    drafts[i : i + 2] = [_Draft(merged, c.start_ms, nxt.end_ms)]
                    first[i : i + 2] = [start]
                    continue
        i += 1

    # 3. กันเวลาทับกัน
    for a, b in zip(drafts, drafts[1:], strict=False):
        a.end_ms = min(a.end_ms, b.start_ms)

    # 4. แบ่งบรรทัด
    return [Cue(d.start_ms, d.end_ms, _lines(d.tokens, opts)) for d in drafts]


# ---------- outputs (CRLF, ไม่มี BOM: ผู้เรียก encode เป็น utf-8 เอง) ----------


def _ts(ms: int) -> str:
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, milli = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"


def to_srt(cues: Sequence[Cue]) -> str:
    blocks = [
        f"{n}{CRLF}{_ts(c.start_ms)} --> {_ts(c.end_ms)}{CRLF}" + CRLF.join(c.lines) + CRLF
        for n, c in enumerate(cues, start=1)
    ]
    return CRLF.join(blocks)


def _paragraphs(tokens: Sequence[Token]) -> list[str]:
    paras: list[list[Token]] = []
    for tok in tokens:
        if paras and tok.s - paras[-1][-1].e < PARAGRAPH_GAP_MS:
            paras[-1].append(tok)
        else:
            paras.append([tok])
    return [cue_text(p) for p in paras]


def to_txt(tokens: Sequence[Token]) -> str:
    if not tokens:
        return ""
    return (CRLF + CRLF).join(_paragraphs(tokens)) + CRLF


def _md_time(ms: int) -> str:
    total = ms // 1000
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if ms >= 3_600_000 else f"{m:02d}:{s:02d}"


def md_time(ms: int) -> str:
    """เวลาในหัวข้อ .md: mm:ss หรือ h:mm:ss (ปัดวินาทีทิ้ง ชั่วโมงไม่เติมศูนย์)"""
    return _md_time(ms)


def md_title(text: str) -> str:
    """ชื่อเรื่อง/ชื่อ chapter ในไฟล์ .md: รวมช่องว่างทุกแบบเป็นช่องเดียว ตัดหัวท้าย (collapse ของ C6)"""
    return _collapse(text)


def to_md(tokens: Sequence[Token], *, title: str, video_id: str, chapters: Sequence[tuple[int, str]]) -> str:
    """หัวเรื่อง + ลิงก์คลิป แล้วแบ่งหัวข้อตาม chapter (หรือทุก 2 นาทีถ้าไม่มี chapter) หัวข้อว่างถูกข้าม"""
    out = ["# " + _collapse(title), "", f"https://www.youtube.com/watch?v={video_id}"]
    out += md_sections(tokens, chapters)
    return CRLF.join(out) + CRLF


def md_sections(tokens: Sequence[Token], chapters: Sequence[tuple[int, str]], level: int = 2) -> list[str]:
    """ส่วนเนื้อหาของ to_md (ไม่มีหัวเรื่องและลิงก์) เป็นรายการบรรทัด แต่ละหัวข้อขึ้นต้นด้วยบรรทัดว่าง

    level = จำนวน # ของหัวข้อเวลา (to_md ใช้ 2, โน้ตใช้ 3 ให้อยู่ใต้ "## ทรานสคริปต์")
    """
    out: list[str] = []
    hashes = "#" * level
    ordered = sorted(chapters, key=lambda ch: ch[0])  # stable: start เท่ากันคงลำดับเดิม

    # section key -> (start ms, heading suffix, tokens)
    sections: dict[int, tuple[int, str, list[Token]]] = {}
    for tok in tokens:
        if ordered:
            key = 0
            for j, (start, _) in enumerate(ordered):
                if start <= tok.s:
                    key = j
            start_ms, suffix = ordered[key][0], " " + _collapse(ordered[key][1])
        else:
            key = tok.s // MD_SECTION_MS
            start_ms, suffix = key * MD_SECTION_MS, ""
        sections.setdefault(key, (start_ms, suffix, []))[2].append(tok)

    for key in sorted(sections):
        start_ms, suffix, toks = sections[key]
        out += ["", f"{hashes} [{_md_time(start_ms)}]{suffix}", ""]
        for n, para in enumerate(_paragraphs(toks)):
            if n:
                out.append("")
            out.append(para)
    return out
