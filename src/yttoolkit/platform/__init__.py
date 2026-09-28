"""จุดเดียวที่รู้ว่ากำลังรันบนระบบปฏิบัติการไหน"""

from __future__ import annotations

import sys

from .base import Platform


def current() -> Platform:
    if sys.platform == "win32":
        from .windows import WindowsPlatform

        return WindowsPlatform()
    if sys.platform == "darwin":
        from .macos import MacPlatform

        return MacPlatform()
    raise RuntimeError(f"ยังไม่รองรับระบบปฏิบัติการนี้: {sys.platform}")


__all__ = ["Platform", "current"]
