"""ไฟล์ซับที่สร้างจากข้อมูลจริงต้องตรงกับ golden ทุกไบต์ (PRD AC-SUB-06, AC-SUB-08)

golden ทุกไฟล์ (tests/fixtures/subs/golden/*) และ token ที่ parser ให้ (tests/fixtures/subs/tokens/*.json)
สร้างได้ทางเดียวคือรัน `YT_UPDATE_GOLDEN=1 uv run pytest tests/unit/test_srt_golden.py`
ฝั่งเว็บ (web/src/lib/srt-parity.test.ts) อ่านไฟล์ชุดเดียวกันไปเทียบกับ srt-builder.ts จึงห้ามแก้ golden เพื่อให้เทสผ่าน

หมายเหตุ: ไฟล์ golden เก็บ CRLF ตามจริง จึงเขียนด้วย write_bytes / อ่านด้วย read_bytes เท่านั้น (โหมดข้อความบน Windows จะแปลงบรรทัด)
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from yttoolkit.core import thai_fallback as tf
from yttoolkit.core.srt_builder import (
    PRESETS,
    SubOptions,
    Token,
    build_cues,
    cue_text,
    display_len,
    is_punct_only,
    to_md,
    to_srt,
    to_txt,
)
from yttoolkit.core.subparse import ParsedTrack, parse_json3, parse_vtt

SUBS = Path(__file__).resolve().parents[1] / "fixtures" / "subs"
TOKENS_DIR = SUBS / "tokens"
GOLDEN_DIR = SUBS / "golden"
UPDATE = os.environ.get("YT_UPDATE_GOLDEN") == "1"
_REGENERATED = False  # True เมื่อรอบนี้เขียน golden ใหม่ ทำให้เทสสุดท้ายของไฟล์ล้มเหลวโดยตั้งใจ

# jNQXAC9IVRw มี chapter จริง 3 อัน (probe/jNQXAC9IVRw.json) ใช้กับ en-owner ตัวเดียว
_JNQ_CHAPTERS = [
    {"startMs": 0, "title": "Intro"},
    {"startMs": 5000, "title": "The cool thing"},
    {"startMs": 17000, "title": "End"},
]

# ชื่อ golden -> (video id, ไฟล์ fixture, ตัว parse, chapters ของ .md)
CASES: dict[str, tuple[str, str, str, list[dict]]] = {
    "th-asr": ("88o5Sk8_m1Y", "th-orig.json3", "json3", []),
    "th-vtt": ("88o5Sk8_m1Y", "th-orig.vtt", "vtt", []),
    "en-asr": ("8lpOfyoxcvU", "en-US-orig.json3", "json3", []),
    "en-owner": ("jNQXAC9IVRw", "en.json3", "json3", _JNQ_CHAPTERS),
    # iG9CE55wbtY (ซับ TED) ถูกแทนด้วย fixture ที่เขียนเอง OWNERTHSUB1 ตามคำตอบ Q9 = ข
    "th-owner": ("OWNERTHSUB1", "th.json3", "json3", []),
}
# preset "ทีละคำ" (word, เพิ่ม 2026-10-01) มี golden เฉพาะซับอัตโนมัติที่มีเวลาระดับคำ ไทยและอังกฤษ
WORD_NAMES = ("th-asr", "en-asr")
CUSTOM_NAME = "th-asr.custom-tokens.srt"
CUSTOM_OPTS = SubOptions(max_chars=30, lines=2, min_ms=1000, max_ms=6000, mode="tokens", tokens_per_cue=4)


@pytest.fixture(autouse=True)
def _keep_data_dir_out_of_home(tmp_path, monkeypatch):
    # PyThaiNLP สร้างโฟลเดอร์ข้อมูลตอนใช้ครั้งแรก เก็บไว้นอก ~/
    monkeypatch.setenv(tf.DATA_ENV, str(tmp_path / "pythainlp-data"))


def parse_case(name: str) -> ParsedTrack:
    video_id, filename, kind, _ = CASES[name]
    data = (SUBS / video_id / filename).read_bytes()
    return parse_json3(data) if kind == "json3" else parse_vtt(data)


def md_meta(name: str) -> dict:
    video_id, _, _, chapters = CASES[name]
    return {"title": f"Golden {name}", "videoId": video_id, "chapters": chapters}


def tokens_doc(name: str) -> dict:
    parsed = parse_case(name)
    return {
        "tokens": [{"t": t.t, "s": t.s, "e": t.e} for t in parsed.tokens],
        "hasWordTiming": parsed.has_word_timing,
        "md": md_meta(name),
    }


def outputs(name: str, tokens: list[Token], md: dict) -> dict[str, str]:
    """ชื่อไฟล์ golden -> ข้อความที่ต้องได้ (ครบทุกไฟล์ของ name นี้)"""
    out: dict[str, str] = {}
    for preset, opts in PRESETS.items():
        if preset == "word" and name not in WORD_NAMES:
            continue
        out[f"{name}.{preset}.srt"] = to_srt(build_cues(tokens, opts))
    out[f"{name}.txt"] = to_txt(tokens)
    chapters = [(c["startMs"], c["title"]) for c in md["chapters"]]
    out[f"{name}.md"] = to_md(tokens, title=md["title"], video_id=md["videoId"], chapters=chapters)
    if name == "th-asr":
        out[CUSTOM_NAME] = to_srt(build_cues(tokens, CUSTOM_OPTS))
    return out


def _token_file(name: str) -> Path:
    return TOKENS_DIR / f"{name}.json"


def _write_json(path: Path, doc: dict) -> None:
    text = json.dumps(doc, ensure_ascii=False, indent=1) + "\n"
    path.write_bytes(text.encode("utf-8"))


@pytest.fixture(scope="module", autouse=True)
def _update_goldens(tmp_path_factory):
    """YT_UPDATE_GOLDEN=1: เขียน token และ golden ใหม่ก่อนเทสรัน ห้ามใช้เมื่อมี CI และรอบนั้นจบแดงเสมอ (ดู test_zz_...)"""
    global _REGENERATED
    if not UPDATE:
        yield
        return
    if os.environ.get("CI"):
        pytest.fail("YT_UPDATE_GOLDEN=1 is refused when CI is set: goldens are never regenerated in CI", pytrace=False)
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv(tf.DATA_ENV, str(tmp_path_factory.mktemp("pythainlp-data")))
        TOKENS_DIR.mkdir(parents=True, exist_ok=True)
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        for name in CASES:
            doc = tokens_doc(name)
            _write_json(_token_file(name), doc)
            tokens = [Token(**t) for t in doc["tokens"]]
            for filename, text in outputs(name, tokens, doc["md"]).items():
                (GOLDEN_DIR / filename).write_bytes(text.encode("utf-8"))
        _REGENERATED = True
        yield


@pytest.mark.parametrize("name", CASES)
def test_parser_tokens_match_stored_tokens(name):
    path = _token_file(name)
    assert path.is_file(), f"{path.name} is missing: run with YT_UPDATE_GOLDEN=1"
    stored = json.loads(path.read_bytes().decode("utf-8"))
    assert tokens_doc(name) == stored


@pytest.mark.parametrize("name", CASES)
def test_outputs_match_golden_bytes(name):
    stored = json.loads(_token_file(name).read_bytes().decode("utf-8"))
    tokens = [Token(**t) for t in stored["tokens"]]
    produced = outputs(name, tokens, stored["md"])
    assert len(produced) >= 5
    for filename, text in produced.items():
        path = GOLDEN_DIR / filename
        assert path.is_file(), f"{filename} is missing: run with YT_UPDATE_GOLDEN=1"
        assert path.read_bytes() == text.encode("utf-8"), filename


def test_md_meta_is_the_single_source():
    for name in CASES:
        stored = json.loads(_token_file(name).read_bytes().decode("utf-8"))
        assert stored["md"] == md_meta(name)
    assert md_meta("en-owner")["chapters"] == _JNQ_CHAPTERS
    assert all(md_meta(n)["chapters"] == [] for n in CASES if n != "en-owner")


def test_custom_options_differ_from_presets():
    # ถ้า custom-tokens เท่ากับ preset ใดก็ตาม golden นี้ก็ไม่ได้ทดสอบอะไรเพิ่ม
    tokens = list(parse_case("th-asr").tokens)
    custom = to_srt(build_cues(tokens, CUSTOM_OPTS))
    assert all(custom != to_srt(build_cues(tokens, opts)) for opts in PRESETS.values())


def test_golden_dir_holds_exactly_the_expected_files():
    # 5 ชื่อ x (short/medium/long + txt + md) + word ของ th-asr, en-asr + custom-tokens = 28 ไฟล์
    expected = {CUSTOM_NAME}
    for name in CASES:
        expected |= {f"{name}.{p}.srt" for p in ("short", "medium", "long")} | {f"{name}.txt", f"{name}.md"}
    expected |= {f"{name}.word.srt" for name in WORD_NAMES}
    assert len(expected) == 28
    assert {p.name for p in GOLDEN_DIR.iterdir()} == expected


def test_word_goldens_have_one_token_per_cue():
    for name in WORD_NAMES:
        stored = json.loads(_token_file(name).read_bytes().decode("utf-8"))
        tokens = [Token(**t) for t in stored["tokens"]]
        cues = build_cues(tokens, PRESETS["word"])
        # owner round 3: เครื่องหมายล้วน ("." "," ...) ไม่นับเป็นคำ เกาะคำข้างเคียง จึงได้ไม่เกิน 1 คำต่อซับ
        # fix round 2 (review #1): ซับที่มีแต่เครื่องหมายเกิดได้เฉพาะเมื่อเกาะแล้วเกินเวลานานสุดหรือตัวอักษรสูงสุด
        # (en-asr มี 2 ซับ: "." ที่ยาวราว 6 และ 3 วินาที)
        words = [t for t in tokens if not is_punct_only(t)]
        opts = PRESETS["word"]
        alone = 0
        for k, c in enumerate(cues):
            text = " ".join(c.lines)
            assert display_len(text) > 0
            if is_punct_only(Token(text, 0, 0)):
                alone += 1
                prev = cues[k - 1]
                assert c.end_ms - prev.start_ms > opts.max_ms or display_len(prev.lines[-1] + text) > opts.max_chars
        assert len(cues) == len(words) + alone
        assert alone <= 2
        # ต่อข้อความทุกซับกลับได้ทั้งแทร็ก (ไม่มีอะไรหาย)
        assert " ".join(" ".join(c.lines) for c in cues).replace(" ", "") == cue_text(tokens).replace(" ", "")


def test_zz_goldens_were_not_regenerated():
    """ต้องอยู่ท้ายไฟล์: รอบที่เขียน golden เองเทสอื่นผ่านเพราะเทียบกับไฟล์ที่เพิ่งเขียน จึงต้องจบแดงเสมอ"""
    assert not _REGENERATED, "goldens regenerated, review git diff and re-run without YT_UPDATE_GOLDEN"
