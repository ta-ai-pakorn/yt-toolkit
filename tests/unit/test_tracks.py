from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from yttoolkit.core.tracks import (
    TRACK_ID,
    Track,
    default_track_id,
    find_track,
    list_tracks,
    original_language,
    trim_captions,
    tracks_payload,
)
from yttoolkit.core.videos import trim_probe

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SRC = Path(__file__).resolve().parents[2] / "src" / "yttoolkit"


def load(name: str) -> dict:
    return json.loads((FIXTURES / "probe" / f"{name}.json").read_text(encoding="utf-8"))


def trimmed(name: str) -> dict:
    return trim_probe(load(name))


def ids(tracks: list[Track], group: str) -> list[str]:
    return [t.id for t in tracks if t.group == group]


def entry(ext: str, url: str, name: str | None = "Thai", **extra: str) -> dict:
    item = {"ext": ext, "url": url, **extra}
    if name is not None:
        item["name"] = name
    return item


FAKE = "https://fake.invalid/subs/SYNTH/"


def raw_with(subtitles: dict | None = None, auto: dict | None = None, **extra) -> dict:
    return {
        "id": "SYNTHETIC01",
        "formats": [],
        "subtitles": subtitles or {},
        "automatic_captions": auto or {},
        **extra,
    }


# ---------- TRACK_ID ----------


@pytest.mark.parametrize("value", ["o.th", "a.th-orig", "a.en-US-orig", "t.zh-Hans", "a.yue"])
def test_track_id_accepts_c1_ids(value: str) -> None:
    assert TRACK_ID.fullmatch(value)
    assert TRACK_ID.match(value)


@pytest.mark.parametrize(
    "value", ["x.th", "a.", "a.th/../x", "th", "o.th\n", "o." + "a" * 65, "O.th", "o.th.x"]
)
def test_track_id_rejects_malformed_ids(value: str) -> None:
    assert not TRACK_ID.match(value)


# ---------- 88o5Sk8_m1Y (AC-SUB-01) ----------


def test_88o5_original_is_only_th_orig_and_auto_th_duplicate_is_dropped() -> None:
    data = trimmed("88o5Sk8_m1Y")
    tracks = list_tracks(data)
    assert ids(tracks, "original") == ["a.th-orig"]
    assert ids(tracks, "owner") == []
    assert "t.th" not in {t.id for t in tracks}
    assert data["captions"]["translateFrom"] == "th-orig"


def test_88o5_translated_keys_are_the_captured_languages() -> None:
    tracks = list_tracks(trimmed("88o5Sk8_m1Y"))
    keys = {t.id.removeprefix("t.") for t in tracks if t.group == "translated"}
    assert keys
    assert keys <= {"en", "ja", "fr", "ko", "zh-Hans"}


def test_88o5_default_is_the_thai_original_track() -> None:
    data = trimmed("88o5Sk8_m1Y")
    assert original_language(data) == "th"
    assert default_track_id(list_tracks(data), original_language(data)) == "a.th-orig"
    assert tracks_payload(data)["defaultTrackId"] == "a.th-orig"


def test_88o5_translated_url_is_built_from_the_original_with_tlang() -> None:
    track = find_track(trimmed("88o5Sk8_m1Y"), "t.en")
    assert track is not None
    assert track.json3 == "https://fake.invalid/subs/88o5Sk8_m1Y/th-orig.json3?tlang=en"
    assert track.vtt == "https://fake.invalid/subs/88o5Sk8_m1Y/th-orig.vtt?tlang=en"
    assert (track.lang, track.name, track.group) == ("en", "English", "translated")


def test_88o5_original_track_fields() -> None:
    track = find_track(trimmed("88o5Sk8_m1Y"), "a.th-orig")
    assert track == Track(
        id="a.th-orig",
        lang="th",
        name="Thai (Original)",
        group="original",
        json3="https://fake.invalid/subs/88o5Sk8_m1Y/th-orig.json3",
        vtt="https://fake.invalid/subs/88o5Sk8_m1Y/th-orig.vtt",
    )


