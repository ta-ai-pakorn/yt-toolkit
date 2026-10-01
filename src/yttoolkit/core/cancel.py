"""สัญญาณยกเลิกงาน"""

from __future__ import annotations


class JobCancelled(Exception):
    """โยนเมื่อผู้ใช้กดยกเลิกหรือโปรแกรมกำลังปิด แล้วงานต้องหยุดทันที"""
