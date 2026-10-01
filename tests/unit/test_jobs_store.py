from datetime import UTC, datetime, timedelta
import pytest
from yttoolkit.core.db import Database
from yttoolkit.core.jobs import InvalidTransition, JobStore, NewJob, OutputFile, uuid7

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)

@pytest.fixture
def store(tmp_path):
    db = Database(tmp_path / "app.db"); db.migrate()
    clock = {"now": NOW}
    s = JobStore(db, now=lambda: clock["now"])
    s.clock = clock
    yield s
    db.close()

def add(store, n=1, kind="video"):
    return store.add([NewJob(f"vid{i:08d}", kind, {"maxQuality": False}, f"คลิป {i}") for i in range(n)])

def test_add_appends_positions_in_order(store):
    jobs = add(store, 3)
    assert [j.position for j in jobs] == [1, 2, 3]
    assert all(j.status == "queued" for j in jobs)
    assert [j.id for j in store.queued()] == [j.id for j in jobs]

def test_transition_rules(store):
    (job,) = add(store)
    running = store.transition(job.id, "running")
    assert running.started_at is not None
    with pytest.raises(InvalidTransition):
        store.transition(job.id, "running")          # running -> running is not a transition
    done = store.transition(job.id, "done", outputs=(OutputFile("C:/out", "a [x]/a.mp4", 10, "video"),), notes=("NO_SUBTITLES",))
    assert done.finished_at is not None and done.outputs[0].rel == "a [x]/a.mp4"
    with pytest.raises(InvalidTransition):
        store.transition(job.id, "queued")

def test_requeue_front_and_end(store):
    a, b, c = add(store, 3)
    store.transition(c.id, "running")
    front = store.requeue(c.id, front=True)
    assert front.status == "queued" and front.position < a.position
    store.transition(front.id, "running"); store.transition(front.id, "failed", error_code="E_NETWORK")
    end = store.requeue(front.id)
    assert end.position > b.position and end.error_code is None

def test_reorder_reuses_existing_slots(store):
    a, b, c, d = add(store, 4)
    store.reorder([d.id, b.id, "unknown"])
    order = [j.id for j in store.queued()]
    assert order == [a.id, d.id, c.id, b.id]

def test_interrupt_running_and_pending(store):
    a, b = add(store, 2)
    store.transition(a.id, "running")
    assert store.pending_count() == 2
    assert store.interrupt_running("งานหยุดกลางคันเพราะปิดโปรแกรม") == 1
    got = store.get(a.id)
    assert (got.status, got.error_code) == ("interrupted", "E_INTERRUPTED")
    assert store.pending_count() == 1

def test_default_list_windows(store):
    a, b, c = add(store, 3)
    for j in (a, b):
        store.transition(j.id, "running")
    store.transition(a.id, "done")
    store.clock["now"] = NOW + timedelta(hours=25)
    store.transition(b.id, "cancelled")
    ids = {j.id for j in store.list_default()}
    assert ids == {c.id}          # done older than 24 h and cancelled are hidden

def test_to_api_shape(store):
    (job,) = add(store)
    api = store.get(job.id).to_api()
    assert api == {"id": job.id, "videoId": "vid00000000", "title": "คลิป 0", "kind": "video",
                   "params": {"maxQuality": False}, "status": "queued", "position": 1, "createdAt": api["createdAt"]}

def test_uuid7_sorts_by_time():
    ids = [uuid7() for _ in range(50)]
    assert all(len(i) == 36 and i[14] == "7" for i in ids)
    assert ids == sorted(ids)


# ---- เพิ่มเติมจาก brief: ขอบของ contract C1/C2/C4 ----

def test_uuid7_variant_and_format():
    value = uuid7()
    assert value[19] in "89ab"
    assert [len(p) for p in value.split("-")] == [8, 4, 4, 4, 12]
    assert value == value.lower()


def test_unknown_job_raises_key_error(store):
    assert store.get("nope") is None
    with pytest.raises(KeyError):
        store.transition("nope", "running")
    with pytest.raises(KeyError):
        store.update("nope", progress=0.5)
    with pytest.raises(KeyError):
        store.requeue("nope")


