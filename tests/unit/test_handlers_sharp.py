"""งานภาพคม (M5 รอบ B C7) และ contact sheet / zip จากชุดภาพคม: ตัวโหลดปลอม + FakeMediaTools ไม่แตะเครือข่าย"""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path

import pytest
from helpers_sharp import BBB, BBB_TITLE, JOB_ID, NOW, ZOO, SharpEnv
from PIL import Image

from yttoolkit.core import files, handlers
from yttoolkit.core.cancel import JobCancelled
from yttoolkit.core.jobs import JobResult
from yttoolkit.core.sharp import fast_times
from yttoolkit.core.sharp_store import read_sharp
from yttoolkit.core.yterrors import YtError


@pytest.fixture
def env(tmp_path):
    made = SharpEnv(tmp_path)
    yield made
    made.close()


def _folder(result: JobResult) -> Path:
    (out,) = result.outputs
    return Path(out.root) / out.rel


def _clip_folder(env: SharpEnv, video_id: str = BBB, title: str = BBB_TITLE) -> Path:
    return files.plan_output(env.out.resolve(), title, video_id, "", "mp4").parent


def _sharp_dirs(env: SharpEnv, video_id: str = BBB, title: str = BBB_TITLE) -> list[str]:
    folder = _clip_folder(env, video_id, title)
    return sorted(p.name for p in folder.iterdir() if p.is_dir()) if folder.exists() else []


def _cache_children(env: SharpEnv, video_id: str = BBB) -> list[str]:
    folder = env.cache / video_id
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


def test_same_times_writes_the_cache_and_a_folder(env):
    result, ctx = env.run("frames_sharp", BBB, {})
    (out,) = result.outputs
    folder = _folder(result)
    assert out.kind == "folder" and out.files == 128
    assert folder == files.plan_sharp_dir(env.out.resolve(), BBB_TITLE, BBB)
    names = sorted(p.name for p in folder.iterdir())
    assert len(names) == 128 and names[0] == "frame_00-00-00.jpg" and files.PARTIAL_MARKER not in names
    assert out.size_bytes == sum(p.stat().st_size for p in folder.iterdir())
    index = read_sharp(env.cache, BBB)
    assert index["origin"] == "manual" and index["intervalMs"] is None
    assert index["createdAt"] == NOW.isoformat(timespec="seconds")
    assert [f["tMs"] for f in index["frames"]] == fast_times(env.videos.raw(BBB))
    extract = [f"extracting_frames:{i}/128" for i in range(1, 129)]
    assert ctx.stages == ["probing", "downloading_video", *extract, "writing"]
    assert {(call.long_side, call.dynamic_range) for call in env.media.frames} == {(1280, None)}
    assert env.downloader.choices[0].format_spec == "298"
    assert not (ctx.workdir / "media.mp4").exists()  # AC-FRAME-03: วิดีโอชั่วคราวถูกลบทันทีที่ดึงภาพเสร็จ
    assert (folder.parent / files.SOURCE_NOTE_NAME).is_file()
    assert result.notes == () and result.title == BBB_TITLE
    assert _cache_children(env) == ["sharp"]


def test_custom_interval_names_the_frames_by_time(env):
    result, ctx = env.run("frames_sharp", BBB, {"intervalS": 60})
    names = sorted(p.name for p in _folder(result).iterdir())
    assert names == [f"frame_00-{m:02d}-00.jpg" for m in range(11)]
    index = read_sharp(env.cache, BBB)
    assert index["intervalMs"] == 60_000 and [f["tMs"] for f in index["frames"]] == list(range(0, 660_000, 60_000))
    assert ctx.titles == [BBB_TITLE]
    fractions = [p[0] for p in ctx.progresses if p[0] is not None]
    assert fractions[-11:] == pytest.approx([i / 11 for i in range(11)])  # ภาพที่ i: (i-1)/n


def test_custom_interval_over_200_is_raised_with_a_note(env):
    result, _ = env.run("frames_sharp", BBB, {"intervalS": 2})
    assert result.outputs[0].files == 159
    assert result.notes == ("SHARP_INTERVAL_RAISED:4",)
    assert read_sharp(env.cache, BBB)["intervalMs"] == 4000


def test_same_times_over_200_falls_back_with_a_note(env, monkeypatch):  # Review Focus 4
    monkeypatch.setattr(handlers, "fast_times", lambda raw: list(range(0, 636_000, 3000)))
    result, _ = env.run("frames_sharp", BBB, {})
    assert result.outputs[0].files == 159
    assert result.notes == ("SHARP_INTERVAL_RAISED:4",)


