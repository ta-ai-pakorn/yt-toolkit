import os

import httpx

from yttoolkit import lifecycle, runstate
from yttoolkit.core import tools
from yttoolkit.runstate import RunInfo


class FakeResponse:
    def __init__(self, status_code: int, body: dict | None = None):
        self.status_code = status_code
        self._body = body or {}

    def json(self) -> dict:
        return self._body


def _running(paths, fake_platform, pid=4242, port=8787, holds_lock=True) -> RunInfo:
    info = RunInfo(port=port, pid=pid, token="tok", started_at="x")
    runstate.write(paths.app_json, info)
    fake_platform.alive.add(pid)
    if holds_lock:  # แอพที่รันอยู่จริงถือ run/app.lock ไว้ตลอดอายุ
        fake_platform.locked.add(paths.run / "app.lock")
    return info


def test_base_url():
    assert lifecycle.base_url(8787) == "http://127.0.0.1:8787"


def test_is_alive_handles_errors():
    def boom(url, timeout):
        raise httpx.ConnectError("refused")

    assert lifecycle.is_alive(8787, get=boom) is False
    assert lifecycle.is_alive(8787, get=lambda url, timeout: FakeResponse(200)) is True


def test_find_running_ignores_stale_file(paths, fake_platform):
    runstate.write(paths.app_json, RunInfo(8787, 999, "t", "x"))
    assert lifecycle.find_running(paths, fake_platform, alive=lambda port: True) is None


def test_find_running_detects_live_instance(paths, fake_platform):
    info = _running(paths, fake_platform)
    assert lifecycle.find_running(paths, fake_platform, alive=lambda port: True) == info
    assert lifecycle.find_running(paths, fake_platform, alive=lambda port: False) is None


def test_default_output_dir(fake_platform):
    assert lifecycle.default_output_dir(fake_platform) == fake_platform.downloads / "YT-Toolkit"


def test_prepare_environment_puts_scripts_first(monkeypatch):
    monkeypatch.setenv("PATH", "somewhere")
    lifecycle.prepare_environment()
    assert os.environ["PATH"].split(os.pathsep)[0] == str(tools.scripts_dir())


def test_server_binds_localhost_only(paths, fake_platform):  # AC-SEC-01
    from yttoolkit.app import AppContext

    ctx = AppContext(paths, fake_platform, 8787, "t", "0.1.0", None, paths.data_root, lambda: None)
    assert lifecycle.Server(ctx).config.host == "127.0.0.1"


def test_start_waits_for_other_starter_and_opens_browser(paths, fake_platform, monkeypatch):  # FR-LIFE-2
    fake_platform.locked.add(paths.run / "app.lock")  # อีกโปรเซสถือ lock อยู่ก่อนแล้ว
    info = RunInfo(port=8787, pid=123, token="t", started_at="x")
    responses = iter([None, None, info])

    def fake_find_running(p, pl):
        return next(responses)

    monkeypatch.setattr(lifecycle, "find_running", fake_find_running)
    opened = []
    monkeypatch.setattr(lifecycle.webbrowser, "open", opened.append)

    def run_app_must_not_be_called(**kwargs):
        raise AssertionError("run_app ไม่ควรถูกเรียกตอนรอโปรเซสอื่นเปิดอยู่")

    monkeypatch.setattr(lifecycle, "run_app", run_app_must_not_be_called)

    result = lifecycle.start(paths, fake_platform, wait_timeout=1.0, sleep=lambda s: None)
    assert result == 0
    assert opened == ["http://127.0.0.1:8787"]


def test_start_gives_up_when_other_starter_never_finishes(paths, fake_platform, monkeypatch):  # FR-LIFE-2
    fake_platform.locked.add(paths.run / "app.lock")  # อีกโปรเซสถือ lock อยู่ก่อนแล้ว
    monkeypatch.setattr(lifecycle, "find_running", lambda p, pl: None)
    opened = []
    monkeypatch.setattr(lifecycle.webbrowser, "open", opened.append)

    def run_app_must_not_be_called(**kwargs):
        raise AssertionError("run_app ไม่ควรถูกเรียกตอนหาโปรเซสอื่นไม่เจอ")

    monkeypatch.setattr(lifecycle, "run_app", run_app_must_not_be_called)

    result = lifecycle.start(paths, fake_platform, wait_timeout=0.05, sleep=lambda s: None)
    assert result == 1
    assert opened == []


def test_stop_when_not_running(paths, fake_platform):
    out = []
    assert lifecycle.stop(paths, fake_platform, out=out.append) == 0
    assert out == ["YT Toolkit ไม่ได้เปิดอยู่"]


