"""ไอคอนที่ system tray (Windows) / menu bar (macOS) ต้องรันที่ main thread"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import pystray
from PIL import Image, ImageDraw

if TYPE_CHECKING:
    from .platform import Platform

ACCENT = (245, 185, 66, 255)  # --accent #F5B942
ON_ACCENT = (26, 20, 5, 255)  # --on-accent #1A1405
WINDOW = (14, 15, 17, 255)  # film window color #0E0F11
MENU_LABELS = ("เปิดแอพ", "เปิดโฟลเดอร์ผลลัพธ์", "ปิดโปรแกรม")
RUNNING_LABEL = "กำลังทำ {n} งาน"  # แถวแรกของเมนู กดไม่ได้ บอกจำนวนงานที่กำลังทำ (FR-LIFE-6)
# M6 รอบ D1: Windows แสดงข้อความนี้บนหน้าจอปิดเครื่อง ถ้าแอพยังเก็บงานไม่เสร็จ (ปกติเสร็จก่อนข้อความจะโผล่)
SHUTDOWN_REASON = "กำลังบันทึกงาน"


def make_icon_image(size: int = 64) -> Image.Image:
    """Draw A2 logo: amber rounded square with dark film window and play triangle.

    For size <= 32, uses simplified variant without sprocket holes for crispness.
    For size > 32, draws full A2 logo with sprocket holes.
    """
    if size <= 32:
        return _make_icon_image_small(size)
    else:
        return _make_icon_image_full(size)


def _make_icon_image_small(size: int) -> Image.Image:
    """Small variant on 16-unit grid for crisp rendering at small sizes."""
    # Render at 4x size for pixel-perfect color preservation, then downscale
    large_size = size * 4
    large_image = Image.new("RGBA", (large_size, large_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(large_image)

    # Scale factor from 16-unit grid to pixel coordinates
    k = (size * 4) / 16

    # Amber rounded square background (radius 3.5 units)
    draw.rounded_rectangle((0, 0, large_size - 1, large_size - 1), radius=int(3.5 * k), fill=ACCENT)

    # Dark film window (x 2..14, y 4..12 units, radius 1 unit)
    window_bbox = (int(2 * k), int(4 * k), int(14 * k - 1), int(12 * k - 1))
    draw.rounded_rectangle(window_bbox, radius=int(1 * k), fill=WINDOW)

    # Amber play triangle: points (6.5, 5.5), (6.5, 10.5), (10.5, 8) units
    triangle = [
        (int(6.5 * k), int(5.5 * k)),
        (int(6.5 * k), int(10.5 * k)),
        (int(10.5 * k), int(8 * k)),
    ]
    draw.polygon(triangle, fill=ACCENT)

    # Downscale with BOX filter to preserve exact colors in pixel-aligned regions
    return large_image.resize((size, size), Image.BOX)


def _make_icon_image_full(size: int) -> Image.Image:
    """Full A2 logo variant with sprocket holes (for size > 32)."""
    # Render at 4x size for pixel-perfect color preservation, then downscale
    large_size = size * 4
    large_image = Image.new("RGBA", (large_size, large_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(large_image)

    # Scale factor from 64-unit grid to pixel coordinates
    k = (size * 4) / 64

    # Amber rounded square background (rx 14 units)
    draw.rounded_rectangle((0, 0, large_size - 1, large_size - 1), radius=int(14 * k), fill=ACCENT)

    # Dark film window (8..56, 14..50 units, rx 4)
    window_bbox = (int(8 * k), int(14 * k), int(56 * k), int(50 * k))
    draw.rounded_rectangle(window_bbox, radius=int(4 * k), fill=WINDOW)

    # 6 amber sprocket holes: 5x6 rx 1.5 at x ∈ {11, 48}, y ∈ {18, 29, 40}
    hole_positions = [(11, 18), (11, 29), (11, 40), (48, 18), (48, 29), (48, 40)]
    for x, y in hole_positions:
        bbox = (int(x * k), int(y * k), int((x + 5) * k), int((y + 6) * k))
        draw.rounded_rectangle(bbox, radius=int(1.5 * k), fill=ACCENT)

    # Amber play triangle: points (27, 22.5), (27, 41.5), (43, 32) units
    triangle = [
        (int(27 * k), int(22.5 * k)),
        (int(27 * k), int(41.5 * k)),
        (int(43 * k), int(32 * k)),
    ]
    draw.polygon(triangle, fill=ACCENT)

    # Downscale with BOX filter to preserve exact colors in pixel-aligned regions
    return large_image.resize((size, size), Image.BOX)


def running_text(running_count: Callable[[], int]) -> Callable[[pystray.MenuItem], str]:
    """ข้อความแถวจำนวนงาน pystray เรียกใหม่ทุกครั้งที่สร้างเมนู (ตอน update_menu) จึงได้ตัวเลขล่าสุด"""

    def text(item: pystray.MenuItem) -> str:
        return RUNNING_LABEL.format(n=running_count())

    return text


def build_menu(
    open_app: Callable[[], None],
    open_output: Callable[[], None],
    quit_app: Callable[[], None],
    running_count: Callable[[], int],
) -> pystray.Menu:
    return pystray.Menu(
        pystray.MenuItem(running_text(running_count), None, enabled=False),
        pystray.MenuItem(MENU_LABELS[0], lambda icon, item: open_app(), default=True),
        pystray.MenuItem(MENU_LABELS[1], lambda icon, item: open_output()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(MENU_LABELS[2], lambda icon, item: quit_app()),
    )


def build_tray(
    open_app: Callable[[], None],
    open_output: Callable[[], None],
    quit_app: Callable[[], None],
    running_count: Callable[[], int],
) -> pystray.Icon:
    return pystray.Icon(
        "yt-toolkit",
        make_icon_image(32),
        "YT Toolkit",
        menu=build_menu(open_app, open_output, quit_app, running_count),
    )


def install_session_end(icon: pystray.Icon, plat: Platform, on_session_end: Callable[[], None]) -> bool:
    """M6 รอบ D1: ให้หน้าต่าง tray ตอบข้อความปิดเครื่อง/ออกจากระบบ (ตัวจัดการมาจาก platform ที่เดียวที่รู้จักระบบ)

    pystray ตอบ 0 ให้ทุกข้อความที่ไม่มีตัวจัดการ ซึ่ง WM_QUERYENDSESSION = 0 แปลว่า "ห้ามปิดเครื่อง"
    จึงเพิ่มตัวจัดการลงใน icon._message_handlers (มีใน pystray 0.19.5 ตัว win32) icon ที่ไม่มีช่องนี้ (macOS) ข้าม
    คืน True ถ้าใส่ตัวจัดการได้"""
    table = getattr(icon, "_message_handlers", None)
    if not isinstance(table, dict):
        return False
    handlers = plat.tray_message_handlers(on_session_end, lambda: getattr(icon, "_hwnd", None), SHUTDOWN_REASON)
    table.update(handlers)
    return bool(handlers)
