"""ตัวซ่อนข้อมูลส่วนตัวในข้อความ log / error (stdlib ล้วน: probe ใช้ได้ก่อนโหลดเว็บ)

- redact_home: แทนโฟลเดอร์ผู้ใช้ด้วย ~ (ชื่อผู้ใช้ Windows ห้ามหลุดไปกับ log หรือภาพหน้าจอ)
- redact_secrets (M5 รอบ C): ปิดค่าของ header Cookie / Set-Cookie และค่าของคุกกี้เข้าสู่ระบบของยูทูป
  เป็นตาข่ายกันพลาดชั้นสุดท้าย โค้ดของแอพไม่ log ค่าพวกนี้อยู่แล้ว
- HomePathFilter / SecretFilter: ตัวกรองของ logging.Handler ที่ใช้สองตัวข้างบน (ข้อความ + traceback)
  probe.setup_file_log ใส่ให้ app.log ตั้งแต่สร้าง handler (ก่อนโหลด lifecycle) จึงครอบความล้มเหลวตอนเปิดโปรแกรมด้วย
- (M6 รอบ B) mask_user_paths / mask_media_urls / scrub_titles: ปิด path นอกโฟลเดอร์ผู้ใช้ ลิงก์ไฟล์ของยูทูป และชื่อคลิป
  redact_log_detail = ชุดของบรรทัด job_failed ใน app.log · redact_report = ชุดของรายงานแจ้งปัญหา (เพิ่ม token และชื่อคุกกี้)
"""

from __future__ import annotations

import functools
import logging
import re
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import quote

MASK = "<hidden>"
# คุกกี้เข้าสู่ระบบของ Google/ยูทูปที่รู้จัก (เก็บแค่ชื่อ ค่าถูกแทนด้วย MASK)
SIGN_IN_COOKIE_NAMES = (
    "SAPISID",
    "APISID",
    "HSID",
    "SID",
    "SSID",
    "SIDCC",
    "LOGIN_INFO",
    "__Secure-1PSID",
    "__Secure-3PSID",
    "__Secure-1PAPISID",
    "__Secure-3PAPISID",
    "__Secure-1PSIDTS",
    "__Secure-3PSIDTS",
    "__Secure-1PSIDCC",
    "__Secure-3PSIDCC",
)
# Cookie: a=b · Set-Cookie: a=b · 'Cookie': 'a=b' (repr ของ dict header) · Cookie: SID="v" (ค่ามีอัญประกาศ)
# ถ้าค่าเปิดด้วยอัญประกาศ ปิดถึงอัญประกาศปิดตัวเดียวกัน ถ้าไม่ใช่ ปิดถึงท้ายบรรทัด (ข้ามส่วนที่อยู่ในอัญประกาศคู่)
_HEADER = re.compile(
    r"(?i)(\b(?:set-)?cookie['\"]?\s*:\s*)(?:(['\"])[^\r\n]*?(?=\2|[\r\n]|\Z)|(?:[^\r\n'\"]|\"[^\"\r\n]*\")*)"
)
# Authorization: SAPISIDHASH <ts>_<hash> SAPISID1PHASH <ts>_<hash> (โทเคนเข้าสู่ระบบที่คำนวณจาก SAPISID)
_AUTH = re.compile(r"\b(SAPISID(?:1P|3P)?HASH\s+)[^\s'\",;]+")
# SAPISID=abc · SAPISID<TAB>abc (บรรทัดของ cookies.txt) · SAPISID\tabc (repr ของบรรทัดนั้น: tab กลายเป็น \ กับ t สองตัวอักษร)
# · "SAPISID": "abc" · ไม่จับชื่อที่เป็นส่วนของชื่ออื่น
_NAMES = "|".join(re.escape(n) for n in sorted(SIGN_IN_COOKIE_NAMES, key=len, reverse=True))
_NAMED = re.compile(
    rf"(?:(?<![A-Za-z0-9_-])|(?<=\\t))({_NAMES})(['\"]?(?:\s*[=:]\s*|(?:\t|\\t)+)['\"]?)([^\s;,'\"]+)"
)
# name='SAPISID', value='abc' (repr ของ http.cookiejar.Cookie) · {"name": "SAPISID", ..., "value": "abc"} (JSON ของส่วนเสริมส่งออกคุกกี้)
# ชื่อมาก่อนค่าในวัตถุเดียวกัน (ระหว่างกลางมีคีย์อื่นได้ แต่ห้ามข้ามปีกกาหรือวงเล็บ)
_PAIR = re.compile(
    rf"(\bname['\"]?\s*[=:]\s*['\"]?(?:{_NAMES})(?![A-Za-z0-9_-])['\"]?[^{{}}()]{{0,500}}?"
    r"\bvalue['\"]?\s*[=:]\s*['\"]?)([^'\"\s,;}]+)"
)


