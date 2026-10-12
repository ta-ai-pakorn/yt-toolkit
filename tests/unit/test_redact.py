"""ตัวซ่อนข้อมูลส่วนตัวใน log (yttoolkit.redact · M5 รอบ C spec 3): ค่าคุกกี้และโฟลเดอร์ผู้ใช้ ตั้งแต่บรรทัดแรกของ app.log"""

from __future__ import annotations

import http.cookiejar
import logging
import logging.handlers
import subprocess
import sys
from pathlib import Path, PureWindowsPath

import pytest

from yttoolkit import lifecycle, probe, redact
from yttoolkit.api import errors
from yttoolkit.redact import MASK, HomePathFilter, SecretFilter, add_redaction, redact_secrets

CANARY = "canary-7f3a9e"


@pytest.fixture
def restore_root_logging():
    root = logging.getLogger()
    before = list(root.handlers)
    level = root.level
    yield root
    for h in list(root.handlers):
        if h not in before:
            root.removeHandler(h)
            h.close()
    root.setLevel(level)


@pytest.mark.parametrize(
    "text",
    [
        f"Cookie: SAPISID={CANARY}; PREF=f6=8",
        f"set-cookie: __Secure-3PSID={CANARY}; Path=/; Secure",
        f"headers={{'Cookie': 'LOGIN_INFO={CANARY}; x=1', 'User-Agent': 'ua'}}",
        f".youtube.com\tTRUE\t/\tTRUE\t1999999999\tSAPISID\t{CANARY}",
        f"#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t1999999999\t__Secure-1PSIDTS\t{CANARY}",
        f'{{"SID": "{CANARY}"}}',
        f"jar has SSID={CANARY},HSID={CANARY}",
    ],
)
def test_secret_values_are_masked(text: str) -> None:
    out = redact_secrets(text)
    assert CANARY not in out
    assert MASK in out


def _cookiejar_cookie(name: str, value: str) -> http.cookiejar.Cookie:
    return http.cookiejar.Cookie(
        0, name, value, None, False, ".youtube.com", True, True, "/", True, True, 1999999999, False, None, None, {}
    )


# รูปแบบ repr / JSON ที่ค่าคุกกี้เข้าสู่ระบบหลุดเข้า log ทางข้อความ exception (แต่ละตัวใช้ค่า canary ไม่ซ้ำกัน)
_REPR_SHAPES = {
    "repr-of-cookies-txt-line": lambda c: repr(f".youtube.com\tTRUE\t/\tTRUE\t1999\tSAPISID\t{c}\n"),
    "repr-of-cookies-txt-line-httponly": lambda c: repr(f"#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t1\t__Secure-3PSID\t{c}"),
    "cookiejar-cookie-repr": lambda c: repr(_cookiejar_cookie("SAPISID", c)),
    "cookiejar-list-repr": lambda c: repr([_cookiejar_cookie("PREF", "x"), _cookiejar_cookie("__Secure-1PSIDTS", c)]),
    "json-name-value": lambda c: f'[{{"name": "SAPISID", "value": "{c}"}}]',
    "json-name-value-compact": lambda c: f'[{{"name":"LOGIN_INFO","value":"{c}"}}]',
    "json-cookie-editor-order": lambda c: (
        f'{{"domain": ".youtube.com", "name": "SID", "path": "/", "secure": true, "value": "{c}"}}'
    ),
    "name-equals-value-equals": lambda c: f"Cookie(name='HSID', value='{c}', port=None)",
}


@pytest.mark.parametrize("shape", sorted(_REPR_SHAPES))
def test_sign_in_cookie_masked_in_repr_and_json_forms(shape: str) -> None:
    canary = f"canary-{shape}-4c1d"
    text = _REPR_SHAPES[shape](canary)
    out = redact_secrets(text)
    assert canary not in out, out
    assert MASK in out


def test_pair_masking_keeps_other_cookies_and_ordinary_name_value_text() -> None:
    kept = redact_secrets(repr([_cookiejar_cookie("PREF", "f6=8"), _cookiejar_cookie("SAPISID", CANARY)]))
    assert CANARY not in kept and "f6=8" in kept  # คุกกี้ที่ไม่ใช่การเข้าสู่ระบบไม่ถูกแตะ
    for text in (
        '{"name": "Alice", "value": 42}',
        "name='report', value='final'",
        "name=SIDEBAR value=open",  # SID ไม่ใช่ชื่อทั้งคำ
        "the name and the value of the field",
    ):
        assert redact_secrets(text) == text


