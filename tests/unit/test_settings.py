from __future__ import annotations

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
        {"theme": "blue"},
        {"filenameStyle": "x"},
        {"lastUsed": []},
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
