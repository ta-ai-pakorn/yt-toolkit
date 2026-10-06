"""ขอบเขตของงานที่ใช้บัญชียูทูปชั่วคราว (M5 รอบ C spec 2.3-2.4)

signed_in(jar) ครอบงานหนึ่งชิ้น (probe ของหน้า W2 / งานในคิวทั้งงาน / ถ่ายภาพคมหนึ่งครั้ง) ทุกคำขอ yt-dlp ใน
ขอบเขตนี้ใช้บัญชีนั้น (core/extractor อ่าน current_jar() แล้วส่งให้ _ydl(with_account=...)) และ VideoService
ไม่เขียนข้อมูลคลิปลงดิสก์ ค่าเก็บใน contextvars จึงแยกตามเธรด/งาน ไม่รั่วไปงานอื่นที่รันพร้อมกัน
ใช้แค่ stdlib กับ core/yterrors (ไม่ import yt_dlp)
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_JAR: ContextVar[Any | None] = ContextVar("yttoolkit_account_jar", default=None)


def current_jar() -> Any | None:
    """jar ของบัญชีที่งานนี้ใช้อยู่ None = ไม่ได้ใช้บัญชี (คำขอแบบไม่ระบุตัวตนตามปกติ)"""
    return _JAR.get()


@contextmanager
def signed_in(jar: Any) -> Iterator[None]:
    """ให้ทุกคำขอยูทูปในบล็อกนี้ใช้ jar ของบัญชีชั่วคราว (ออกจากบล็อก = กลับเป็นค่าเดิม)"""
    if jar is None:
        raise ValueError("signed_in ต้องมี jar")
    token = _JAR.set(jar)
    try:
        yield
    finally:
        _JAR.reset(token)
