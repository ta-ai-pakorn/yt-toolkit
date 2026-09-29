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
    assert lifecycle.find_running(paths, fake_platform, alive=lambda port, pid: True) is None


def test_find_running_detects_live_instance(paths, fake_platform):
    info = _running(paths, fake_platform)
    assert lifecycle.find_running(paths, fake_platform, alive=lambda port, pid: True) == info
    assert lifecycle.find_running(paths, fake_platform, alive=lambda port, pid: False) is None


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


# ---- M1 follow-ups: Task 1 ----------------------------------------------------------------------------------------


class FakeServer:
    """แทน lifecycle.Server ในเทสที่ไม่ต้องการ uvicorn จริง"""

    def __init__(self, ready: bool = True):
        self.ready = ready
        self.started = False
        self.stopped = False
        self.joined: list[float | None] = []

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def join(self, timeout: float | None = None) -> None:
        self.joined.append(timeout)

    def wait_until_ready(self, timeout: float = 15.0) -> bool:
        return self.ready


def test_start_clears_stale_app_json_before_run_app(paths, fake_platform, monkeypatch):  # item 1
    runstate.write(paths.app_json, RunInfo(port=8787, pid=999, token="old", started_at="old"))
    seen = {}

    def fake_run_app(**kwargs):
        seen["app_json_exists"] = paths.app_json.exists()
        seen["locked"] = (paths.run / "app.lock") in fake_platform.locked
        return 0

    monkeypatch.setattr(lifecycle, "run_app", fake_run_app)
    assert lifecycle.start(paths, fake_platform, sleep=lambda s: None) == 0
    assert seen == {"app_json_exists": False, "locked": True}
    assert fake_platform.locked == set()


def test_serve_clears_stale_app_json_before_run_app(paths, fake_platform, monkeypatch):  # item 1
    runstate.write(paths.app_json, RunInfo(port=8787, pid=999, token="old", started_at="old"))
    seen = {}

    def fake_run_app(**kwargs):
        seen["app_json_exists"] = paths.app_json.exists()
        return 0

    monkeypatch.setattr(lifecycle, "default_paths", lambda: paths)
    monkeypatch.setattr(lifecycle, "current", lambda: fake_platform)
    monkeypatch.setattr(lifecycle, "run_app", fake_run_app)
    assert lifecycle.serve(port=9000) == 0
    assert seen == {"app_json_exists": False}
    assert fake_platform.locked == set()


def test_start_takes_over_when_lock_frees_during_wait(paths, fake_platform, monkeypatch):  # item 2
    lock = paths.run / "app.lock"
    fake_platform.locked.add(lock)  # อีกโปรเซสถือ lock อยู่ แล้วตายไประหว่างรอ โดยไม่เคยเขียน app.json
    runstate.write(paths.app_json, RunInfo(port=8787, pid=999, token="old", started_at="old"))
    monkeypatch.setattr(lifecycle, "find_running", lambda p, pl: None)
    opened = []
    monkeypatch.setattr(lifecycle.webbrowser, "open", opened.append)
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            fake_platform.locked.discard(lock)  # lock ว่างระหว่างรอ

    calls = {}

    def fake_run_app(**kwargs):
        calls["app_json_exists"] = paths.app_json.exists()
        calls["locked"] = lock in fake_platform.locked
        return 0

    monkeypatch.setattr(lifecycle, "run_app", fake_run_app)
    assert lifecycle.start(paths, fake_platform, wait_timeout=100.0, sleep=sleep) == 0
    assert len(sleeps) == 2
    assert calls == {"app_json_exists": False, "locked": True}
    assert opened == []
    assert fake_platform.locked == set()  # เจ้าของใหม่ปล่อย lock ตอนจบ


def test_stop_does_not_kill_when_app_json_was_replaced(paths, fake_platform):  # item 3
    info = _running(paths, fake_platform, holds_lock=True)
    newer = RunInfo(port=8788, pid=7777, token="new", started_at="newer")

    def sleep(seconds):
        runstate.write(paths.app_json, newer)  # แอพเดิมปิด แล้วมีอินสแตนซ์ใหม่เขียน app.json ทับ

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
    assert runstate.read(paths.app_json) == newer  # ห้ามลบ app.json ของอินสแตนซ์ใหม่
    assert out == ["YT Toolkit ไม่ได้เปิดอยู่"]


