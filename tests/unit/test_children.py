"""children.run_adopted: เปิดลูกแล้วส่งให้ adopt ทันที (M6 รอบ D1)"""

from __future__ import annotations

import subprocess
import sys
import time

import pytest

from yttoolkit.children import run_adopted


def test_run_adopted_returns_output_and_adopts_the_child():
    adopted: list[int] = []
    out = run_adopted([sys.executable, "-c", "print('ok')"], lambda p: adopted.append(p.pid),
                      capture_output=True, text=True, timeout=30)
    assert out.returncode == 0 and out.stdout.strip() == "ok"
    assert len(adopted) == 1


def test_a_raising_adopt_kills_the_child_instead_of_waiting_forever():
    seen: list[subprocess.Popen] = []

    def broken(proc):
        seen.append(proc)
        raise RuntimeError("adopt failed")

    start = time.monotonic()
    with pytest.raises(RuntimeError):
        run_adopted([sys.executable, "-c", "import time; time.sleep(60)"], broken)
    assert time.monotonic() - start < 20  # ไม่ได้รอลูกหลับครบ 60 วินาที
    assert seen[0].poll() is not None