@pytest.mark.parametrize(
    "text",
    [
        f'Cookie: SID="{CANARY}"; HSID=x',
        f'Cookie: SID="{CANARY}"',
        f'cookie: a=1; SID="{CANARY}"; b="2"',
        f"set-cookie: SID=\"{CANARY}\"; Path=/",
        f"headers={{'Cookie': 'SID=\"{CANARY}\"; x=1'}}",
    ],
)
def test_quoted_cookie_header_value_is_fully_masked(text: str) -> None:
    out = redact_secrets(text)
    assert CANARY not in out
    assert MASK in out


def test_cookie_header_inside_dict_repr_keeps_the_rest() -> None:
    out = redact_secrets("headers={'Cookie': 'a=b; c=d', 'User-Agent': 'ua'}")
    assert out == f"headers={{'Cookie': '{MASK}', 'User-Agent': 'ua'}}"


@pytest.mark.parametrize(
    "scheme", ["SAPISIDHASH", "SAPISID1PHASH", "SAPISID3PHASH"]
)
def test_sapisid_authorization_tokens_are_masked(scheme: str) -> None:
    canary = f"1700000000_{scheme.lower()}_9b2e"
    out = redact_secrets(f"Authorization: {scheme} {canary}")
    assert canary not in out
    assert out == f"Authorization: {scheme} {MASK}"


def test_all_three_sapisid_authorization_tokens_in_one_header() -> None:
    text = "Authorization: SAPISIDHASH 1_aaa SAPISID1PHASH 2_bbb SAPISID3PHASH 3_ccc"
    out = redact_secrets(text)
    assert out == f"Authorization: SAPISIDHASH {MASK} SAPISID1PHASH {MASK} SAPISID3PHASH {MASK}"


def test_other_text_is_left_alone() -> None:
    for text in (
        "probe aqz-KE-bpKQ: 200 OK",
        "Extracting cookies from firefox",
        "VISITOR_INFO1_LIVE expired",  # คุกกี้ผู้ชมแบบไม่ระบุตัวตน ไม่ใช่การเข้าสู่ระบบ
        "PSID=1 is not a sign-in name, nor is XSAPISID=2",
        "Authorization: Bearer abc123 for the name and value fields",
    ):
        assert redact_secrets(text) == text


def _format(record: logging.LogRecord, *filters: logging.Filter) -> str:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    for f in filters:
        handler.addFilter(f)
    assert handler.filter(record)
    return handler.format(record)


def test_secret_filter_masks_args_and_traceback() -> None:
    try:
        raise RuntimeError(f"request failed with Cookie: SAPISID={CANARY}")
    except RuntimeError:
        exc_info = sys.exc_info()
    record = logging.LogRecord(
        "yttoolkit", logging.ERROR, __file__, 1, "ส่ง %s ไม่ได้", (f"SID={CANARY}",), exc_info
    )
    text = _format(record, SecretFilter())
    assert CANARY not in text
    assert "Traceback" in text and "RuntimeError" in text


def test_filter_never_leaves_raw_args_when_the_message_cannot_be_formatted() -> None:
    # "%s %s" กับ args ตัวเดียว: getMessage() พัง handleError จะพิมพ์ args ดิบออก stderr ถ้าไม่ถูกแทนที่
    record = logging.LogRecord("yttoolkit", logging.ERROR, __file__, 1, "ส่ง %s และ %s", (f"SAPISID={CANARY}",), None)
    with pytest.raises(TypeError):
        record.getMessage()
    for kind in (SecretFilter, HomePathFilter):
        rec = logging.LogRecord("yttoolkit", logging.ERROR, __file__, 1, "ส่ง %s และ %s", (f"SAPISID={CANARY}",), None)
        assert kind().filter(rec)
        assert rec.args == ()
        assert rec.getMessage() == "(จัดรูปข้อความ log ไม่ได้: TypeError)"
        assert CANARY not in rec.getMessage()
        assert CANARY not in repr(rec.__dict__)


def test_home_filter_moved_but_keeps_its_old_names() -> None:
    assert lifecycle.HomePathFilter is HomePathFilter
    assert errors.redact_home is redact.redact_home
    assert errors._home_aliases is redact._home_aliases
    home = str(Path.home())
    record = logging.LogRecord("yttoolkit", logging.INFO, __file__, 1, "เปิด %s", (f"{home}\\x.mp4",), None)
    assert _format(record, HomePathFilter()) == "เปิด ~\\x.mp4"


