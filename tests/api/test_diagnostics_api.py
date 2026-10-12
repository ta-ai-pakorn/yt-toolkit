"""POST /api/diagnostics (M6 รอบ B spec 2.1 · AC-SET-04) และบรรทัด api_error ของ ErrorLogMiddleware (spec 3.3)"""

from __future__ import annotations

import logging
import random
import re
from pathlib import Path, PureWindowsPath

import pytest
from fastapi.testclient import TestClient

from yttoolkit import redact
from yttoolkit.api import errors
from yttoolkit.api.diagnostics import MAX_DETAIL
from yttoolkit.core import files, tools
from yttoolkit.core.db import Database
from yttoolkit.core.events import EventBus
from yttoolkit.core.jobs import JobStore, NewJob
from yttoolkit.core.queue import QueueRunner
from yttoolkit.core.settings import SettingsStore
from yttoolkit.core.tools import ToolStatus

TOKEN = "test-token"
BASE = "http://127.0.0.1:8787"
AUTH = {"X-Toolkit-Token": TOKEN, "Origin": BASE}
BBB = "aqz-KE-bpKQ"
TITLE = "บิ๊กบัคบันนี่ ฉบับทดสอบ"
HOME = PureWindowsPath("C:/Users/somchai")
PRD_LABELS = (
    "## รายงานปัญหา YT Toolkit\n",
    "- เวลา: ",
    "- แอพ: 0.1.0 (commit abc1234) · ระบบ: Windows 11 (10.0.26200)\n",
    "- yt-dlp: 2026.09.20 · ffmpeg: ไม่มี · JS runtime: deno 2.9.7\n",
    "- บัญชียูทูป: ไม่ได้ใช้บัญชี\n",
    "### error\n",
    "- รหัส: ",
    "- รายละเอียด: ",
    "### log ล่าสุด (50 บรรทัด)\n```text\n",
)


@pytest.fixture(autouse=True)
def fixed_tools(monkeypatch):
    """ไม่เรียก ffmpeg / deno / yt-dlp จริง (รายงานใช้ผลของสามตัวนี้ตรง ๆ)"""
    monkeypatch.setattr(tools, "ytdlp_status", lambda **kwargs: ToolStatus("ok", name="yt-dlp", version="2026.09.20"))
    monkeypatch.setattr(tools, "ffmpeg_status", lambda paths, plat: ToolStatus("error", name="ffmpeg", message="x"))
    monkeypatch.setattr(tools, "find_js_runtime", lambda plat: ToolStatus("ok", name="deno", version="2.9.7"))


@pytest.fixture
def somchai(monkeypatch):
    monkeypatch.setattr(errors.Path, "home", lambda: HOME)
    monkeypatch.setattr(redact, "_home_aliases", lambda home: ())


class Env:
    def __init__(self, make_client, tmp_path: Path) -> None:
        self.db = Database(tmp_path / "app.db")
        self.db.migrate()
        self.store = JobStore(self.db)
        self.bus = EventBus()
        settings = SettingsStore(self.db, tmp_path / "out")
        self.runner = QueueRunner(self.store, self.bus, {}, settings=settings, work_root=tmp_path / "work",
                                  rng=random.Random(1), spawn=lambda fn: None, redact=lambda text: text)  # fmt: skip
        self.client: TestClient = make_client(queue=self.runner, events=self.bus, settings=settings, db=self.db)

    def failed_job(self, code: str, detail: str, title: str = TITLE):
        (job,) = self.store.add([NewJob(BBB, "video", {}, title)])
        self.store.transition(job.id, "running")
        return self.store.transition(job.id, "failed", error_code=code, error_message="m", error_detail=detail)

    def report(self, body: dict) -> str:
        resp = self.client.post("/api/diagnostics", json=body, headers=AUTH)
        assert resp.status_code == 200, resp.text
        return resp.json()["report"]


@pytest.fixture
def env(make_client, tmp_path):
    e = Env(make_client, tmp_path)
    yield e
    e.runner.shutdown(timeout=0.1)
    e.bus.close()
    e.db.close()


def _in_order(text: str, parts: tuple[str, ...]) -> bool:
    at = 0
    for part in parts:
        found = text.find(part, at)
        if found < 0:
            return False
        at = found + len(part)
    return True


# ---------- AC-SET-04: รายงานของงานที่พลาด ----------


