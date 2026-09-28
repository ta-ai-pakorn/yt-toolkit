import pystray

from yttoolkit.tray import ACCENT, MENU_LABELS, WINDOW, build_menu, make_icon_image


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
    menu = build_menu(lambda: calls.append("open"), lambda: calls.append("folder"), lambda: calls.append("quit"))
    items = [item for item in menu.items if item is not pystray.Menu.SEPARATOR]
    assert tuple(item.text for item in items) == MENU_LABELS
    assert items[0].default is True
    for item in items:
        item(None)
    assert calls == ["open", "folder", "quit"]