def test_stop_does_not_kill_when_same_pid_but_different_started_at(paths, fake_platform):  # item 3
    info = _running(paths, fake_platform, holds_lock=True)
    reused = RunInfo(port=info.port, pid=info.pid, token="new", started_at="later")

    def sleep(seconds):
        runstate.write(paths.app_json, reused)

    out = []
    lifecycle.stop(
        paths,
        fake_platform,
        post=lambda url, json, headers, timeout: FakeResponse(200, {"ok": True}),
        sleep=sleep,
        out=out.append,
    )
    assert fake_platform.killed == []
    assert runstate.read(paths.app_json) == reused
    assert out == ["YT Toolkit ไม่ได้เปิดอยู่"]


def test_stop_does_not_kill_when_app_json_vanished(paths, fake_platform):  # item 3
    _running(paths, fake_platform, holds_lock=True)

    def sleep(seconds):
        runstate.clear(paths.app_json)

    out = []
    lifecycle.stop(
        paths,
        fake_platform,
        post=lambda url, json, headers, timeout: FakeResponse(200, {"ok": True}),
        sleep=sleep,
        out=out.append,
    )
    assert fake_platform.killed == []
    assert out == ["YT Toolkit ไม่ได้เปิดอยู่"]


def test_stop_does_not_clear_newer_app_json_after_graceful_exit(paths, fake_platform):  # item 3
    info = _running(paths, fake_platform)
    newer = RunInfo(port=8788, pid=7777, token="new", started_at="newer")

    def post(url, json, headers, timeout):
        fake_platform.alive.discard(info.pid)  # แอพเดิมปิดตัวเอง
        runstate.write(paths.app_json, newer)  # และอินสแตนซ์ใหม่เขียนทับทันที
        return FakeResponse(200, {"ok": True})

    lifecycle.stop(paths, fake_platform, post=post, sleep=lambda s: None, out=lambda m: None)
    assert runstate.read(paths.app_json) == newer


def _run_app_kwargs(paths, fake_platform):
    return {
        "paths": paths,
        "plat": fake_platform,
        "port": 8787,
        "with_tray": False,
        "open_browser": False,
        "auto_ffmpeg": False,
    }


def test_run_app_cleans_up_after_startup_timeout(paths, fake_platform, monkeypatch, caplog):  # item 4
    server = FakeServer(ready=False)
    monkeypatch.setattr(lifecycle, "Server", lambda ctx: server)
    runstate.write(paths.app_json, RunInfo(port=1, pid=1, token="t", started_at="x"))
    with caplog.at_level("ERROR", logger="yttoolkit"):
        assert lifecycle.run_app(**_run_app_kwargs(paths, fake_platform)) == 1
    assert server.started and server.stopped
    assert len(server.joined) == 1 and server.joined[0] is not None  # join แบบมี timeout สั้น ๆ
    assert not paths.app_json.exists()
    assert "เปิดเซิร์ฟเวอร์ไม่สำเร็จ" in caplog.text


def test_start_releases_lock_after_startup_timeout(paths, fake_platform, monkeypatch):  # item 4
    server = FakeServer(ready=False)
    monkeypatch.setattr(lifecycle, "Server", lambda ctx: server)
    monkeypatch.setenv("YT_TOOLKIT_TRAY", "0")
    monkeypatch.setenv("YT_TOOLKIT_OPEN_BROWSER", "0")
    assert lifecycle.start(paths, fake_platform, sleep=lambda s: None) != 0
    assert server.stopped
    assert not paths.app_json.exists()
    assert fake_platform.locked == set()  # ปล่อย lock คืน เปิดใหม่ได้ทันที


def test_setup_file_logging_uses_rotating_handler(paths):  # item 6
    import logging
    import logging.handlers

    root = logging.getLogger()
    before = list(root.handlers)
    level = root.level
    try:
        lifecycle.setup_file_logging(paths)
        added = [h for h in root.handlers if h not in before]
        assert len(added) == 1
        handler = added[0]
        assert isinstance(handler, logging.handlers.RotatingFileHandler)
        assert handler.maxBytes == 1_000_000
        assert handler.backupCount == 3
        assert handler.encoding == "utf-8"
        assert handler.baseFilename == str((paths.logs / "app.log").resolve())
    finally:
        for h in list(root.handlers):
            if h not in before:
                root.removeHandler(h)
                h.close()
        root.setLevel(level)


def test_wait_succeeds_when_instance_answers(paths, fake_platform, monkeypatch):  # item 7
    info = RunInfo(port=8790, pid=1, token="t", started_at="x")
    responses = iter([None, None, info])
    monkeypatch.setattr(lifecycle, "find_running", lambda p, pl: next(responses))
    sleeps = []
    out = []
    assert lifecycle.wait(paths, fake_platform, timeout=25, sleep=sleeps.append, out=out.append) == 0
    assert sleeps == [0.5, 0.5]
    assert out == ["เปิด YT Toolkit แล้ว ที่ http://127.0.0.1:8790"]