def test_translated_entries_store_only_key_and_name() -> None:
    captions = trimmed("88o5Sk8_m1Y")["captions"]
    assert captions["translated"]
    assert all(set(item) == {"key", "name"} for item in captions["translated"])
    assert "tlang" not in json.dumps(captions)


# ---------- 8lpOfyoxcvU ----------


def test_8lpo_two_originals_and_thai_audio_wins() -> None:
    data = trimmed("8lpOfyoxcvU")
    tracks = list_tracks(data)
    assert ids(tracks, "original") == ["a.en-US-orig", "a.th-orig"]
    assert original_language(data) == "th"
    assert default_track_id(tracks, "th") == "a.th-orig"
    assert tracks_payload(data)["defaultTrackId"] == "a.th-orig"
    assert data["captions"]["translateFrom"] == "th-orig"


def test_8lpo_mixed_auto_keys_with_an_orig_twin_are_dropped() -> None:
    all_ids = {t.id for t in list_tracks(trimmed("8lpOfyoxcvU"))}
    # th มีทั้ง entry tlang และไม่ tlang (คลิปพากย์) และ en-US ซ้ำกับ en-US-orig
    assert not {"t.th", "a.th", "t.en-US", "a.en-US"} & all_ids
    assert "t.en" in all_ids


def test_8lpo_translation_is_built_from_the_thai_original() -> None:
    track = find_track(trimmed("8lpOfyoxcvU"), "t.en")
    assert track is not None
    assert track.json3 == "https://fake.invalid/subs/8lpOfyoxcvU/th-orig.json3?tlang=en"


# ---------- jNQXAC9IVRw ----------


def test_jnq_owner_tracks_and_hls_auto_entries_are_ignored() -> None:
    data = trimmed("jNQXAC9IVRw")
    tracks = list_tracks(data)
    assert ids(tracks, "owner") == ["o.en", "o.de"]
    assert ids(tracks, "original") == []
    assert ids(tracks, "translated") == []
    assert data["captions"]["translateFrom"] is None
    assert "m3u8" not in json.dumps(data["captions"])
    assert tracks_payload(data)["defaultTrackId"] == "o.en"


def test_jnq_owner_track_fields() -> None:
    track = find_track(trimmed("jNQXAC9IVRw"), "o.de")
    assert track == Track(
        id="o.de",
        lang="de",
        name="German",
        group="owner",
        json3="https://fake.invalid/subs/jNQXAC9IVRw/de.json3",
        vtt="https://fake.invalid/subs/jNQXAC9IVRw/de.vtt",
    )


# ---------- OWNERTHSUB1 (Q8 = ก, Q9 = ข) ----------


def test_owner_thai_subtitles_win_over_the_english_original() -> None:
    data = trimmed("OWNERTHSUB1")
    tracks = list_tracks(data)
    assert ids(tracks, "owner") == ["o.th", "o.en"]
    assert ids(tracks, "original") == ["a.en-orig"]
    assert original_language(data) == "en"
    assert default_track_id(tracks, "en") == "o.th"
    assert default_track_id(tracks, "en", prefer="th") == "o.th"
    assert tracks_payload(data)["defaultTrackId"] == "o.th"


def test_without_prefer_the_owner_track_in_the_original_language_wins() -> None:
    tracks = list_tracks(trimmed("OWNERTHSUB1"))
    assert default_track_id(tracks, "en", prefer=None) == "o.en"


# ---------- NOORIGSUB01 (AC-SUB-02) ----------


def test_noorig_untranslatable_asr_is_original_and_there_is_no_default() -> None:
    data = trimmed("NOORIGSUB01")
    tracks = list_tracks(data)
    assert ids(tracks, "original") == ["a.yue"]
    assert ids(tracks, "translated") == ["t.en", "t.th"]
    assert ids(tracks, "owner") == []
    assert original_language(data) is None
    assert default_track_id(tracks, None) is None
    payload = tracks_payload(data)
    assert "defaultTrackId" not in payload
    assert [t["id"] for t in payload["tracks"]] == ["a.yue", "t.en", "t.th"]


