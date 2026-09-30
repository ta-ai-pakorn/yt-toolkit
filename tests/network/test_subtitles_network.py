"""ซับจากยูทูปจริง (M3): แทร็กของคลิปจริงตรงกับที่ fixture ปลอมคาดไว้ และ token ผ่าน AC-SUB-03/04

รันเองด้วย: uv run pytest -m network -q tests/network/test_subtitles_network.py -s
id ของคลิปอยู่ใน tests/network_videos.toml ([subtitles]) เทสอ่านยูทูปสด ๆ แล้วเก็บแค่ใน temp ไม่มีอะไรลงรีโป
ยูทูปตอบ 429 หรือขอยืนยันว่าไม่ใช่บอท (E_BOT_CHECK) = เทสตก ให้รายงานผล ห้ามแก้เทสให้หลวมลง
"""

from __future__ import annotations

import time
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from yttoolkit.core import thai_fallback as tf
from yttoolkit.core.db import Database
from yttoolkit.core.extractor import YtDlpExtractor, ytdlp_version
from yttoolkit.core.srt_builder import PRESETS, Cue, Token, build_cues
from yttoolkit.core.subparse import ParsedTrack, parse_json3, parse_vtt
from yttoolkit.core.subtitles import SubtitleService
from yttoolkit.core.tracks import find_track
from yttoolkit.core.videos import VideoService

pytestmark = pytest.mark.network

_TOML = Path(__file__).resolve().parents[1] / "network_videos.toml"
CLIPS: dict[str, str] = tomllib.loads(_TOML.read_text(encoding="utf-8"))["subtitles"]

THAI_ASR = CLIPS["thai_asr"]
MULTI_AUDIO = CLIPS["multi_audio_orig"]
OWNER_CHAPTERS = CLIPS["owner_subs_chapters"]
OWNER_THAI = CLIPS["owner_thai"]
NO_SUBS = CLIPS["no_subs"]


@dataclass
class Env:
    extractor: YtDlpExtractor
    videos: VideoService
    subs: SubtitleService
    payloads: dict[str, dict] = field(default_factory=dict)
    timings: list[str] = field(default_factory=list)


@pytest.fixture(scope="module")
def env(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Env]:
    root = tmp_path_factory.mktemp("subs-network")
    # import yt_dlp ก่อน เวลา import จะได้ไม่ปนเข้าไปในเวลา probe ที่วัด
    ytdlp_version()
    with pytest.MonkeyPatch.context() as mp:
        # PyThaiNLP สร้างโฟลเดอร์ข้อมูลตอนใช้ครั้งแรก เก็บไว้ใน temp ไม่ใช่ ~/
        mp.setenv(tf.DATA_ENV, str(root / "pythainlp-data"))
        db = Database(root / "app.db")
        db.migrate()
        extractor = YtDlpExtractor()
        videos = VideoService(db, extractor)
        state = Env(extractor, videos, SubtitleService(videos, extractor.fetch_subtitle, root / "cache"))
        try:
            yield state
        finally:
            extractor.close()
            db.close()
            # ASCII ล้วน: คอนโซล Windows ภาษาไทย (cp874) พิมพ์ตัว "·" ไม่ได้ (เคยทำให้ teardown พัง)
            print("\n[timings] " + ", ".join(state.timings))


def tracks_of(env: Env, video_id: str) -> dict:
    """probe สด (refresh) ครั้งเดียวต่อคลิป แล้วคืน payload ของ /subtitles (จับเวลา probe ไว้)"""
    if video_id not in env.payloads:
        start = time.monotonic()
        env.videos.get(video_id, refresh=True)
        took = time.monotonic() - start
        env.payloads[video_id] = env.subs.tracks(video_id)
        env.timings.append(f"probe {video_id} {took:.2f}s")
        print(f"probe {video_id}: {took:.2f}s")
    return env.payloads[video_id]


def ids(payload: dict, group: str) -> list[str]:
    return [t["id"] for t in payload["tracks"] if t["group"] == group]


# ---------- แทร็กของแต่ละคลิป (ค่าเดียวกับเทส fixture ปลอมใน tests/unit/test_tracks.py) ----------


def test_thai_asr_clip_defaults_to_th_orig(env: Env) -> None:
    payload = tracks_of(env, THAI_ASR)
    assert ids(payload, "owner") == []
    assert ids(payload, "original") == ["a.th-orig"]
    assert "t.en" in ids(payload, "translated")
    assert payload.get("defaultTrackId") == "a.th-orig"


def test_multi_audio_clip_has_two_originals_and_thai_audio_wins(env: Env) -> None:
    payload = tracks_of(env, MULTI_AUDIO)
    assert ids(payload, "owner") == []
    assert sorted(ids(payload, "original")) == ["a.en-US-orig", "a.th-orig"]
    assert payload.get("defaultTrackId") == "a.th-orig"


def test_owner_subs_clip_with_chapters_and_description(env: Env) -> None:
    payload = tracks_of(env, OWNER_CHAPTERS)
    # auto en/de ของคลิปนี้เป็นแค่ HLS m3u8 ซึ่งต้องถูกทิ้ง
    assert sorted(ids(payload, "owner")) == ["o.de", "o.en"]
    assert ids(payload, "original") == []
    assert ids(payload, "translated") == []
    assert payload.get("defaultTrackId") == "o.en"
    info = env.videos.get(OWNER_CHAPTERS)
    assert len(info["chapters"]) == 3
    assert info.get("description", "").strip()


def test_owner_thai_subtitles_win_over_the_english_original(env: Env) -> None:
    payload = tracks_of(env, OWNER_THAI)
    assert "o.th" in ids(payload, "owner")
    assert "a.en-orig" in ids(payload, "original")
    assert payload.get("defaultTrackId") == "o.th"  # Q8 = ก


