"""แปลงข้อความ error ดิบของ yt-dlp เป็นรหัส error ของแอพ (PRD ข้อ 7)

เป็นฟังก์ชันล้วน ไม่ import yt_dlp: ใช้แค่ข้อความ จึงเทสได้ด้วยข้อความจริงที่เก็บไว้ใน
tests/fixtures/errors/ (แต่ละไฟล์ชื่อ <รหัส>-<n>.txt)
"""

from __future__ import annotations

import re
from collections.abc import Mapping

# ข้อความถึงผู้ใช้ คัดลอกตรงตัวจาก PRD ข้อ 7 (เฉพาะรหัสที่ core ใช้)
# E_NETWORK ใช้รุ่นไม่มีตัวนับครั้ง ตัวนับ "ครั้งที่ n/3" หน้าเว็บสร้างเองจาก Job.attempt (M4)
# ข้อความที่มี {ชื่อ} เติมค่าจาก YtError(params=...) เช่น E_DISK_FULL ใช้ {"size": "3.2 GB"}
MESSAGES: dict[str, str] = {
    "E_INVALID_INPUT": "ลิงก์นี้ไม่ใช่ลิงก์ยูทูป ลองคัดลอกจากแถบที่อยู่ของเบราว์เซอร์อีกครั้ง",
    # PRD ข้อ 7 "ตั้งแต่ M4" (มีคิวแล้ว): คิวพักเองแบบเบรกฉุกเฉิน
    "E_BOT_CHECK": "ยูทูปขอให้ยืนยันว่าไม่ใช่บอท พักคิวไว้ 10 นาทีก่อนนะ",
    "E_VIDEO_PRIVATE": "คลิปนี้เป็นส่วนตัว เจ้าของต้องเปิดเป็นสาธารณะก่อน",
    "E_VIDEO_UNAVAILABLE": "คลิปนี้ถูกลบหรือไม่มีแล้ว",
    "E_GEO_BLOCKED": "คลิปนี้ดูในประเทศไทยไม่ได้",
    "E_AGE_RESTRICTED": "คลิปนี้จำกัดอายุ ต้องล็อกอินถึงจะโหลดได้ ซึ่งเวอร์ชันนี้ยังไม่รองรับ",
    "E_LIVE_NOT_READY": "คลิปนี้ยังถ่ายทอดสดอยู่หรือยังไม่เผยแพร่ ลองใหม่หลังจบไลฟ์",
    # M5 รอบ B มีโหมดคมแล้ว (BRD #33): ข้อความชวนไปกด "ขอภาพคม"
    "E_NO_STORYBOARD": 'คลิปนี้ไม่มีภาพตัวอย่างแบบเร็ว กด "ขอภาพคม" แทนได้',
    "E_NO_SUBTITLES": "คลิปนี้ไม่มีซับ",
    # ชุดภาพคมใน cache หายไป (ล้าง cache) ก่อนงาน contact sheet / zip แบบภาพคมได้เริ่ม
    "E_NO_SHARP_FRAMES": 'ภาพคมของคลิปนี้ถูกล้างไปแล้ว กด "ขอภาพคม" ใหม่ได้',
    # ยูทูปตอบ 429 เฉพาะคำขอซับแปล (tlang) ไม่ใช่การขอยืนยันว่าไม่ใช่บอท จึงไม่พักคิว (M4)
    "E_TRANSLATION_BLOCKED": "ยูทูปยังไม่ให้โหลดซับแปลอัตโนมัติในตอนนี้ เลือกซับภาษาต้นฉบับแทน",
    # เซสชันผู้ชมยังอายุไม่ถึง 75 วินาที (owner round 3) หน้าเว็บนับถอยหลังจาก retryAfterSeconds แล้วโหลดให้เอง
    "E_SESSION_WARMING": "กำลังเตรียมซับแปลจากยูทูป รอสักครู่แล้วโหลดใหม่",
    "E_NETWORK": "เน็ตหลุด ลองใหม่อีกครั้ง",
    # M4 งานโหลด (C11)
    "E_FFMPEG_MISSING": 'ยังไม่มีโปรแกรมแปลงไฟล์ (ffmpeg) กด "โหลด ffmpeg ใหม่" ในหน้าตรวจสุขภาพ',
    "E_DISK_FULL": "พื้นที่ไม่พอ ต้องมีว่างอย่างน้อย {size}",
    "E_OUTPUT_NOT_WRITABLE": "บันทึกลงโฟลเดอร์นี้ไม่ได้ ลองเปลี่ยนโฟลเดอร์ในหน้าตั้งค่า",
    "E_INTERRUPTED": "งานหยุดกลางคันเพราะปิดโปรแกรม",
    "E_JOB_STATE": "งานนี้เปลี่ยนสถานะไปแล้ว ลองรีเฟรชหน้าเว็บ",
    # ยูทูปตอบ 4xx อื่นที่ไม่ใช่ 429 (เช่น 403 ตอนโหลดไฟล์) ไม่ใช่เน็ตหลุด จึงไม่ลองใหม่อัตโนมัติและไม่พักคิว (Q2)
    "E_YT_REFUSED": "ยูทูปไม่ยอมส่งไฟล์ของคลิปนี้ตอนนี้ ลองใหม่ภายหลัง",
    "E_UNKNOWN": "มีบางอย่างผิดพลาด ถ่ายภาพหน้าจอนี้ส่งให้ผู้ดูแล",
}