def redact_secrets(text: str) -> str:
    """ปิดค่าคุกกี้ใน text: header Cookie / Set-Cookie ทั้งค่า, Authorization: SAPISIDHASH และค่าของคุกกี้เข้าสู่ระบบที่รู้จักชื่อ"""
    text = _HEADER.sub(lambda m: f"{m.group(1)}{m.group(2) or ''}{MASK}", text)
    text = _AUTH.sub(lambda m: f"{m.group(1)}{MASK}", text)
    text = _PAIR.sub(lambda m: f"{m.group(1)}{MASK}", text)
    return _NAMED.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK}", text)


@functools.cache
def _home_aliases(home: str) -> tuple[str, ...]:
    """ชื่ออื่นของโฟลเดอร์ผู้ใช้ (Windows: ชื่อสั้นแบบ 8.3 เช่น SOMCHA~1) หาครั้งเดียวแล้วจำไว้"""
    from .platform import current

    try:
        return tuple(current().path_aliases(Path(home)))
    except (OSError, RuntimeError):
        return ()


def redact_home(text: str) -> str:
    """แทนโฟลเดอร์ผู้ใช้ด้วย ~ เพื่อไม่ให้ชื่อผู้ใช้หลุดไปกับภาพหน้าจอที่ส่งต่อ"""
    home = str(Path.home())
    if not home.strip("/\\"):
        return text
    # แบบปกติ, แบบ / และแบบ backslash สองตัว (มาจาก repr เช่น str(OSError) บน Windows) ทั้งชื่อเต็มและชื่อสั้น
    forms = {
        form
        for name in (home, *_home_aliases(home))
        for form in (name, name.replace("\\", "/"), name.replace("\\", "\\\\"))
    }
    # M6 รอบ B: แบบ percent-encoded ด้วย (file:///C:/Users/... และ path ใน URL ที่ yt-dlp ยกมา) ตัวพิมพ์ของ %xx ไม่สำคัญ
    variants = forms | {quote(f, safe="") for f in forms} | {quote(f.replace("\\", "/"), safe="/") for f in forms}
    variants |= {quote(f.replace("\\", "/"), safe="/:") for f in forms}  # Path.as_uri(): file:///C:/Users/Som%20Chai
    # รวมเป็น regex เดียว เรียงยาวก่อน จึงไม่มีแบบไหนไปจับแค่บางส่วนของอีกแบบ
    alternatives = "|".join(re.escape(v) for v in sorted(variants, key=len, reverse=True))
    # ไม่แตะโฟลเดอร์ข้างเคียงที่ชื่อขึ้นต้นเหมือนกัน เช่น C:\Users\Som กับ C:\Users\Somchai
    # ผลข้างเคียงที่ตั้งใจ: home ที่ตามด้วยจุดทันที (เช่นท้ายประโยค) จะไม่ถูกแทน เพราะจุดเป็นส่วนของชื่อโฟลเดอร์ได้
    return re.sub(f"(?:{alternatives})" + r"(?![\w.\-])", "~", text, flags=re.IGNORECASE)


class _RewriteFilter(logging.Filter):
    """แก้ข้อความ log (รวม args) traceback และ stack ด้วย rewrite ก่อนเขียน"""

    _formatter = logging.Formatter()

    def rewrite(self, text: str) -> str:
        raise NotImplementedError

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = self.rewrite(record.getMessage())
        except Exception as error:
            # จัดรูปข้อความไม่ได้: ไม่ปล่อย args ดิบให้ handleError พิมพ์ออก stderr ใส่ข้อความคงที่ (ชื่อชนิดของ error เท่านั้น)
            message = f"(จัดรูปข้อความ log ไม่ได้: {type(error).__name__})"
        record.msg = message
        record.args = ()
        if record.exc_info and not record.exc_text:
            record.exc_text = self._formatter.formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = self.rewrite(record.exc_text)
        if record.stack_info:
            record.stack_info = self.rewrite(record.stack_info)
        return True


class HomePathFilter(_RewriteFilter):
    """แทนโฟลเดอร์ผู้ใช้ด้วย ~ ในข้อความ log และ traceback ก่อนเขียนลงไฟล์

    log.exception ของคิวงานและ lifecycle อาจมี path เต็ม ซึ่งมีชื่อผู้ใช้ Windows ติดไปกับไฟล์ log ที่ส่งต่อ
    """

    def rewrite(self, text: str) -> str:
        return redact_home(text)


