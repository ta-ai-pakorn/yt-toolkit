"""ไอคอนที่ system tray (Windows) / menu bar (macOS) ต้องรันที่ main thread"""

from __future__ import annotations

from collections.abc import Callable

import pystray
from PIL import Image, ImageDraw

ACCENT = (245, 185, 66, 255)  # --accent #F5B942
ON_ACCENT = (26, 20, 5, 255)  # --on-accent #1A1405
WINDOW = (14, 15, 17, 255)  # film window color #0E0F11
MENU_LABELS = ("เปิดแอพ", "เปิดโฟลเดอร์ผลลัพธ์", "ปิดโปรแกรม")


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
    # Render at 4x size for anti-aliasing, then downscale
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

    # Downscale to requested size with anti-aliasing
    return large_image.resize((size, size), Image.LANCZOS)


def _make_icon_image_full(size: int) -> Image.Image:
    """Full A2 logo variant with sprocket holes (for size > 32)."""
    # Render at 4x size for anti-aliasing, then downscale
    scale = 4
    large_size = size * scale
    large_image = Image.new("RGBA", (large_size, large_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(large_image)

    # Amber rounded square background (rx 14 → scaled to 56)
    draw.rounded_rectangle((0, 0, large_size - 1, large_size - 1), radius=14 * scale, fill=ACCENT)

    # Dark film window (8..56, 14..50, rx 4 → scaled)
    window_bbox = (8 * scale, 14 * scale, 56 * scale, 50 * scale)
    draw.rounded_rectangle(window_bbox, radius=4 * scale, fill=WINDOW)

    # 6 amber sprocket holes: 5x6 rx 1.5 at x ∈ {11, 48}, y ∈ {18, 29, 40}
    hole_positions = [(11, 18), (11, 29), (11, 40), (48, 18), (48, 29), (48, 40)]
    for x, y in hole_positions:
        bbox = (x * scale, y * scale, (x + 5) * scale, (y + 6) * scale)
        draw.rounded_rectangle(bbox, radius=int(1.5 * scale), fill=ACCENT)

    # Amber play triangle: points (27, 22.5), (27, 41.5), (43, 32)
    triangle = [
        (27 * scale, int(22.5 * scale)),
        (27 * scale, int(41.5 * scale)),
        (43 * scale, 32 * scale),
    ]
    draw.polygon(triangle, fill=ACCENT)

    # Downscale to requested size with anti-aliasing
    return large_image.resize((size, size), Image.LANCZOS)


def build_menu(
    open_app: Callable[[], None], open_output: Callable[[], None], quit_app: Callable[[], None]
) -> pystray.Menu:
    return pystray.Menu(
        pystray.MenuItem(MENU_LABELS[0], lambda icon, item: open_app(), default=True),
        pystray.MenuItem(MENU_LABELS[1], lambda icon, item: open_output()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(MENU_LABELS[2], lambda icon, item: quit_app()),
    )


def build_tray(
    open_app: Callable[[], None], open_output: Callable[[], None], quit_app: Callable[[], None]
) -> pystray.Icon:
    return pystray.Icon(
        "yt-toolkit", make_icon_image(32), "YT Toolkit", menu=build_menu(open_app, open_output, quit_app)
    )