# ข้อความสำรองของข้อความที่มี {ชื่อ} เมื่อไม่มีค่าให้เติม (ผู้ใช้ต้องไม่เห็น "{size}")
# เช่น files.py / media.py โยน E_DISK_FULL ตอนเขียนไฟล์ไม่ลงโดยไม่รู้ว่าต้องใช้พื้นที่เท่าไร
MESSAGES_NO_PARAMS: dict[str, str] = {
    "E_DISK_FULL": "พื้นที่ไม่พอ ลบไฟล์หรือเลือกโฟลเดอร์อื่นในหน้าตั้งค่า",
}

# ตรวจตามลำดับนี้ รหัสที่เจาะจงมาก่อนคำกว้าง ๆ เพราะข้อความจริงมักมีหลายวลีปนกัน เช่น
# "Video unavailable. ... blocked it in your country" = ติดประเทศ ไม่ใช่คลิปหาย
# และ "Unable to download API page: HTTP Error 429" = โดนจำกัดความถี่ ไม่ใช่เน็ตหลุด
# วลีทั้งหมดเป็นตัวพิมพ์เล็ก และใช้ ' แทน ’ (ยูทูปส่ง "you’re" มาแบบอัญประกาศโค้ง)
# กฎหนึ่งข้อเป็นวลี (หาแบบ substring) หรือ regex ที่คอมไพล์แล้ว (หาด้วย search)
_RULES: tuple[tuple[str, tuple[str | re.Pattern[str], ...]], ...] = (
    (
        "E_BOT_CHECK",
        (
            "confirm you're not a bot",
            # ยูทูปจำกัดความถี่ (rate limit) ต้องพักคิวแบบเดียวกับโดนถามว่าเป็นบอท
            "rate-limited by youtube",
            "http error 429",
            "captcha",
        ),
    ),
    (
        "E_VIDEO_PRIVATE",
        ("private video", "this video is private", "this playlist is private"),
    ),
    (
        "E_GEO_BLOCKED",
        (
            "not made this video available in your country",
            "blocked it in your country",
            "not available from your location",
        ),
    ),
    (
        "E_AGE_RESTRICTED",
        (
            "sign in to confirm your age",
            "age-restricted",
            "inappropriate for some users",
        ),
    ),
    ("E_LIVE_NOT_READY", ("this live event will begin", "premieres in", "is_upcoming")),
    (
        "E_VIDEO_UNAVAILABLE",
        (
            "video unavailable",
            "this video is unavailable",
            "this video has been removed",
            "this video is no longer available",
            "is not a valid url",
            "incomplete youtube id",
            "playlist does not exist",
        ),
    ),
    # HTTP 4xx ที่ไม่ใช่ 429 (429 = E_BOT_CHECK ข้างบนแล้ว) ต้องมาก่อน E_NETWORK เพราะข้อความมักมี
    # "unable to download" ปนมาด้วย (M2 follow-up: 4xx ห้ามลองใหม่อัตโนมัติ)
    ("E_YT_REFUSED", (re.compile(r"http error 4(?!29)\d\d"),)),
    (
        "E_NETWORK",
        (
            "unable to download",
            "timed out",
            "getaddrinfo failed",
            "connection reset",
            "http error 5",
            "a network error has occurred",
        ),
    ),
)


def classify(message: str) -> str:
    """ข้อความ error ของ yt-dlp -> รหัส error ใน PRD ข้อ 7 (ไม่สนตัวพิมพ์เล็ก/ใหญ่)"""
    text = message.lower().replace("’", "'")
    for code, phrases in _RULES:
        if any(
            phrase.search(text) if isinstance(phrase, re.Pattern) else phrase in text
            for phrase in phrases
        ):
            return code
    return "E_UNKNOWN"


class YtError(Exception):
    """error ที่มาจากการดึงข้อมูลยูทูป: code = รหัสใน PRD ข้อ 7, detail = ข้อความเทคนิคดิบ

    retry_after = อีกกี่วินาทีลองใหม่ได้ (มีเฉพาะ E_SESSION_WARMING) API ส่งเป็น retryAfterSeconds และ Retry-After
    params = ค่าที่เติมลงข้อความ (เช่น E_DISK_FULL ใช้ {"size": "3.2 GB"}) ไม่มี = ข้อความตามตาราง
    """

    code: str
    detail: str
    retry_after: int | None
    params: Mapping[str, str] | None

    def __init__(
        self,
        code: str,
        detail: str = "",
        *,
        retry_after: int | None = None,
        params: Mapping[str, str] | None = None,
    ) -> None:
        self.code = code
        self.detail = detail
        self.retry_after = retry_after
        self.params = params
        super().__init__(f"{code}: {detail or self.message}")

    @property
    def message(self) -> str:
        """ข้อความภาษาไทยถึงผู้ใช้ รหัสที่ไม่รู้จักใช้ข้อความของ E_UNKNOWN

        ข้อความที่มี {ชื่อ} เติมค่าจาก params ไม่มี params หรือค่าไม่ครบ = ข้อความสำรองใน MESSAGES_NO_PARAMS
        (error ห้ามพังซ้อน และห้ามโชว์ {ชื่อ} ดิบ) ข้อความธรรมดาไม่สน params
        """
        template = MESSAGES.get(self.code, MESSAGES["E_UNKNOWN"])
        fallback = MESSAGES_NO_PARAMS.get(self.code)
        if fallback is None:
            return template
        try:
            return template.format_map(self.params or {})
        except (KeyError, ValueError, IndexError):
            return fallback