class SecretFilter(_RewriteFilter):
    """ปิดค่าคุกกี้ (header Cookie / Set-Cookie และคุกกี้เข้าสู่ระบบของยูทูป) ในข้อความ log และ traceback"""

    def rewrite(self, text: str) -> str:
        return redact_secrets(text)


def add_redaction(handler: logging.Handler) -> None:
    """ใส่ HomePathFilter และ SecretFilter ให้ handler (เรียกซ้ำได้ ไม่ใส่ซ้ำ)"""
    for kind in (HomePathFilter, SecretFilter):
        if not any(isinstance(f, kind) for f in handler.filters):
            handler.addFilter(kind())


# ---------- M6 รอบ B: บรรทัด job_failed ใน app.log และรายงานแจ้งปัญหา ----------

PATH_MASK = "<path>"
TITLE_MASK = "<title>"
URL_MASK = "<url>"
TITLE_MIN = 4  # ชื่อคลิปที่สั้นกว่านี้ไม่ปิด (จะไปโดนคำธรรมดา)
TITLE_PREFIX = 16  # ชื่อไฟล์ที่ถูกตัดสั้น: ขึ้นต้นด้วย 16 ตัวแรกของชื่อไฟล์ของคลิป = ถือว่าเป็นชื่อคลิป
# ไดรฟ์ (C:\ หรือ C:/) หรือ UNC (\\server\share\) · ตัวอักษรที่ติดคำก่อนหน้าไม่ใช่ไดรฟ์ (https:// ไม่ใช่ไดรฟ์ s:)
# UNC เริ่มได้แค่ต้นข้อความหรือหลังช่องว่าง/อัญประกาศ/วงเล็บ/=,;: ไม่งั้น ~\\Downloads\\ (repr ที่ backslash สองตัว) จะถูกมองเป็น UNC
_ROOT = r"""(?:(?<![A-Za-z0-9])[A-Za-z]:[\\/]|(?<![^\s'"(=,;:\[<{|])\\\\[^\\/\s'"<>|]+[\\/])"""
_QUOTED_PATH = re.compile(r"""(['"])(""" + _ROOT + r""")[^\r\n]*?\1""")
_PATH_TOKEN = r"""[^\s'"<>|,;)]"""
_BARE_PATH = re.compile(_ROOT + _PATH_TOKEN + "*")
# ส่วนต่อของ path ที่มีช่องว่าง: หยุดที่ key=value, ://, ราก path ใหม่ (ไดรฟ์ \\ ~) และวงเล็บ/อัญประกาศ
_PATH_TAIL = re.compile(
    r"""(?! *[A-Za-z_][\w.-]*=)(?! *\S*://)(?! *[A-Za-z]:[\\/])(?! *(?:\\\\|~))(?! *\S*[\[\]{}(])"""
    + " "
    + _PATH_TOKEN
    + "+"
)
_FRAME_LINE = re.compile(r'^\s*File ".*", line \d+')
# รวมแบบ JSON-escaped (https:\/\/host\/path) · ")" ท้ายลิงก์ไม่ถูกกิน
_MEDIA_URL = re.compile(
    r"""(?i)https?:(?:\\?/){2}(?:[a-z0-9-]+\.)*googlevideo\.com(?::\d+)?(?:(?:[/?#]|\\/)[^\s'"<>)]*)?"""
)
_MASKS = re.compile("(" + "|".join(re.escape(m) for m in (PATH_MASK, TITLE_MASK, URL_MASK, MASK)) + ")")
_COOKIE_NAME = re.compile(rf"(?<![A-Za-z0-9_-])(?:{_NAMES})(?![A-Za-z0-9_-])")


def _mask_paths_in_line(line: str) -> str:
    if _FRAME_LINE.match(line):
        return line  # บรรทัด File "...", line N ของ traceback ชี้โค้ดของแอพ (C4): คง path ไว้ (โฟลเดอร์ผู้ใช้เป็น ~ แล้ว)
    line = _QUOTED_PATH.sub(lambda m: f"{m.group(1)}{PATH_MASK}{m.group(1)}", line)
    out: list[str] = []
    pos = 0
    while m := _BARE_PATH.search(line, pos):
        end = m.end()
        # ชื่อโฟลเดอร์ที่มีช่องว่าง: ต่อข้ามช่องว่างเดี่ยวตราบที่ยังมีตัวคั่น path ตามมาในบรรทัด (คำธรรมดาท้าย path ไม่ถูกกิน)
        scan = end
        while t := _PATH_TAIL.match(line, scan):
            scan = t.end()
            if "\\" in t.group() or "/" in t.group():
                end = scan  # ตัดท้ายที่คำสุดท้ายที่มีตัวคั่น คำธรรมดาหลังจากนั้นไม่ถูกกิน
        out += [line[pos : m.start()], PATH_MASK]
        pos = end
    return "".join(out) + line[pos:]