def test_noorig_translations_use_the_first_original_track() -> None:
    data = trimmed("NOORIGSUB01")
    assert data["captions"]["translateFrom"] == "yue"
    track = find_track(data, "t.th")
    assert track is not None
    assert track.json3 == "https://fake.invalid/subs/88o5Sk8_m1Y/th-orig.json3?tlang=th"
    assert track.vtt is None


def test_missing_yt_dlp_name_falls_back_to_the_key() -> None:
    tracks = list_tracks(trimmed("NOORIGSUB01"))
    assert [(t.id, t.name) for t in tracks] == [
        ("a.yue", "yue"),
        ("t.en", "en"),
        ("t.th", "th"),
    ]


# ---------- aqz-KE-bpKQ ----------


def test_bbb_has_no_tracks() -> None:
    data = trimmed("aqz-KE-bpKQ")
    assert data["captions"] == {
        "owner": [],
        "original": [],
        "translated": [],
        "translateFrom": None,
    }
    assert tracks_payload(data) == {"tracks": []}


# ---------- payload shape ----------


def test_payload_track_items_have_exactly_the_c1_fields() -> None:
    payload = tracks_payload(trimmed("88o5Sk8_m1Y"))
    assert payload["tracks"]
    for item in payload["tracks"]:
        assert set(item) == {"id", "lang", "name", "group"}
    groups = [t["group"] for t in payload["tracks"]]
    assert groups == sorted(groups, key=["owner", "original", "translated"].index)


def test_all_listed_ids_match_track_id() -> None:
    for name in ("88o5Sk8_m1Y", "8lpOfyoxcvU", "jNQXAC9IVRw", "OWNERTHSUB1", "NOORIGSUB01"):
        for track in list_tracks(trimmed(name)):
            assert TRACK_ID.fullmatch(track.id), track.id


# ---------- synthetic classification ----------


def test_live_chat_is_dropped() -> None:
    raw = raw_with(
        subtitles={
            "live_chat": [entry("json3", FAKE + "live_chat.json3", "Live chat")],
            "th": [entry("json3", FAKE + "th.json3")],
        }
    )
    assert [o["key"] for o in trim_captions(raw)["owner"]] == ["th"]


def test_key_with_only_srv3_entries_is_dropped() -> None:
    raw = raw_with(
        subtitles={"en": [entry("srv3", FAKE + "en.srv3", "English")]},
        auto={
            "th-orig": [entry("srv3", FAKE + "th-orig.srv3")],
            "fr": [entry("srv3", FAKE + "th-orig.srv3?tlang=fr", "French")],
        },
    )
    captions = trim_captions(raw)
    assert captions == {"owner": [], "original": [], "translated": [], "translateFrom": None}


def test_mixed_key_with_an_orig_twin_is_dropped() -> None:
    raw = raw_with(
        auto={
            "th": [
                entry("json3", FAKE + "th-orig.json3?tlang=th"),
                entry("json3", FAKE + "th-orig.json3"),
            ],
            "th-orig": [entry("json3", FAKE + "th-orig.json3", "Thai (Original)")],
        }
    )
    captions = trim_captions(raw)
    assert [o["key"] for o in captions["original"]] == ["th-orig"]
    assert captions["translated"] == []


def test_mixed_key_without_an_orig_twin_is_original() -> None:
    raw = raw_with(
        auto={
            "th": [
                entry("json3", FAKE + "x.json3?tlang=th"),
                entry("json3", FAKE + "th.json3"),
            ],
        }
    )
    captions = trim_captions(raw)
    assert captions["original"] == [
        {"key": "th", "name": "Thai", "json3": FAKE + "th.json3", "vtt": None}
    ]


