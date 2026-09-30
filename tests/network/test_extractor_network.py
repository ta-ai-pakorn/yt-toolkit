"""เทสที่ต่อยูทูปจริง รันเองด้วย: uv run pytest -m network -q tests/network"""

from __future__ import annotations

import io
import time
from collections.abc import Iterator

import pytest
from PIL import Image

from yttoolkit.core.extractor import YtDlpExtractor, ytdlp_version
from yttoolkit.core.yterrors import YtError

pytestmark = pytest.mark.network

BBB = "aqz-KE-bpKQ"  # Big Buck Bunny (Blender Foundation, CC BY 3.0)
PRIVATE = "yZIXLfi8CZQ"  # คลิปส่วนตัวที่ yt-dlp ใช้ในเทสของตัวเอง ('skip': 'Private video')
SINGLE_VIDEO_PLAYLIST = (
    "PLt5yu3-wZAlSLRHmI1qNm0wjyVNWw1pCU"  # จากเทสของ yt-dlp มีคลิปเดียวคือ BBB
)


@pytest.fixture(scope="module")
def ex() -> Iterator[YtDlpExtractor]:
    ytdlp_version()  # import yt_dlp ก่อน จะได้ไม่นับเวลา import ไปในเวลา probe
    extractor = YtDlpExtractor()
    yield extractor
    extractor.close()


def _timed_probe(ex: YtDlpExtractor) -> tuple[dict, float]:
    start = time.monotonic()
    info = ex.probe(BBB)
    return info, time.monotonic() - start


@pytest.fixture(scope="module")
def bbb(ex: YtDlpExtractor) -> tuple[dict, float]:
    return _timed_probe(ex)


def test_probe_is_fast(ex: YtDlpExtractor, bbb: tuple[dict, float]) -> None:
    # ครั้งแรกอาจช้าเพราะเน็ต/deno เริ่มทำงาน ให้ลองซ้ำได้หนึ่งครั้งแล้วดูเวลาที่ดีที่สุด
    times = [bbb[1]]
    if times[0] >= 5:
        times.append(_timed_probe(ex)[1])
    best = min(times)
    print(f"probe times: {', '.join(f'{t:.2f}s' for t in times)} (best {best:.2f}s)")
    assert best < 5, f"probe ใช้เวลา {best:.2f} วินาที"


def test_probe_has_storyboard(bbb: tuple[dict, float]) -> None:
    info, _ = bbb
    assert info["id"] == BBB
    assert info["live_status"] == "not_live"
    boards = {
        f["format_id"]: f
        for f in info["formats"]
        if f.get("format_note") == "storyboard"
    }
    assert "sb0" in boards
    sb0 = boards["sb0"]
    assert (sb0["width"], sb0["height"], sb0["rows"], sb0["columns"]) == (
        320,
        180,
        3,
        3,
    )
    assert len(sb0["fragments"]) == 15


def test_fetch_real_storyboard_grid(
    ex: YtDlpExtractor, bbb: tuple[dict, float]
) -> None:
    info, _ = bbb
    sb0 = next(f for f in info["formats"] if f["format_id"] == "sb0")
    data = ex.fetch(sb0["fragments"][0]["url"])
    with Image.open(io.BytesIO(data)) as img:
        assert img.size == (3 * sb0["width"], 3 * sb0["height"])


def test_private_video_is_classified(ex: YtDlpExtractor) -> None:
    with pytest.raises(YtError) as exc:
        ex.probe(PRIVATE)
    if "private" not in exc.value.detail.lower():
        pytest.skip(f"คลิปทดสอบไม่ได้เป็นส่วนตัวแล้ว: {exc.value.detail}")
    assert exc.value.code == "E_VIDEO_PRIVATE"


def test_missing_video_is_unavailable(ex: YtDlpExtractor) -> None:
    with pytest.raises(YtError) as exc:
        ex.probe("aaaaaaaaaaa")
    assert exc.value.code == "E_VIDEO_UNAVAILABLE"


def test_playlist_flat(ex: YtDlpExtractor) -> None:
    info = ex.playlist(SINGLE_VIDEO_PLAYLIST, 200)
    assert info["title"]
    (entry,) = info["entries"]
    assert entry["id"] == BBB
    assert entry["title"]
    assert entry["duration"] == 635
    assert entry.get("thumbnails") or entry.get("thumbnail")
