"""ค่าคุกกี้ของบัญชีชั่วคราวต้องอยู่ในหน่วยความจำเท่านั้น (M5 รอบ C spec 3 · แบบเดียวกับ AC-SET-06)

นำเข้าไฟล์ที่ค่าทุกตัว (และชื่อคุกกี้หนึ่งตัว) เป็น canary ที่ไม่ซ้ำกับอะไร แล้วใช้แอพเต็มชุดในโหมดข้อมูลปลอม
(open_services + create_app ตัวจริง คิวทำงานจริง ไม่ต่อเน็ต): probe ที่ใช้บัญชี งานที่ใช้บัญชีแล้วสำเร็จ
งานที่ใช้บัญชีแล้วพลาด /health และ GET /cookies · แล้วตรวจว่า canary ไม่อยู่ใน log (ทั้งที่จับได้และ app.log)
ข้อความที่พิมพ์ออกหน้าจอ (stdout/stderr: yt-dlp write_string ไม่ผ่าน logging) ข่าว SSE คำตอบของ API ทุกคำตอบ
และไม่มีไฟล์ใดในโฟลเดอร์ข้อมูลหรือโฟลเดอร์ temp ที่มี canary
(M6 รอบ B · AC-SET-06) รายงานแจ้งปัญหา POST /api/diagnostics ทั้งสามแบบ (งานที่พลาด error จากหน้าเว็บ หน้าตรวจสุขภาพ)
ผ่านเงื่อนไขเดียวกัน ไม่มีชื่อคุกกี้เลย และพูดถึงบัญชีแค่บรรทัดสถานะ
(M6 รอบ A spec 7.3) ไฟล์สำรองค่าตั้ง GET /api/settings/export และ GET /api/storage · POST /api/storage/clear
ตอนถือบัญชีอยู่ ผ่านเงื่อนไขเดียวกัน (การล้างต้องไม่เขียนข้อมูลคุกกี้ลงที่ใด ตรวจด้วยการเดินไฟล์ท้ายเทส)
"""

from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from yttoolkit import lifecycle, probe
from yttoolkit.app import AppContext, create_app
from yttoolkit.core.events import Event

PORT = 8787
TOKEN = "privacy-token"
BASE = f"http://127.0.0.1:{PORT}"
AUTH = {"X-Toolkit-Token": TOKEN, "Origin": BASE}
CANARIES = ("cnry-sapisid-5e1f0a", "cnry-3psid-77b2c4", "cnry-login-0d9e31", "cnry-name-a4f6e8", "cnry-pref-31c7d5")
ACCOUNT_FILE = (
    "# Netscape HTTP Cookie File\n"
    f".youtube.com\tTRUE\t/\tTRUE\t1999999999\tSAPISID\t{CANARIES[0]}\n"
    f"#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t1999999999\t__Secure-3PSID\t{CANARIES[1]}\n"
    f".youtube.com\tTRUE\t/\tTRUE\t1999999999\tLOGIN_INFO\t{CANARIES[2]}\n"
    f".youtube.com\tTRUE\t/\tFALSE\t1999999999\t{CANARIES[3]}\tx\n"
    f".google.com\tTRUE\t/\tFALSE\t0\tPREF\t{CANARIES[4]}\n"
)
VIDEO = {"maxQuality": False, "splitChapters": False, "noAudio": False, "audioLanguage": "original"}


def _assert_clean(text: str, where: str) -> None:
    for canary in CANARIES:
        assert canary not in text, f"{canary} หลุดไปที่ {where}"