def test_add_keeps_counting_after_jobs_finish(store):
    (a,) = add(store)
    store.transition(a.id, "cancelled")
    (b,) = add(store)
    assert b.position == 2


def test_add_rejects_unknown_kind(store):
    with pytest.raises(ValueError):
        store.add([NewJob("vid00000000", "playlist", {})])


def test_update_only_while_running(store):
    (job,) = add(store)
    with pytest.raises(InvalidTransition):
        store.update(job.id, progress=0.1)
    store.transition(job.id, "running")
    got = store.update(job.id, stage="downloading_video", progress=0.25, speed_bps=1000, eta_s=9,
                       attempt=1, title="ชื่อใหม่")
    assert (got.stage, got.progress, got.speed_bps, got.eta_s, got.attempt, got.title) == (
        "downloading_video", 0.25, 1000, 9, 1, "ชื่อใหม่")
    with pytest.raises(ValueError):
        store.update(job.id, status="done")
    with pytest.raises(ValueError):
        store.update(job.id, position=7)


def test_transition_rejects_unknown_status_and_fields(store):
    (job,) = add(store)
    with pytest.raises(InvalidTransition):
        store.transition(job.id, "paused")
    with pytest.raises(ValueError):
        store.transition(job.id, "running", position=3)
    assert store.get(job.id).status == "queued"


def test_failed_fields_round_trip_and_api_error(store):
    (job,) = add(store)
    store.transition(job.id, "running")
    failed = store.transition(job.id, "failed", error_code="E_NETWORK",
                              error_message="เน็ตหลุด ลองใหม่อีกครั้ง", error_detail="timed out")
    api = store.get(job.id).to_api()
    assert api["error"] == {"code": "E_NETWORK", "message": "เน็ตหลุด ลองใหม่อีกครั้ง", "detail": "timed out"}
    assert api["startedAt"] == failed.started_at and api["finishedAt"] == failed.finished_at
    assert failed.finished_at.endswith("+00:00")


def test_to_api_outputs_notes_and_attempt(store):
    (job,) = add(store)
    store.transition(job.id, "running")
    store.update(job.id, attempt=2)
    assert store.get(job.id).to_api()["attempt"] == 2
    store.transition(job.id, "done", progress=1.0, title="ชื่อจริง",
                     outputs=(OutputFile("C:/out", "ชื่อ [x]/ชื่อ.mp4", 10, "video"),
                              OutputFile("C:/out", "ชื่อ [x]/แหล่งที่มา.txt", 3, "subtitle")),
                     notes=("NO_SUBTITLES", "SOMETHING_UNKNOWN"))
    api = store.get(job.id).to_api()
    assert api["outputs"] == [{"index": 0, "name": "ชื่อ.mp4", "sizeBytes": 10},
                              {"index": 1, "name": "แหล่งที่มา.txt", "sizeBytes": 3}]
    assert api["notes"] == [{"code": "NO_SUBTITLES", "message": "คลิปนี้ไม่มีซับ"}]
    assert api["title"] == "ชื่อจริง" and api["progress"] == 1.0
    assert "C:/out" not in str(api)
    got = store.get(job.id)
    assert got.outputs[0] == OutputFile("C:/out", "ชื่อ [x]/ชื่อ.mp4", 10, "video")
    assert got.notes == ("NO_SUBTITLES", "SOMETHING_UNKNOWN")


def test_requeue_clears_run_state_but_keeps_bot_checks(store):
    (job,) = add(store)
    store.transition(job.id, "running")
    store.update(job.id, stage="merging", progress=0.5, attempt=1, bot_checks=1)
    again = store.requeue(job.id, front=True)
    assert (again.status, again.stage, again.progress, again.attempt, again.bot_checks) == (
        "queued", None, None, 0, 1)
    assert again.started_at is None and again.finished_at is None


