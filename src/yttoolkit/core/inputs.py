"""ตัวแยกลิงก์ยูทูป: ข้อความที่ผู้ใช้วางมา -> รายการคลิป/เพลย์ลิสต์ที่ถูกต้อง

เป็นฟังก์ชันล้วน (pure) ใช้แค่ไลบรารีมาตรฐาน: ไม่เรียกเครือข่าย ไม่รันคำสั่งใด ๆ
(AC-SEC-05) — อะไรที่ไม่ตรงรูปแบบเป๊ะ ๆ จะได้ชนิด "invalid" เท่านั้น
ตัวคั่นที่ถูก URL-encode (เช่น watch%3Fv%3D...) ไม่ถูกถอดรหัส จึงเป็น invalid

ข้อความที่คัดลอกมาจากแชต (LINE) มีคำทักทาย เลขข้อ และหลายลิงก์ในบรรทัดเดียว: scan_text ดึงลิงก์ออกมาจาก
ตรงไหนของบรรทัดก็ได้ แต่ละลิงก์ยังต้องผ่านการตรวจแบบเข้มของ parse_line ทุกข้อ ข้อความธรรมดาถูกข้ามเงียบ ๆ
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qs, urlsplit

Kind = Literal["video", "playlist", "ambiguous", "invalid"]

VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
PLAYLIST_ID = re.compile(r"[A-Za-z0-9_-]{10,64}")
_HAS_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
_MARKDOWN_LINK = re.compile(r"\[[^\[\]]*\]\(([^()]*)\)")
_WRAPPERS = {"<": ">", '"': '"', "'": "'", "(": ")"}
_WHITESPACE = re.compile(r"\s")
# อักขระที่ไม่เคยอยู่ในลิงก์ยูทูปจริง แต่เป็นของเชลล์ (AC-SEC-05) — เจอแล้วปฏิเสธทั้งบรรทัด
# (& ไม่อยู่ในรายการนี้เพราะเป็นตัวคั่นพารามิเตอร์ของ URL; โดเมน/ID ถูกตรวจแบบเข้มอยู่แล้ว)
_SHELL_CHARS = re.compile(r"[;|$()`<>\\\"'{}^]")

_YOUTUBE_HOSTS = frozenset(
    {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
)
_SHORT_HOSTS = frozenset({"youtu.be", "www.youtu.be"})
_NOCOOKIE_HOSTS = frozenset({"youtube-nocookie.com", "www.youtube-nocookie.com"})


@dataclass(frozen=True)
class InputItem:
    input: str
    kind: Kind
    video_id: str | None = None
    playlist_id: str | None = None
    # ลิงก์คลิปที่มาพร้อม "มิกซ์" อัตโนมัติของยูทูป (list=RD...) ใช้กับชนิด ambiguous เท่านั้น
    is_mix: bool = False


def _invalid(text: str) -> InputItem:
    return InputItem(input=text, kind="invalid")


# เพลย์ลิสต์ที่ YouTube Music จัดไว้ (id ขึ้นต้น RDCLAK) เป็นเพลย์ลิสต์ปกติที่มีจำนวนแน่นอน ไม่ใช่มิกซ์
_CURATED_PREFIX = "RDCLAK"


def is_mix_id(list_id: str) -> bool:
    """กฎเดียวของทั้งแอพว่า id ไหนเป็นมิกซ์อัตโนมัติ (radio) ของยูทูป

    มิกซ์ขึ้นต้นด้วย "RD" ตัวพิมพ์ใหญ่เท่านั้น: ID ของยูทูปแยกตัวพิมพ์ใหญ่/เล็ก จึงไม่ปรับเป็นตัวใหญ่ก่อนเทียบ
    ("rd..." เป็นเพลย์ลิสต์ปกติ) · ยกเว้น "RDCLAK..." = เพลย์ลิสต์ของ YouTube Music ใช้ทางเพลย์ลิสต์ปกติ
    """
    return list_id.startswith("RD") and not list_id.startswith(_CURATED_PREFIX)


def _playlist_item(text: str, list_id: str | None) -> InputItem:
    """เพลย์ลิสต์ล้วน — มิกซ์ (RD) ที่ไม่มีคลิปตั้งต้น (v=) ดึงรายการไม่ได้ จึงไม่รับ"""
    if list_id is None or is_mix_id(list_id):
        return _invalid(text)
    return InputItem(input=text, kind="playlist", playlist_id=list_id)


def _video_item(text: str, video_id: str, list_id: str | None) -> InputItem:
    """คลิปเดียว — ถ้ามี list ด้วย (รวมมิกซ์ RD) ต้องให้ผู้ใช้เลือกว่าเอาคลิปนี้หรือทั้งรายการ"""
    if list_id is None:
        return InputItem(input=text, kind="video", video_id=video_id)
    return InputItem(
        input=text,
        kind="ambiguous",
        video_id=video_id,
        playlist_id=list_id,
        is_mix=is_mix_id(list_id),
    )


def _first_param(
    query: dict[str, list[str]], key: str, pattern: re.Pattern[str]
) -> str | None:
    values = query.get(key)
    if not values:
        return None
    return values[0] if pattern.fullmatch(values[0]) else None


def _single_segment(path: str) -> str | None:
    """'/abc' หรือ '/abc/' -> 'abc' ; เส้นทางอื่น -> None"""
    parts = path.split("/")
    if parts and parts[-1] == "":
        parts = parts[:-1]
    if len(parts) == 2 and parts[0] == "" and parts[1]:
        return parts[1]
    return None


def _prefixed_segment(path: str, prefix: str) -> str | None:
    """'/shorts/abc' (มี / ท้ายได้) -> 'abc' เมื่อ prefix = 'shorts'"""
    parts = path.split("/")
    if parts and parts[-1] == "":
        parts = parts[:-1]
    if len(parts) == 3 and parts[0] == "" and parts[1] == prefix and parts[2]:
        return parts[2]
    return None


def _parse_line_body(text: str) -> InputItem:
    if VIDEO_ID.fullmatch(text):
        return InputItem(input=text, kind="video", video_id=text)
    if _WHITESPACE.search(text) or _SHELL_CHARS.search(text):
        return _invalid(text)

    candidate = text if _HAS_SCHEME.match(text) else f"https://{text}"
    try:
        parts = urlsplit(candidate)
        host = parts.hostname
        port = parts.port
    except ValueError:
        return _invalid(text)
    if parts.scheme not in ("http", "https") or not host or port is not None:
        return _invalid(text)
    if parts.username is not None or parts.password is not None:
        return _invalid(text)

    query = parse_qs(parts.query, keep_blank_values=False)
    list_id = _first_param(query, "list", PLAYLIST_ID)
    path = parts.path

    if host in _SHORT_HOSTS:
        video_id = _single_segment(path)
        if video_id and VIDEO_ID.fullmatch(video_id):
            return _video_item(text, video_id, list_id)
        return _invalid(text)

    if host in _NOCOOKIE_HOSTS:
        return _parse_embed(text, path, list_id)

    if host not in _YOUTUBE_HOSTS:
        return _invalid(text)

    if _single_segment(path) == "watch":
        video_id = _first_param(query, "v", VIDEO_ID)
        if video_id:
            return _video_item(text, video_id, list_id)
        return _playlist_item(text, list_id)

    if _single_segment(path) == "playlist":
        return _playlist_item(text, list_id)

    for prefix in ("shorts", "live", "v", "e"):
        video_id = _prefixed_segment(path, prefix)
        if video_id and VIDEO_ID.fullmatch(video_id):
            return _video_item(text, video_id, list_id)

    return _parse_embed(text, path, list_id)


def _parse_embed(text: str, path: str, list_id: str | None) -> InputItem:
    segment = _prefixed_segment(path, "embed")
    if segment == "videoseries":
        return _playlist_item(text, list_id)
    if segment and VIDEO_ID.fullmatch(segment):
        return _video_item(text, segment, list_id)
    return _invalid(text)


def _strip_one_punct(text: str) -> str:
    return text[:-1] if text.endswith((".", ",")) else text


def _unwrap(text: str) -> str:
    """ถอดเครื่องหมายห่อ "ชั้นเดียว": [ข้อความ](url), <..>, "..", '..', (..)"""
    md = _MARKDOWN_LINK.fullmatch(text)
    if md:
        return md.group(1)
    if len(text) >= 2 and _WRAPPERS.get(text[0]) == text[-1]:
        return text[1:-1]
    return text


def _clean(text: str) -> str:
    """ลอกสิ่งที่แอปแชต/ประโยคใส่มารอบลิงก์ (ห่อชั้นเดียว + จุด/จุลภาคท้ายตัวเดียว)"""
    bare = _strip_one_punct(text)
    if bare != text:
        # ห่อแล้วปิดประโยคด้วยจุดข้างนอก เช่น (https://youtu.be/ID).
        unwrapped = _unwrap(bare)
        if unwrapped != bare:
            return unwrapped
    return _strip_one_punct(_unwrap(text))


def parse_line(line: str) -> InputItem:
    """แยกหนึ่งบรรทัดเป็นหนึ่งรายการ — ไม่เคย raise; ไม่รู้จัก = invalid

    item.input คือบรรทัดเดิม (ตัดช่องว่างหัวท้าย) ส่วนเนื้อที่ถูกถอดห่อแล้วต้องผ่านการตรวจเดิมทุกข้อ
    """
    text = line.strip()
    result = _parse_line_body(_clean(text))
    return InputItem(
        input=text,
        kind=result.kind,
        video_id=result.video_id,
        playlist_id=result.playlist_id,
        is_mix=result.is_mix,
    )


def _dedupe_key(item: InputItem) -> tuple[str, str | None, str | None]:
    if item.kind == "invalid":
        return ("invalid", item.input, None)
    return (item.kind, item.video_id, item.playlist_id)


# ---------- ดึงลิงก์ออกจากข้อความปน (แชต LINE) ----------

# อักขระที่อยู่ในลิงก์ได้: ASCII ที่พิมพ์ได้ ยกเว้น " < > (ตัวห่อลิงก์) · ภาษาไทย/ช่องว่าง = ลิงก์จบตรงนั้น
_URL_CHAR = r"[!#-;=?-~]"
# ชิ้นที่หน้าตาเป็นลิงก์: มี scheme (https://...) หรือเป็นชื่อโดเมน (ตามด้วยเส้นทางได้)
# scheme ยาวไม่เกิน 32 ตัว และเริ่มได้เฉพาะต้นคำ ทั้งสองแบบจึงไม่วนหาซ้ำจนช้ากับข้อความยาว 20,000 ตัว
_CANDIDATE = re.compile(
    rf"(?<![A-Za-z0-9])(?P<scheme>[A-Za-z][A-Za-z0-9+.-]{{0,31}}://){_URL_CHAR}*"
    rf"|(?<![A-Za-z0-9._@/:%-])(?P<host>(?:[A-Za-z0-9-]+\.)+[A-Za-z]{{2,}})(?![A-Za-z0-9-]|://)"
    rf"(?P<path>[/?#]{_URL_CHAR}*)?"
)
# เครื่องหมายท้ายประโยค/วงเล็บปิด/เครื่องหมายคำพูดที่ติดท้ายลิงก์มา (ID ของยูทูปไม่มีอักขระพวกนี้)
_TRAILING = ".,;:!?)]}'"
# เลขข้อ "1." "1)" และสัญลักษณ์หัวข้อ "-" "•" หน้าลิงก์ ไม่นับว่าเป็นข้อความที่ถูกข้าม
_LIST_MARK = re.compile(r"(?<!\w)\d{1,3}[.)]|[-•*]")
_WORD = re.compile(r"\w")
_LINK_HOSTS = _YOUTUBE_HOSTS | _SHORT_HOSTS | _NOCOOKIE_HOSTS


@dataclass(frozen=True)
class ScanResult:
    items: list[InputItem]
    # มีข้อความที่ไม่ใช่ลิงก์ถูกข้ามไป (คำทักทาย คำขอบคุณ ฯลฯ) — หน้าเว็บบอกเบา ๆ ไม่ใช่ error
    skipped_text: bool


def _looks_like_link(match: re.Match[str]) -> bool:
    """ชื่อโดเมนล้วน ๆ (เช่น file.txt) ไม่นับเป็นลิงก์ ยกเว้นขึ้นต้น www. หรือเป็นโดเมนของยูทูป"""
    if match.group("scheme") or match.group("path"):
        return True
    host = match.group("host").lower()
    return host.startswith("www.") or host in _LINK_HOSTS


def _scan_line(line: str) -> tuple[list[InputItem], bool]:
    """หนึ่งบรรทัด -> (ลิงก์ที่พบตามลำดับ, มีข้อความอื่นถูกข้ามไหม)

    บรรทัดที่ทั้งบรรทัดเป็นลิงก์/รหัสคลิปอยู่แล้ว ใช้ parse_line ตรง ๆ (รองรับการห่อ [ข้อความ](url) ฯลฯ เหมือนเดิม)
    ไม่งั้นหาชิ้นที่เป็นลิงก์ในบรรทัด: ลิงก์ยูทูปที่ถูกต้อง = รายการ, ลิงก์เว็บอื่น/ลิงก์ยูทูปที่ผิดรูป = แถว invalid
    ส่วนคำธรรมดา (รวมคำ 11 ตัวในประโยค) ไม่ใช่รหัสคลิป ถูกข้าม
    """
    whole = parse_line(line)
    if whole.kind != "invalid":
        return [whole], False
    items: list[InputItem] = []
    rest: list[str] = []
    end = 0
    for match in _CANDIDATE.finditer(line):
        if not _looks_like_link(match):
            continue
        link = match.group(0).rstrip(_TRAILING)
        rest.append(line[end : match.start()])
        rest.append(match.group(0)[len(link) :])
        end = match.end()
        items.append(parse_line(link))
    rest.append(line[end:])
    leftover = _LIST_MARK.sub(" ", " ".join(rest))
    return items, _WORD.search(leftover) is not None


def scan_text(text: str) -> ScanResult:
    """แยกข้อความหลายบรรทัด: ดึงลิงก์จากทุกบรรทัด ตัดรายการซ้ำ (ตัวแรกชนะ คงลำดับ)

    บรรทัด invalid เทียบซ้ำด้วยข้อความเดิม เพื่อให้แต่ละลิงก์ผิดยังแจ้งเตือนแยกกันได้
    """
    seen: set[tuple[str, str | None, str | None]] = set()
    items: list[InputItem] = []
    skipped = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        found, line_skipped = _scan_line(line)
        skipped = skipped or line_skipped
        for item in found:
            key = _dedupe_key(item)
            if key in seen:
                continue
            seen.add(key)
            items.append(item)
    return ScanResult(items=items, skipped_text=skipped)


def parse_text(text: str) -> list[InputItem]:
    """รายการลิงก์จากข้อความหลายบรรทัด (ดู scan_text)"""
    return scan_text(text).items
