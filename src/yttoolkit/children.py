"""เปิดโปรเซสลูกแบบผูกกับแอพ (stdlib ล้วน ไม่ดูระบบปฏิบัติการเอง: ตัวผูกจริงมาจาก Platform.adopt_child)

core ห้าม import platform จึงแยกไว้ที่นี่ให้ core, lifecycle และ platform ใช้ร่วมกัน
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from typing import Any


def run_adopted(
    args: Sequence[str],
    adopt: Callable[[subprocess.Popen], None],
    *,
    timeout: float | None = None,
    capture_output: bool = False,
    **kwargs: Any,
) -> subprocess.CompletedProcess:
    """เหมือน subprocess.run (ไม่มี input/check) แต่ส่งโปรเซสให้ adopt ทันทีหลังเปิด
    โปรเซสลูกที่แอพเปิดต้องผ่าน adopt จะได้ไม่ค้างทำงานต่อหลังแอพโดนปิดกลางคัน (End task, แครช)"""
    argv = list(args)
    if capture_output:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
    with subprocess.Popen(argv, **kwargs) as proc:
        try:
            adopt(proc)  # อยู่ใน try: adopt โยน = ปิดลูกก่อน ไม่ให้ Popen.__exit__ รอลูกที่ยังรันไปตลอด
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise
        except BaseException:
            proc.kill()
            raise
    return subprocess.CompletedProcess(argv, proc.returncode, stdout, stderr)