def test_no_storyboard_uses_the_default_interval_and_notes_low_resolution(env):
    result, _ = env.run("frames_sharp", ZOO, {})
    assert result.outputs[0].files == 19
    assert read_sharp(env.cache, ZOO)["intervalMs"] == 1000
    assert result.notes == ("SHARP_LOW_RES:240",)
    assert env.downloader.choices[0].format_spec == "134"


def test_hdr_only_clip_is_tone_mapped(env):
    env.downloader.formats_hook = lambda formats: [{**f, "dynamic_range": "HDR10"} for f in formats]
    result, _ = env.run("frames_sharp", BBB, {"intervalS": 60})
    assert {call.dynamic_range for call in env.media.frames} == {"HDR10"}
    assert result.notes == ()


def test_frames_near_the_end_are_dropped(env):  # Review Focus 3
    env.media.frame_limit_ms = 600_000
    result, _ = env.run("frames_sharp", BBB, {"intervalS": 60})
    assert result.outputs[0].files == 10
    assert [f["tMs"] for f in read_sharp(env.cache, BBB)["frames"]][-1] == 540_000
    assert len(list(_folder(result).iterdir())) == 10


def test_zero_frames_fails_and_keeps_the_old_set(env):  # Review Focus 3
    env.run("frames_sharp", BBB, {"intervalS": 300})
    env.media.frame_limit_ms = 0
    with pytest.raises(YtError) as err:
        env.run("frames_sharp", BBB, {"intervalS": 60})
    assert err.value.code == "E_UNKNOWN"
    assert len(read_sharp(env.cache, BBB)["frames"]) == 3
    assert _sharp_dirs(env) == [files.plan_sharp_dir(env.out.resolve(), BBB_TITLE, BBB).name]
    assert _cache_children(env) == ["sharp"]


def test_zero_frames_logs_the_cause_without_paths(env, caplog):  # controller ruling 4
    env.media.frame_limit_ms = 0
    with caplog.at_level(logging.INFO, logger="yttoolkit"), pytest.raises(YtError):
        env.run("frames_sharp", BBB, {"intervalS": 60})
    (line,) = [r.getMessage() for r in caplog.records if "(0/11" in r.getMessage()]
    assert JOB_ID in line and BBB in line and "format 298" in line
    assert str(env.tmp) not in line and BBB_TITLE not in line


def test_a_mid_clip_drop_is_logged_once_without_paths(env, caplog):
    env.media.frame_limit_ms = 300_000  # คลิป 634 วินาที: ภาพที่ 300..600 วินาทีหายทั้ง 6 ภาพ (ยังห่างท้ายคลิป)
    with caplog.at_level(logging.INFO, logger="yttoolkit"):
        result, _ = env.run("frames_sharp", BBB, {"intervalS": 60})
    assert result.outputs[0].files == 5
    (line,) = [r.getMessage() for r in caplog.records if "ภาพหายกลางคลิป" in r.getMessage()]
    assert JOB_ID in line and "6/11" in line
    assert str(env.tmp) not in line and BBB_TITLE not in line and BBB not in line


def test_a_tail_only_drop_is_not_logged(env, caplog):
    env.media.frame_limit_ms = 18_000  # คลิป 19 วินาที: หายแค่ภาพที่ 18 วินาที (วินาทีสุดท้าย) = ท้ายคลิปตามปกติ
    with caplog.at_level(logging.INFO, logger="yttoolkit"):
        result, _ = env.run("frames_sharp", ZOO, {"intervalS": 1})
    assert result.outputs[0].files == 18
    assert not any("ภาพหายกลางคลิป" in r.getMessage() for r in caplog.records)


def test_cancel_during_extraction_keeps_the_previous_set(env):
    env.run("frames_sharp", BBB, {"intervalS": 300})
    with pytest.raises(JobCancelled):
        env.run("frames_sharp", BBB, {"intervalS": 60}, cancel_on="extracting_frames:2/11")
    assert len(read_sharp(env.cache, BBB)["frames"]) == 3
    assert len(_sharp_dirs(env)) == 1
    assert _cache_children(env) == ["sharp"]


def test_failed_commit_removes_the_new_folder_and_keeps_the_old_set(env, monkeypatch):
    env.run("frames_sharp", BBB, {"intervalS": 300})

    def broken(*_args, **_kwargs):
        raise YtError("E_UNKNOWN", "swap sharp set: PermissionError")

    monkeypatch.setattr(handlers, "commit_sharp", broken)
    with pytest.raises(YtError):
        env.run("frames_sharp", BBB, {"intervalS": 60})
    assert len(read_sharp(env.cache, BBB)["frames"]) == 3
    assert len(_sharp_dirs(env)) == 1
    assert _cache_children(env) == ["sharp"]


