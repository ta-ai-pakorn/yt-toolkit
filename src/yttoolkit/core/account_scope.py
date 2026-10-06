"""ขอบเขตของงานที่ใช้บัญชียูทูปชั่วคราว (M5 รอบ C spec 2.3-2.4)

signed_in(jar) ครอบงานหนึ่งชิ้น (probe ของหน้า W2 / งานในคิวทั้งงาน / ถ่ายภาพคมหนึ่งครั้ง) ทุกคำขอ yt-dlp ใน
ขอบเขตนี้ใช้บัญชีนั้น (core/extractor อ่าน current_jar() แล้วส่งให้ _ydl(with_account=...)) และ VideoService
ไม่เขียนข้อมูลคลิปลงดิสก์ ค่าเก็บใน contextvars จึงแยกตามเธรด/งาน ไม่รั่วไปงานอื่นที่รันพร้อมกัน
ใช้แค่ stdlib กับ core/yterrors (ไม่ import yt_dlp)
"""

from __future__ import annotations

import itertools
import logging
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Protocol, TypeVar

from .yterrors import ACCOUNT_CODES, YtError

log = logging.getLogger("yttoolkit")

T = TypeVar("T")
_JAR: ContextVar[Any | None] = ContextVar("yttoolkit_account_jar", default=None)
# ลำดับตอนที่ขอบเขตนี้ได้ jar มา (เทียบกับลำดับตอนล้างข้อมูลที่ได้ด้วยบัญชี VideoService.forget_signed_in)
_SCOPE_EPOCH: ContextVar[int | None] = ContextVar("yttoolkit_account_epoch", default=None)
_EPOCHS = itertools.count(1)
_EPOCH_LOCK = threading.Lock()


class AccountGate(Protocol):
    """ส่วนของ AccountService ที่จุดเรียกยูทูปใช้ (core/account_session.py)"""

    def jar(self) -> Any | None: ...
    def mark_used(self, job_id: str | None) -> None: ...


def current_jar() -> Any | None:
    """jar ของบัญชีที่งานนี้ใช้อยู่ None = ไม่ได้ใช้บัญชี (คำขอแบบไม่ระบุตัวตนตามปกติ)"""
    return _JAR.get()


def account_epoch() -> int:
    """เลขลำดับที่เพิ่มขึ้นทุกครั้งที่เรียก (ทุกเธรดใช้ตัวนับเดียวกัน) ใช้บอกว่าเหตุการณ์บัญชีไหนเกิดก่อน-หลัง"""
    with _EPOCH_LOCK:
        return next(_EPOCHS)


def scope_epoch() -> int | None:
    """ลำดับตอนที่ขอบเขตที่ใช้บัญชีนี้ได้ jar มา None = ไม่อยู่ในขอบเขตที่ใช้บัญชี
    ขอบเขตที่ได้ jar มาก่อน forget_signed_in ครั้งล่าสุด = บัญชีที่ถูกลบ/ถูกแทนแล้ว (งานที่รันค้างใช้ต่อได้ แต่ห้ามเก็บผล)"""
    return _SCOPE_EPOCH.get()


def with_account_retry(accounts: AccountGate | None, call: Callable[[], T], *, job_id: str | None = None) -> T:
    """กฎลองซ้ำของ spec 2.4: เรียกแบบไม่ใช้บัญชีก่อนเสมอ ได้ E_AGE_RESTRICTED / E_VIDEO_PRIVATE และถือบัญชีอยู่
    = เรียก call() ซ้ำอีกครั้งเดียวทั้งก้อนใน signed_in(jar) (ทุกคำขอของงานนั้นใช้บัญชีเดียวกัน)

    - รหัสอื่น (E_BOT_CHECK, E_NETWORK ฯลฯ) ไม่ลองด้วยบัญชี โยนต่อทันที (C9)
    - รอบที่ใช้บัญชีพลาด = YtError รหัสเดิม detail กลาง ๆ ไม่มีข้อความดิบของ yt-dlp และตัดสาย exception (from None)
      รหัสใน ACCOUNT_CODES ติด account_tried (ข้อความ "ลองด้วยบัญชีแล้ว...") บัญชียังอยู่
    - อยู่ในขอบเขตที่ใช้บัญชีแล้ว (งานซ้อนงาน) = เรียกตรง ๆ ไม่ลองซ้ำซ้อน
    job_id = งานในคิว (นับเข้ากฎคิวว่างของ AccountService) · None = หน้าเว็บ/ถ่ายภาพคม
    """
    if accounts is None or _JAR.get() is not None:
        return call()
    try:
        return call()
    except YtError as exc:
        if exc.code not in ACCOUNT_CODES:
            raise
        # ลำดับก่อนอ่าน jar: บัญชีถูกล้างหลังจากนี้ (AccountService ทิ้ง jar ก่อนเรียก on_clear) = ขอบเขตนี้นับเป็นของเก่า
        epoch = account_epoch()
        jar = accounts.jar()
        if jar is None:
            raise
        code = exc.code
    log.info("ลองอีกครั้งด้วยบัญชียูทูปชั่วคราว (%s)", code)
    accounts.mark_used(job_id)
    with _scope(jar, epoch):
        try:
            return call()
        except YtError as exc:
            raise YtError(
                exc.code,
                f"signed-in retry failed ({exc.code})",
                retry_after=exc.retry_after,
                params=exc.params,
                account_tried=exc.code in ACCOUNT_CODES,
            ) from None


@contextmanager
def signed_in(jar: Any) -> Iterator[None]:
    """ให้ทุกคำขอยูทูปในบล็อกนี้ใช้ jar ของบัญชีชั่วคราว (ออกจากบล็อก = กลับเป็นค่าเดิม)"""
    with _scope(jar, account_epoch()):
        yield


@contextmanager
def _scope(jar: Any, epoch: int) -> Iterator[None]:
    if jar is None:
        raise ValueError("signed_in ต้องมี jar")
    token = _JAR.set(jar)
    epoch_token = _SCOPE_EPOCH.set(epoch)
    try:
        yield
    finally:
        _SCOPE_EPOCH.reset(epoch_token)
        _JAR.reset(token)
