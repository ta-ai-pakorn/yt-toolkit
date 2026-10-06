"""ตัวซ่อนข้อมูลส่วนตัวใน log (yttoolkit.redact · M5 รอบ C spec 3): ค่าคุกกี้และโฟลเดอร์ผู้ใช้ ตั้งแต่บรรทัดแรกของ app.log"""

from __future__ import annotations

import http.cookiejar
import logging
import logging.handlers
import subprocess
import sys
from pathlib import Path

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
