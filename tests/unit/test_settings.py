from __future__ import annotations

import sys
from pathlib import Path

import pytest

from yttoolkit.core.db import Database
from yttoolkit.core.settings import SettingsError, SettingsStore
from yttoolkit.core.srt_builder import PRESETS


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "app.db")
    database.migrate()
    yield database
    database.close()


@pytest.fixture
def store(db, tmp_path):
    return SettingsStore(db, tmp_path / "out")


def test_defaults_match_the_c5_table(store, tmp_path):
    assert store.get() == {
        "outputDir": str(tmp_path / "out"),
        "videoDefault": "compat-1080",
        "audioDefault": "m4a",
        "audioLanguage": "original",
        "mp3Kbps": 192,
        "subPreset": "medium",
        "subCustom": {
            "maxChars": PRESETS["medium"].max_chars,
            "lines": PRESETS["medium"].lines,
            "minMs": PRESETS["medium"].min_ms,
            "maxMs": PRESETS["medium"].max_ms,
            "mode": "chars",
        },
        "concurrency": 2,
        "sponsorblockDefault": ["sponsor", "selfpromo", "interaction"],
        "autoSharpFrames": True,
        "theme": "system",
        "filenameStyle": "title",
        "cookies": {"enabled": False, "source": None, "warningAccepted": False},
        "statsResetAt": None,
        "lastUsed": {},
    }
    assert store.output_dir() == tmp_path / "out"
    assert store.concurrency() == 2


def test_get_returns_a_copy(store):
    store.get()["sponsorblockDefault"].append("x")
    assert store.get()["sponsorblockDefault"] == ["sponsor", "selfpromo", "interaction"]


def test_patch_persists_across_stores(db, tmp_path, store):
    result = store.patch({"concurrency": 3})
    assert result["concurrency"] == 3
    again = SettingsStore(db, tmp_path / "out")
    assert again.concurrency() == 3
    assert again.get()["audioDefault"] == "m4a"


def test_patch_changes_only_the_named_keys(store):
    store.patch({"theme": "dark"})
    store.patch({"mp3Kbps": 320})
    got = store.get()
    assert got["theme"] == "dark" and got["mp3Kbps"] == 320 and got["concurrency"] == 2


@pytest.mark.parametrize(
    "bad",
    [
        {"concurrency": 4},
        {"concurrency": True},
        {"concurrency": "2"},
        {"nope": 1},
        {"cookies": {"enabled": True}},
        {"statsResetAt": "x"},
        {"outputDir": "relative"},
        {"outputDir": ""},
        {"outputDir": 5},
        {"videoDefault": "4k"},
        {"audioDefault": "flac"},
        {"audioLanguage": "not a tag"},
        {"mp3Kbps": 64},
        {"subPreset": "huge"},
        {"subCustom": {"maxChars": 1}},
        {"subCustom": "x"},
        {"sponsorblockDefault": "sponsor"},
        {"sponsorblockDefault": ["Bad Name"]},
        {"sponsorblockDefault": []},
        {"sponsorblockDefault": ["sponsor", "poi_highlight"]},
        {"sponsorblockDefault": ["chapter"]},
        {"theme": "blue"},
        {"filenameStyle": "x"},
        {"lastUsed": []},
        {"autoSharpFrames": 1},
        {"autoSharpFrames": "true"},
        {"autoSharpFrames": None},
    ],
)
def test_invalid_patch_is_rejected_and_changes_nothing(store, bad):
    with pytest.raises(SettingsError) as info:
        store.patch({"concurrency": 1, **bad})
    assert info.value.code == "E_BAD_REQUEST"
    assert store.concurrency() == 2


def test_patch_with_an_unwritable_folder(store, tmp_path):
    a_file = tmp_path / "file.txt"
    a_file.write_text("x")
    with pytest.raises(SettingsError) as info:
        store.patch({"concurrency": 1, "outputDir": str(a_file)})
    assert info.value.code == "E_OUTPUT_NOT_WRITABLE"
    assert store.concurrency() == 2
    assert store.output_dir() == tmp_path / "out"


def test_patch_output_dir_creates_the_folder_and_leaves_no_probe(store, tmp_path):
    target = tmp_path / "deep" / "new"
    store.patch({"outputDir": str(target)})
    assert target.is_dir()
    assert list(target.iterdir()) == []
    assert store.output_dir() == target


def test_word_preset_is_accepted(store):
    assert store.patch({"subPreset": "word"})["subPreset"] == "word"


def test_sub_custom_is_normalised(store):
    custom = {"maxChars": 30, "lines": 2, "minMs": 1000, "maxMs": 6000, "mode": "tokens", "tokensPerCue": 3, "extra": 1}
    assert store.patch({"subCustom": custom})["subCustom"] == {
        "maxChars": 30,
        "lines": 2,
        "minMs": 1000,
        "maxMs": 6000,
        "mode": "tokens",
        "tokensPerCue": 3,
    }


def test_empty_patch_is_a_no_op(store):
    assert store.patch({}) == store.get()


def test_non_mapping_patch_is_rejected(store):
    with pytest.raises(SettingsError) as info:
        store.patch([("a", 1)])  # type: ignore[arg-type]
    assert info.value.code == "E_BAD_REQUEST"


def test_get_exposes_only_cookie_status_fields(store):
    assert set(store.get()["cookies"]) == {"enabled", "source", "warningAccepted"}


def test_corrupt_stored_row_falls_back_to_default(db, store):
    db.execute("INSERT INTO settings (key, value_json) VALUES ('concurrency', '{broken')")
    assert store.concurrency() == 2


