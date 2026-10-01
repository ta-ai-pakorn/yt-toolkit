"""เซสชันผู้ชมแบบไม่ระบุตัวตนของยูทูป (owner round 3, 2026-10-01): ไฟล์คุกกี้ 1 ไฟล์ที่ probe และการโหลดซับใช้ร่วมกัน

ทำไมต้องมี: ยูทูปให้โหลดซับแปลอัตโนมัติ (tlang) ได้เฉพาะเมื่อเซสชันผู้ชม (คุกกี้ VISITOR_INFO1_LIVE
ที่ยูทูปออกให้ผู้เข้าชมทุกคน) มีอายุราว 75 วินาทีขึ้นไป เซสชันใหม่หรือไม่มีเซสชันได้ 429 ทุกครั้ง (spike 2026-10-01)
เซสชันที่อายุถึงแล้วใช้ได้กับทุกคลิป จึงรอแค่ครั้งแรกครั้งเดียว

- ไฟล์ `<data>/visitor-session.txt` (รูปแบบ Netscape ที่ yt-dlp อ่าน/เขียน) เวลาเกิดอยู่ข้าง ๆ ใน
  `visitor-session.json` = {"createdAt": epoch วินาที}
- ในไฟล์มีแต่คุกกี้ที่ yt-dlp ได้จากยูทูปเอง (ผู้เข้าชม/ความยินยอม) ไม่เคยนำเข้าคุกกี้จากเบราว์เซอร์ (นั่นคือ M5 แบบเลือกเปิดเอง)
- ห้ามบันทึกค่าคุกกี้ลง log, ข้อความ error หรือหน้าตรวจสุขภาพ (log ได้แค่ "มี/ไม่มี" และอายุ)
- นาฬิกาเริ่มเมื่อเห็นคุกกี้ผู้เข้าชมครั้งแรก (แบบเดียวกับ yt-dlp PR #15709) และเริ่มใหม่เมื่อค่าคุกกี้นั้นเปลี่ยน
  (เทียบในหน่วยความจำเท่านั้น ไม่เก็บค่าหรือ hash ลงดิสก์)
- อายุเกิน 30 วัน, ไฟล์หาย หรือไฟล์เวลาเสีย = ลบทิ้งแล้วเริ่มเซสชันใหม่ (นาฬิกาเริ่มใหม่)
- โหลดไฟล์เข้าหน่วยความจำครั้งเดียว ทุกคนใช้ jar ก้อนเดียวกัน (CookieJar ของ Python กันชนกันเองอยู่แล้ว)
  การโหลด/บันทึกทั้งหมดอยู่ใต้ล็อกเดียวของโปรเซส และบันทึกแบบเขียนไฟล์ชั่วคราวแล้ว os.replace
  probe ที่รันพร้อมกันจึงไม่เขียนทับกันจนคุกกี้หาย

โมดูลนี้ไม่ import yt_dlp: ผู้เรียก (extractor) ส่งตัวสร้าง jar เข้ามา (YoutubeDLCookieJar) เทสใช้ MozillaCookieJar
"""

from __future__ import annotations

import contextlib
import json
import logging
import math
import os
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger("yttoolkit")

SESSION_FILE = "visitor-session.txt"
META_FILE = "visitor-session.json"
VISITOR_COOKIE = "VISITOR_INFO1_LIVE"
MAX_AGE_S = 30 * 24 * 3600  # เซสชันเก่ากว่านี้ทิ้งแล้วเริ่มใหม่
MIN_TRANSLATION_AGE_S = 75  # ซับแปลโหลดได้เมื่อเซสชันอายุถึงเท่านี้ (spike: 75 วินาที 6/6, ไม่ถึง 8 วินาที 0/10)


# ตัวสร้าง jar เปล่าที่ผูกกับชื่อไฟล์ (YoutubeDLCookieJar หรือ MozillaCookieJar) ต้องมี load/save/set_cookie
JarFactory = Callable[[str], Any]