def _wait_done(services, job_id: str, timeout: float = 20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = services.queue.store.get(job_id)
        if job is not None and job.status in ("done", "failed", "cancelled", "interrupted"):
            return job
        time.sleep(0.05)
    raise AssertionError(f"งาน {job_id} ไม่จบใน {timeout} วินาที")


@pytest.fixture
def app_env(paths, fake_platform, tmp_path, monkeypatch, caplog):
    temp_root = tmp_path / "temp-root"
    temp_root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp_root))  # ไฟล์ชั่วคราวทุกไฟล์ของโปรเซสนี้มาอยู่ที่นี่
    root = logging.getLogger()
    before = list(root.handlers)
    probe.setup_file_log(paths)  # app.log จริงพร้อมตัวกรอง (แบบเดียวกับ start)
    caplog.set_level(logging.DEBUG)
    monkeypatch.delenv(lifecycle.ACCOUNT_GRACE_ENV, raising=False)  # grace ที่ย่นไว้ในเชลล์ลบบัญชีก่อนเทสตรวจไม่ได้
    services = lifecycle.open_services(paths, fake_platform, fake=True)
    ctx = AppContext(
        paths=paths, plat=fake_platform, port=PORT, token=TOKEN, version="0.1.0", commit=None,
        output_dir=services.settings.output_dir(), request_shutdown=lambda: None,
        health=lambda: {"tools": {}, "disk": {}, "output": {}, "network": {}},
        db=services.db, videos=services.videos, extractor=services.extractor, cache_root=paths.cache, fake=True,
        subtitles=services.subtitles, settings=services.settings, queue=services.queue, events=services.events,
        media=services.media, pinned=services.pinned, on_bot_check=services.queue.brake,
    )  # fmt: skip
    ctx.captures = services.captures
    ctx.accounts = services.accounts
    client = TestClient(create_app(ctx), base_url=BASE)
    sub = services.events.subscribe()
    services.queue.start()
    try:
        yield services, client, sub, temp_root
    finally:
        lifecycle.shutdown_services(services, timeout=2.0)
        services.db.close()
        for handler in list(root.handlers):
            if handler not in before:
                root.removeHandler(handler)
                handler.close()