def test_stop_graceful(paths, fake_platform):
    info = _running(paths, fake_platform)
    posts = []

    def post(url, json, headers, timeout):
        posts.append((url, json, headers))
        fake_platform.alive.discard(info.pid)  # แอพปิดตัวเอง
        return FakeResponse(200, {"ok": True})

    out = []
    assert lifecycle.stop(paths, fake_platform, post=post, sleep=lambda s: None, out=out.append) == 0
    url, body, headers = posts[0]
    assert url == "http://127.0.0.1:8787/api/shutdown"
    assert body == {"force": False}
    assert headers == {"X-Toolkit-Token": "tok", "Origin": "http://127.0.0.1:8787"}
    assert fake_platform.killed == []
    assert not paths.app_json.exists()
    assert out == ["ปิดโปรแกรมแล้ว"]


def test_stop_pending_user_declines(paths, fake_platform):
    _running(paths, fake_platform)
    result = lifecycle.stop(
        paths,
        fake_platform,
        post=lambda url, json, headers, timeout: FakeResponse(409, {"pendingJobs": 2}),
        ask=lambda prompt: "n",
        sleep=lambda s: None,
        out=lambda msg: None,
    )
    assert result == 1
    assert fake_platform.killed == []
    assert paths.app_json.exists()


def test_stop_pending_user_confirms_forces(paths, fake_platform):
    info = _running(paths, fake_platform)
    bodies = []

    def post(url, json, headers, timeout):
        bodies.append(json)
        if json["force"]:
            fake_platform.alive.discard(info.pid)
            return FakeResponse(200, {"ok": True})
        return FakeResponse(409, {"pendingJobs": 1})

    prompts = []

    def ask(prompt):
        prompts.append(prompt)
        return "Y"

    assert lifecycle.stop(paths, fake_platform, post=post, ask=ask, sleep=lambda s: None, out=lambda m: None) == 0
    assert bodies == [{"force": False}, {"force": True}]
    assert prompts == ["มีงานค้าง 1 งาน ปิดเลยไหม (Y/N) "]


def test_stop_kills_when_app_does_not_exit(paths, fake_platform):
    info = _running(paths, fake_platform, holds_lock=True)
    result = lifecycle.stop(
        paths,
        fake_platform,
        post=lambda url, json, headers, timeout: FakeResponse(200, {"ok": True}),
        sleep=lambda s: None,
        out=lambda m: None,
    )
    assert result == 0
    assert fake_platform.killed == [info.pid]


def test_stop_kills_when_api_unreachable(paths, fake_platform):
    info = _running(paths, fake_platform, holds_lock=True)

    def refused(url, json, headers, timeout):
        raise httpx.ConnectError("refused")

    lifecycle.stop(paths, fake_platform, post=refused, sleep=lambda s: None, out=lambda m: None)
    assert fake_platform.killed == [info.pid]


def test_stop_does_not_kill_reused_pid_when_lock_is_free(paths, fake_platform):
    # app.json ค้างจากตอนเครื่องดับ แล้ว Windows เอา pid เดิมไปให้โปรแกรมอื่น (เช่น Excel)
    info = _running(paths, fake_platform, holds_lock=False)

    def post_must_not_be_called(url, json, headers, timeout):
        raise AssertionError("ไม่ควรเรียก /api/shutdown เมื่อไม่มีแอพถือ lock")

    out = []
    result = lifecycle.stop(paths, fake_platform, post=post_must_not_be_called, sleep=lambda s: None, out=out.append)
    assert result == 0
    assert fake_platform.killed == []
    assert info.pid in fake_platform.alive
    assert not paths.app_json.exists()
    assert out == ["YT Toolkit ไม่ได้เปิดอยู่"]
    assert fake_platform.locked == set()  # ปล่อย lock คืนทันที


def test_stop_does_not_kill_when_lock_frees_during_wait(paths, fake_platform):
    info = _running(paths, fake_platform, holds_lock=True)
    lock = paths.run / "app.lock"

    def sleep(seconds):
        fake_platform.locked.discard(lock)  # แอพปิดตัวและปล่อย lock ระหว่างรอ แต่ pid ยังไม่หายทันที

    out = []
    result = lifecycle.stop(
        paths,
        fake_platform,
        post=lambda url, json, headers, timeout: FakeResponse(200, {"ok": True}),
        sleep=sleep,
        out=out.append,
    )
    assert result == 0
    assert fake_platform.killed == []
    assert info.pid in fake_platform.alive
    assert not paths.app_json.exists()
    assert fake_platform.locked == set()