# ---------- fix round 1 ----------


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_last_used_rejects_non_finite_numbers(store, bad):
    with pytest.raises(SettingsError) as info:
        store.patch({"lastUsed": {"x": bad}})
    assert info.value.code == "E_BAD_REQUEST"
    assert store.get()["lastUsed"] == {}  # GET ยังทำงานปกติ


def test_last_used_is_stored_as_plain_json(store):
    assert store.patch({"lastUsed": {"a": (1, 2), "b": 1.5}})["lastUsed"] == {"a": [1, 2], "b": 1.5}


@pytest.mark.parametrize(
    "bad",
    [
        {"concurrency": 2.0},
        {"mp3Kbps": 192.0},
        {"mp3Kbps": True},
        {"audioDefault": 1},
        {"theme": ["dark"]},
    ],
)
def test_floats_and_wrong_types_are_not_accepted_as_enum_values(store, bad):
    with pytest.raises(SettingsError) as info:
        store.patch(bad)
    assert info.value.code == "E_BAD_REQUEST"


def test_output_dir_with_a_nul_byte_is_a_bad_request(store, tmp_path):
    with pytest.raises(SettingsError) as info:
        store.patch({"outputDir": str(tmp_path / "a\x00b")})
    assert info.value.code == "E_BAD_REQUEST"
    assert info.value.key == "outputDir"


def test_ensure_writable_turns_value_errors_into_not_writable(tmp_path):
    from yttoolkit.core.settings import ensure_writable

    with pytest.raises(SettingsError) as info:
        ensure_writable(Path(str(tmp_path / "a\x00b")))
    assert info.value.code == "E_OUTPUT_NOT_WRITABLE"


def test_output_dir_is_stripped_and_normalised(store, tmp_path):
    messy = f"  {tmp_path / 'a' / '..' / 'clean'}  "
    assert store.patch({"outputDir": messy})["outputDir"] == str(tmp_path / "clean")


@pytest.mark.skipif(sys.platform != "win32", reason="ชื่อ path แบบ Windows")
@pytest.mark.parametrize(
    "bad",
    [
        "C:\\Users\\x\\Videos.",
        "C:\\Users\\x \\Videos",
        "C:\\Users\\CON\\Videos",
        "C:\\Users\\nul.txt",
        "C:\\Users\\Lpt1",
        "D:\\com9",
        "C:\\Users\\x\\..\\NUL",
    ],
)
def test_windows_unsafe_output_dirs_are_rejected(store, bad):
    with pytest.raises(SettingsError) as info:
        store.patch({"outputDir": bad})
    assert info.value.code == "E_BAD_REQUEST"
    assert info.value.key == "outputDir"


@pytest.mark.skipif(sys.platform != "win32", reason="ชื่อ path แบบ Windows")
def test_windows_dotdot_and_unc_paths_normalise_and_pass_validation():
    from yttoolkit.core.settings import _validate_output_dir

    assert _validate_output_dir("C:\\Users\\x\\a\\..\\Videos") == "C:\\Users\\x\\Videos"
    assert _validate_output_dir("\\\\server\\share\\Videos") == "\\\\server\\share\\Videos"
    assert _validate_output_dir("C:/Users/x/Videos") == "C:\\Users\\x\\Videos"
    assert _validate_output_dir("  C:\\Users\\x\\Videos  ") == "C:\\Users\\x\\Videos"


def test_probe_file_names_are_unique_and_removed(tmp_path, monkeypatch):
    from yttoolkit.core.settings import ensure_writable

    seen: list[str] = []
    original = Path.write_bytes

    def spy(self, data):
        seen.append(self.name)
        return original(self, data)

    monkeypatch.setattr(Path, "write_bytes", spy)
    ensure_writable(tmp_path)
    ensure_writable(tmp_path)
    assert len(seen) == 2
    assert seen[0] != seen[1]
    assert all(name.startswith(".yt-toolkit-write-test-") for name in seen)
    assert list(tmp_path.iterdir()) == []


def test_patch_probes_the_folder_without_holding_the_lock(db, tmp_path, monkeypatch):
    import yttoolkit.core.settings as module

    store = SettingsStore(db, tmp_path / "out")
    held: list[bool] = []

    def probe(folder):
        held.append(store._lock._is_owned())  # type: ignore[attr-defined]

    monkeypatch.setattr(module, "ensure_writable", probe)
    store.patch({"outputDir": str(tmp_path / "x")})
    assert held == [False]


@pytest.mark.parametrize(
    ("key", "stored"),
    [
        ("concurrency", "9"),
        ("concurrency", "2.0"),
        ("theme", '"purple"'),
        ("outputDir", '"relative"'),
        ("subCustom", '{"maxChars": 1}'),
        ("lastUsed", "[]"),
    ],
)
def test_stored_values_are_revalidated_on_read(db, store, key, stored):
    default = store.get()[key]
    db.execute("INSERT INTO settings (key, value_json) VALUES (?, ?)", (key, stored))
    assert store.get()[key] == default


def test_stored_valid_value_survives_revalidation(db, store):
    db.execute("INSERT INTO settings (key, value_json) VALUES ('concurrency', '3')")
    assert store.concurrency() == 3


def test_sponsorblock_default_keeps_order_and_drops_duplicates(store):
    saved = store.patch({"sponsorblockDefault": ["filler", "sponsor", "filler", "music_offtopic"]})
    assert saved["sponsorblockDefault"] == ["filler", "sponsor", "music_offtopic"]


def test_auto_sharp_frames_can_be_switched_off_and_on(store):
    assert store.patch({"autoSharpFrames": False})["autoSharpFrames"] is False
    assert store.patch({"autoSharpFrames": True})["autoSharpFrames"] is True
