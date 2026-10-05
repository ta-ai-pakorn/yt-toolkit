from __future__ import annotations

from pathlib import Path

import pytest

from yttoolkit.core.yterrors import MESSAGES, MESSAGES_NO_PARAMS, YtError, classify

ERRORS_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "errors"
FIXTURES = sorted(ERRORS_DIR.glob("*.txt"))
CLASSIFIER_CODES = {
    "E_BOT_CHECK",
    "E_VIDEO_PRIVATE",
    "E_VIDEO_UNAVAILABLE",
    "E_GEO_BLOCKED",
    "E_AGE_RESTRICTED",
    "E_LIVE_NOT_READY",
    "E_YT_REFUSED",
    "E_NETWORK",
    "E_UNKNOWN",
}
# รหัสที่เพิ่งมีใน MESSAGES แต่ PRD ข้อ 7 ยังไม่มีแถว (ว่าง = ทุกรหัสมีแถวใน PRD แล้ว)
# M4 (C11) เพิ่มแถว E_JOB_STATE และ E_YT_REFUSED แล้ว รหัสใหม่ที่ยังไม่มีแถวให้ใส่ที่นี่ชั่วคราว
# (มีแถวแล้วจะถูกตรวจทันที และ test_prd_pending_codes_have_no_prd_row เตือนให้ลบออกจากชุด)
PRD_PENDING: set[str] = set()
PRD = Path(__file__).resolve().parents[2] / "PRD.md"


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
        ("HTTP Error 404: Not Found", "E_YT_REFUSED"),
        ("ERROR: unable to download video data: HTTP Error 410: Gone", "E_YT_REFUSED"),
        ("HTTP Error 400: Bad Request", "E_YT_REFUSED"),
        ("... HTTP Error 429: Too Many Requests", "E_BOT_CHECK"),
        ("unable to download video data: HTTP Error 429", "E_BOT_CHECK"),
        ("HTTP Error 4", "E_UNKNOWN"),
    ],
)
def test_phrases_case_insensitive(message: str, code: str) -> None:
    assert classify(message) == code


def test_refused_4xx_is_not_a_network_error() -> None:
    # M2 follow-up / Q2: 4xx ที่ไม่ใช่ 429 ห้ามลองใหม่อัตโนมัติ จึงต้องไม่เป็น E_NETWORK
    assert classify("ERROR: unable to download video data: HTTP Error 403: Forbidden") == "E_YT_REFUSED"
    assert classify("Video unavailable. HTTP Error 404: Not Found") == "E_VIDEO_UNAVAILABLE"
    assert classify("unable to download video data: HTTP Error 503") == "E_NETWORK"


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
    # PRD ข้อ 7 "ตั้งแต่ M4" (มีคิวแล้ว)
    assert MESSAGES["E_BOT_CHECK"] == "ยูทูปขอให้ยืนยันว่าไม่ใช่บอท พักคิวไว้ 10 นาทีก่อนนะ"
    assert (
        MESSAGES["E_LIVE_NOT_READY"] == "คลิปนี้ยังถ่ายทอดสดอยู่หรือยังไม่เผยแพร่ ลองใหม่หลังจบไลฟ์"
    )
    assert MESSAGES["E_NO_STORYBOARD"] == 'คลิปนี้ไม่มีภาพตัวอย่างแบบเร็ว กด "ขอภาพคม" แทนได้'
    assert MESSAGES["E_NETWORK"] == "เน็ตหลุด ลองใหม่อีกครั้ง"
    assert (
        MESSAGES["E_TRANSLATION_BLOCKED"]
        == "ยูทูปยังไม่ให้โหลดซับแปลอัตโนมัติในตอนนี้ เลือกซับภาษาต้นฉบับแทน"
    )
    assert MESSAGES["E_UNKNOWN"] == "มีบางอย่างผิดพลาด ถ่ายภาพหน้าจอนี้ส่งให้ผู้ดูแล"


def test_m4_messages_are_verbatim_c11_copy() -> None:
    assert MESSAGES["E_FFMPEG_MISSING"] == 'ยังไม่มีโปรแกรมแปลงไฟล์ (ffmpeg) กด "โหลด ffmpeg ใหม่" ในหน้าตรวจสุขภาพ'
    assert MESSAGES["E_DISK_FULL"] == "พื้นที่ไม่พอ ต้องมีว่างอย่างน้อย {size}"
    assert MESSAGES["E_OUTPUT_NOT_WRITABLE"] == "บันทึกลงโฟลเดอร์นี้ไม่ได้ ลองเปลี่ยนโฟลเดอร์ในหน้าตั้งค่า"
    assert MESSAGES["E_INTERRUPTED"] == "งานหยุดกลางคันเพราะปิดโปรแกรม"
    assert MESSAGES["E_JOB_STATE"] == "งานนี้เปลี่ยนสถานะไปแล้ว ลองรีเฟรชหน้าเว็บ"
    assert MESSAGES["E_YT_REFUSED"] == "ยูทูปไม่ยอมส่งไฟล์ของคลิปนี้ตอนนี้ ลองใหม่ภายหลัง"
    assert MESSAGES["E_NETWORK"] == "เน็ตหลุด ลองใหม่อีกครั้ง"


