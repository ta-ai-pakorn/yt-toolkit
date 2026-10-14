from datetime import UTC, datetime, timedelta
import pytest
from yttoolkit.core.db import Database
from yttoolkit.core.jobs import NOTES, InvalidTransition, JobStore, NewJob, OutputFile, count_stage, is_stage, note_api, split_stage, uuid7, valued_note

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
    with pytest.raises(ValueError):
        store.update(job.id, bot_checks=1)          # bot_checks goes through requeue() only


def test_update_title_none_keeps_title(store):
    (job,) = add(store)
    store.transition(job.id, "running")
    got = store.update(job.id, title=None, progress=0.5)
    assert (got.title, got.progress) == ("คลิป 0", 0.5)
    done = store.transition(job.id, "done", title=None)
    assert done.title == "คลิป 0"


def test_transition_rejects_unknown_status_and_fields(store):
    (job,) = add(store)
    with pytest.raises(ValueError):
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


def test_requeue_clears_run_state_and_sets_bot_checks_at_once(store):
    a, b = add(store, 2)
    store.transition(b.id, "running")
    store.update(b.id, stage="merging", progress=0.5, attempt=1)
    again = store.requeue(b.id, front=True, bot_checks=1)       # Q1: one transaction
    assert (again.status, again.stage, again.progress, again.attempt, again.bot_checks) == (
        "queued", None, None, 0, 1)
    assert again.started_at is None and again.finished_at is None
    assert again.position < a.position


def test_requeue_keeps_bot_checks_unless_reset(store):
    (job,) = add(store)
    store.transition(job.id, "running")
    store.requeue(job.id, front=True, bot_checks=1)
    store.transition(job.id, "running")
    store.transition(job.id, "failed", error_code="E_BOT_CHECK")
    kept = store.requeue(job.id)
    assert kept.bot_checks == 1
    store.transition(job.id, "running")
    store.transition(job.id, "failed", error_code="E_BOT_CHECK")
    retried = store.requeue(job.id, reset_bot_checks=True)     # manual retry
    assert retried.bot_checks == 0
    with pytest.raises(ValueError):
        store.requeue(job.id, bot_checks=1, reset_bot_checks=True)


def test_transition_to_queued_points_to_requeue(store):
    a, b, c = add(store, 3)
    store.transition(c.id, "running"); store.interrupt_running("หยุด")
    store.transition(a.id, "running")
    store.transition(b.id, "running"); store.transition(b.id, "failed")
    for job_id in (a.id, b.id, c.id):
        with pytest.raises(InvalidTransition, match="requeue"):
            store.transition(job_id, "queued")
    assert [store.get(j).status for j in (a.id, b.id, c.id)] == ["running", "failed", "interrupted"]


@pytest.mark.parametrize("to", ["done", "failed", "cancelled", "interrupted"])
def test_stopping_clears_run_fields(store, to):
    (job,) = add(store)
    store.transition(job.id, "running")
    store.update(job.id, stage="merging", progress=0.7, speed_bps=500, eta_s=4, attempt=2)
    got = store.transition(job.id, to)
    assert (got.stage, got.speed_bps, got.eta_s, got.attempt, got.progress) == (None, None, None, 0, 0.7)
    assert "attempt" not in got.to_api() and "speedBps" not in got.to_api()


def test_stopping_keeps_explicit_run_fields(store):
    (job,) = add(store)
    store.transition(job.id, "running")
    store.update(job.id, stage="merging", speed_bps=500, eta_s=4, attempt=3)
    got = store.transition(job.id, "failed", stage="writing", attempt=3, error_code="E_NETWORK")
    assert (got.stage, got.attempt, got.speed_bps, got.eta_s) == ("writing", 3, None, None)


def test_interrupt_running_clears_run_fields(store):
    (job,) = add(store)
    store.transition(job.id, "running")
    store.update(job.id, stage="downloading_audio", speed_bps=500, eta_s=4, attempt=1)
    store.interrupt_running("หยุด")
    got = store.get(job.id)
    assert (got.stage, got.speed_bps, got.eta_s, got.attempt) == (None, None, None, 0)


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


def test_m5a_stages_are_stored(store):
    (job,) = add(store)
    store.transition(job.id, "running")
    for stage in ("cutting", "cutting_ads", split_stage(3, 12)):
        assert store.update(job.id, stage=stage).stage == stage
    with pytest.raises(ValueError):
        store.update(job.id, stage="splitting:x/12")


def test_is_stage_and_split_stage_bounds():
    assert is_stage("writing") and is_stage("cutting_ads") and is_stage("splitting:1/2")
    assert not is_stage("splitting:1/2/3") and not is_stage("splitting:") and not is_stage("nope")
    assert split_stage(1, 1) == "splitting:1/1"
    for bad in ((0, 3), (4, 3), (1, 10_000)):
        with pytest.raises(ValueError):
            split_stage(*bad)


def test_m5a_notes_are_verbatim():
    assert NOTES["SPONSORBLOCK_EMPTY"] == "ไม่มีข้อมูลจากชุมชน ไม่ได้ตัดโฆษณา"
    assert NOTES["SPONSORBLOCK_UNREACHABLE"] == "ติดต่อ SponsorBlock ไม่ได้ ไม่ได้ตัดโฆษณา"
    assert NOTES["NO_CHAPTERS"] == "คลิปนี้ไม่มี chapter ได้ไฟล์เต็ม"


def test_m5b_count_stages_are_stored(store):
    (job,) = add(store)
    store.transition(job.id, "running")
    for stage in (count_stage("extracting_frames", 3, 120), count_stage("sharp_frames", 1, 1)):
        assert store.update(job.id, stage=stage).stage == stage
    for bad in ("extracting_frames:0x/3", "sharp_frames:", "extracting:1/2", "sharp_frames:1/2/3"):
        with pytest.raises(ValueError):
            store.update(job.id, stage=bad)