def test_job_report_has_every_prd_heading_and_no_personal_data(env, somchai, paths) -> None:
    paths.logs.mkdir(parents=True, exist_ok=True)
    (paths.logs / "app.log").write_text(f"INFO yttoolkit: token={TOKEN} เปิด C:\\Users\\somchai\\x\n", encoding="utf-8")
    detail = f"[Errno 28] No space left: 'C:\\\\Users\\\\somchai\\\\Downloads\\\\{TITLE}.mp4' · copy 'D:\\\\out\\\\{TITLE}.mp4'"
    job = env.failed_job("E_DISK_FULL", detail)
    report = env.report({"jobId": job.id, "code": "E_NETWORK", "detail": "ignored"})
    assert _in_order(report, PRD_LABELS), report
    assert re.search(r"^- เวลา: \d{4}-\d{2}-\d{2} \d{2}:\d{2} \([+-]\d{2}:\d{2}\)$", report, re.M)
    assert f"- รหัส: E_DISK_FULL · งาน: video (videoId {BBB})\n" in report  # จากงาน ไม่ใช่จาก body
    assert "ignored" not in report and "E_NETWORK" not in report
    assert "~\\\\Downloads" in report
    for leaked in ("somchai", TITLE, "D:\\", TOKEN):
        assert leaked not in report, leaked


def test_the_videos_row_title_is_hidden_too(env, paths) -> None:
    env.db.execute(
        "INSERT INTO videos (video_id, title, probe_json, probed_at, opened_at) VALUES (?, ?, '{}', 'x', 'x')",
        (BBB, "ชื่อในประวัติที่ยาวพอ"),
    )
    report = env.report({"code": "E_NETWORK", "detail": "เปิด ชื่อในประวัติที่ยาวพอ ไม่ได้", "videoId": BBB})
    assert "ชื่อในประวัติที่ยาวพอ" not in report and "<title>" in report


def test_a_job_without_a_title_still_hides_the_videos_row_title(env, paths) -> None:
    # ผลรีวิว T6: ชื่องานว่าง มีแค่ตาราง videos ที่รู้ชื่อ ต้องปิดทั้งชื่อเต็ม ชื่อไฟล์ และชื่อไฟล์ที่ถูกตัดสั้น
    row_title = "ชื่อที่รู้แค่ในตาราง videos เท่านั้น: ยาวพอให้ตัด"
    env.db.execute(
        "INSERT INTO videos (video_id, title, probe_json, probed_at, opened_at) VALUES (?, ?, '{}', 'x', 'x')",
        (BBB, row_title),
    )
    safe = files.safe_component(row_title, "")
    assert safe != row_title  # ":" ใช้ในชื่อไฟล์ไม่ได้ จึงเป็นอีกรูปแบบหนึ่ง
    job = env.failed_job("E_DISK_FULL", f"open '{row_title}' · '{safe}.mp4' · '{safe[:20]}.part'", title="")
    assert job.title == ""
    report = env.report({"jobId": job.id})
    for leaked in (row_title, safe, safe[:16]):
        assert leaked not in report, leaked
    assert report.count("<title>") >= 3


# ---------- รูปแบบอื่นของ body ----------


def test_non_job_report_uses_the_body_with_the_screen_label(env) -> None:
    report = env.report({"code": "E_YT_REFUSED", "detail": "HTTP Error 403", "context": "video-header", "videoId": BBB})
    assert f"- รหัส: E_YT_REFUSED · หน้าจอ: video-header (videoId {BBB})\n- รายละเอียด: HTTP Error 403\n" in report


def test_empty_body_is_the_health_report_without_an_error_section(env) -> None:
    for body in ({}, {"context": "health"}):
        report = env.report(body)
        assert "### error" not in report
        assert "### log ล่าสุด (50 บรรทัด)" in report


def test_unknown_job_id_falls_back_to_the_body_and_never_404s(env) -> None:
    report = env.report({"jobId": "nope-123", "code": "E_UNKNOWN", "detail": "gone", "context": "queue"})
    assert "- รหัส: E_UNKNOWN · หน้าจอ: queue\n- รายละเอียด: gone\n" in report
    assert "- รหัส: ไม่มี" in env.report({"jobId": "nope-123"})


