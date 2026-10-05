"""ชุดภาพคมใน cache (M5 รอบ B spec 5): อ่าน เตรียม สลับแบบ atomic ทิ้ง และล้างของค้างตอนเปิดโปรแกรม"""

from __future__ import annotations

import json
import pathlib
from pathlib import Path

import pytest

from yttoolkit.core import sharp_store
from yttoolkit.core.sharp_store import (
    FOLDER,
    commit_sharp,
    discard_sharp,
    prepare_sharp,
    read_sharp,
    sweep_sharp_leftovers,
)
from yttoolkit.core.yterrors import YtError

COVER = Path(__file__).resolve().parents[1] / "fixtures" / "media" / "cover.jpg"
BBB = "aqz-KE-bpKQ"
JOB_A = "01900000-0000-7000-8000-00000000000a"
JOB_B = "01900000-0000-7000-8000-00000000000b"
WHEN = "2026-10-05T03:00:00+00:00"


def _frames(times: list[int]) -> list[tuple[int, Path]]:
    return [(t, COVER) for t in times]


def _install(cache: Path, job: str, times: list[int], *, origin: str = "manual", interval_ms: int | None = None) -> dict:
    staged = prepare_sharp(cache, BBB, job, _frames(times), origin=origin, interval_ms=interval_ms, created_at=WHEN)
    return commit_sharp(cache, BBB, staged)


def test_prepare_then_commit_writes_the_index_and_frames(tmp_path: Path) -> None:
    index = _install(tmp_path, JOB_A, [0, 60_000, 120_000], interval_ms=60_000)
    assert index == {
        "origin": "manual", "intervalMs": 60_000, "createdAt": WHEN,
        "frames": [{"index": 0, "tMs": 0, "file": "f_0000.jpg"}, {"index": 1, "tMs": 60_000, "file": "f_0001.jpg"},
                   {"index": 2, "tMs": 120_000, "file": "f_0002.jpg"}],
    }  # fmt: skip
    folder = tmp_path / BBB / FOLDER
    assert sorted(p.name for p in folder.iterdir()) == ["f_0000.jpg", "f_0001.jpg", "f_0002.jpg", "index.json"]
    assert read_sharp(tmp_path, BBB) == index
    assert sorted(p.name for p in (tmp_path / BBB).iterdir()) == [FOLDER]


def test_a_new_set_replaces_the_old_one(tmp_path: Path) -> None:
    _install(tmp_path, JOB_A, [0, 1000, 2000])
    index = _install(tmp_path, JOB_B, [0], origin="auto")
    assert index["origin"] == "auto" and len(index["frames"]) == 1
    assert sorted(p.name for p in (tmp_path / BBB / FOLDER).iterdir()) == ["f_0000.jpg", "index.json"]
    assert sorted(p.name for p in (tmp_path / BBB).iterdir()) == [FOLDER]


def test_staged_set_is_invisible_until_commit_and_discard_removes_it(tmp_path: Path) -> None:
    _install(tmp_path, JOB_A, [0, 1000])
    staged = prepare_sharp(tmp_path, BBB, JOB_B, _frames([5000]), origin="manual", interval_ms=None, created_at=WHEN)
    assert staged.name == f"sharp.tmp-{JOB_B}"
    assert len(read_sharp(tmp_path, BBB)["frames"]) == 2
    discard_sharp(staged)
    assert not staged.exists()
    assert len(read_sharp(tmp_path, BBB)["frames"]) == 2


@pytest.mark.parametrize(
    ("frames", "origin", "job"),
    [([], "manual", JOB_A), ([(0, COVER)], "other", JOB_A), ([(0, COVER)], "manual", "../x")],
)
def test_prepare_rejects_bad_input(tmp_path: Path, frames, origin, job) -> None:
    with pytest.raises(ValueError):
        prepare_sharp(tmp_path, BBB, job, frames, origin=origin, interval_ms=None, created_at=WHEN)
    with pytest.raises(ValueError):
        prepare_sharp(tmp_path, "bad id", JOB_A, [(0, COVER)], origin="manual", interval_ms=None, created_at=WHEN)


