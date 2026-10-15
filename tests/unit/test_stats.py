"""สถิติของฉัน (M6 รอบ C spec §1): นับจากตาราง jobs ในเครื่อง · AC-STAT-01"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from yttoolkit.core.db import Database
from yttoolkit.core.stats import compute

NOW = datetime(2026, 10, 15, 5, 0, tzinfo=UTC)  # 15 ต.ค. 2569 12:00 เวลาไทย


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "stats.db")
    database.migrate()
    yield database
    database.close()


def out(kind: str, size: object = 100, **extra) -> dict:
    return {"root": "C:/secret-root", "rel": f"ชื่อคลิปลับ/{kind}.bin", "sizeBytes": size, "kind": kind, **extra}


_n = {"i": 0}


def add(db: Database, video: str, finished: str | None, outputs: object, *, status: str = "done") -> None:
    _n["i"] += 1
    raw = outputs if isinstance(outputs, str) or outputs is None else json.dumps(outputs)
    db.execute(
        "INSERT INTO jobs (id, video_id, title, kind, params_json, status, position, outputs_json, created_at, finished_at) "
        "VALUES (?, ?, 'ชื่อคลิปลับ', 'video', '{}', ?, ?, ?, '2026-01-01T00:00:00+00:00', ?)",
        (f"j{_n['i']}", video, status, _n["i"], raw, finished),
    )


def test_ac_stat_01_counts_done_jobs_only(db):
    add(db, "A", "2026-10-02T03:00:00+00:00", [out("video", 1000)])
    add(db, "A", "2026-10-03T03:00:00+00:00", [out("audio", 200)])
    add(db, "B", "2026-10-04T03:00:00+00:00", [out("video", 3000)])
    add(db, "B", "2026-09-10T03:00:00+00:00", [out("subtitle", 10)])
    add(db, "C", "2026-09-11T03:00:00+00:00", [out("video", 500)])
    add(db, "D", "2026-10-05T03:00:00+00:00", [out("video", 9)], status="failed")
    add(db, "D", "2026-10-06T03:00:00+00:00", [out("video", 9)], status="failed")
    add(db, "E", "2026-10-07T03:00:00+00:00", [out("video", 9)], status="cancelled")
    stats = compute(db, None, NOW)
    assert stats["since"] is None
    assert (stats["clips"], stats["files"], stats["totalBytes"]) == (3, 5, 4710)
    assert stats["byKind"] == [
        {"kind": "video", "files": 3, "bytes": 4500},
        {"kind": "audio", "files": 1, "bytes": 200},
        {"kind": "subtitle", "files": 1, "bytes": 10},
    ]
    assert stats["byMonth"] == [
        {"month": "2026-10", "clips": 2, "files": 3, "bytes": 4200},
        {"month": "2026-09", "clips": 2, "files": 2, "bytes": 510},
    ]


def test_empty_is_all_zero(db):
    assert compute(db, None, NOW) == {
        "since": None, "clips": 0, "files": 0, "totalBytes": 0, "byKind": [], "byMonth": [],
    }


def test_month_edge_is_thai_time(db):
    add(db, "A", "2026-09-30T17:00:00+00:00", [out("video", 1)])  # 1 ต.ค. 00:00 เวลาไทย
    add(db, "B", "2026-09-30T16:59:59+00:00", [out("video", 1)])  # 30 ก.ย. 23:59:59 เวลาไทย
    months = [m["month"] for m in compute(db, None, NOW)["byMonth"]]
    assert months == ["2026-10", "2026-09"]


def test_window_is_current_month_and_eleven_before(db):
    add(db, "A", "2025-11-01T00:00:00+07:00", [out("video", 1)])  # เดือนที่ 12 นับจากเดือนนี้ = อยู่ในตาราง
    add(db, "B", "2025-10-31T23:59:59+07:00", [out("video", 1)])  # เดือนที่ 13 = นับในยอดรวม ไม่อยู่ในตาราง
    stats = compute(db, None, NOW)
    assert stats["clips"] == 2
    assert [m["month"] for m in stats["byMonth"]] == ["2025-11"]


def test_future_month_counts_in_totals_only(db):
    add(db, "A", "2026-11-02T00:00:00+00:00", [out("video", 1)])
    stats = compute(db, None, NOW)
    assert stats["files"] == 1 and stats["byMonth"] == []


def test_kind_mapping_and_folder_counts_once(db):
    add(db, "A", "2026-10-02T03:00:00+00:00", [
        out("note", 5), out("subtitle", 5),
        out("image", 1), out("archive", 2), out("folder", 40, files=40),
        out("mystery", 999),
    ])
    stats = compute(db, None, NOW)
    assert stats["files"] == 5 and stats["totalBytes"] == 53
    assert stats["byKind"] == [
        {"kind": "image", "files": 3, "bytes": 43},
        {"kind": "subtitle", "files": 2, "bytes": 10},
    ]


def test_tie_goes_to_more_bytes_then_fixed_order(db):
    add(db, "A", "2026-10-02T03:00:00+00:00", [out("audio", 50), out("video", 10), out("image", 50), out("subtitle", 50)])
    kinds = [k["kind"] for k in compute(db, None, NOW)["byKind"]]
    assert kinds == ["audio", "subtitle", "image", "video"]


def test_since_is_inclusive(db):
    add(db, "A", "2026-10-10T03:00:00+00:00", [out("video", 1)])
    add(db, "B", "2026-10-10T02:59:59+00:00", [out("video", 1)])
    stats = compute(db, "2026-10-10T03:00:00+00:00", NOW)
    assert stats["since"] == "2026-10-10T03:00:00+00:00"
    assert stats["clips"] == 1


def test_since_compares_datetimes_across_offsets(db):
    add(db, "A", "2026-10-10T03:00:00.000000+00:00", [out("video", 1)])
    add(db, "B", "2026-10-10T09:59:59+07:00", [out("video", 1)])  # = 02:59:59 UTC
    assert compute(db, "2026-10-10T10:00:00+07:00", NOW)["clips"] == 1


def test_naive_finished_at_is_utc(db):
    add(db, "A", "2026-09-30T17:00:00", [out("video", 1)])
    assert compute(db, None, NOW)["byMonth"][0]["month"] == "2026-10"


@pytest.mark.parametrize("since", ["not-a-date", 12, ["x"], ""])
def test_unparsable_since_counts_everything(db, since):
    add(db, "A", "2026-10-02T03:00:00+00:00", [out("video", 1)])
    stats = compute(db, since, NOW)
    assert stats["since"] is None and stats["clips"] == 1


@pytest.mark.parametrize("raw", [None, "not json", '"oops"', "{}", "42"])
def test_bad_outputs_json_counts_clip_with_no_files(db, raw):
    add(db, "A", "2026-10-02T03:00:00+00:00", raw)
    stats = compute(db, None, NOW)
    assert (stats["clips"], stats["files"], stats["totalBytes"]) == (1, 0, 0)
    assert stats["byMonth"] == [{"month": "2026-10", "clips": 1, "files": 0, "bytes": 0}]


def test_bad_items_and_sizes(db):
    add(db, "A", "2026-10-02T03:00:00+00:00", ["str", 7, None, out("video", -5), out("video", "12"), out("video", True), out("video", 3.5)])
    add(db, "A", "2026-10-02T04:00:00+00:00", [{"kind": "audio"}])  # ไม่มี sizeBytes
    stats = compute(db, None, NOW)
    assert stats["files"] == 5 and stats["totalBytes"] == 0


@pytest.mark.parametrize(
    "finished",
    [None, "", "yesterday", "9999-12-31T23:30:00+00:00", "0001-01-01T00:00:00+05:00"],  # สองอันหลัง: แปลงเป็น UTC+07:00 แล้วล้น
)
def test_unparsable_finished_at_skips_the_job(db, finished):
    add(db, "A", finished, [out("video", 1)])
    assert compute(db, None, NOW)["clips"] == 0


def test_far_past_finished_at_still_counts(db):
    add(db, "A", "0001-01-01T00:00:00+00:00", [out("video", 1)])
    stats = compute(db, None, NOW)
    assert stats["clips"] == 1 and stats["byMonth"] == []  # นอกหน้าต่าง 12 เดือน นับเฉพาะยอดรวม


def test_clip_in_two_months_counts_in_both_rows_once_in_total(db):
    add(db, "A", "2026-10-02T03:00:00+00:00", [out("video", 1)])
    add(db, "A", "2026-09-02T03:00:00+00:00", [out("video", 1)])
    stats = compute(db, None, NOW)
    assert stats["clips"] == 1
    assert [m["clips"] for m in stats["byMonth"]] == [1, 1]


def test_result_has_no_title_or_path(db):
    add(db, "A", "2026-10-02T03:00:00+00:00", [out("video", 1)])
    text = json.dumps(compute(db, None, NOW), ensure_ascii=False)
    for leak in ("ชื่อคลิปลับ", "secret-root", "C:/", ".bin"):
        assert leak not in text


def test_non_string_kind_is_skipped_not_fatal(db):
    add(db, "A", "2026-10-02T03:00:00+00:00", [out("video", 7), {"kind": ["video"], "sizeBytes": 5}, {"kind": {"a": 1}, "sizeBytes": 5}])
    stats = compute(db, None, NOW)
    assert (stats["clips"], stats["files"], stats["totalBytes"]) == (1, 1, 7)
