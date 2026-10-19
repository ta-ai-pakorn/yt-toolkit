import ctypes
import sys
import threading
import time
import types
from ctypes import wintypes

import pystray
import pytest

from yttoolkit.tray import (
    ACCENT,
    MENU_LABELS,
    RUNNING_LABEL,
    SHUTDOWN_REASON,
    WINDOW,
    build_menu,
    build_tray,
    install_session_end,
    make_icon_image,
)


def test_icon_image_is_amber_square():
    img = make_icon_image(64)
    assert img.size == (64, 64)
    assert img.getpixel((5, 32)) == ACCENT


def test_icon_image_has_film_window_and_play():
    img = make_icon_image(64)
    assert img.getpixel((32, 16)) == WINDOW       # film window (top area, outside the triangle)
    assert img.getpixel((35, 32)) == ACCENT       # inside the play triangle
    assert img.getpixel((13, 20)) == ACCENT       # a sprocket hole
    assert img.getpixel((20, 20)) == WINDOW       # window between hole column and triangle


def test_icon_image_small_sizes():
    for size in (16, 32):
        assert make_icon_image(size).size == (size, size)


def test_icon_image_small_variant():
    """Test small variant (size <= 32) has window but no sprocket holes."""
    # 16px small variant
    img16 = make_icon_image(16)
    assert img16.size == (16, 16)
    assert img16.getpixel((3, 6)) == WINDOW       # window, away from the triangle
    assert img16.getpixel((8, 8)) == ACCENT       # inside the triangle
    assert img16.getpixel((1, 8)) == ACCENT       # outer frame

    # 32px small variant
    img32 = make_icon_image(32)
    assert img32.size == (32, 32)
    assert img32.getpixel((6, 10)) == WINDOW      # where a sprocket hole sits in full design (no holes at small size)


def test_menu_labels_and_actions():
    calls = []
    menu = build_menu(
        lambda: calls.append("open"), lambda: calls.append("folder"), lambda: calls.append("quit"), lambda: 0
    )
    items = [item for item in menu.items if item is not pystray.Menu.SEPARATOR]
    assert tuple(item.text for item in items[1:]) == MENU_LABELS
    assert items[1].default is True
    for item in items[1:]:
        item(None)
    assert calls == ["open", "folder", "quit"]


def test_menu_first_row_shows_running_count_and_is_disabled():  # FR-LIFE-6
    count = {"n": 0}
    menu = build_menu(lambda: None, lambda: None, lambda: None, lambda: count["n"])
    first = menu.items[0]
    assert RUNNING_LABEL == "กำลังทำ {n} งาน"
    assert first.text == "กำลังทำ 0 งาน"
    assert first.enabled is False
    count["n"] = 2
    assert first.text == "กำลังทำ 2 งาน"  # อ่านตัวเลขใหม่ทุกครั้งที่สร้างเมนู


def test_build_tray_wires_running_count():
    icon = build_tray(lambda: None, lambda: None, lambda: None, lambda: 3)
    assert icon.menu.items[0].text == "กำลังทำ 3 งาน"


# ---------- M6 รอบ D1: ไม่ขวาง Windows ปิดเครื่อง ----------


class _Plat:
    def __init__(self, handlers: dict) -> None:
        self.handlers = handlers
        self.calls: list = []

    def tray_message_handlers(self, on_session_end, window, reason):
        self.calls.append((on_session_end, window(), reason))
        return self.handlers


def test_install_session_end_adds_platform_handlers_to_the_icon():
    icon = types.SimpleNamespace(_message_handlers={1: "old"}, _hwnd=1234)
    plat = _Plat({0x11: "query", 0x16: "end"})
    hook = object()
    assert install_session_end(icon, plat, hook) is True
    assert icon._message_handlers == {1: "old", 0x11: "query", 0x16: "end"}
    assert plat.calls == [(hook, 1234, SHUTDOWN_REASON)]
    assert SHUTDOWN_REASON == "กำลังบันทึกงาน"


def test_install_session_end_skips_icons_without_a_message_table():
    plat = _Plat({0x11: "query"})
    assert install_session_end(types.SimpleNamespace(), plat, lambda: None) is False  # macOS: pystray ตัวอื่น
    assert plat.calls == []
    icon = types.SimpleNamespace(_message_handlers={})
    assert install_session_end(icon, _Plat({}), lambda: None) is False  # platform ไม่มีข้อความปิดเครื่อง


@pytest.mark.skipif(sys.platform != "win32", reason="ส่งข้อความไปที่หน้าต่าง tray จริงของ Windows")
def test_real_tray_window_allows_shutdown_and_runs_hook_only_when_session_ends():
    """เหมือน Exp 1 ของ audit: ก่อนแก้ หน้าต่าง tray ตอบ WM_QUERYENDSESSION ด้วย 0 (ขวางการปิดเครื่อง)"""
    from yttoolkit.platform import current

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    send = user32.SendMessageTimeoutW
    send.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM, wintypes.UINT, wintypes.UINT,
                     ctypes.POINTER(ctypes.c_size_t))  # fmt: skip
    send.restype = ctypes.c_size_t
    icon = build_tray(lambda: None, lambda: None, lambda: None, lambda: 0)
    ended: list[int] = []
    assert install_session_end(icon, current(), lambda: ended.append(1)) is True
    results: dict = {}

    def probe() -> None:
        try:
            deadline = time.monotonic() + 10
            while not getattr(icon, "_hwnd", None) and time.monotonic() < deadline:
                time.sleep(0.05)
            for name, msg, wparam, lparam in (
                ("query_shutdown", 0x0011, 0, 0),
                ("query_logoff", 0x0011, 0, 0x80000000),  # ENDSESSION_LOGOFF
                ("end_cancelled", 0x0016, 0, 0),  # โปรแกรมอื่นยกเลิกการปิดเครื่อง
            ):
                out = ctypes.c_size_t(99)
                assert send(icon._hwnd, msg, wparam, lparam, 0x0002, 3000, ctypes.byref(out))
                results[name] = (out.value, len(ended))
            out = ctypes.c_size_t(99)
            assert send(icon._hwnd, 0x0016, 1, 0, 0x0002, 5000, ctypes.byref(out))  # WM_ENDSESSION(TRUE)
            results["end"] = (out.value, len(ended))
        finally:
            icon.stop()

    thread = threading.Thread(target=probe, daemon=True)
    thread.start()
    icon.run()
    thread.join(5)
    assert results["query_shutdown"] == (1, 0)
    assert results["query_logoff"] == (1, 0)
    assert results["end_cancelled"] == (0, 0)
    assert results["end"] == (0, 1)
