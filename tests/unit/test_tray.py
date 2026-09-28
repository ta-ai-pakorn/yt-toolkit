from yttoolkit.tray import ACCENT, MENU_LABELS, build_menu, make_icon_image


def test_icon_image_is_amber_square():
    img = make_icon_image(64)
    assert img.size == (64, 64)
    assert img.getpixel((5, 32)) == ACCENT


def test_menu_labels_and_actions():
    calls = []
    menu = build_menu(lambda: calls.append("open"), lambda: calls.append("folder"), lambda: calls.append("quit"))
    items = [item for item in menu.items if item.text]
    assert tuple(item.text for item in items) == MENU_LABELS
    assert items[0].default is True
    for item in items:
        item(None)
    assert calls == ["open", "folder", "quit"]
