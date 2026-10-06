"""ตัวซ่อนข้อมูลส่วนตัวในข้อความ log / error (stdlib ล้วน: probe ใช้ได้ก่อนโหลดเว็บ)

- redact_home: แทนโฟลเดอร์ผู้ใช้ด้วย ~ (ชื่อผู้ใช้ Windows ห้ามหลุดไปกับ log หรือภาพหน้าจอ)
- redact_secrets (M5 รอบ C): ปิดค่าของ header Cookie / Set-Cookie และค่าของคุกกี้เข้าสู่ระบบของยูทูป
  เป็นตาข่ายกันพลาดชั้นสุดท้าย โค้ดของแอพไม่ log ค่าพวกนี้อยู่แล้ว
- HomePathFilter / SecretFilter: ตัวกรองของ logging.Handler ที่ใช้สองตัวข้างบน (ข้อความ + traceback)
  probe.setup_file_log ใส่ให้ app.log ตั้งแต่สร้าง handler (ก่อนโหลด lifecycle) จึงครอบความล้มเหลวตอนเปิดโปรแกรมด้วย
"""

from __future__ import annotations

import functools
import logging
import re
from pathlib import Path

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
    variants = {
        form
        for name in (home, *_home_aliases(home))
        for form in (name, name.replace("\\", "/"), name.replace("\\", "\\\\"))
    }
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
