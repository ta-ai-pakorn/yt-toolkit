"""ไอคอนที่ system tray (Windows) / menu bar (macOS) ต้องรันที่ main thread"""

from __future__ import annotations

from collections.abc import Callable

import pystray
from PIL import Image, ImageDraw

ACCENT = (245, 185, 66, 255)  # --accent #F5B942
ON_ACCENT = (26, 20, 5, 255)  # --on-accent #1A1405
MENU_LABELS = ("เปิดแอพ", "เปิดโฟลเดอร์ผลลัพธ์", "ปิดโปรแกรม")


def make_icon_image(size: int = 64) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=size // 5, fill=ACCENT)
    draw.polygon(
        [(size * 0.38, size * 0.28), (size * 0.38, size * 0.72), (size * 0.74, size * 0.5)],
        fill=ON_ACCENT,
    )
    return image


def build_menu(
    open_app: Callable[[], None], open_output: Callable[[], None], quit_app: Callable[[], None]
) -> pystray.Menu:
    return pystray.Menu(
        pystray.MenuItem(MENU_LABELS[0], lambda icon, item: open_app(), default=True),
        pystray.MenuItem(MENU_LABELS[1], lambda icon, item: open_output()),
        pystray.MenuItem("", lambda icon, item: None),  # Visual separator with no text
        pystray.MenuItem(MENU_LABELS[2], lambda icon, item: quit_app()),
    )


def build_tray(
    open_app: Callable[[], None], open_output: Callable[[], None], quit_app: Callable[[], None]
) -> pystray.Icon:
    return pystray.Icon(
        "yt-toolkit", make_icon_image(), "YT Toolkit", menu=build_menu(open_app, open_output, quit_app)
    )