def test_canaries_never_leave_memory(app_env, paths, caplog, capsys) -> None:
    services, client, sub, temp_root = app_env
    bodies: list[str] = []

    def call(method: str, url: str, **kwargs) -> dict:
        resp = client.request(method, url, **kwargs)
        bodies.append(resp.text)
        return resp.json()

    status = call("POST", "/api/cookies/import", json={"text": ACCOUNT_FILE, "acceptWarning": True}, headers=AUTH)
    assert status["active"] is True
    call("POST", "/api/cookies/import", json={"text": "broken " + CANARIES[0], "acceptWarning": True}, headers=AUTH)
    assert call("GET", "/api/videos/ACCOUNTAGE1")["title"] == "คลิปจำกัดอายุ"  # probe ที่ใช้บัญชี
    private = call("GET", "/api/videos/PRIVATEVID1")  # บัญชีไม่มีสิทธิ์: ข้อความ "ลองด้วยบัญชีแล้ว..."
    assert private["error"]["code"] == "E_VIDEO_PRIVATE"
    jobs = call("POST", "/api/jobs", headers=AUTH, json={"items": [
        {"videoId": "ACCOUNTAGE1", "kind": "video", "params": VIDEO},
        {"videoId": "PRIVATEVID1", "kind": "video", "params": VIDEO},
    ]})["jobs"]  # fmt: skip
    done, failed = (_wait_done(services, job["id"]) for job in jobs)
    assert done.status == "done"
    assert failed.status == "failed" and failed.error_code == "E_VIDEO_PRIVATE"
    call("GET", "/api/jobs")
    call("GET", "/api/health")
    assert call("GET", "/api/cookies")["active"] is True
    # M6 รอบ B (AC-SET-06): รายงานแจ้งปัญหาตอนถือบัญชีอยู่ ทั้งงานที่พลาด error จากหน้าเว็บ และหน้าตรวจสุขภาพ
    reports = [
        call("POST", "/api/diagnostics", headers=AUTH, json={"jobId": failed.id})["report"],
        call("POST", "/api/diagnostics", headers=AUTH, json={
            "code": "E_VIDEO_PRIVATE", "detail": failed.error_detail or "-", "context": "video-header",
            "videoId": "PRIVATEVID1",
        })["report"],
        call("POST", "/api/diagnostics", headers=AUTH, json={})["report"],
    ]  # fmt: skip
    for report in reports:
        _assert_clean(report, "รายงานแจ้งปัญหา")
        for name in ("SAPISID", "__Secure-3PSID", "LOGIN_INFO", CANARIES[3]):
            assert name not in report, f"ชื่อคุกกี้ {name} อยู่ในรายงาน"
        # ส่วนหัวและหัวข้อ error พูดถึงบัญชีแค่บรรทัดสถานะ (log ล่าสุดเป็นบรรทัดของแอพเอง ผ่านกฎ canary เดียวกันแล้วด้านบน)
        head = report.split("### log ล่าสุด", 1)[0]
        assert [line for line in head.splitlines() if "บัญชี" in line] == ["- บัญชียูทูป: ใช้บัญชีชั่วคราวอยู่"]
    assert "- รหัส: E_VIDEO_PRIVATE · งาน: video (videoId PRIVATEVID1)" in reports[0]
    # M6 รอบ A (spec 7.3): ไฟล์สำรองค่าตั้ง และขนาด/ล้างข้อมูลชั่วคราว ตอนถือบัญชีอยู่ ไม่มีคุกกี้ ชื่อคุกกี้ หรือ token
    exported = client.get("/api/settings/export")
    bodies.append(exported.text)
    assert exported.status_code == 200 and exported.json()["app"] == "yt-toolkit"
    for name in ("SAPISID", "__Secure-3PSID", "LOGIN_INFO", CANARIES[3], TOKEN, "cookies"):
        assert name not in exported.text, f"{name} อยู่ในไฟล์สำรองค่าตั้ง"
    assert set(call("GET", "/api/storage")) == {"cacheBytes", "workBytes", "reclaimableBytes"}
    assert set(call("POST", "/api/storage/clear", headers=AUTH)) == {"freedBytes"}
    assert call("DELETE", "/api/cookies", headers=AUTH)["active"] is False

    for text in bodies:
        _assert_clean(text, "คำตอบของ API")
    events = []
    while isinstance(item := sub.get(0), Event):
        events.append(item)
    assert any(e.name == "account" for e in events)
    for event in events:
        _assert_clean(repr(event.data), f"ข่าว SSE {event.name}")
    for record in caplog.records:
        _assert_clean(record.getMessage(), "log")
        if record.exc_info:
            _assert_clean(logging.Formatter().formatException(record.exc_info), "traceback ใน log")
    for handler in logging.getLogger().handlers:
        handler.flush()
    log_file = paths.logs / "app.log"
    assert log_file.is_file()
    _assert_clean(log_file.read_text(encoding="utf-8"), "app.log")
    # ที่พิมพ์ตรงลง sys.stdout / sys.stderr โดยไม่ผ่าน logging (yt-dlp write_string อ่าน sys.stderr ตอนเรียก)
    # ใช้ capsys ไม่ใช่ capfd: capfd สร้างไฟล์ชั่วคราวของตัวเองทุกช่วงเทสต์ ซึ่งจะไปอยู่ใน temp ที่ตรวจและถูกล็อกไว้
    out, err = capsys.readouterr()
    _assert_clean(out, "stdout")
    _assert_clean(err, "stderr")

    for folder in (paths.data_root, temp_root):  # data/ work/ run/ cache/ output/ app.db และ temp
        for path in Path(folder).rglob("*"):
            _assert_clean(path.name, f"ชื่อไฟล์ {path.name}")
            if path.is_file():
                data = path.read_bytes()
                for canary in CANARIES:
                    assert canary.encode() not in data, f"{canary} อยู่ในไฟล์ {path.relative_to(folder)}"