def test_clip_without_subtitles_has_no_tracks(env: Env) -> None:
    payload = tracks_of(env, NO_SUBS)
    assert payload == {"tracks": []}


# ---------- token ของซับไทยอัตโนมัติ: AC-SUB-03/04 ที่ preset กลาง ----------


def _nospace(text: str) -> str:
    return text.replace(" ", "")


def _assert_tokens_are_clean(tokens: tuple[Token, ...]) -> None:
    assert tokens
    for i, tok in enumerate(tokens):
        # บล็อก aAppend ที่มีแค่ "\n" ต้องไม่หลุดเข้ามาเป็น token (AC-SUB-03)
        assert tok.t.strip(" "), f"token {i} is blank: {tok!r}"
        assert "\n" not in tok.t, f"token {i} has a line break: {tok!r}"
        assert tok.e >= tok.s, f"token {i} ends before it starts: {tok!r}"
        if i + 1 < len(tokens):
            assert tokens[i + 1].s >= tok.s and tok.e <= tokens[i + 1].s, f"tokens {i}/{i + 1} overlap"


def _assert_no_repeated_cues(cues: list[Cue]) -> None:
    """AC-SUB-03: ไม่มีซับสองอันติดกันที่ข้อความเหมือนกัน และไม่ซ้อนแบบ rolling caption"""
    for i in range(1, len(cues)):
        prev, cue = " ".join(cues[i - 1].lines), " ".join(cues[i].lines)
        assert cue != prev, f"cue {i + 1} repeats cue {i}: {cue!r}"
        assert prev not in cues[i].lines, f"cue {i + 1} contains the whole previous cue: {cue!r}"


def _assert_cues_cut_at_token_boundaries(tokens: tuple[Token, ...], cues: list[Cue]) -> None:
    """AC-SUB-04: ต่อซับกลับได้ข้อความเดิมทุกตัวอักษร และทุกซับคือ token ทั้งตัวติดกัน"""
    assert "".join(_nospace("".join(c.lines)) for c in cues) == "".join(_nospace(t.t) for t in tokens)
    pos = 0
    for cue in cues:
        want = _nospace("".join(cue.lines))
        got = ""
        while len(got) < len(want):
            got += _nospace(tokens[pos].t)
            pos += 1
        assert got == want, f"cue is not a run of whole tokens: {cue.lines!r}"
    assert pos == len(tokens)


def _check_medium(parsed: ParsedTrack) -> list[Cue]:
    _assert_tokens_are_clean(parsed.tokens)
    cues = build_cues(parsed.tokens, PRESETS["medium"])
    assert cues
    _assert_no_repeated_cues(cues)
    _assert_cues_cut_at_token_boundaries(parsed.tokens, cues)
    return cues


def test_thai_asr_json3_tokens_pass_ac_sub_03_04(env: Env) -> None:
    tracks_of(env, THAI_ASR)
    start = time.monotonic()
    parsed = env.subs.tokens(THAI_ASR, "a.th-orig")
    took = time.monotonic() - start
    env.timings.append(f"tokens {THAI_ASR} a.th-orig {took:.2f}s")
    assert parsed.source == "json3"
    assert parsed.has_word_timing
    cues = _check_medium(parsed)
    print(f"tokens {THAI_ASR} a.th-orig (json3): {took:.2f}s, {len(parsed.tokens)} tokens, {len(cues)} cues at medium")


def test_thai_asr_forced_vtt_passes_the_same_checks(env: Env) -> None:
    tracks_of(env, THAI_ASR)
    track = find_track(env.videos.raw(THAI_ASR), "a.th-orig")
    assert track is not None and track.vtt
    start = time.monotonic()
    parsed = parse_vtt(env.extractor.fetch_subtitle(track.vtt))
    took = time.monotonic() - start
    env.timings.append(f"vtt {THAI_ASR} a.th-orig {took:.2f}s")
    assert parsed.source == "vtt"
    cues = _check_medium(parsed)
    json3 = env.subs.tokens(THAI_ASR, "a.th-orig").tokens
    same = "".join(t.t for t in json3) == "".join(t.t for t in parsed.tokens)
    print(
        f"vtt {THAI_ASR} a.th-orig: {took:.2f}s, {len(parsed.tokens)} tokens "
        f"(json3 {len(json3)}, same text: {same}), {len(cues)} cues at medium"
    )


# ---------- ซับแปลที่สร้างลิงก์เองด้วย tlang (เรื่องที่แผน M3 บอกว่า "ยังไม่ได้ยืนยัน") ----------


def test_translated_url_built_with_tlang_returns_english(env: Env) -> None:
    tracks_of(env, THAI_ASR)
    track = find_track(env.videos.raw(THAI_ASR), "t.en")
    assert track is not None and track.json3
    assert "tlang=en" in track.json3
    start = time.monotonic()
    parsed = parse_json3(env.extractor.fetch_subtitle(track.json3))
    took = time.monotonic() - start
    env.timings.append(f"tlang=en {took:.2f}s")
    text = "".join(t.t for t in parsed.tokens)
    chars = [c for c in text if not c.isspace()]
    ascii_letters = sum(1 for c in chars if c.isascii() and c.isalpha())
    ratio = ascii_letters / len(chars) if chars else 0.0
    print(f"tlang=en {THAI_ASR}: {took:.2f}s, {len(parsed.tokens)} tokens, ASCII letters {ratio:.0%}")
    assert chars
    assert ratio >= 0.5, f"ASCII letters only {ratio:.0%}: {text[:120]!r}"
