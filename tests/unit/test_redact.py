"""ตัวซ่อนข้อมูลส่วนตัวใน log (yttoolkit.redact · M5 รอบ C spec 3): ค่าคุกกี้และโฟลเดอร์ผู้ใช้ ตั้งแต่บรรทัดแรกของ app.log"""

from __future__ import annotations

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


def test_other_text_is_left_alone() -> None:
    for text in (
        "probe aqz-KE-bpKQ: 200 OK",
        "Extracting cookies from firefox",
        "VISITOR_INFO1_LIVE expired",  # คุกกี้ผู้ชมแบบไม่ระบุตัวตน ไม่ใช่การเข้าสู่ระบบ
        "PSID=1 is not a sign-in name, nor is XSAPISID=2",
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


def test_redact_module_does_not_load_the_web_stack() -> None:
    code = (
        "import sys, yttoolkit.redact\n"
        "print(','.join(sorted({'httpx', 'fastapi', 'uvicorn', 'starlette'} & set(sys.modules))))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60, check=True)
    assert out.stdout.strip() == ""