def test_unusable_protocol_host_and_ext_are_ignored() -> None:
    raw = raw_with(
        subtitles={
            "en": [
                entry("json3", "https://evil.example/en.json3", "English"),
                entry("vtt", FAKE + "en.m3u8", "English", protocol="m3u8_native"),
                entry("ttml", FAKE + "en.ttml", "English"),
            ],
            "de": [
                entry("json3", "https://www.youtube.com/api/timedtext?v=x&fmt=json3", "German"),
                entry("vtt", FAKE + "de.vtt", "German", protocol="https"),
            ],
        }
    )
    assert trim_captions(raw)["owner"] == [
        {
            "key": "de",
            "name": "German",
            "json3": "https://www.youtube.com/api/timedtext?v=x&fmt=json3",
            "vtt": FAKE + "de.vtt",
        }
    ]


def test_keys_that_cannot_form_a_track_id_are_dropped() -> None:
    raw = raw_with(
        subtitles={
            "th/../x": [entry("json3", FAKE + "a.json3")],
            "a" * 65: [entry("json3", FAKE + "b.json3")],
            "th": [entry("json3", FAKE + "th.json3")],
        }
    )
    assert [o["key"] for o in trim_captions(raw)["owner"]] == ["th"]


def test_owner_urls_ignore_tlang_entries() -> None:
    raw = raw_with(
        subtitles={
            "th": [
                entry("json3", FAKE + "th.json3?tlang=en"),
                entry("json3", FAKE + "th.json3"),
                entry("vtt", FAKE + "th.vtt"),
            ]
        }
    )
    assert trim_captions(raw)["owner"] == [
        {"key": "th", "name": "Thai", "json3": FAKE + "th.json3", "vtt": FAKE + "th.vtt"}
    ]


def test_tlang_is_appended_and_other_query_params_are_kept() -> None:
    base = "https://www.youtube.com/api/timedtext?v=x&expire=1&fmt=json3"
    raw = raw_with(
        auto={
            "th-orig": [entry("json3", base)],
            "en": [entry("json3", base + "&tlang=en", "English")],
        }
    )
    track = find_track(trim_probe(raw), "t.en")
    assert track is not None
    assert track.json3 == base + "&tlang=en"
    assert track.vtt is None


def test_orig_key_with_only_tlang_entries_is_not_fetchable() -> None:
    raw = raw_with(
        auto={
            "th-orig": [entry("json3", FAKE + "th-orig.json3?tlang=de")],
            "en": [entry("json3", FAKE + "th-orig.json3?tlang=en", "English")],
        }
    )
    data = trim_probe(raw)
    assert data["captions"]["original"] == []
    assert data["captions"]["translateFrom"] is None
    assert list_tracks(data) == []  # แทร็กแปลไม่มีต้นฉบับให้แปล


def test_raw_without_caption_dicts_gives_empty_groups() -> None:
    assert trim_captions({"id": "x"}) == {
        "owner": [],
        "original": [],
        "translated": [],
        "translateFrom": None,
    }
    assert trim_captions({"subtitles": None, "automatic_captions": "junk"})["owner"] == []


def test_trim_captions_does_not_mutate_input() -> None:
    raw = load("8lpOfyoxcvU")
    before = copy.deepcopy(raw)
    trim_captions(raw)
    assert raw == before


# ---------- original_language ----------


def _audio(language: str, note: str, preference: int | None = None) -> dict:
    fmt = {
        "format_id": f"140-{language}",
        "vcodec": "none",
        "acodec": "mp4a.40.2",
        "language": language,
        "format_note": note,
    }
    if preference is not None:
        fmt["language_preference"] = preference
    return fmt


def _orig(key: str) -> list[dict]:
    return [entry("json3", FAKE + f"{key}.json3", key)]


def test_original_language_prefers_the_audio_original_matching_an_original_key() -> None:
    raw = raw_with(
        auto={"en-US-orig": _orig("en-US-orig"), "th-orig": _orig("th-orig")},
        formats=[
            _audio("en-US", "American English - dubbed-auto"),
            _audio("th", "Thai original (default)", 10),
        ],
    )
    data = trim_probe(raw)
    assert original_language(data) == "th"
    assert data["captions"]["translateFrom"] == "th-orig"


