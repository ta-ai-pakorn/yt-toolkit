"""บริการถ่ายภาพคมตรงจุด (M5 รอบ B2 C7): ไม่ใช้เน็ต ไม่ใช้ ffmpeg (ชิ้นภาพจาก fixture + FakeMediaTools)"""

from __future__ import annotations

import errno
import json
import shutil
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from helpers_capture import BBB, MEDIA, TITLE, FakeVideos, FixtureFetcher, StubQueue, StubSettings, clip_info
from PIL import Image

from yttoolkit.core.capture import OUTPUT_DIR, Capture, CaptureRejected, CaptureService, recorded_output
from yttoolkit.core.media import FakeMediaTools, FrameCall
from yttoolkit.core.yterrors import YtError

COVER = MEDIA / "cover.jpg"
with Image.open(COVER) as _img:
    COVER_SIZE = _img.size


@dataclass
class Env:
    service: CaptureService
    fetcher: FixtureFetcher
    media: FakeMediaTools
    settings: StubSettings
    queue: StubQueue
    videos: FakeVideos
    cache: Path
    work: Path
    out: Path

    @property
    def captures(self) -> Path:
        return self.cache / BBB / "captures"

    @property
    def folder(self) -> Path:
        return self.out / f"{TITLE} [{BBB}]" / OUTPUT_DIR

    def index(self) -> list[dict]:
        return json.loads((self.captures / "index.json").read_text(encoding="utf-8"))["captures"]


@pytest.fixture
def env(tmp_path: Path) -> Env:
    fetcher, media, queue = FixtureFetcher(), FakeMediaTools(MEDIA), StubQueue()
    settings, videos = StubSettings(tmp_path / "out"), FakeVideos({BBB: clip_info()})
    service = CaptureService(videos, fetcher, media, tmp_path / "cache", settings, queue, work_root=tmp_path / "work",
                             now=lambda: datetime(2026, 10, 5, 8, 0, tzinfo=UTC))  # fmt: skip
    return Env(service, fetcher, media, settings, queue, videos, tmp_path / "cache", tmp_path / "work", tmp_path / "out")


def _work_is_clean(env: Env) -> bool:
    return not env.work.exists() or list(env.work.iterdir()) == []


def test_capture_writes_the_cache_copy_the_folder_copy_then_the_index(env: Env) -> None:
    capture, created = env.service.capture(BBB, 125_400)
    assert created is True
    assert capture == Capture("c_125400", 125_400, COVER_SIZE[0], COVER_SIZE[1], "c_125400.jpg")
    cached = env.captures / "c_125400.jpg"
    assert cached.read_bytes() == COVER.read_bytes() == (env.folder / "frame_00-02-05.jpg").read_bytes()
    assert env.service.cache_path(BBB, capture) == cached
    assert env.index() == [{
        "id": "c_125400", "tMs": 125_400, "width": COVER_SIZE[0], "height": COVER_SIZE[1], "file": "c_125400.jpg",
        "outputRoot": str(env.out), "outputRel": f"{TITLE} [{BBB}]/ภาพที่ถ่าย/frame_00-02-05.jpg",
        "createdAt": "2026-10-05T08:00:00+00:00",
    }]  # fmt: skip
    assert env.fetcher.calls == [(BBB, 125_400, 2160)]
    # ชิ้นที่ได้เริ่มที่ 125.0 วินาที: ดึงภาพที่ 0.4 วินาทีของชิ้น ไม่ย่อ (long_side None) SDR
    assert env.media.frames == [FrameCall("piece.mp4", "frame.jpg", 400, None, None)]
    assert _work_is_clean(env)


def test_the_same_moment_is_returned_without_fetching(env: Env) -> None:
    first, _ = env.service.capture(BBB, 2_000)
    env.queue.paused_until = datetime(2099, 1, 1, tzinfo=UTC)  # ภาพเดิมไม่ต้องใช้เน็ต: คิวพักก็ได้ภาพเดิม
    again, created = env.service.capture(BBB, 2_000)
    assert again == first and created is False
    assert len(env.fetcher.calls) == 1 and len(env.index()) == 1


def test_second_capture_while_one_runs_is_busy(env: Env) -> None:
    env.fetcher.gate = threading.Event()
    results: dict[str, tuple[Capture, bool]] = {}
    worker = threading.Thread(target=lambda: results.setdefault("first", env.service.capture(BBB, 1_000)))
    worker.start()
    assert env.fetcher.started.wait(5)
    with pytest.raises(YtError) as busy:
        env.service.capture(BBB, 2_000)
    assert busy.value.code == "E_CAPTURE_BUSY"
    env.fetcher.gate.set()
    worker.join(10)
    assert results["first"][1] is True
    assert [call[1] for call in env.fetcher.calls] == [1_000]
    assert env.service.capture(BBB, 2_000)[1] is True  # ปลดล็อกแล้วถ่ายต่อได้


