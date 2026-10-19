"""คิวงานใน serve จริง (โหมดข้อมูลปลอม): โหลดจนเสร็จ กู้งานหลังโปรแกรมดับ (AC-Q-05) ข่าว SSE และปิดโปรแกรมขณะมีงาน

รันเซิร์ฟเวอร์จริงบน port 8850-8869 เท่านั้น (ห้ามแตะ 8787 ของเจ้าของ และ 8791 ของ preview) ปิดด้วย PID เท่านั้น
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest

from yttoolkit import lifecycle, runstate
from yttoolkit.config import Paths
from yttoolkit.platform import current

BBB = "aqz-KE-bpKQ"
BBB_TITLE = "Big Buck Bunny 60fps 4K - Official Blender Foundation Short Film"
SLOW = "SLOWDOWNLD1"  # 40 ขั้น x 250 ms = งานที่ใช้เวลาราว 10 วินาที (tests/fixtures/downloads/behaviors.json)
VIDEO_PARAMS = {"maxQuality": False, "splitChapters": False, "noAudio": False, "audioLanguage": "original"}
PORTS = range(8850, 8870)


def reap_when_it_exits(proc: subprocess.Popen) -> None:
    """เก็บโปรเซส serve ทันทีที่มันจบ (เธรดรอ proc.wait) ให้ pid_alive เห็นว่าแอพปิดแล้วเหมือนของจริง

    เทสต์นี้เป็นแม่ของ serve: บน macOS/Linux โปรเซสลูกที่จบแล้วแต่แม่ยังไม่ wait จะค้างเป็น zombie
    os.kill(pid, 0) ยังสำเร็จ lifecycle.stop จึงคิดว่าแอพยังเปิดอยู่และรอครบ STOP_WAIT_S ทุกครั้ง
    ของจริงไม่เป็นแบบนี้: คำสั่ง stop เป็นคนละโปรเซสกับแม่ของแอพ (Windows ไม่มี zombie เวลาจึงสั้นอยู่แล้ว)
    """
    threading.Thread(target=proc.wait, name="reap-serve", daemon=True).start()


class KillRecorder:
    """ส่งต่อทุกอย่างให้ platform จริง แต่จดไว้ว่า lifecycle.stop สั่ง kill หรือไม่

    แอพที่ปิดตัวเองช้ากว่า STOP_WAIT_S ถูก kill แล้วก็ยังออกด้วยรหัส 0 ได้ (uvicorn ออกเงียบ ๆ เมื่อโดน SIGTERM)
    เทสต์ที่ดูแค่รหัสออกกับเวลารวมจึงแยกไม่ออกว่าแอพปิดตัวเองเรียบร้อย หรือโดนบังคับปิด
    """

    def __init__(self, plat) -> None:
        self._plat = plat
        self.killed: list[int] = []

    def kill(self, pid: int) -> None:
        self.killed.append(pid)
        self._plat.kill(pid)

    def __getattr__(self, name: str):
        return getattr(self._plat, name)


class App:
    """serve หนึ่งรอบ (โปรเซสจริง) กับตัวช่วยเรียก API"""

    def __init__(self, data_root: Path) -> None:
        self.paths = Paths(data_root=data_root)
        self.plat = current()
        port = runstate.pick_port(PORTS)
        assert port in PORTS
        env = {
            **os.environ,
            "YT_TOOLKIT_DATA_ROOT": str(data_root),
            "YT_TOOLKIT_FAKE": "1",
            "YT_TOOLKIT_FFMPEG_PATH_LOOKUP": "0",
        }
        self.proc = subprocess.Popen([sys.executable, "-m", "yttoolkit", "serve", "--port", str(port)], env=env)
        reap_when_it_exits(self.proc)
        deadline = time.monotonic() + 30
        info = None
        while time.monotonic() < deadline and info is None:
            if self.proc.poll() is not None:
                break
            info = lifecycle.find_running(self.paths, self.plat)
            if info is None:
                time.sleep(0.2)
        assert info is not None, "serve ไม่ขึ้นภายใน 30 วินาที"
        assert info.port == port
        self.info = info
        self.base = lifecycle.base_url(port)
        self.headers = {"X-Toolkit-Token": info.token, "Origin": self.base}
        self.client = httpx.Client(base_url=self.base, headers=self.headers, timeout=10)

    def post_jobs(self, *items: dict) -> list[dict]:
        resp = self.client.post("/api/jobs", json={"items": list(items)})
        assert resp.status_code == 200, resp.text
        return resp.json()["jobs"]

    def job(self, job_id: str) -> dict | None:
        resp = self.client.get("/api/jobs")
        assert resp.status_code == 200, resp.text
        return next((j for j in resp.json()["jobs"] if j["id"] == job_id), None)

    def wait_job(self, job_id: str, done: Callable[[dict], bool], timeout: float = 30) -> dict:
        deadline = time.monotonic() + timeout
        job = None
        while time.monotonic() < deadline:
            job = self.job(job_id)
            if job is not None and done(job):
                return job
            time.sleep(0.2)
        raise AssertionError(f"งาน {job_id} ไม่ถึงสถานะที่รอภายใน {timeout} วินาที (ล่าสุด: {job})")

    def close(self) -> None:
        self.client.close()
        if self.proc.poll() is None:
            if self.plat.pid_alive(self.info.pid):
                self.plat.kill(self.info.pid)
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=10)


@contextmanager
def serve(data_root: Path) -> Iterator[App]:
    app = App(data_root)
    try:
        yield app
    finally:
        app.close()


def video_item(video_id: str) -> dict:
    return {"videoId": video_id, "kind": "video", "params": VIDEO_PARAMS}


def is_status(*statuses: str) -> Callable[[dict], bool]:
    return lambda job: job["status"] in statuses


def work_children(paths: Paths) -> list[Path]:
    return list(paths.work.iterdir()) if paths.work.exists() else []


def test_video_job_runs_to_done_and_lands_in_output_folder(tmp_path):
    with serve(tmp_path) as app:
        (job,) = app.post_jobs(video_item(BBB))
        assert job["status"] == "queued"
        done = app.wait_job(job["id"], is_status("done", "failed", "interrupted"))
        assert done["status"] == "done", done
        assert done["title"] == BBB_TITLE
        folders = [p for p in (tmp_path / "output").iterdir() if p.is_dir()]
        assert len(folders) == 1
        folder = folders[0]
        assert folder.name.endswith(f" [{BBB}]") and folder.name.startswith("Big Buck Bunny")
        assert [p.name for p in folder.glob("*.mp4")], list(folder.iterdir())
        assert all(p.stat().st_size > 0 for p in folder.glob("*.mp4"))
        assert (folder / "แหล่งที่มา.txt").is_file()
        assert work_children(app.paths) == []
        assert len(done["outputs"]) == 1 and done["outputs"][0]["name"].endswith(".mp4")
        assert (folder / done["outputs"][0]["name"]).is_file()
        # ชื่อในประวัติมาจากแถวของคลิปที่ handler probe ไว้ (คลิปที่ไม่เคยเปิดใน W2)
        history = app.client.get("/api/history", params={"scope": "all"}).json()["items"]
        assert any(item["videoId"] == BBB and item["title"] == BBB_TITLE for item in history)


def test_job_running_when_app_dies_is_interrupted_after_restart_and_can_retry(tmp_path):  # AC-Q-05
    with serve(tmp_path) as app:
        (job,) = app.post_jobs(video_item(SLOW))
        app.wait_job(job["id"], lambda j: j["status"] == "running" and (j.get("progress") or 0) > 0)
        assert work_children(app.paths) != []  # มีไฟล์ระหว่างทำค้างอยู่ตอนโปรแกรมดับ
        app.plat.kill(app.info.pid)  # โปรแกรมดับกะทันหัน (ไม่ได้ปิดตามขั้นตอน)
        app.proc.wait(timeout=15)
    with serve(tmp_path) as app:
        stopped = app.job(job["id"])
        assert stopped is not None
        assert stopped["status"] == "interrupted"
        assert stopped["error"]["code"] == "E_INTERRUPTED"
        assert work_children(app.paths) == []
        resp = app.client.post(f"/api/jobs/{job['id']}/retry")
        assert resp.status_code == 200, resp.text
        again = app.wait_job(job["id"], is_status("running", "done"))
        assert again["status"] in ("running", "done")
        assert again.get("error") is None


def test_events_stream_receives_job_created(tmp_path):
    with serve(tmp_path) as app:
        timeout = httpx.Timeout(10, read=5)
        with httpx.stream("GET", f"{app.base}/api/events", headers=app.headers, timeout=timeout) as stream:
            assert stream.status_code == 200
            assert stream.headers["content-type"].startswith("text/event-stream")
            lines = stream.iter_lines()
            assert next(lines).startswith("retry:")  # สตรีมเปิดแล้ว ผู้ฟังลงทะเบียนกับ bus แล้ว
            (job,) = app.post_jobs(video_item(BBB))
            deadline = time.monotonic() + 10
            event = None
            for line in lines:
                if event == "job.created" and line.startswith("data:") and job["id"] in line:
                    break
                if line.startswith("event:"):
                    event = line.split(":", 1)[1].strip()
                assert time.monotonic() < deadline, "ไม่ได้ข่าว job.created ภายใน 10 วินาที"
            else:
                pytest.fail("สตรีมจบก่อนได้ข่าว job.created")


def test_stop_with_running_job_exits_and_job_is_interrupted(tmp_path):
    with serve(tmp_path) as app:
        (job,) = app.post_jobs(video_item(SLOW))
        app.wait_job(job["id"], is_status("running"))
        asked: list[str] = []
        plat = KillRecorder(app.plat)
        started = time.monotonic()
        code = lifecycle.stop(app.paths, plat, ask=lambda q: asked.append(q) or "y", out=lambda m: None)
        elapsed = time.monotonic() - started
        assert code == 0
        # แอพปิดตัวเองเรียบร้อยภายในเวลาที่ stop รอ (ออกแบบไว้ราว 8.5 วินาทีเมื่อแย่ที่สุด) ไม่ใช่โดน kill ตอนครบ STOP_WAIT_S
        assert plat.killed == []
        assert elapsed < lifecycle.STOP_WAIT_S
        assert app.proc.wait(timeout=15) == 0
        assert asked and "1" in asked[0]  # ถามยืนยันเพราะมีงานค้าง
        assert not app.plat.pid_alive(app.info.pid)
        assert not app.paths.app_json.exists()
    with serve(tmp_path) as app:
        stopped = app.job(job["id"])
        assert stopped is not None
        assert stopped["status"] == "interrupted"
        assert stopped["error"]["code"] == "E_INTERRUPTED"
        assert work_children(app.paths) == []