def test_works_without_a_queue_or_database(make_client) -> None:
    resp = make_client().post("/api/diagnostics", json={"code": "E_OFFLINE", "context": "crash"}, headers=AUTH)
    assert resp.status_code == 200
    assert "- รหัส: E_OFFLINE · หน้าจอ: crash\n" in resp.json()["report"]


def test_account_line_reads_only_the_status(env) -> None:
    class Accounts:
        def status(self) -> dict:
            return {"active": True, "importedAt": "2026-10-12T01:00:00+00:00", "expiresAt": "x", "used": True}

    env.client.app.state.ctx.accounts = Accounts()
    report = env.report({})
    assert "- บัญชียูทูป: ใช้บัญชีชั่วคราวอยู่\n" in report
    assert "2026-10-12T01" not in report


def test_response_is_not_cached_and_logs_one_line_without_the_detail(env, caplog) -> None:
    with caplog.at_level(logging.INFO, logger="yttoolkit"):
        resp = env.client.post("/api/diagnostics", json={"code": "E_NETWORK", "detail": "secret-detail-77",
                                                         "context": "video-frames"}, headers=AUTH)  # fmt: skip
    assert resp.headers["cache-control"] == "no-store"
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("diagnostics ")]
    assert lines == ["diagnostics code=E_NETWORK context=video-frames job=-"]
    assert "secret-detail-77" not in caplog.text


def test_the_report_never_contains_its_own_log_line(env, paths) -> None:
    from yttoolkit import probe

    root = logging.getLogger()
    before, level = list(root.handlers), root.level
    try:
        probe.setup_file_log(paths)
        first = env.report({"context": "health"})
        second = env.report({"context": "health"})
    finally:
        for handler in list(root.handlers):
            if handler not in before:
                root.removeHandler(handler)
                handler.close()
        root.setLevel(level)
    assert "diagnostics code=" not in first
    assert "diagnostics code=- context=health job=-" in second  # บรรทัดของครั้งก่อนอยู่ใน log แล้ว


# ---------- 422: ตรวจ body เอง ไม่ยกค่าที่ส่งมา ----------

BAD = "evil-value-9z"


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"jobId": "a", BAD: "x"}, "body has an unknown field"),
        ({"code": f"E_{BAD}"}, "code must match ^E_[A-Z0-9_]{1,40}$"),
        ({"jobId": f"{BAD}/../x"}, "jobId must match ^[A-Za-z0-9_-]{1,64}$"),
        ({"videoId": BAD}, "videoId must match ^[A-Za-z0-9_-]{11}$"),
        ({"context": f"Video {BAD}"}, "context must match ^[a-z][a-z0-9-]{0,31}$"),
        ({"detail": BAD + "x" * MAX_DETAIL}, "detail longer than 4000 characters"),
        ({"code": 5}, "code must be a string"),
        ({"jobId": "abc\n"}, "jobId must match ^[A-Za-z0-9_-]{1,64}$"),
    ],
)
def test_bad_fields_are_422_and_never_echo_the_value(env, caplog, body, detail) -> None:
    with caplog.at_level(logging.INFO, logger="yttoolkit"):
        resp = env.client.post("/api/diagnostics", json=body, headers=AUTH)
    assert resp.status_code == 422
    error = resp.json()["error"]
    assert (error["code"], error["detail"]) == ("E_BAD_REQUEST", detail)
    assert BAD not in resp.text and BAD not in caplog.text
    assert "api_error method=POST path=/api/diagnostics status=422 code=E_BAD_REQUEST" in caplog.text


@pytest.mark.parametrize("raw", [b"[1, 2]", b'"text"', b"{not json", b""])
def test_a_body_that_is_not_a_json_object_is_422(env, raw) -> None:
    resp = env.client.post("/api/diagnostics", content=raw, headers={**AUTH, "Content-Type": "application/json"})
    assert resp.status_code == 422
    assert resp.json()["error"]["detail"] == "body must be a JSON object"


def test_detail_at_exactly_the_limit_is_accepted(env) -> None:
    assert "### error" in env.report({"code": "E_UNKNOWN", "detail": "d" * MAX_DETAIL})


# ---------- token: รายงานมี log จึงต้องผ่าน token เสมอ ----------