def test_paused_queue_refuses_with_the_bangkok_time(env: Env) -> None:
    env.queue.paused_until = datetime(2026, 10, 5, 10, 10, tzinfo=UTC)
    with pytest.raises(YtError) as info:
        env.service.capture(BBB, 1_000)
    assert info.value.code == "E_QUEUE_PAUSED"
    assert info.value.message == "พักการโหลดอยู่เพราะยูทูปขอตรวจสอบ ลองใหม่หลัง 17:10"
    assert env.fetcher.calls == []


@pytest.mark.parametrize(
    ("info", "t_ms"),
    [
        (clip_info(live=True), 1_000),
        (clip_info(duration_s=0), 1_000),
        (clip_info(duration_s=10), -1),
        (clip_info(duration_s=10), 10_000),
        (clip_info(duration_s=10), True),
        (clip_info(duration_s=10), "1000"),
    ],
)
def test_requests_the_clip_cannot_serve_are_rejected(env: Env, info: dict, t_ms: object) -> None:
    env.videos.infos[BBB] = info
    with pytest.raises(CaptureRejected):
        env.service.capture(BBB, t_ms)  # type: ignore[arg-type]
    assert env.fetcher.calls == []


def test_a_bad_video_id_is_invalid_input(env: Env) -> None:
    with pytest.raises(YtError) as info:
        env.service.capture("../x", 0)
    assert info.value.code == "E_INVALID_INPUT"


def test_two_captures_in_one_second_get_numbered_names(env: Env) -> None:
    env.service.capture(BBB, 125_400)
    env.service.capture(BBB, 125_800)
    assert sorted(p.name for p in env.folder.iterdir()) == ["frame_00-02-05.jpg", "frame_00-02-05_2.jpg"]
    assert [e["outputRel"].rsplit("/", 1)[1] for e in env.index()] == ["frame_00-02-05.jpg", "frame_00-02-05_2.jpg"]


def test_output_failure_rolls_back_the_cache_copy(env: Env, tmp_path: Path) -> None:
    blocked = tmp_path / "blocked"
    blocked.write_bytes(b"not a folder")
    env.settings.output = blocked
    with pytest.raises(YtError) as info:
        env.service.capture(BBB, 1_000)
    assert info.value.code == "E_OUTPUT_NOT_WRITABLE"
    assert not (env.captures / "c_1000.jpg").exists()
    assert not (env.captures / "index.json").exists()
    assert env.service.list(BBB) == [] and _work_is_clean(env)


def test_unwritable_output_root_error_names_no_path(env: Env, tmp_path: Path) -> None:
    # API log รายละเอียดของ error: ห้ามมี path ของโฟลเดอร์ผลลัพธ์ (ส่งแค่ชื่อชนิดของ error เดิม)
    root = tmp_path / "ผลลัพธ์ของพิธ" / "blocked-output-root"
    root.parent.mkdir()
    root.write_bytes(b"not a folder")
    env.settings.output = root
    with pytest.raises(YtError) as info:
        env.service.capture(BBB, 1_000)
    assert info.value.code == "E_OUTPUT_NOT_WRITABLE"
    detail = info.value.detail
    assert detail.isidentifier() and detail.endswith("Error")
    assert not any(part.strip("\\/") in str(info.value) for part in root.parts if part.strip("\\/"))
    assert isinstance(info.value.__cause__, YtError)  # ยังโยงถึงต้นเหตุ (from err)