def test_count_stage_bounds():
    assert count_stage("extracting_frames", 1, 1) == "extracting_frames:1/1"
    assert is_stage("sharp_frames:2/9") and is_stage("extracting_frames:200/200") and is_stage("splitting:1/2")
    for args in (("extracting_frames", 0, 3), ("extracting_frames", 4, 3), ("sharp_frames", 1, 10_000), ("cutting", 1, 2)):
        with pytest.raises(ValueError):
            count_stage(*args)


def test_valued_notes_fill_their_message():
    assert NOTES["SHARP_LOW_RES"] == "คลิปนี้มีภาพสูงสุด {h}p ภาพจึงเล็กกว่าปกติ"
    assert NOTES["SHARP_INTERVAL_RAISED"] == "ปรับเป็นทุก {n} วินาทีเพื่อไม่ให้เกิน 200 ภาพ"
    assert valued_note("SHARP_LOW_RES", 480) == "SHARP_LOW_RES:480"
    assert note_api("SHARP_LOW_RES:480") == {"code": "SHARP_LOW_RES", "message": "คลิปนี้มีภาพสูงสุด 480p ภาพจึงเล็กกว่าปกติ"}
    assert note_api("SHARP_INTERVAL_RAISED:4") == {
        "code": "SHARP_INTERVAL_RAISED", "message": "ปรับเป็นทุก 4 วินาทีเพื่อไม่ให้เกิน 200 ภาพ"}
    assert note_api("NO_SUBTITLES") == {"code": "NO_SUBTITLES", "message": "คลิปนี้ไม่มีซับ"}
    bad_values = ("SHARP_LOW_RES", "SHARP_LOW_RES:x", "SHARP_LOW_RES:-1", "SHARP_LOW_RES:²", "SHARP_LOW_RES:٣")
    for bad in (*bad_values, "NO_SUBTITLES:3", "NOPE", "NOPE:1"):
        assert note_api(bad) is None
    for args in (("NO_SUBTITLES", 1), ("SHARP_LOW_RES", -1)):
        with pytest.raises(ValueError):
            valued_note(*args)


def test_to_api_fills_valued_notes_and_lists_folder_outputs(store):
    (job,) = add(store, kind="frames_sharp")
    store.transition(job.id, "running")
    folder = OutputFile("C:/out", "คลิป [aqz-KE-bpKQ]/คลิป - ภาพคม", 1234, "folder", files=12)
    done = store.transition(job.id, "done", outputs=(folder,), notes=(valued_note("SHARP_LOW_RES", 360), "BROKEN:1"))
    api = done.to_api()
    assert api["outputs"] == [{"index": 0, "name": "คลิป - ภาพคม", "sizeBytes": 1234, "files": 12}]
    assert api["notes"] == [{"code": "SHARP_LOW_RES", "message": "คลิปนี้มีภาพสูงสุด 360p ภาพจึงเล็กกว่าปกติ"}]
    assert store.get(job.id).outputs == (folder,)


def test_plain_outputs_have_no_files_key(store):
    (job,) = add(store)
    store.transition(job.id, "running")
    plain = OutputFile("C:/out", "a/b.mp4", 9, "video")
    done = store.transition(job.id, "done", outputs=(plain,))
    assert store.get(job.id).outputs[0].files is None
    assert "files" not in done.to_api()["outputs"][0]

# ---------- M6 รอบ A: jobs.filename_style และชื่อช่อง ----------

def test_filename_style_is_written_on_start_and_survives_requeue(store):
    (job,) = add(store)
    assert job.filename_style is None
    running = store.transition(job.id, "running", filename_style="title-channel")
    assert running.filename_style == "title-channel"
    failed = store.transition(job.id, "failed", error_code="E_NETWORK", error_message="m")
    assert failed.filename_style == "title-channel"
    again = store.requeue(job.id, reset_bot_checks=True)
    assert again.filename_style == "title-channel" and again.error_code is None
    assert "filenameStyle" not in again.to_api() and "filename_style" not in again.to_api()

def test_update_cannot_change_the_filename_style(store):
    (job,) = add(store)
    store.transition(job.id, "running", filename_style="title")
    with pytest.raises(ValueError):
        store.update(job.id, filename_style="title-quality")

def test_channel_of_reads_the_videos_row(store):
    sql = "INSERT INTO videos (video_id, title, channel, probe_json, probed_at, opened_at) VALUES (?, 't', ?, '{}', 'x', 'x')"
    store._db.execute(sql, ("vid00000000", "ครัวบ้านเรา"))
    store._db.execute(sql, ("vid00000001", None))
    assert store.channel_of("vid00000000") == "ครัวบ้านเรา"
    assert store.channel_of("vid00000001") == ""
    assert store.channel_of("missing0000") == ""

def test_filename_style_is_written_once(store):
    # รีวิว T2 M3: ตั้งได้ครั้งเดียว การเริ่มครั้งต่อไป (หรือ transition อื่น) ที่ส่งค่าอื่นมาไม่เปลี่ยนค่าแรก
    (job,) = add(store)
    store.transition(job.id, "running", filename_style="title-channel")
    store.transition(job.id, "failed", error_code="E_NETWORK", error_message="m", filename_style="title")
    store.requeue(job.id, reset_bot_checks=True)
    again = store.transition(job.id, "running", filename_style="title-quality")
    assert again.filename_style == "title-channel"
    assert store.get(job.id).filename_style == "title-channel"