def mask_user_paths(text: str) -> str:
    """แทน path เต็มที่ไม่อยู่ใต้โฟลเดอร์ผู้ใช้ (ไดรฟ์อื่น โฟลเดอร์แชร์) ด้วย <path> · path ที่เป็น ~ แล้วคงไว้

    path ที่ขึ้นต้นหลังอัญประกาศยาวถึงอัญประกาศปิดตัวเดียวกัน (repr ของ OSError ที่ชื่อมีช่องว่าง)
    ไม่อย่างนั้นยาวถึงช่องว่าง หรือ ' " < > | , ; ) ตัวแรก
    """
    return "".join(_mask_paths_in_line(line) for line in text.splitlines(keepends=True))


def mask_media_urls(text: str) -> str:
    """ลิงก์ไฟล์สื่อของยูทูป (*.googlevideo.com) มีเลข IP ของผู้ใช้และลายเซ็น: แทนด้วย <url>"""
    return _MEDIA_URL.sub(URL_MASK, text)


def scrub_titles(text: str, titles: Iterable[str]) -> str:
    """แทนชื่อคลิปด้วย <title>: ชื่อตรงตัว ชื่อแบบที่ใช้เป็นชื่อไฟล์ (safe_component) และชื่อไฟล์ที่ถูกตัดสั้น"""
    from .core.files import safe_component  # stdlib ล้วน import ตอนใช้ probe จะได้ไม่โหลด core

    titles = tuple(titles)

    def scrub(chunk: str) -> str:
        for title in titles:
            if len(title) < TITLE_MIN:
                continue
            chunk = chunk.replace(title, TITLE_MASK)
            safe = safe_component(title, "")
            if len(safe) >= TITLE_MIN and safe != title:
                chunk = chunk.replace(safe, TITLE_MASK)
            if len(safe) >= TITLE_PREFIX:
                # หางชื่อไฟล์ที่ถูกตัด: หยุดก่อนช่อง key=value ถัดไป (code= job=) จะได้ไม่กินข้อมูลวินิจฉัย
                tail = r"""(?:(?![ \t]+[A-Za-z_]+=)[^\\/'"\r\n])*"""
                chunk = re.sub(re.escape(safe[:TITLE_PREFIX]) + tail, TITLE_MASK, chunk)
        return chunk

    # ไม่แตะตัวปิดข้อมูลที่ใส่ไว้แล้ว (ชื่อคลิป "path" ต้องไม่ทำให้ <path> เป็น <<title>>)
    return "".join(part if i % 2 else scrub(part) for i, part in enumerate(_MASKS.split(text)))


def redact_log_detail(text: str, titles: Iterable[str] = ()) -> str:
    """ชุดซ่อนข้อมูลของบรรทัด job_failed ใน app.log (เรียกที่เดียว: core/queue.py)

    โฟลเดอร์ผู้ใช้ → ค่าคุกกี้ → ชื่อคลิป → path อื่น → ลิงก์ไฟล์ของยูทูป
    """
    # ชื่อคลิปก่อน path: ชื่อไฟล์ที่มีช่องว่าง (Destination: D:\out\ชื่อ คลิป.mp4) จะถูกปิดครบก่อน path จะตัดที่ช่องว่าง
    text = scrub_titles(redact_secrets(redact_home(text)), tuple(titles))
    return mask_media_urls(mask_user_paths(text))


def redact_report(text: str, *, token: str, titles: Iterable[str] = ()) -> str:
    """ชุดซ่อนข้อมูลของรายงานแจ้งปัญหา (เรียกที่เดียว: core/diagnostics.build_report)

    = redact_log_detail + token ของแอพเป็น <hidden> + ชื่อคุกกี้เข้าสู่ระบบทั้งคำเป็น <hidden> (รายงานไม่มีชื่อคุกกี้เลย FR-CK-5)
    """
    text = redact_log_detail(text, titles)
    if token:
        text = text.replace(token, MASK)
    return _COOKIE_NAME.sub(MASK, text)