def test_read_sharp_rejects_broken_sets(tmp_path: Path) -> None:
    assert read_sharp(tmp_path, BBB) is None
    assert read_sharp(tmp_path, "not an id") is None
    _install(tmp_path, JOB_A, [0, 1000])
    index_path = tmp_path / BBB / FOLDER / "index.json"
    (tmp_path / BBB / FOLDER / "f_0001.jpg").unlink()
    assert read_sharp(tmp_path, BBB) is None  # ไฟล์ภาพหาย
    _install(tmp_path, JOB_B, [0])
    doc = json.loads(index_path.read_text(encoding="utf-8"))
    for broken in ({**doc, "origin": "x"}, {**doc, "intervalMs": True}, {**doc, "frames": []},
                   {**doc, "frames": [{"index": 0, "tMs": -1, "file": "f_0000.jpg"}]}, {**doc, "createdAt": None}):  # fmt: skip
        index_path.write_text(json.dumps(broken), encoding="utf-8")
        assert read_sharp(tmp_path, BBB) is None
    index_path.write_text("{", encoding="utf-8")
    assert read_sharp(tmp_path, BBB) is None


def test_commit_retries_a_locked_rename_then_succeeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install(tmp_path, JOB_A, [0])
    real = pathlib.Path.rename
    locked = {"left": 3}

    def rename(self, target):
        if self.name == FOLDER and locked["left"]:
            locked["left"] -= 1
            raise PermissionError(13, "ไฟล์ถูกเปิดค้างอยู่")
        return real(self, target)

    monkeypatch.setattr(pathlib.Path, "rename", rename)
    monkeypatch.setattr(sharp_store, "RENAME_WAIT_S", 0)
    index = _install(tmp_path, JOB_B, [0, 1000])
    assert len(index["frames"]) == 2 and locked["left"] == 0


def test_commit_failure_keeps_the_previous_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install(tmp_path, JOB_A, [0, 1000, 2000])
    real = pathlib.Path.rename

    def rename(self, target):
        if self.name.startswith("sharp.tmp-"):
            raise PermissionError(13, "ล็อก")
        return real(self, target)

    monkeypatch.setattr(pathlib.Path, "rename", rename)
    monkeypatch.setattr(sharp_store, "RENAME_WAIT_S", 0)
    staged = prepare_sharp(tmp_path, BBB, JOB_B, _frames([0]), origin="manual", interval_ms=None, created_at=WHEN)
    with pytest.raises(YtError) as err:
        commit_sharp(tmp_path, BBB, staged)
    assert err.value.code == "E_UNKNOWN"
    assert len(read_sharp(tmp_path, BBB)["frames"]) == 3
    assert sorted(p.name for p in (tmp_path / BBB).iterdir()) == [FOLDER]


def test_sweep_removes_tmp_and_old_folders(tmp_path: Path) -> None:
    _install(tmp_path, JOB_A, [0])
    (tmp_path / BBB / f"sharp.tmp-{JOB_B}").mkdir()
    (tmp_path / BBB / "sharp.old-x").mkdir()
    (tmp_path / BBB / "storyboard").mkdir()
    (tmp_path / "loose.txt").write_text("x", encoding="utf-8")
    assert sweep_sharp_leftovers(tmp_path) == 2
    assert sorted(p.name for p in (tmp_path / BBB).iterdir()) == [FOLDER, "storyboard"]
    assert read_sharp(tmp_path, BBB) is not None


def test_sweep_restores_the_old_set_when_sharp_is_missing(tmp_path: Path) -> None:  # Review Focus 2
    _install(tmp_path, JOB_A, [0, 1000])
    (tmp_path / BBB / FOLDER).rename(tmp_path / BBB / f"sharp.old-{JOB_B}")  # ดับระหว่างสลับ: ชุดเดิมถูกย้ายออกแล้ว
    (tmp_path / BBB / f"sharp.tmp-{JOB_B}").mkdir()
    assert read_sharp(tmp_path, BBB) is None
    assert sweep_sharp_leftovers(tmp_path) == 2
    assert len(read_sharp(tmp_path, BBB)["frames"]) == 2


