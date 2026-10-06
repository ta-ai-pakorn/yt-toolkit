"""บัญชียูทูปชั่วคราวใน core/extractor.py (M5 รอบ C spec 2.1, 2.3): ตัวอ่าน cookies.txt และการต่อ jar เข้า yt-dlp

ไม่ต่อเน็ต ไม่ import yt_dlp ตรง ๆ (YoutubeDL จริงสร้างผ่าน YtDlpExtractor._ydl เท่านั้น)
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from yttoolkit.core.account_scope import current_jar, signed_in
from yttoolkit.core.download import DownloadChoice, DownloadHooks
from yttoolkit.core.extractor import (
    ACCOUNT_FORBIDDEN_OPTS,
    FakeExtractor,
    YtDlpExtractor,
    parse_account_cookies,
    visitor_session,
)
from yttoolkit.core.yterrors import YtError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CANARY = "canary-acc-41d2"
HEADER = "# Netscape HTTP Cookie File\n"


def _line(domain: str, name: str, value: str = CANARY, *, flag: str | None = None, expires: str = "1999999999") -> str:
    flag = flag if flag is not None else ("TRUE" if domain.startswith(".") else "FALSE")
    return "\t".join((domain, flag, "/", "TRUE", expires, name, value))


GOOD = HEADER + "\n".join(
    (
        _line(".youtube.com", "SAPISID"),
        "#HttpOnly_" + _line(".youtube.com", "__Secure-3PSID"),
        _line(".google.com", "SID"),
        _line("accounts.google.com", "LSID"),
        _line(".example.com", "TRACKER"),
        _line(".youtube.com.evil.test", "SAPISID"),
        "",
        "# a comment line",
    )
) + "\n"


def _names(jar: Any) -> set[tuple[str, str]]:
    return {(c.domain, c.name) for c in jar}


# ---------- parse_account_cookies ----------


def test_keeps_only_youtube_and_google_domains() -> None:
    jar = parse_account_cookies(GOOD)
    assert _names(jar) == {
        (".youtube.com", "SAPISID"),
        (".youtube.com", "__Secure-3PSID"),
        (".google.com", "SID"),
        ("accounts.google.com", "LSID"),
    }


def test_bom_crlf_and_no_header_are_fine() -> None:
    text = "﻿" + _line(".youtube.com", "LOGIN_INFO") + "\r\n" + _line("www.youtube.com", "PREF") + "\r\n"
    assert _names(parse_account_cookies(text)) == {(".youtube.com", "LOGIN_INFO"), ("www.youtube.com", "PREF")}


def test_a_wrong_domain_flag_is_fixed_not_fatal() -> None:
    jar = parse_account_cookies(_line(".youtube.com", "SAPISID", flag="FALSE") + "\n")
    assert _names(jar) == {(".youtube.com", "SAPISID")}


@pytest.mark.parametrize(
    "text",
    [
        _line(".youtube.com", "PREF") + "\n",  # ไม่มีคุกกี้เข้าสู่ระบบ
        _line(".google.com", "SAPISID") + "\n",  # คุกกี้เข้าสู่ระบบของ google.com อย่างเดียวไม่พอ
        "",
        HEADER,
    ],
)
def test_no_youtube_sign_in_cookie_is_invalid(text: str) -> None:
    with pytest.raises(YtError) as info:
        parse_account_cookies(text)
    assert (info.value.code, info.value.detail) == ("E_COOKIES_INVALID", "no YouTube sign-in cookie")


@pytest.mark.parametrize(
    ("text", "detail"),
    [
        (HEADER + f"garbage {CANARY}\n", "line 2: expected 7 tab-separated fields"),
        (HEADER + _line(".youtube.com", "SAPISID") + f"\t{CANARY}\n", "line 2: expected 7 tab-separated fields"),
        ('[{"domain": ".youtube.com", "value": "' + CANARY + '"}]', "line 1: expected 7 tab-separated fields"),
        (HEADER + _line(".youtube.com", "SAPISID", expires=f"x{CANARY}") + "\n", "line 2: expiry is not a number"),
    ],
)
def test_garbage_is_invalid_and_never_echoes_the_line(text: str, detail: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(YtError) as info:
        parse_account_cookies(text)
    assert (info.value.code, info.value.detail) == ("E_COOKIES_INVALID", detail)
    assert info.value.__cause__ is None
    assert CANARY not in str(info.value)
    out = capsys.readouterr()
    assert CANARY not in out.out and CANARY not in out.err  # ตัวอ่านของ yt-dlp ไม่ได้พิมพ์บรรทัดที่เสีย


def test_parsing_writes_no_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    parse_account_cookies(GOOD)
    assert list(tmp_path.iterdir()) == []


# ---------- _ydl(with_account=...) กับ YoutubeDL จริง (สัญญา API ภายในของ yt-dlp) ----------


def test_attach_account_on_a_real_youtubedl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """เหมือน test_attach_session_on_a_real_youtubedl: ต้องผ่านทุกครั้งที่อัปเดต yt-dlp ไม่ต่อเน็ต"""
    monkeypatch.chdir(tmp_path)
    jar = parse_account_cookies(GOOD)
    session = visitor_session(tmp_path / "data")
    ext = YtDlpExtractor(session=session)
    with ext._ydl({"quiet": True, "no_warnings": True, "cookiefile": "x.txt"}, with_session=True, with_account=jar) as ydl:
        assert ydl.cookiejar is jar
        assert all(handler.cookiejar is jar for handler in ydl._request_director.handlers.values())
        assert "cookiefile" not in ydl.params or ydl.params["cookiefile"] is None
        assert not any(ydl.params.get(key) for key in ACCOUNT_FORBIDDEN_OPTS)
        assert CANARY in (ydl.cookiejar.get_cookie_header("https://www.youtube.com/watch?v=x") or "")
        ydl._load_cookies(f"ROTATED={CANARY}; Domain=.youtube.com", autoscope=False)  # ยูทูปหมุนคุกกี้ระหว่างงาน
        ydl.save_cookies()
    assert list(tmp_path.iterdir()) == []  # ไม่มี x.txt ไม่มีไฟล์เซสชันผู้ชม ไม่มีไฟล์อื่น
    assert "ROTATED" in {c.name for c in jar}  # คุกกี้ใหม่อยู่ใน jar ก้อนเดิมในหน่วยความจำ


@pytest.mark.parametrize("key", sorted(ACCOUNT_FORBIDDEN_OPTS))
def test_traffic_printing_options_are_refused_with_an_account(key: str) -> None:
    jar = parse_account_cookies(GOOD)
    with pytest.raises(ValueError):
        with YtDlpExtractor()._ydl({"quiet": True, key: True}, with_account=jar):
            pass


# ---------- ทุกจุดที่ใช้เซสชันผู้ชมส่งบัญชีของขอบเขตไปที่ _ydl ----------


class FakeYDL:
    def __init__(self) -> None:
        self.params: dict = {}

    def extract_info(self, url: str, download: bool = False) -> dict:
        return {"id": "aqz-KE-bpKQ", "live_status": "not_live", "formats": []}

    def sanitize_info(self, info: dict, remove_private_keys: bool = False) -> dict:
        return dict(info)

    def process_ie_result(self, info: dict, download: bool = True) -> dict:
        raise YtError("E_NETWORK", "fake: stop before downloading")

    def urlopen(self, request: Any) -> Any:
        class Response:
            def __enter__(self) -> Response:
                return self

            def __exit__(self, *exc: object) -> None:
                return None

            def read(self) -> bytes:
                return b"{}"

        return Response()


def _recording(ext: YtDlpExtractor, monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    seen: list[Any] = []

    @contextmanager
    def fake_ydl(opts: dict, *, with_session: bool = False, with_account: Any | None = None):
        seen.append(with_account)
        yield FakeYDL()

    monkeypatch.setattr(ext, "_ydl", fake_ydl)
    return seen


def _hooks() -> DownloadHooks:
    return DownloadHooks(on_stage=lambda s: None, on_progress=lambda *a: None, is_cancelled=lambda: False,
                         ffmpeg_location=None)  # fmt: skip


def _choose(info: dict) -> DownloadChoice:
    return DownloadChoice("bv*+ba", True, None, (), None)


def test_every_signed_in_call_site_passes_the_scope_jar(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ext = YtDlpExtractor()
    seen = _recording(ext, monkeypatch)
    jar = object()
    with signed_in(jar):
        ext.probe("aqz-KE-bpKQ")
        ext.fetch_subtitle("https://www.youtube.com/api/timedtext?v=x")
        with pytest.raises(YtError):
            ext.download("aqz-KE-bpKQ", _choose, tmp_path, _hooks())
        with pytest.raises(YtError) as info:
            ext.fetch_frame_piece("aqz-KE-bpKQ", 1000, None, tmp_path / "piece.mp4")
        assert info.value.code == "E_CAPTURE_UNSUPPORTED"  # ไม่มี format ให้เลือก (FakeYDL) แต่ _ydl ได้ jar แล้ว
    assert seen == [jar] * 5  # probe, ซับ, ดึงข้อมูลก่อนโหลด, โหลด, ถ่ายภาพคม


def test_without_a_scope_nothing_is_signed_in(monkeypatch: pytest.MonkeyPatch) -> None:
    ext = YtDlpExtractor()
    seen = _recording(ext, monkeypatch)
    ext.probe("aqz-KE-bpKQ")
    assert seen == [None]


def test_playlists_never_use_the_account(monkeypatch: pytest.MonkeyPatch) -> None:
    ext = YtDlpExtractor()
    seen = _recording(ext, monkeypatch)
    with signed_in(object()):
        ext.playlist("PLfakeplaylist250", 10)
    assert seen == [None]


def test_scope_resets_after_the_block() -> None:
    jar = object()
    with signed_in(jar):
        assert current_jar() is jar
    assert current_jar() is None
    with pytest.raises(ValueError):
        with signed_in(None):
            pass


# ---------- FakeExtractor: คลิปที่ต้องใช้บัญชี ----------


@pytest.mark.parametrize(("video_id", "code"), [("ACCOUNTAGE1", "E_AGE_RESTRICTED"), ("ACCOUNTMEM1", "E_VIDEO_PRIVATE")])
def test_fake_clip_needs_the_account(video_id: str, code: str) -> None:
    fake = FakeExtractor(FIXTURES)
    with pytest.raises(YtError) as info:
        fake.probe(video_id)
    assert info.value.code == code
    with signed_in(object()):
        info_dict = fake.probe(video_id)
    assert info_dict["id"] == video_id


def test_fake_private_clip_stays_private_with_the_account() -> None:
    fake = FakeExtractor(FIXTURES)
    with signed_in(object()), pytest.raises(YtError) as info:
        fake.probe(FakeExtractor.PRIVATE_ID)
    assert info.value.code == "E_VIDEO_PRIVATE"


def test_fake_download_follows_the_same_rule(tmp_path: Path) -> None:
    doc = json.loads((FIXTURES / "downloads" / "behaviors.json").read_text(encoding="utf-8"))
    for entry in [doc["default"], *doc["videos"].values()]:
        entry["stepMs"] = 0
    behaviors = tmp_path / "behaviors.json"
    behaviors.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    fake = FakeExtractor(FIXTURES, behaviors=behaviors)
    with pytest.raises(YtError):
        fake.download("ACCOUNTAGE1", _choose, tmp_path / "w1", _hooks())
    with signed_in(object()):
        result = fake.download("ACCOUNTAGE1", _choose, tmp_path / "w2", _hooks())
    assert result.path.is_file()