def test_no_token_or_a_foreign_origin_is_403(env, caplog) -> None:
    with caplog.at_level(logging.INFO, logger="yttoolkit"):
        no_token = env.client.post("/api/diagnostics", json={}, headers={"Origin": BASE})
        foreign = env.client.post("/api/diagnostics", json={}, headers={"X-Toolkit-Token": TOKEN,
                                                                        "Origin": "http://evil.example"})  # fmt: skip
    assert no_token.status_code == foreign.status_code == 403
    assert no_token.json()["error"]["code"] == "E_FORBIDDEN"
    assert "report" not in no_token.text
    assert "api_error method=POST path=/api/diagnostics status=403 code=E_FORBIDDEN" in caplog.text


def test_there_is_no_get_that_returns_the_report(env) -> None:
    resp = env.client.get("/api/diagnostics?jobId=x")
    assert resp.status_code in (404, 405)
    assert "report" not in resp.text and "รายงานปัญหา" not in resp.text


# ---------- ErrorLogMiddleware (spec 3.3) ----------


def _api_lines(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.getMessage().startswith("api_error ")]


def test_a_409_is_an_info_line_with_method_path_and_code(env, caplog) -> None:
    (job,) = env.store.add([NewJob(BBB, "video", {})])
    with caplog.at_level(logging.DEBUG, logger="yttoolkit"):
        resp = env.client.post(f"/api/jobs/{job.id}/retry?secret=q1", headers=AUTH)
    assert resp.status_code == 409
    (record,) = _api_lines(caplog)
    assert record.levelno == logging.INFO
    assert record.getMessage() == f"api_error method=POST path=/api/jobs/{job.id}/retry status=409 code=E_JOB_STATE"
    assert "secret" not in caplog.text  # ไม่มี query string


def test_a_404_is_debug_only(env, caplog) -> None:
    with caplog.at_level(logging.DEBUG, logger="yttoolkit"):
        assert env.client.get("/api/nope").status_code == 404
    (record,) = _api_lines(caplog)
    assert record.levelno == logging.DEBUG  # root เป็น INFO ในแอพจริง: บรรทัดนี้ไม่ถูกเขียนลง app.log
    assert record.getMessage() == "api_error method=GET path=/api/nope status=404 code=E_NOT_FOUND"


def test_a_path_with_a_line_break_cannot_forge_a_log_line(env, caplog) -> None:
    with caplog.at_level(logging.INFO, logger="yttoolkit"):
        env.client.post("/api/videos/bad%0Aid/captures", json={"tMs": 0}, headers=AUTH)
    assert "bad\nid" not in caplog.text
    assert all("\n" not in r.getMessage() for r in _api_lines(caplog))


def test_success_and_non_api_paths_are_not_logged(env, caplog) -> None:
    with caplog.at_level(logging.DEBUG, logger="yttoolkit"):
        assert env.client.get("/api/ping").status_code == 200
        env.client.get("/no-such-page")
    assert _api_lines(caplog) == []


def test_an_unhandled_500_logs_a_warning_line_and_the_traceback_line(make_client, caplog) -> None:
    app = make_client().app

    @app.get("/api/test-boom")
    def boom():
        raise RuntimeError("kaboom")

    app.router.routes.insert(0, app.router.routes.pop())
    client = TestClient(app, base_url=BASE, raise_server_exceptions=False)
    with caplog.at_level(logging.INFO, logger="yttoolkit"):
        assert client.get("/api/test-boom").status_code == 500
    (line,) = _api_lines(caplog)
    assert line.levelno == logging.WARNING
    assert line.getMessage() == "api_error method=GET path=/api/test-boom status=500 code=E_UNKNOWN"
    traced = [r for r in caplog.records if r.exc_info]
    assert len(traced) == 1 and "code=E_UNKNOWN" in traced[0].getMessage()


def test_a_502_from_a_route_is_a_warning(make_client, caplog) -> None:
    app = make_client().app

    @app.get("/api/test-refused")
    def refused():
        return errors.error_response(502, "E_YT_REFUSED", "m", "detail-should-not-be-logged")

    app.router.routes.insert(0, app.router.routes.pop())
    with caplog.at_level(logging.INFO, logger="yttoolkit"):
        assert TestClient(app, base_url=BASE).get("/api/test-refused").status_code == 502
    (line,) = _api_lines(caplog)
    assert line.levelno == logging.WARNING and line.getMessage().endswith("status=502 code=E_YT_REFUSED")
    assert "detail-should-not-be-logged" not in caplog.text