def test_sweep_skips_a_broken_old_set_and_restores_the_next_valid_one(tmp_path: Path) -> None:
    _install(tmp_path, JOB_A, [0, 1000])
    folder = tmp_path / BBB
    (folder / FOLDER).rename(folder / "sharp.old-b")  # ชุดดี (เรียงทีหลัง)
    broken = folder / "sharp.old-a"  # เรียงก่อน แต่เสีย: index อ่านไม่ได้
    broken.mkdir()
    (broken / "index.json").write_text("{not json", encoding="utf-8")
    assert sweep_sharp_leftovers(tmp_path) == 2
    assert sorted(p.name for p in folder.iterdir()) == [FOLDER]
    assert len(read_sharp(tmp_path, BBB)["frames"]) == 2


def test_sweep_deletes_every_old_set_when_none_is_valid(tmp_path: Path) -> None:
    (tmp_path / BBB / "sharp.old-a").mkdir(parents=True)
    (tmp_path / BBB / "sharp.old-b").mkdir()
    assert sweep_sharp_leftovers(tmp_path) == 2
    assert list((tmp_path / BBB).iterdir()) == []


def test_sweep_of_a_missing_cache_root_is_zero(tmp_path: Path) -> None:
    assert sweep_sharp_leftovers(tmp_path / "nope") == 0


@pytest.mark.parametrize(
    ("frames", "interval_ms", "created_at"),
    [
        ([(0, COVER)], 0, WHEN),
        ([(0, COVER)], -5, WHEN),
        ([(0, COVER)], True, WHEN),
        ([(0, COVER)], 1.5, WHEN),
        ([(-1, COVER)], None, WHEN),
        ([(0, COVER), (True, COVER)], None, WHEN),
        ([(0, COVER)], None, None),
    ],
)
def test_prepare_rejects_what_read_sharp_would_reject(tmp_path: Path, frames, interval_ms, created_at) -> None:
    _install(tmp_path, JOB_A, [0, 1000])
    with pytest.raises(ValueError):
        prepare_sharp(tmp_path, BBB, JOB_B, frames, origin="manual", interval_ms=interval_ms, created_at=created_at)
    assert sorted(p.name for p in (tmp_path / BBB).iterdir()) == [FOLDER]  # ไม่เหลือโฟลเดอร์ staged
    assert len(read_sharp(tmp_path, BBB)["frames"]) == 2


def test_commit_of_an_invalid_staged_set_keeps_the_previous_set(tmp_path: Path) -> None:
    _install(tmp_path, JOB_A, [0, 1000, 2000])
    staged = prepare_sharp(tmp_path, BBB, JOB_B, _frames([0]), origin="auto", interval_ms=None, created_at=WHEN)
    doc = json.loads((staged / "index.json").read_text(encoding="utf-8"))
    (staged / "index.json").write_text(json.dumps({**doc, "intervalMs": 0}), encoding="utf-8")
    with pytest.raises(YtError) as err:
        commit_sharp(tmp_path, BBB, staged)
    assert err.value.code == "E_UNKNOWN"
    assert not staged.exists()
    assert len(read_sharp(tmp_path, BBB)["frames"]) == 3
    assert sorted(p.name for p in (tmp_path / BBB).iterdir()) == [FOLDER]
    staged = prepare_sharp(tmp_path, BBB, JOB_B, _frames([0]), origin="auto", interval_ms=None, created_at=WHEN)
    (staged / "f_0000.jpg").unlink()  # ไฟล์ภาพหายก่อนสลับ
    with pytest.raises(YtError):
        commit_sharp(tmp_path, BBB, staged)
    assert len(read_sharp(tmp_path, BBB)["frames"]) == 3