def test_second_request_replaces_the_cache_and_adds_a_numbered_folder(env):
    env.run("frames_sharp", BBB, {"intervalS": 300})
    second, _ = env.run("frames_sharp", BBB, {"intervalS": 60})
    base = files.plan_sharp_dir(env.out.resolve(), BBB_TITLE, BBB).name
    assert _sharp_dirs(env) == [base, f"{base} (2)"]
    assert _folder(second).name == f"{base} (2)"
    assert read_sharp(env.cache, BBB)["intervalMs"] == 60_000


def test_disk_check_counts_the_video_and_the_frames(env):
    env.free = 1000
    with pytest.raises(YtError) as err:
        env.run("frames_sharp", BBB, {"intervalS": 60})
    assert err.value.code == "E_DISK_FULL"
    assert "170 MB" in err.value.message  # ceil(150 524 867 × 1.1) + 11 × 400 000 ไบต์
    assert env.media.frames == []


def test_live_or_unknown_duration_fails(env, monkeypatch):
    real = env.videos.get
    for patch, code in (({"isLive": True}, "E_LIVE_NOT_READY"), ({"durationS": 0}, "E_UNKNOWN")):
        monkeypatch.setattr(env.videos, "get", lambda video_id, patch=patch, **kw: {**real(video_id, **kw), **patch})
        with pytest.raises(YtError) as err:
            env.run("frames_sharp", BBB, {})
        assert err.value.code == code
    assert env.downloader.choices == []


@pytest.mark.parametrize("bad", [0, 3601, "5", True])
def test_a_broken_stored_interval_fails(env, bad):
    with pytest.raises(YtError) as err:
        env.run("frames_sharp", BBB, {"intervalS": bad})
    assert err.value.code == "E_UNKNOWN"


def test_contact_sheet_from_the_sharp_set(env):
    env.run("frames_sharp", BBB, {"intervalS": 60})
    result, ctx = env.run("contact_sheet", BBB, {"source": "sharp", "columns": 5})
    (out,) = result.outputs
    path = Path(out.root) / out.rel
    assert path == files.plan_output(env.out.resolve(), BBB_TITLE, BBB, " - contact sheet", "jpg")
    assert ctx.stages == ["probing", "converting", "writing"]
    with Image.open(path) as sheet:
        assert sheet.width == 5 * 320 + 6 * 8


def test_frames_zip_from_the_sharp_set(env):
    env.run("frames_sharp", BBB, {"intervalS": 60})
    result, _ = env.run("frames_zip", BBB, {"source": "sharp"})
    (out,) = result.outputs
    with zipfile.ZipFile(io.BytesIO((Path(out.root) / out.rel).read_bytes())) as archive:
        assert archive.namelist() == [f"frame_00-{m:02d}-00.jpg" for m in range(11)]


@pytest.mark.parametrize("kind", ["contact_sheet", "frames_zip"])
def test_sharp_source_without_a_set_fails(env, kind):
    with pytest.raises(YtError) as err:
        env.run(kind, BBB, {"source": "sharp"})
    assert err.value.code == "E_NO_SHARP_FRAMES"
    assert not _clip_folder(env).exists()


def test_a_purged_frame_file_is_no_sharp_frames(env):
    env.run("frames_sharp", BBB, {"intervalS": 60})
    (env.cache / BBB / "sharp" / "f_0003.jpg").unlink()
    with pytest.raises(YtError) as err:
        env.run("contact_sheet", BBB, {"source": "sharp", "columns": 5})
    assert err.value.code == "E_NO_SHARP_FRAMES"


def test_logs_have_no_absolute_paths(env, caplog):
    with caplog.at_level(logging.INFO, logger="yttoolkit"):
        env.run("frames_sharp", BBB, {"intervalS": 60})
    assert all(str(env.tmp) not in r.getMessage() for r in caplog.records)
    # controller ruling 2: ไม่มีชื่อคลิปหรือ path สัมพัทธ์ของโฟลเดอร์ภาพคมด้วย
    assert all(BBB_TITLE not in r.getMessage() and "ภาพคม/" not in r.getMessage() for r in caplog.records)
    assert any(JOB_ID in r.getMessage() and "11" in r.getMessage() for r in caplog.records)