def test_original_language_uses_the_audio_language_alone_when_no_key_matches() -> None:
    raw = raw_with(
        auto={"en-orig": _orig("en-orig")},
        formats=[_audio("pt-BR", "Portuguese original (default)", 10)],
    )
    data = trim_probe(raw)
    assert original_language(data) == "pt"
    # ไม่มีต้นฉบับภาษานั้น -> แปลจากต้นฉบับตัวแรก
    assert data["captions"]["translateFrom"] == "en-orig"


def test_original_language_falls_back_to_the_first_orig_key() -> None:
    raw = raw_with(
        auto={"yue": _orig("yue"), "en-GB-orig": _orig("en-GB-orig")},
        formats=[_audio("", "medium")],
    )
    data = trim_probe(raw)
    assert original_language(data) == "en"
    assert data["captions"]["translateFrom"] == "en-GB-orig"


def test_original_language_of_an_old_row_without_captions() -> None:
    old = trimmed("88o5Sk8_m1Y")
    del old["captions"]
    assert original_language(old) == "th"
    assert original_language({}) is None
    assert list_tracks(old) == []
    assert tracks_payload(old) == {"tracks": []}
    assert find_track(old, "a.th-orig") is None


# ---------- default_track_id ----------


def _t(track_id: str) -> Track:
    prefix, key = track_id.split(".", 1)
    group = {"o": "owner", "a": "original", "t": "translated"}[prefix]
    return Track(track_id, key.removesuffix("-orig"), key, group, "u", None)


def test_default_prefers_owner_in_prefer_language_by_base() -> None:
    tracks = [_t("o.en"), _t("o.th-TH"), _t("a.en-orig")]
    assert default_track_id(tracks, "en") == "o.th-TH"


def test_default_owner_in_original_language_by_base() -> None:
    tracks = [_t("o.de"), _t("o.en-GB"), _t("a.en-orig")]
    assert default_track_id(tracks, "en") == "o.en-GB"


def test_default_original_track_by_base() -> None:
    tracks = [_t("a.en-orig"), _t("a.en-US-orig"), _t("t.th")]
    assert default_track_id(tracks, "en") == "a.en-orig"
    tracks = [_t("a.th-orig"), _t("a.en-US-orig"), _t("t.th")]
    assert default_track_id(tracks, "en") == "a.en-US-orig"


def test_default_first_owner_then_none() -> None:
    assert default_track_id([_t("o.de"), _t("o.fr"), _t("a.en-orig")], "ja") == "o.de"
    assert default_track_id([_t("a.en-orig"), _t("t.th")], "ja") is None
    assert default_track_id([_t("a.en-orig"), _t("t.th")], None) is None
    assert default_track_id([], "th") is None


def test_default_never_returns_a_translated_track() -> None:
    assert default_track_id([_t("t.th"), _t("t.en")], "th") is None


def test_default_original_requires_an_orig_key() -> None:
    assert default_track_id([_t("a.yue")], "yue") is None


# ---------- find_track ----------


@pytest.mark.parametrize("value", ["x.th", "a.", "a.th/../x", "", "a.th-orig ", "o.zz"])
def test_find_track_rejects_malformed_or_unknown_ids(value: str) -> None:
    assert find_track(trimmed("88o5Sk8_m1Y"), value) is None


def test_find_track_needs_the_right_group_prefix() -> None:
    data = trimmed("88o5Sk8_m1Y")
    assert find_track(data, "o.th-orig") is None
    assert find_track(data, "t.th-orig") is None
    assert find_track(data, "a.th-orig") is not None


# ---------- boundaries ----------


def test_tracks_module_respects_core_boundaries() -> None:
    text = (SRC / "core" / "tracks.py").read_text(encoding="utf-8")
    assert not re.search(r"^\s*(from|import)\s+yt_dlp", text, re.MULTILINE)
    assert not re.search(r"yttoolkit\.(api|platform)|from\s+\.\.(api|platform)", text)