def test_add_redaction_is_idempotent() -> None:
    handler = logging.StreamHandler()
    add_redaction(handler)
    add_redaction(handler)
    kinds = [type(f) for f in handler.filters]
    assert kinds.count(HomePathFilter) == 1 and kinds.count(SecretFilter) == 1


def test_app_log_hides_a_secret_written_before_lifecycle_loads(paths, restore_root_logging) -> None:
    # สิ่งที่ __main__ ทำเป็นอย่างแรก (ก่อน import lifecycle): ตัวกรองต้องอยู่แล้ว
    probe.setup_file_log(paths)
    added = [h for h in restore_root_logging.handlers if isinstance(h, logging.handlers.RotatingFileHandler)
             and h.baseFilename == str((paths.logs / "app.log").resolve())]  # fmt: skip
    assert len(added) == 1
    assert {type(f) for f in added[0].filters} >= {HomePathFilter, SecretFilter}
    logging.getLogger("yttoolkit").error("เปิดโปรแกรมไม่สำเร็จ: Cookie: SAPISID=%s home=%s", CANARY, Path.home())
    added[0].flush()
    text = (paths.logs / "app.log").read_text(encoding="utf-8")
    assert "เปิดโปรแกรมไม่สำเร็จ" in text
    assert CANARY not in text and str(Path.home()) not in text


def test_lifecycle_adds_the_secret_filter_once(paths, restore_root_logging) -> None:
    probe.setup_file_log(paths)
    lifecycle.setup_file_logging(paths)
    lifecycle.setup_file_logging(paths)
    handler = next(h for h in restore_root_logging.handlers if isinstance(h, logging.handlers.RotatingFileHandler)
                   and h.baseFilename == str((paths.logs / "app.log").resolve()))  # fmt: skip
    assert [type(f) for f in handler.filters].count(SecretFilter) == 1


def test_serve_console_handlers_get_both_redaction_filters(paths, fake_platform, monkeypatch, restore_root_logging) -> None:
    root = restore_root_logging
    saved = list(root.handlers)
    root.handlers[:] = []  # pytest ใส่ handler ของตัวเองไว้แล้ว basicConfig จะไม่สร้าง console handler ให้ ล้างก่อนเหมือนโปรเซสใหม่
    try:
        seen = {}

        def fake_run_app(**kwargs):
            seen["handlers"] = list(logging.getLogger().handlers)
            return 0

        monkeypatch.setattr(lifecycle, "default_paths", lambda: paths)
        monkeypatch.setattr(lifecycle, "current", lambda: fake_platform)
        monkeypatch.setattr(lifecycle, "run_app", fake_run_app)
        assert lifecycle.serve(port=9000) == 0
        handlers = seen["handlers"]
        assert handlers, "serve() ต้องตั้ง console handler ผ่าน basicConfig"
        for handler in handlers:
            kinds = [type(f) for f in handler.filters]
            assert kinds.count(HomePathFilter) == 1 and kinds.count(SecretFilter) == 1
    finally:
        root.handlers[:] = saved


