import logging
from pathlib import Path, PureWindowsPath

from fastapi import FastAPI
from fastapi.testclient import TestClient

from yttoolkit.api import errors
from yttoolkit.api.errors import error_body, install_error_handlers

# ค่าเดียวกับ tests/api/conftest.py (import conftest ตรง ๆ ไม่ได้)
BASE = "http://127.0.0.1:8787"
AUTH = {"X-Toolkit-Token": "test-token", "Origin": BASE}
BAD_REQUEST_MESSAGE = "ข้อมูลที่ส่งมาไม่ถูกต้อง ลองรีเฟรชหน้าเว็บ"


def test_unknown_api_path_uses_not_found_envelope(make_client):
    resp = make_client().get("/api/nope")
    assert resp.status_code == 404
    assert resp.json() == {"error": {"code": "E_NOT_FOUND", "message": "ไม่พบสิ่งที่ขอ", "detail": "Not Found"}}


def test_routing_404_uses_not_found_envelope():
    # แอพจริงมี SPA catch-all จึงไม่มี 404 จาก routing ตรง ๆ ใช้แอพเปล่าตรวจแทน
    app = FastAPI()
    install_error_handlers(app)
    resp = TestClient(app, base_url=BASE).get("/nothing-here")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "E_NOT_FOUND"


def test_validation_error_uses_bad_request_envelope(make_client):
    resp = make_client().post(
        "/api/shutdown", content=b"{not json", headers={**AUTH, "Content-Type": "application/json"}
    )
    assert resp.status_code == 422
    body = resp.json()["error"]
    assert body["code"] == "E_BAD_REQUEST"
    assert body["message"] == BAD_REQUEST_MESSAGE


def test_other_http_exception_keeps_status_with_http_code(make_client):
    resp = make_client().post("/api/nope", headers=AUTH)  # มีแค่ GET catch-all จึงได้ 405
    assert resp.status_code == 405
    assert resp.headers["allow"] == "GET"
    assert resp.json()["error"] == {"code": "E_HTTP_405", "message": BAD_REQUEST_MESSAGE, "detail": "Method Not Allowed"}


def test_unhandled_exception_uses_unknown_envelope_and_logs(make_client, caplog):
    app = make_client().app

    @app.get("/test-boom")
    def boom():
        raise RuntimeError("kaboom")

    # ย้าย route ทดสอบขึ้นก่อน SPA catch-all
    app.router.routes.insert(0, app.router.routes.pop())
    client = TestClient(app, base_url=BASE, raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR, logger="yttoolkit"):
        resp = client.get("/test-boom")
    assert resp.status_code == 500
    assert resp.json()["error"] == {
        "code": "E_UNKNOWN",
        "message": "มีบางอย่างผิดพลาด ถ่ายภาพหน้าจอนี้ส่งให้ผู้ดูแล",
        "detail": "kaboom",
    }
    records = [r for r in caplog.records if r.exc_info]
    assert records and isinstance(records[0].exc_info[1], RuntimeError)


def test_error_body_redacts_real_home():
    home = str(Path.home())
    detail = f"เปิด {home}{'/'}Videos/a.mp4 ไม่ได้"
    assert error_body("E_X", "m", detail)["error"]["detail"] == "เปิด ~/Videos/a.mp4 ไม่ได้"


def test_error_body_redacts_windows_home_any_case_and_slash(monkeypatch):
    monkeypatch.setattr(errors.Path, "home", lambda: PureWindowsPath("C:/Users/Somchai"))
    detail = r"a C:\Users\Somchai\x.txt b c:\users\SOMCHAI\y c C:/Users/Somchai/z"
    assert error_body("E_X", "m", detail)["error"]["detail"] == r"a ~\x.txt b ~\y c ~/z"


def test_error_body_keeps_sibling_folder_that_shares_home_prefix(monkeypatch):
    monkeypatch.setattr(errors.Path, "home", lambda: PureWindowsPath("C:/Users/Som"))
    assert error_body("E_X", "m", r"C:\Users\Somchai\x")["error"]["detail"] == r"C:\Users\Somchai\x"


def test_error_body_keeps_none_detail():
    assert error_body("E_X", "m")["error"]["detail"] is None


def test_error_body_redacts_home_inside_real_oserror_repr():
    # str(OSError) ใส่ path แบบ repr บน Windows backslash จะกลายเป็นสองตัว
    home = str(Path.home())
    detail = str(FileNotFoundError(2, "No such file", home + r"\Videos\a.mp4"))
    expected = str(FileNotFoundError(2, "No such file", "~" + r"\Videos\a.mp4"))
    assert error_body("E_X", "m", detail)["error"]["detail"] == expected


def test_error_body_redacts_doubled_backslash_windows_home(monkeypatch):
    monkeypatch.setattr(errors.Path, "home", lambda: PureWindowsPath("C:/Users/Somchai"))
    detail = str(FileNotFoundError(2, "No such file", r"C:\Users\Somchai\Videos\a.mp4"))
    assert detail == r"[Errno 2] No such file: 'C:\\Users\\Somchai\\Videos\\a.mp4'"
    assert error_body("E_X", "m", detail)["error"]["detail"] == r"[Errno 2] No such file: '~\\Videos\\a.mp4'"


def test_error_body_keeps_home_followed_by_dot(monkeypatch):
    # ตั้งใจไม่แทน: ตัวกันโฟลเดอร์ข้างเคียงมองจุดเป็นส่วนของชื่อ (เช่น C:\Users\Somchai.old)
    monkeypatch.setattr(errors.Path, "home", lambda: PureWindowsPath("C:/Users/Somchai"))
    assert error_body("E_X", "m", r"อยู่ที่ C:\Users\Somchai.")["error"]["detail"] == r"อยู่ที่ C:\Users\Somchai."


def test_http_exception_304_has_no_body():
    from fastapi import HTTPException as FastAPIHTTPException

    app = FastAPI()
    install_error_handlers(app)

    @app.get("/cached")
    def cached():
        raise FastAPIHTTPException(status_code=304)

    resp = TestClient(app, base_url=BASE).get("/cached")
    assert resp.status_code == 304
    assert resp.content == b""