def _visitor_value(jar: Any) -> str | None:
    """ค่าคุกกี้ผู้เข้าชมของยูทูปใน jar (ใช้เทียบในหน่วยความจำเท่านั้น ห้าม log)"""
    for cookie in list(jar):
        if cookie.name == VISITOR_COOKIE and "youtube" in (cookie.domain or ""):
            return cookie.value
    return None


def _cookies_lock(jar: Any) -> Any:
    """ล็อกภายในของ http.cookiejar.CookieJar: บันทึกระหว่างที่อีก thread กำลังเพิ่มคุกกี้ต้องไม่พัง"""
    lock = getattr(jar, "_cookies_lock", None)
    return lock if lock is not None else contextlib.nullcontext()


class VisitorSession:
    def __init__(
        self,
        folder: Path,
        jar_factory: JarFactory,
        *,
        clock: Callable[[], float] = time.time,
        max_age_s: float = MAX_AGE_S,
    ) -> None:
        self.folder = Path(folder)
        self._factory = jar_factory
        self._clock = clock
        self._max_age_s = max_age_s
        self._lock = threading.RLock()
        self._jar: Any = None
        self._created_at: float | None = None
        self._visitor: str | None = None

    @property
    def path(self) -> Path:
        return self.folder / SESSION_FILE

    @property
    def meta_path(self) -> Path:
        return self.folder / META_FILE

    # ---------- อ่าน ----------

    def jar(self) -> Any:
        """jar ก้อนเดียวของโปรเซส (โหลดจากไฟล์ครั้งแรกที่เรียก) เซสชันเกิน 30 วัน = เริ่มใหม่ก่อนคืน"""
        with self._lock:
            if self._jar is None:
                self._load()
            elif self._expired():
                self._reset("อายุเกิน 30 วัน")
            return self._jar

    def age(self) -> float | None:
        """อายุเซสชัน (วินาที) None = ยังไม่มีคุกกี้ผู้เข้าชม (ต้อง probe สักครั้งก่อน)"""
        with self._lock:
            self.jar()
            if self._created_at is None:
                return None
            return max(0.0, self._clock() - self._created_at)

    def wait_seconds(self, min_age_s: float = MIN_TRANSLATION_AGE_S) -> int | None:
        """อีกกี่วินาทีเซสชันจึงอายุถึง min_age_s (ปัดขึ้น อย่างน้อย 1) 0 = ถึงแล้ว None = ยังไม่มีเซสชัน"""
        age = self.age()
        if age is None:
            return None
        if age >= min_age_s:
            return 0
        return max(1, math.ceil(min_age_s - age))

    # ---------- เขียน ----------

    def save(self, source: Any = None) -> None:
        """บันทึก jar ลงไฟล์ (เขียนไฟล์ชั่วคราวแล้ว replace) ใต้ล็อกของโปรเซส

        source = jar ของ YoutubeDL ตัวที่เพิ่งใช้ ถ้าไม่ใช่ก้อนเดียวกับของเรา (yt-dlp โหลดเอง) รวมคุกกี้เข้ามาก่อน
        บันทึกไม่ได้แค่ log (ไม่มีค่าคุกกี้) ครั้งหน้าลองใหม่ ผู้ใช้ยังใช้แอพได้ตามปกติ
        """
        with self._lock:
            jar = self.jar()
            if source is not None and source is not jar:
                for cookie in list(source):
                    jar.set_cookie(cookie)
            self._track_visitor(jar)
            try:
                self.folder.mkdir(parents=True, exist_ok=True)
                tmp = self.folder / f".{SESSION_FILE}.{uuid.uuid4().hex}.tmp"
                try:
                    with _cookies_lock(jar):
                        jar.save(str(tmp), ignore_discard=True, ignore_expires=True)
                    os.replace(tmp, self.path)
                finally:
                    tmp.unlink(missing_ok=True)
                self._write_meta()
            except OSError as exc:
                log.warning("บันทึกเซสชันผู้ชมของยูทูปไม่สำเร็จ (%s) ครั้งหน้าจะลองใหม่", type(exc).__name__)

    def reset(self) -> None:
        """ลบเซสชันทิ้งแล้วเริ่มใหม่ (นาฬิกาเริ่มใหม่เมื่อ probe ครั้งถัดไปได้คุกกี้ผู้เข้าชม)"""
        with self._lock:
            self._reset("สั่งล้าง")

    # ---------- ภายใน ----------

    def _expired(self) -> bool:
        return self._created_at is not None and self._clock() - self._created_at > self._max_age_s

    def _load(self) -> None:
        jar = self._factory(str(self.path))
        created = self._read_meta()
        has_file = self.path.is_file()
        if not has_file:
            # ไม่มีไฟล์คุกกี้ = เซสชันใหม่ (ไฟล์เวลาเก่าที่ค้างอยู่ใช้ไม่ได้)
            self._clear_files()
            self._set(jar, None)
            return
        try:
            jar.load(str(self.path), ignore_discard=True, ignore_expires=True)
        except (OSError, ValueError) as exc:  # http.cookiejar.LoadError เป็น OSError
            log.warning("ไฟล์เซสชันผู้ชมของยูทูปเสีย (%s) เริ่มเซสชันใหม่", type(exc).__name__)
            self._clear_files()
            self._set(self._factory(str(self.path)), None)
            return
        visitor = _visitor_value(jar)
        if visitor is not None and created is None:
            # มีคุกกี้แต่ไม่รู้ว่าเกิดเมื่อไร: บอกอายุไม่ได้ เริ่มใหม่ให้นาฬิกาตรงความจริง
            log.info("เซสชันผู้ชมของยูทูปไม่มีเวลาเกิด เริ่มเซสชันใหม่")
            self._clear_files()
            self._set(self._factory(str(self.path)), None)
            return
        self._set(jar, created if visitor is not None else None)
        self._visitor = visitor
        if self._expired():
            self._reset("อายุเกิน 30 วัน")

    def _set(self, jar: Any, created_at: float | None) -> None:
        self._jar = jar
        self._created_at = created_at
        self._visitor = None

    def _reset(self, reason: str) -> None:
        log.info("เริ่มเซสชันผู้ชมของยูทูปใหม่ (%s)", reason)
        self._clear_files()
        self._set(self._factory(str(self.path)), None)

    def _track_visitor(self, jar: Any) -> None:
        """เริ่มนาฬิกาเมื่อเห็นคุกกี้ผู้เข้าชมครั้งแรก หรือเมื่อยูทูปเปลี่ยนค่า (เทียบในหน่วยความจำเท่านั้น)"""
        current = _visitor_value(jar)
        if current is None:
            return
        if self._created_at is None:
            self._created_at = self._clock()
            log.info("ได้เซสชันผู้ชมของยูทูปแล้ว (ซับแปลจะโหลดได้ในอีก %s วินาที)", MIN_TRANSLATION_AGE_S)
        elif self._visitor is not None and current != self._visitor:
            self._created_at = self._clock()
            log.info("ยูทูปออกเซสชันผู้ชมใหม่ให้ เริ่มนับอายุใหม่")
        self._visitor = current

    def _read_meta(self) -> float | None:
        try:
            doc = json.loads(self.meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        created = doc.get("createdAt") if isinstance(doc, dict) else None
        if isinstance(created, bool) or not isinstance(created, int | float) or not math.isfinite(created):
            return None
        # เวลาเกิดในอนาคต (นาฬิกาเครื่องถูกย้อน) เชื่อไม่ได้
        if created > self._clock() + 60:
            return None
        return float(created)

    def _write_meta(self) -> None:
        if self._created_at is None:
            self.meta_path.unlink(missing_ok=True)
            return
        body = json.dumps({"createdAt": self._created_at}).encode("utf-8")
        tmp = self.folder / f".{META_FILE}.{uuid.uuid4().hex}.tmp"
        try:
            tmp.write_bytes(body)
            os.replace(tmp, self.meta_path)
        finally:
            tmp.unlink(missing_ok=True)

    def _clear_files(self) -> None:
        for path in (self.path, self.meta_path):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                log.warning("ลบไฟล์เซสชันผู้ชมเก่าไม่ได้ (%s) จะเขียนทับรอบหน้า", path.name)

