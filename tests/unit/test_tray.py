import pystray

from yttoolkit.tray import ACCENT, MENU_LABELS, RUNNING_LABEL, WINDOW, build_menu, build_tray, make_icon_image


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