def test_wait_times_out_with_log_path(paths, fake_platform, monkeypatch):  # item 7
    monkeypatch.setattr(lifecycle, "find_running", lambda p, pl: None)
    out = []
    assert lifecycle.wait(paths, fake_platform, timeout=0.05, sleep=lambda s: None, out=out.append) == 1
    expected = str((paths.logs / "app.log").absolute())
    assert out == [f"เปิดโปรแกรมไม่สำเร็จ ดูรายละเอียดได้ที่ {expected}"]


def test_wait_timeout_zero_checks_exactly_once(paths, fake_platform, monkeypatch):  # item 7
    calls = []

    def find(p, pl):
        calls.append(1)

    monkeypatch.setattr(lifecycle, "find_running", find)
    sleeps = []
    out = []
    assert lifecycle.wait(paths, fake_platform, timeout=0, sleep=sleeps.append, out=out.append) == 1
    assert len(calls) == 1
    assert sleeps == []
    assert out[0].startswith("เปิดโปรแกรมไม่สำเร็จ")

    info = RunInfo(port=8787, pid=1, token="t", started_at="x")
    monkeypatch.setattr(lifecycle, "find_running", lambda p, pl: info)
    assert lifecycle.wait(paths, fake_platform, timeout=0, sleep=sleeps.append, out=out.append) == 0


def test_cli_wait_passes_timeout(monkeypatch):  # item 7
    from yttoolkit import __main__ as cli

    seen = []
    monkeypatch.setattr(lifecycle, "wait", lambda **kw: seen.append(kw) or 0)
    assert cli.main(["wait"]) == 0
    assert cli.main(["wait", "--timeout", "0"]) == 0
    assert cli.main(["wait", "--timeout", "3.5"]) == 0
    assert [kw["timeout"] for kw in seen] == [25.0, 0.0, 3.5]


# ---- M1 follow-ups: Task 1 fix round 1 ----------------------------------------------------------------------------


def test_stop_early_branch_does_not_clear_replaced_app_json(paths, fake_platform):  # fix round 1, item 2
    _running(paths, fake_platform, holds_lock=False)  # ล็อกว่าง = ไม่มีแอพเปิดอยู่
    newer = RunInfo(port=8788, pid=7777, token="new", started_at="newer")
    real_try_lock = fake_platform.try_lock

    def try_lock(path):
        runstate.write(paths.app_json, newer)  # อินสแตนซ์ใหม่เขียน app.json ทันทีหลังเราเช็ก lock
        return real_try_lock(path)

    fake_platform.try_lock = try_lock
    out = []
    assert lifecycle.stop(paths, fake_platform, out=out.append) == 0
    assert runstate.read(paths.app_json) == newer
    assert out == ["YT Toolkit ไม่ได้เปิดอยู่"]


def test_is_alive_checks_ping_pid():  # fix round 1, item 3
    class Ping:
        status_code = 200

        def __init__(self, pid):
            self._pid = pid

        def json(self):
            return {"ok": True, "pid": self._pid}

    assert lifecycle.is_alive(8787, 42, get=lambda url, timeout: Ping(42)) is True
    assert lifecycle.is_alive(8787, 42, get=lambda url, timeout: Ping(43)) is False
    assert lifecycle.is_alive(8787, 42, get=lambda url, timeout: FakeResponse(200, {"ok": True})) is False
    assert lifecycle.is_alive(8787, get=lambda url, timeout: FakeResponse(200)) is True  # ไม่ระบุ pid = เช็กแค่ตอบกลับ


def test_find_running_rejects_instance_whose_ping_reports_other_pid(paths, fake_platform):  # item 3
    _running(paths, fake_platform, pid=4242, port=8787)

    class Ping:
        status_code = 200

        def json(self):
            return {"ok": True, "pid": 9999}  # พอร์ตนี้มีโปรแกรมอื่นตอบ ไม่ใช่แอพตาม app.json

    def alive(port, pid):
        return lifecycle.is_alive(port, pid, get=lambda url, timeout: Ping())

    assert lifecycle.find_running(paths, fake_platform, alive=alive) is None


def test_git_commit_passes_platform_popen_flags(monkeypatch, tmp_path, fake_platform):
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured.update(kwargs)

        class Out:
            stdout = "abc1234\n"

        return Out()

    monkeypatch.setattr(lifecycle.subprocess, "run", fake_run)
    fake_platform.popen_flags = 0x1234
    assert lifecycle.git_commit(tmp_path, fake_platform) == "abc1234"
    assert captured["creationflags"] == 0x1234