def _prd_row(prd: str, code: str) -> str | None:
    prefix = f"| `{code}` | "
    return next((line for line in prd.splitlines() if line.startswith(prefix)), None)


def test_messages_match_prd_table() -> None:
    prd = PRD.read_text(encoding="utf-8")
    for code, message in MESSAGES.items():
        if code == "E_NETWORK":
            continue  # รุ่นไม่มีตัวนับครั้ง ดูหมายเหตุใต้ตารางใน PRD ข้อ 7
        if code in PRD_PENDING and _prd_row(prd, code) is None:
            continue
        row = _prd_row(prd, code)
        assert row is not None, code
        # PRD เขียนช่องว่างของข้อความเป็น <ขนาด> และข้อความ "ตั้งแต่ M4" อยู่ในอัญประกาศในช่องหมายเหตุ
        text = message.replace("{size}", "<ขนาด>")
        assert row.startswith(f"| `{code}` | {text} |") or f'"{text}"' in row, code
    assert "เน็ตหลุด ลองใหม่อีกครั้ง" in prd


def test_prd_pending_codes_are_known_messages() -> None:
    assert PRD_PENDING <= MESSAGES.keys()


def test_prd_pending_codes_have_no_prd_row() -> None:
    # PRD มีแถวของรหัสนี้แล้ว = ลบรหัสออกจาก PRD_PENDING (แถวถูกตรวจใน test_messages_match_prd_table แล้ว)
    prd = PRD.read_text(encoding="utf-8")
    for code in sorted(PRD_PENDING):
        assert _prd_row(prd, code) is None, f"{code} มีแถวใน PRD แล้ว ลบออกจาก PRD_PENDING"


def test_disk_full_without_size_never_shows_the_placeholder() -> None:
    # files.py / media.py โยน E_DISK_FULL โดยไม่รู้ขนาด: ใช้ข้อความที่ไม่มีขนาด ห้ามโชว์ "{size}"
    expected = "พื้นที่ไม่พอ ลบไฟล์หรือเลือกโฟลเดอร์อื่นในหน้าตั้งค่า"
    assert MESSAGES_NO_PARAMS["E_DISK_FULL"] == expected
    for err in (
        YtError("E_DISK_FULL"),
        YtError("E_DISK_FULL", "No space left on device"),
        YtError("E_DISK_FULL", params={}),
        YtError("E_DISK_FULL", params={"other": "x"}),
    ):
        assert err.message == expected
        assert "{" not in str(err)
    assert YtError("E_DISK_FULL", params={"size": "120 MB"}).message == "พื้นที่ไม่พอ ต้องมีว่างอย่างน้อย 120 MB"


def test_every_template_has_a_no_params_message() -> None:
    templated = {code for code, text in MESSAGES.items() if "{" in text}
    assert templated == MESSAGES_NO_PARAMS.keys()
    assert all("{" not in text for text in MESSAGES_NO_PARAMS.values())


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


def test_yterror_params_fill_the_message() -> None:
    err = YtError("E_DISK_FULL", "x", params={"size": "3.2 GB"})
    assert err.message == "พื้นที่ไม่พอ ต้องมีว่างอย่างน้อย 3.2 GB"
    assert err.detail == "x" and err.params == {"size": "3.2 GB"}
    assert "3.2 GB" in str(YtError("E_DISK_FULL", params={"size": "3.2 GB"}))


def test_yterror_params_on_a_plain_message_are_ignored() -> None:
    assert YtError("E_DISK_FULL").params is None
    assert YtError("E_NETWORK", params={"size": "1 MB"}).message == MESSAGES["E_NETWORK"]
    # รูปแบบเสียไม่ทำให้ error พังซ้อน
    assert YtError("E_SOMETHING_NEW", params={"size": "1"}).message == MESSAGES["E_UNKNOWN"]


def test_yterror_unknown_code_falls_back_to_unknown_message() -> None:
    assert YtError("E_SOMETHING_NEW").message == MESSAGES["E_UNKNOWN"]


def test_api_reuses_the_unknown_message() -> None:
    from yttoolkit.api import errors

    assert errors.UNKNOWN_MESSAGE is MESSAGES["E_UNKNOWN"]


def test_m5b_messages_are_verbatim_spec_copy() -> None:
    assert MESSAGES["E_NO_SHARP_FRAMES"] == 'ภาพคมของคลิปนี้ถูกล้างไปแล้ว กด "ขอภาพคม" ใหม่ได้'
