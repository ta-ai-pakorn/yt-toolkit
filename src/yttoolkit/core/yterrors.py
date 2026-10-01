"""แปลงข้อความ error ดิบของ yt-dlp เป็นรหัส error ของแอพ (PRD ข้อ 7)

เป็นฟังก์ชันล้วน ไม่ import yt_dlp: ใช้แค่ข้อความ จึงเทสได้ด้วยข้อความจริงที่เก็บไว้ใน
tests/fixtures/errors/ (แต่ละไฟล์ชื่อ <รหัส>-<n>.txt)
"""

from __future__ import annotations

# ข้อความถึงผู้ใช้ คัดลอกตรงตัวจาก PRD ข้อ 7 (เฉพาะรหัสที่ core ใช้)
# E_NETWORK ใช้รุ่นไม่มีตัวนับครั้ง เพราะการนับรอบลองใหม่เป็นหน้าที่ของคิวงานใน M4
MESSAGES: dict[str, str] = {
    "E_INVALID_INPUT": "ลิงก์นี้ไม่ใช่ลิงก์ยูทูป ลองคัดลอกจากแถบที่อยู่ของเบราว์เซอร์อีกครั้ง",
    "E_BOT_CHECK": "ยูทูปขอให้ยืนยันว่าไม่ใช่บอท รอสัก 10 นาทีแล้วค่อยลองใหม่",
    "E_VIDEO_PRIVATE": "คลิปนี้เป็นส่วนตัว เจ้าของต้องเปิดเป็นสาธารณะก่อน",
    "E_VIDEO_UNAVAILABLE": "คลิปนี้ถูกลบหรือไม่มีแล้ว",
    "E_GEO_BLOCKED": "คลิปนี้ดูในประเทศไทยไม่ได้",
    "E_AGE_RESTRICTED": "คลิปนี้จำกัดอายุ ต้องล็อกอินถึงจะโหลดได้ ซึ่งเวอร์ชันนี้ยังไม่รองรับ",
    "E_LIVE_NOT_READY": "คลิปนี้ยังถ่ายทอดสดอยู่หรือยังไม่เผยแพร่ ลองใหม่หลังจบไลฟ์",
    "E_NO_STORYBOARD": "คลิปนี้ไม่มีภาพตัวอย่างแบบเร็ว ภาพคมจะใช้ได้ในเวอร์ชันถัดไป",
    "E_NO_SUBTITLES": "คลิปนี้ไม่มีซับ",
    # ยูทูปตอบ 429 เฉพาะคำขอซับแปล (tlang) ไม่ใช่การขอยืนยันว่าไม่ใช่บอท จึงไม่พักคิว (M4)
    "E_TRANSLATION_BLOCKED": "ยูทูปยังไม่ให้โหลดซับแปลอัตโนมัติในตอนนี้ เลือกซับภาษาต้นฉบับแทน",
    "E_NETWORK": "เน็ตหลุด ลองใหม่อีกครั้ง",
    "E_UNKNOWN": "มีบางอย่างผิดพลาด ถ่ายภาพหน้าจอนี้ส่งให้ผู้ดูแล",
}

# ตรวจตามลำดับนี้ รหัสที่เจาะจงมาก่อนคำกว้าง ๆ เพราะข้อความจริงมักมีหลายวลีปนกัน เช่น
# "Video unavailable. ... blocked it in your country" = ติดประเทศ ไม่ใช่คลิปหาย
# และ "Unable to download API page: HTTP Error 429" = โดนจำกัดความถี่ ไม่ใช่เน็ตหลุด
# วลีทั้งหมดเป็นตัวพิมพ์เล็ก และใช้ ' แทน ’ (ยูทูปส่ง "you’re" มาแบบอัญประกาศโค้ง)
_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
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
        if any(phrase in text for phrase in phrases):
            return code
    return "E_UNKNOWN"


class YtError(Exception):
    """error ที่มาจากการดึงข้อมูลยูทูป: code = รหัสใน PRD ข้อ 7, detail = ข้อความเทคนิคดิบ"""

    code: str
    detail: str

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail or self.message}")

    @property
    def message(self) -> str:
        """ข้อความภาษาไทยถึงผู้ใช้ รหัสที่ไม่รู้จักใช้ข้อความของ E_UNKNOWN"""
        return MESSAGES.get(self.code, MESSAGES["E_UNKNOWN"])