def test_redact_module_does_not_load_the_web_stack() -> None:
    code = (
        "import sys, yttoolkit.redact\n"
        "print(','.join(sorted({'httpx', 'fastapi', 'uvicorn', 'starlette'} & set(sys.modules))))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60, check=True)
    assert out.stdout.strip() == ""


# ---------- M6 รอบ B: path นอกโฟลเดอร์ผู้ใช้ ลิงก์ไฟล์ของยูทูป ชื่อคลิป token และชื่อคุกกี้ ----------

HOME = PureWindowsPath("C:/Users/somchai")
TITLE = "คลิปสอนทำขนม: วิธีทำบัวลอย | ตอนที่ 1"


@pytest.fixture
def somchai_home(monkeypatch):
    """โฟลเดอร์ผู้ใช้ปลอมแบบ Windows (แบบเดียวกับ tests/api/test_errors.py) ไม่มีชื่อสั้นแบบ 8.3"""
    monkeypatch.setattr(errors.Path, "home", lambda: HOME)
    monkeypatch.setattr(redact, "_home_aliases", lambda home: ())


@pytest.mark.parametrize(
    "text",
    [
        "open file:///C:/Users/somchai/Downloads/a.mp4 failed",
        "url=file:///c:/users/SOMCHAI/x",
        "path=C%3A%5CUsers%5Csomchai%5CDownloads",
        "path=C%3a%5cusers%5cSomchai%5cDownloads",
        "path=C%3A/Users/somchai/Downloads",
    ],
)
def test_percent_encoded_and_file_url_home_forms_are_tilde(somchai_home, text: str) -> None:
    out = redact.redact_home(text)
    assert "somchai" not in out.lower()
    assert "~" in out


def test_percent_encoded_home_keeps_the_sibling_guard(somchai_home) -> None:
    assert redact.redact_home("C%3A%5CUsers%5Csomchaiyo") == "C%3A%5CUsers%5Csomchaiyo"


def test_mask_user_paths_quoted_oserror_repr_with_spaces() -> None:
    text = r"[Errno 28] No space left on device: 'D:\\งาน ตัดต่อ\\คลิป ยาว.mp4' (เขียนไม่ได้)"
    assert redact.mask_user_paths(text) == "[Errno 28] No space left on device: '<path>' (เขียนไม่ได้)"


def test_mask_user_paths_double_quoted_unc_and_bare_paths() -> None:
    assert redact.mask_user_paths(r'open "\\nas\share\my clips\a.mp4"') == 'open "<path>"'
    assert redact.mask_user_paths(r"dest \\nas\share\a.mp4, retry") == "dest <path>, retry"
    assert redact.mask_user_paths("saved to E:/out/a.mp4") == "saved to <path>"
    assert redact.mask_user_paths(r"x (D:\out\a.mp4)") == "x (<path>)"


def test_mask_user_paths_keeps_tilde_urls_and_traceback_frames() -> None:
    kept = (
        r"~\Downloads\a.mp4 and ~/Videos",
        r"'~\\Downloads\\a b.mp4' (repr ของ OSError: backslash สองตัว ไม่ใช่ UNC)",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        r'  File "C:\yt-dl\src\yttoolkit\core\queue.py", line 360, in _run_job',
        "ratio 16:9 at 1:30",
    )
    for text in kept:
        assert redact.mask_user_paths(text) == text
    frames = 'Traceback:\n  File "D:\\app\\x.py", line 5, in f\nOSError: D:\\out\\a.mp4\n'
    assert redact.mask_user_paths(frames) == 'Traceback:\n  File "D:\\app\\x.py", line 5, in f\nOSError: <path>\n'


def test_mask_media_urls_masks_only_googlevideo() -> None:
    text = (
        "GET https://rr3---sn-abc.googlevideo.com/videoplayback?ip=203.0.113.9&sig=AB 403 · "
        "https://i.ytimg.com/vi/dQw4w9WgXcQ/hq.jpg ok"
    )
    assert redact.mask_media_urls(text) == "GET <url> 403 · https://i.ytimg.com/vi/dQw4w9WgXcQ/hq.jpg ok"


def test_scrub_titles_exact_safe_name_and_truncated_file_name() -> None:
    from yttoolkit.core.files import safe_component

    safe = safe_component(TITLE, "")
    assert safe != TITLE  # ":" และ "|" ใช้ในชื่อไฟล์ไม่ได้
    text = f"title={TITLE}\nfile ~\\Downloads\\{safe} [x].mp4\ncut '~\\Downloads\\{safe[:20]}.mp4'"
    out = redact.scrub_titles(text, (TITLE,))
    assert "บัวลอย" not in out and "สอนทำขนม" not in out
    assert out.count("<title>") == 3
    assert "~\\Downloads\\<title>" in out


def test_scrub_titles_skips_short_titles_and_empty_input() -> None:
    assert redact.scrub_titles("the job failed", ("job",)) == "the job failed"
    assert redact.scrub_titles("anything", ()) == "anything"


def test_redact_log_detail_runs_every_step_in_order(somchai_home) -> None:
    detail = (
        f"C:\\Users\\somchai\\Downloads\\{TITLE}.mp4 · D:\\out\\a.mp4 · SAPISID={CANARY} · "
        "https://r1---sn-x.googlevideo.com/videoplayback?ip=198.51.100.7"
    )
    out = redact.redact_log_detail(detail, (TITLE,))
    assert out.startswith("~\\Downloads\\<title>")
    assert "somchai" not in out and CANARY not in out and "D:\\" not in out and "198.51.100.7" not in out
    assert TITLE not in out and "<path>" in out and "<url>" in out


def test_redact_report_hides_the_token_and_every_sign_in_cookie_name() -> None:
    token = "tok-9f8e7d6c5b4a"
    names = " ".join(f"{name}=v{i}" for i, name in enumerate(redact.SIGN_IN_COOKIE_NAMES))
    out = redact.redact_report(f"token {token} cookies {names}", token=token, titles=())
    assert token not in out
    for name in redact.SIGN_IN_COOKIE_NAMES:
        assert name not in out
    assert out.startswith("token <hidden> cookies <hidden>=<hidden>")


def test_redact_report_keeps_ids_codes_and_ordinary_words() -> None:
    text = r"E_YT_REFUSED job=a1b2 videoId dQw4w9WgXcQ SIDEBAR XSAPISID ~\Downloads"
    assert redact.redact_report(text, token="", titles=()) == text


def test_redact_report_does_not_load_the_web_stack_or_yt_dlp() -> None:
    code = (
        "import sys, yttoolkit.redact as r\n"
        "r.redact_report('C:/x a', token='t', titles=('คลิปทดสอบยาวพอ',))\n"
        "print(','.join(sorted({'httpx', 'fastapi', 'uvicorn', 'starlette', 'yt_dlp'} & set(sys.modules))))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60, check=True)
    assert out.stdout.strip() == ""


# ---------- M6 รอบ B fix round 1 ----------


@pytest.mark.parametrize("name", ["Som Chai", "สมชาย ใจดี"])
def test_file_uri_home_with_space_or_thai_name_is_tilde(monkeypatch, name: str) -> None:
    home = PureWindowsPath(f"C:/Users/{name}")
    monkeypatch.setattr(errors.Path, "home", lambda: home)
    monkeypatch.setattr(redact, "_home_aliases", lambda h: ())
    from urllib.parse import quote

    uri = f"file:///C:/Users/{quote(name)}/Downloads/a.mp4"
    out = redact.redact_home(f"open {uri} failed")
    assert name.split()[0] not in out and quote(name) not in out
    assert "~" in out


def test_percent_encoded_8_3_alias_is_tilde(monkeypatch) -> None:
    monkeypatch.setattr(errors.Path, "home", lambda: HOME)
    monkeypatch.setattr(redact, "_home_aliases", lambda h: (r"C:\Users\SOMCHA~1",))
    out = redact.redact_home("p=C%3A%5CUsers%5CSOMCHA~1%5Cx")
    assert "SOMCHA" not in out and out.startswith("p=~")


def test_mask_user_paths_unquoted_path_with_spaces_does_not_leak_its_tail() -> None:
    assert redact.mask_user_paths(r"Destination: D:\งาน ตัดต่อ\x.mp4") == "Destination: <path>"
    assert redact.mask_user_paths(r"D:\My Videos\Old Clips\a.mp4, retry") == "<path>, retry"
    assert redact.mask_user_paths(r"D:\a\b.mp4 แล้วไฟล์หาย") == "<path> แล้วไฟล์หาย"


@pytest.mark.parametrize("prefix", ["[", "<", "{", "|"])
def test_mask_user_paths_unc_after_bracket_like_chars(prefix: str) -> None:
    assert "nas" not in redact.mask_user_paths(prefix + r"\\nas\share\a")


def test_mask_media_urls_json_escaped_uppercase_and_closing_paren() -> None:
    assert redact.mask_media_urls(r'{"u": "https:\/\/rr1.googlevideo.com\/videoplayback?ip=1.2.3.4"}') == '{"u": "<url>"}'
    assert redact.mask_media_urls("HTTPS://RR1.GOOGLEVIDEO.COM/videoplayback?ip=1.2.3.4 x") == "<url> x"
    assert redact.mask_media_urls("(https://rr1.googlevideo.com/v?ip=1.2.3.4)") == "(<url>)"


@pytest.mark.parametrize("title", ["path", "title", "hidden", "media"])
def test_scrub_titles_never_corrupts_masks(title: str) -> None:
    out = redact.scrub_titles(f"<path> <title> <url> <hidden> {title}", (title,))
    assert out.startswith("<path> <title> <url> <hidden> ")
    assert out.endswith("<title>")


def test_scrub_titles_prefix_rule_keeps_following_fields() -> None:
    from yttoolkit.core.files import safe_component

    safe = safe_component(TITLE, "")
    out = redact.scrub_titles(rf"file ~\Downloads\{safe[:20]} [x].mp4 code=E_X job=a1b2", (TITLE,))
    assert out == r"file ~\Downloads\<title> code=E_X job=a1b2"


# ---------- fix round 2 ----------


def test_spaced_path_tail_stops_at_key_value_url_and_prose() -> None:
    text = r"D:\a\b.mp4 failed code=E_X job=j1 url=https://youtu.be/abc"
    assert redact.mask_user_paths(text) == "<path> failed code=E_X job=j1 url=https://youtu.be/abc"


def test_two_spaced_paths_on_one_line_keep_the_prose_between() -> None:
    text = r"copy D:\My Clips\a.mp4 then E:\Other Dir\b.mp4, retry"
    assert redact.mask_user_paths(text) == "copy <path> then <path>, retry"


@pytest.mark.parametrize("stop", ["~\\Downloads\\x", "[x]\\y", "'q'\\y", "\\\\nas\\s\\y"])
def test_spaced_path_tail_stops_at_roots_quotes_and_brackets(stop: str) -> None:
    assert redact.mask_user_paths(r"D:\My Clips\a.mp4 " + stop).startswith("<path> ")


def test_log_detail_hides_a_spaced_title_in_a_yt_dlp_destination_line() -> None:
    title = "คลิป สอนทำ ขนมบัวลอย"
    out = redact.redact_log_detail(f"Destination: D:\\out\\{title}.mp4 code=E_X", (title,))
    assert "คลิป" not in out and "ขนม" not in out and "D:" not in out
    assert out.endswith(" code=E_X")
    out = redact.redact_report("Destination: D:\\out\\clip one.mp4", token="", titles=("clip one",))
    assert "one" not in out and "clip" not in out


# ---------- รีวิวท้ายรอบ M3: traceback ของ crash ปิดทุกอย่างใต้โฟลเดอร์ผลลัพธ์ ----------


@pytest.fixture
def somchai_home(monkeypatch):
    monkeypatch.setattr(errors.Path, "home", lambda: PureWindowsPath("C:/Users/somchai"))
    monkeypatch.setattr(redact, "_home_aliases", lambda home: ())


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("open ~\\Downloads\\YT Toolkit\\Secret Clip [id]\\03 Ch.mp4 failed",
         "open ~\\Downloads\\YT Toolkit\\<path>"),
        ("denied: '~\\\\Downloads\\\\YT Toolkit\\\\Secret Clip\\\\x.mp4' (errno 13)",
         "denied: '~\\\\Downloads\\\\YT Toolkit\\\\<path>' (errno 13)"),
        ("at ~/Downloads/YT Toolkit/Secret Clip/x.mp4", "at ~/Downloads/YT Toolkit/<path>"),
        ("at ~\\downloads\\yt toolkit\\Secret.mp4", "at ~\\downloads\\yt toolkit\\<path>"),
        ("sibling ~\\Downloads\\YT Toolkit 2\\Secret.mp4", "sibling ~\\Downloads\\YT Toolkit 2\\Secret.mp4"),
        ('  File "~\\Downloads\\YT Toolkit\\x.py", line 3, in f', '  File "~\\Downloads\\YT Toolkit\\x.py", line 3, in f'),
    ],
)  # fmt: skip
def test_mask_below_roots_hides_everything_under_the_output_folder(somchai_home, text, expected) -> None:
    root = PureWindowsPath("C:/Users/somchai/Downloads/YT Toolkit")
    assert redact.mask_below_roots(redact.redact_home(text), [root]) == expected


def test_crash_trace_redacts_the_traceback_with_titles_and_roots(somchai_home) -> None:
    try:
        raise PermissionError(13, "Permission denied", "C:\\Users\\somchai\\Downloads\\YT Toolkit\\Other Clip\\a.mp4")
    except PermissionError as exc:
        text = redact.crash_trace(exc, titles=("Known Title",), roots=["C:\\Users\\somchai\\Downloads\\YT Toolkit"])
    assert text.startswith("Traceback (most recent call last):")
    assert "Other Clip" not in text and "somchai" not in text
    assert "PermissionError: [Errno 13] Permission denied: '~\\\\Downloads\\\\YT Toolkit\\\\<path>'" in text
