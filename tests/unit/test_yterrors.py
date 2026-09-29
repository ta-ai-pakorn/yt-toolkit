from __future__ import annotations

from pathlib import Path

import pytest

from yttoolkit.core.yterrors import MESSAGES, YtError, classify

ERRORS_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "errors"
FIXTURES = sorted(ERRORS_DIR.glob("*.txt"))
CLASSIFIER_CODES = {
    "E_BOT_CHECK",
    "E_VIDEO_PRIVATE",
    "E_VIDEO_UNAVAILABLE",
    "E_GEO_BLOCKED",
    "E_AGE_RESTRICTED",
    "E_LIVE_NOT_READY",
    "E_NETWORK",
    "E_UNKNOWN",
}


def _expected_code(path: Path) -> str:
    return path.stem.rsplit("-", 1)[0]


@pytest.mark.parametrize("path", FIXTURES, ids=[p.stem for p in FIXTURES])
def test_real_ytdlp_messages(path: Path) -> None:
    assert classify(path.read_text(encoding="utf-8")) == _expected_code(path)


def test_every_code_has_a_fixture() -> None:
    assert {_expected_code(p) for p in FIXTURES} == CLASSIFIER_CODES


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("SIGN IN TO CONFIRM YOU’RE NOT A BOT", "E_BOT_CHECK"),
        ("confirm you're not a bot", "E_BOT_CHECK"),
        ("private VIDEO", "E_VIDEO_PRIVATE"),
        ("This playlist is private.", "E_VIDEO_PRIVATE"),
        ("YouTube is requiring a CAPTCHA challenge", "E_BOT_CHECK"),
        ("A network error has occurred.", "E_NETWORK"),
        ("VIDEO UNAVAILABLE", "E_VIDEO_UNAVAILABLE"),
        (
            "This video has been removed for violating YouTube's policy",
            "E_VIDEO_UNAVAILABLE",
        ),
        (
            "the uploader has NOT MADE THIS VIDEO AVAILABLE IN YOUR COUNTRY",
            "E_GEO_BLOCKED",
        ),
        ("inappropriate for some users", "E_AGE_RESTRICTED"),
        ("status is_upcoming", "E_LIVE_NOT_READY"),
        ("Premieres in 10 hours", "E_LIVE_NOT_READY"),
        ("getaddrinfo failed", "E_NETWORK"),
        ("Read timed out.", "E_NETWORK"),
        ("Connection reset by peer", "E_NETWORK"),
        ("HTTP Error 502: Bad Gateway", "E_NETWORK"),
        ("", "E_UNKNOWN"),
        ("something completely different", "E_UNKNOWN"),
        ("HTTP Error 404: Not Found", "E_UNKNOWN"),
    ],
)
def test_phrases_case_insensitive(message: str, code: str) -> None:
    assert classify(message) == code


def test_specific_code_wins_over_generic_phrases() -> None:
    # ข้อความที่ติดคำกว้าง ๆ (Video unavailable / Unable to download) ต้องได้รหัสที่เจาะจงกว่า
    assert classify("Video unavailable. Blocked it in your country") == "E_GEO_BLOCKED"
    assert (
        classify("Unable to download API page: HTTP Error 429: Too Many Requests")
        == "E_BOT_CHECK"
    )
    assert classify("Video unavailable. This video is private") == "E_VIDEO_PRIVATE"


def test_messages_cover_every_classifier_code() -> None:
    assert CLASSIFIER_CODES <= MESSAGES.keys()
    assert {"E_NO_STORYBOARD", "E_INVALID_INPUT"} <= MESSAGES.keys()


def test_messages_are_verbatim_prd_copy() -> None:
    assert MESSAGES["E_BOT_CHECK"] == "ยูทูปขอให้ยืนยันว่าไม่ใช่บอท พักคิวไว้ 10 นาทีก่อนนะ"
    assert (
        MESSAGES["E_LIVE_NOT_READY"] == "คลิปนี้ยังถ่ายทอดสดอยู่หรือยังไม่เผยแพร่ ลองใหม่หลังจบไลฟ์"
    )
    assert MESSAGES["E_NO_STORYBOARD"] == 'คลิปนี้ไม่มีภาพตัวอย่างแบบเร็ว กด "ขอภาพคม" แทนได้'
    assert MESSAGES["E_NETWORK"] == "เน็ตหลุด ลองใหม่อีกครั้ง"
    assert MESSAGES["E_UNKNOWN"] == "มีบางอย่างผิดพลาด ถ่ายภาพหน้าจอนี้ส่งให้ผู้ดูแล"


def test_messages_match_prd_table() -> None:
    prd = (Path(__file__).resolve().parents[2] / "PRD.md").read_text(encoding="utf-8")
    for code, message in MESSAGES.items():
        if code == "E_NETWORK":
            continue  # รุ่นไม่มีตัวนับครั้ง ดูหมายเหตุใต้ตารางใน PRD ข้อ 7
        assert f"| `{code}` | {message} |" in prd, code
    assert "เน็ตหลุด ลองใหม่อีกครั้ง" in prd


def test_yterror_fields() -> None:
    err = YtError("E_VIDEO_PRIVATE", "ERROR: [youtube] x: Private video")
    assert err.code == "E_VIDEO_PRIVATE"
    assert err.detail == "ERROR: [youtube] x: Private video"
    assert err.message == MESSAGES["E_VIDEO_PRIVATE"]
    assert isinstance(err, Exception)
    assert "E_VIDEO_PRIVATE" in str(err)


def test_yterror_without_detail_uses_thai_message() -> None:
    err = YtError("E_LIVE_NOT_READY")
    assert err.detail == ""
    assert MESSAGES["E_LIVE_NOT_READY"] in str(err)


def test_yterror_unknown_code_falls_back_to_unknown_message() -> None:
    assert YtError("E_SOMETHING_NEW").message == MESSAGES["E_UNKNOWN"]


def test_api_reuses_the_unknown_message() -> None:
    from yttoolkit.api import errors

    assert errors.UNKNOWN_MESSAGE is MESSAGES["E_UNKNOWN"]