def test_requeue_rejects_done_queued_and_cancelled(store):
    a, b, c = add(store, 3)
    store.transition(a.id, "running"); store.transition(a.id, "done")
    store.transition(c.id, "cancelled")
    for job_id in (a.id, b.id, c.id):
        with pytest.raises(InvalidTransition):
            store.requeue(job_id)


def test_requeue_front_with_empty_queue(store):
    a, b = add(store, 2)
    store.transition(a.id, "running"); store.transition(b.id, "running")
    front = store.requeue(a.id, front=True)
    assert front.status == "queued"
    assert [j.id for j in store.queued()] == [a.id]


def test_reorder_ignores_non_queued_and_duplicates(store):
    a, b, c = add(store, 3)
    store.transition(a.id, "running")
    store.reorder([c.id, a.id, c.id, b.id])
    assert [j.id for j in store.queued()] == [c.id, b.id]
    assert store.get(a.id).position == 1


def test_list_status_orders(store):
    a, b, c = add(store, 3)
    store.transition(b.id, "running")
    store.clock["now"] = NOW + timedelta(seconds=1)
    store.transition(a.id, "running")
    assert [j.id for j in store.list_status("running", 10)] == [b.id, a.id]
    assert [j.id for j in store.running()] == [b.id, a.id]
    store.transition(b.id, "done")
    store.clock["now"] = NOW + timedelta(seconds=2)
    store.transition(a.id, "done")
    assert [j.id for j in store.list_status("done", 10)] == [a.id, b.id]
    assert [j.id for j in store.list_status("done", 1)] == [a.id]
    assert [j.id for j in store.list_status("queued", 10)] == [c.id]
    with pytest.raises(ValueError):
        store.list_status("paused", 10)


def test_default_list_order_and_limits(store):
    jobs = add(store, 50)
    # 22 failed (ใน 7 วัน) + 22 done (ใน 24 ชม.) แต่ละกลุ่มเอาแค่ 20 ใหม่สุด
    for i, job in enumerate(jobs[:44]):
        store.clock["now"] = NOW + timedelta(minutes=i)
        store.transition(job.id, "running")
        store.transition(job.id, "failed" if i < 22 else "done")
    old_failed = jobs[44]
    store.clock["now"] = NOW - timedelta(days=8)
    store.transition(old_failed.id, "running"); store.transition(old_failed.id, "failed")
    store.clock["now"] = NOW + timedelta(hours=1)
    store.transition(jobs[46].id, "running")
    store.clock["now"] = NOW + timedelta(hours=1, seconds=1)
    store.transition(jobs[45].id, "running")
    listed = store.list_default()
    ids = [j.id for j in listed]
    assert ids[:2] == [jobs[46].id, jobs[45].id]                       # running by started_at
    assert ids[2:5] == [jobs[47].id, jobs[48].id, jobs[49].id]           # queued by position
    finished = listed[5:]
    assert sum(j.status == "failed" for j in finished) == 20
    assert sum(j.status == "done" for j in finished) == 20
    assert old_failed.id not in ids
    assert jobs[0].id not in ids and jobs[1].id not in ids              # oldest two failed cut by the 20 cap
    stamps = [j.finished_at for j in finished]
    assert stamps == sorted(stamps, reverse=True)


def test_interrupt_running_sets_message_and_finish_time(store):
    (job,) = add(store)
    store.transition(job.id, "running")
    store.interrupt_running("งานหยุดกลางคัน")
    got = store.get(job.id)
    assert got.error_message == "งานหยุดกลางคัน" and got.finished_at is not None
    again = store.requeue(job.id)
    assert again.status == "queued" and again.error_message is None


def test_store_survives_reopen(tmp_path):
    db = Database(tmp_path / "app.db"); db.migrate()
    (job,) = JobStore(db).add([NewJob("vid00000000", "audio", {"format": "mp3"}, "เพลง")])
    db.close()
    db = Database(tmp_path / "app.db"); db.migrate()
    try:
        got = JobStore(db).get(job.id)
        assert (got.kind, got.params, got.title, got.status) == ("audio", {"format": "mp3"}, "เพลง", "queued")
        assert got.created_at.endswith("+00:00")
    finally:
        db.close()