def test_index_failure_rolls_back_both_copies(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    def full(*_args: object) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(env.service, "_write_entries", full)
    with pytest.raises(YtError) as info:
        env.service.capture(BBB, 1_000)
    assert info.value.code == "E_DISK_FULL"
    assert not (env.captures / "c_1000.jpg").exists()
    assert not env.folder.exists() or list(env.folder.iterdir()) == []


def test_temp_dir_is_removed_on_every_path(env: Env) -> None:
    env.fetcher.error = YtError("E_NETWORK", "reset")
    with pytest.raises(YtError):
        env.service.capture(BBB, 1_000)
    assert _work_is_clean(env)
    env.fetcher.error = None
    env.service.capture(BBB, 1_000)
    assert _work_is_clean(env)


def test_bot_check_brakes_the_queue(env: Env) -> None:
    env.fetcher.error = YtError("E_BOT_CHECK", "429")
    with pytest.raises(YtError) as info:
        env.service.capture(BBB, 1_000)
    assert info.value.code == "E_BOT_CHECK" and env.queue.brakes == ["E_BOT_CHECK"]
    env.fetcher.error = YtError("E_NETWORK", "reset")
    with pytest.raises(YtError):
        env.service.capture(BBB, 1_000)
    assert env.queue.brakes == ["E_BOT_CHECK"]


def test_bot_check_while_reading_the_clip_brakes_the_queue(env: Env) -> None:
    env.videos.error = YtError("E_BOT_CHECK", "429")
    with pytest.raises(YtError) as info:
        env.service.capture(BBB, 1_000)
    assert info.value.code == "E_BOT_CHECK" and env.queue.brakes == ["E_BOT_CHECK"]
    assert env.fetcher.calls == []
    env.videos.error = YtError("E_NETWORK", "reset")
    with pytest.raises(YtError):
        env.service.capture(BBB, 1_000)
    assert env.queue.brakes == ["E_BOT_CHECK"]


def test_no_frame_retries_100_ms_earlier_then_fails(env: Env) -> None:
    env.media.frame_limit_ms = 350  # ที่ 0.4 วินาทีของชิ้นไม่มีภาพ ถอยไป 0.3 ได้ภาพ
    assert env.service.capture(BBB, 125_400)[1] is True
    assert [call.t_ms for call in env.media.frames] == [400, 300]
    env.media.frames.clear()
    env.media.frame_limit_ms = 0
    with pytest.raises(YtError) as info:
        env.service.capture(BBB, 125_500)
    assert info.value.code == "E_UNKNOWN"
    assert [call.t_ms for call in env.media.frames] == [500, 400]
    env.media.frames.clear()
    with pytest.raises(YtError):
        env.service.capture(BBB, 125_000)  # ต้นชิ้นพอดี: ไม่มีที่ให้ถอย
    assert [call.t_ms for call in env.media.frames] == [0]
    assert env.service.list(BBB) == [Capture("c_125400", 125_400, *COVER_SIZE, "c_125400.jpg")]


@pytest.mark.parametrize(("quality", "cap"), [("max", 2160), ("1080", 1080), ("720", 720)])
def test_the_setting_sets_the_short_side_cap(env: Env, quality: str, cap: int | None) -> None:
    env.settings.quality = quality
    env.service.capture(BBB, 1_000)
    assert env.fetcher.calls == [(BBB, 1_000, cap)]


def test_missing_ffmpeg_fails_before_any_fetch(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(env.media, "available", lambda: False)
    with pytest.raises(YtError) as info:
        env.service.capture(BBB, 1_000)
    assert info.value.code == "E_FFMPEG_MISSING" and env.fetcher.calls == []


def test_list_is_sorted_and_drops_entries_without_a_cache_file(env: Env) -> None:
    for t_ms in (3_000, 1_000, 2_000):
        env.service.capture(BBB, t_ms)
    assert [c.t_ms for c in env.service.list(BBB)] == [1_000, 2_000, 3_000]
    (env.captures / "c_2000.jpg").unlink()
    assert [c.t_ms for c in env.service.list(BBB)] == [1_000, 3_000]
    assert [e["tMs"] for e in env.index()] == [1_000, 3_000]
    assert env.service.list("bad id") == []


def test_delete_removes_the_folder_copy_the_cache_copy_and_the_entry(env: Env) -> None:
    capture, _ = env.service.capture(BBB, 125_400)
    env.service.delete(BBB, capture.id)
    assert not (env.folder / "frame_00-02-05.jpg").exists()
    assert not (env.captures / "c_125400.jpg").exists()
    assert env.service.list(BBB) == []
    for video_id, capture_id in ((BBB, capture.id), (BBB, "c_x"), (BBB, "../c_1"), ("bad", "c_1")):
        with pytest.raises(KeyError):
            env.service.delete(video_id, capture_id)


def test_delete_with_the_folder_copy_already_gone(env: Env) -> None:
    capture, _ = env.service.capture(BBB, 1_000)
    (env.folder / "frame_00-00-01.jpg").unlink()
    env.service.delete(BBB, capture.id)
    assert env.service.list(BBB) == []


def _edit_entry(env: Env, **patch: str) -> None:
    entries = env.index()
    entries[0].update(patch)
    (env.captures / "index.json").write_text(json.dumps({"captures": entries}, ensure_ascii=False), encoding="utf-8")


def test_delete_skips_a_path_outside_the_recorded_root(env: Env, tmp_path: Path) -> None:
    capture, _ = env.service.capture(BBB, 1_000)
    decoy = tmp_path / "decoy" / OUTPUT_DIR / "frame_00-00-01.jpg"
    decoy.parent.mkdir(parents=True)
    decoy.write_bytes(b"keep me")
    _edit_entry(env, outputRel=f"../decoy/{OUTPUT_DIR}/frame_00-00-01.jpg")
    env.service.delete(BBB, capture.id)
    assert decoy.read_bytes() == b"keep me"
    assert (env.folder / "frame_00-00-01.jpg").exists()  # ไม่ใช่ไฟล์ที่บันทึกไว้ (index ถูกแก้) จึงไม่แตะ
    assert env.service.list(BBB) == []


def test_delete_skips_a_renamed_file(env: Env) -> None:
    capture, _ = env.service.capture(BBB, 1_000)
    renamed = env.folder / "frame_00-00-01 ของฉัน.jpg"
    (env.folder / "frame_00-00-01.jpg").rename(renamed)
    env.service.delete(BBB, capture.id)
    assert renamed.exists() and env.service.list(BBB) == []


def _link_dir(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        try:
            import _winapi  # Windows: junction ไม่ต้องใช้สิทธิ์ผู้ดูแล

            _winapi.CreateJunction(str(target), str(link))
        except (ImportError, OSError, AttributeError):
            pytest.skip("this machine cannot create a directory link")


def test_delete_never_follows_a_linked_folder(env: Env, tmp_path: Path) -> None:
    capture, _ = env.service.capture(BBB, 1_000)
    elsewhere = tmp_path / "elsewhere"
    shutil.move(str(env.folder), str(elsewhere))
    _link_dir(env.folder, elsewhere)
    env.service.delete(BBB, capture.id)
    assert (elsewhere / "frame_00-00-01.jpg").exists()
    assert env.service.list(BBB) == []


def test_delete_uses_the_recorded_root_after_the_setting_changes(env: Env, tmp_path: Path) -> None:
    capture, _ = env.service.capture(BBB, 1_000)
    env.settings.output = tmp_path / "another-output"
    env.service.delete(BBB, capture.id)
    assert not (env.folder / "frame_00-00-01.jpg").exists()


def test_delete_with_a_locked_folder_copy_changes_nothing(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    capture, _ = env.service.capture(BBB, 1_000)
    real_unlink = Path.unlink

    def locked(self: Path, missing_ok: bool = False) -> None:
        if self.name == "frame_00-00-01.jpg":
            raise PermissionError(13, "used by another process")
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", locked)
    with pytest.raises(YtError) as info:
        env.service.delete(BBB, capture.id)
    assert info.value.code == "E_OUTPUT_NOT_WRITABLE"
    monkeypatch.undo()
    assert env.service.list(BBB) == [capture]
    assert (env.captures / "c_1000.jpg").exists()


def test_reveal_dir_prefers_the_recorded_folder_then_the_planned_one(env: Env) -> None:
    assert env.service.reveal_dir(BBB) is None
    env.service.capture(BBB, 1_000)
    assert env.service.reveal_dir(BBB) == env.folder
    (env.folder / "frame_00-00-01.jpg").unlink()
    assert env.service.reveal_dir(BBB) == env.folder  # โฟลเดอร์ตามค่าตั้งปัจจุบันยังอยู่
    env.folder.rmdir()
    assert env.service.reveal_dir(BBB) is None
    assert env.service.reveal_dir("bad id") is None


@pytest.mark.parametrize(
    ("root", "rel"),
    [
        ("\\\\server\\share", f"a/{OUTPUT_DIR}/frame_00-00-01.jpg"),
        ("relative/root", f"a/{OUTPUT_DIR}/frame_00-00-01.jpg"),
        (None, f"a\\{OUTPUT_DIR}\\frame_00-00-01.jpg"),
        (None, f"C:/a/{OUTPUT_DIR}/frame_00-00-01.jpg"),
        (None, f"a/อื่น/frame_00-00-01.jpg"),
        (None, f"a/{OUTPUT_DIR}/notes.txt"),
        (None, f"{OUTPUT_DIR}/frame_00-00-01.jpg"),
    ],
)
def test_recorded_output_refuses_odd_paths(tmp_path: Path, root: str | None, rel: str) -> None:
    assert recorded_output(str(tmp_path) if root is None else root, rel) is None
