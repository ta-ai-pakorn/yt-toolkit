"""ถ่ายภาพคมตรงจุดของ extractor (M5 รอบ B2 C6): ตัวปลอมตัดชิ้นจาก fixture · ตัวจริงยิงคำขอแบบ Range ผ่าน yt-dlp (ถูกแทน ไม่ต่อเน็ต)"""

from __future__ import annotations

import io
import logging
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any, ClassVar, Self

import pytest
import yt_dlp
from yt_dlp.networking import Response
from yt_dlp.networking.exceptions import HTTPError, TransportError
from yt_dlp.utils import DownloadError

from yttoolkit.core.extractor import FakeExtractor, YtDlpExtractor
from yttoolkit.core.frame_piece import MediaIndex, read_index
from yttoolkit.core.yterrors import YtError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
PIECE = FIXTURES / "capture" / "piece.mp4"
BBB = "aqz-KE-bpKQ"
MEDIA_URL = "https://media.invalid/videoplayback?sig=SECRET"


def _index() -> tuple[bytes, MediaIndex]:
    data = PIECE.read_bytes()
    return data, read_index(lambda first, last: data[first : last + 1])


# ---------- ตัวปลอม ----------


def test_fake_cuts_the_fixture_and_maps_the_time_back(tmp_path: Path) -> None:
    fake = FakeExtractor(FIXTURES)
    dest = tmp_path / "work" / "piece.mp4"
    info = fake.fetch_frame_piece(BBB, 125_400, None, dest)
    data, index = _index()
    segment = index.sidx.refs[1]  # 125_400 % 4000 = 1400 อยู่ท่อนที่เริ่ม 1000
    assert dest.read_bytes() == index.init + data[segment.offset : segment.offset + segment.size]
    assert info.path == dest and info.segment_start_ms == 125_000
    assert (info.width, info.height, info.format_id, info.dynamic_range) == (1920, 1080, "fake-capture", None)
    assert ("fetch_frame_piece", BBB) in fake.calls


def test_fake_capture_clip_ignores_the_cap(tmp_path: Path) -> None:
    info = FakeExtractor(FIXTURES).fetch_frame_piece("CAPTURE0001", 3_999, 720, tmp_path / "p.mp4")
    assert info.segment_start_ms == 3_000 and info.height == 1080


@pytest.mark.parametrize(
    ("video_id", "code"),
    [
        ("CAPTURENO01", "E_CAPTURE_UNSUPPORTED"),
        ("CAPTUREBOT1", "E_BOT_CHECK"),
        ("CAPTURENET1", "E_NETWORK"),
        ("PRIVATEVID1", "E_VIDEO_PRIVATE"),
        ("UPCOMINGLV1", "E_LIVE_NOT_READY"),
        ("zzzzzzzzzzz", "E_VIDEO_UNAVAILABLE"),
    ],
)
def test_fake_failures_write_nothing(tmp_path: Path, video_id: str, code: str) -> None:
    dest = tmp_path / "piece.mp4"
    with pytest.raises(YtError) as info:
        FakeExtractor(FIXTURES).fetch_frame_piece(video_id, 1000, None, dest)
    assert info.value.code == code
    assert not dest.exists()


# ---------- ตัวจริง (yt_dlp.YoutubeDL ถูกแทน) ----------


def _format(**extra: Any) -> dict:
    return {
        "format_id": "137", "ext": "mp4", "protocol": "https", "vcodec": "avc1.640028", "acodec": "none",
        "width": 1920, "height": 1080, "url": MEDIA_URL, "http_headers": {"User-Agent": "ua", "Accept": "*/*"},
        **extra,
    }  # fmt: skip


class CaptureYDL:
    """แทน yt_dlp.YoutubeDL: extract_info คืน info ที่ตั้งไว้ · urlopen ตอบตามช่วงไบต์ของหัว Range จาก body"""

    instances: ClassVar[list[CaptureYDL]] = []
    info: ClassVar[object] = None
    body: ClassVar[bytes] = b""
    fail: ClassVar[BaseException | None] = None
    status: ClassVar[int] = 206  # 200 = เซิร์ฟเวอร์ไม่สน Range แล้วส่งทั้งไฟล์

    def __init__(self, params: dict) -> None:
        self.params = params
        self.url = ""
        self.requests: list[Any] = []
        CaptureYDL.instances.append(self)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def extract_info(self, url: str, download: bool = True) -> object:
        assert download is False
        self.url = url
        if isinstance(CaptureYDL.info, BaseException):
            raise CaptureYDL.info
        return CaptureYDL.info

    def sanitize_info(self, info: dict, remove_private_keys: bool = False) -> dict:
        return info

    def urlopen(self, request: Any) -> Response:
        self.requests.append(request)
        if CaptureYDL.fail is not None:
            raise CaptureYDL.fail
        if CaptureYDL.status != 206:
            return Response(io.BytesIO(CaptureYDL.body), request.url, {}, status=CaptureYDL.status)
        first, last = (int(n) for n in request.headers["Range"].removeprefix("bytes=").split("-"))
        return Response(io.BytesIO(CaptureYDL.body[first : last + 1]), request.url, {}, status=206)


@pytest.fixture
def ydl(monkeypatch: pytest.MonkeyPatch) -> type[CaptureYDL]:
    CaptureYDL.instances = []
    CaptureYDL.info = {"id": BBB, "live_status": "not_live", "formats": [_format()]}
    CaptureYDL.body = PIECE.read_bytes()
    CaptureYDL.fail = None
    CaptureYDL.status = 206
    monkeypatch.setattr(yt_dlp, "YoutubeDL", CaptureYDL)
    return CaptureYDL


def test_real_fetches_the_head_then_one_segment(ydl: type[CaptureYDL], tmp_path: Path, caplog) -> None:
    caplog.set_level(logging.INFO, logger="yttoolkit")
    dest = tmp_path / "piece.mp4"
    info = YtDlpExtractor().fetch_frame_piece(BBB, 2_550, 1080, dest)
    (inst,) = ydl.instances
    assert inst.url == f"https://www.youtube.com/watch?v={BBB}"
    assert inst.params["skip_download"] is True and inst.params["noplaylist"] is True
    data, index = _index()
    segment = index.sidx.refs[2]
    assert [r.headers["Range"] for r in inst.requests] == [
        "bytes=0-65535",
        f"bytes={segment.offset}-{segment.offset + segment.size - 1}",
    ]
    assert all(r.url == MEDIA_URL and r.headers["User-Agent"] == "ua" for r in inst.requests)
    assert dest.read_bytes() == index.init + data[segment.offset : segment.offset + segment.size]
    assert (info.segment_start_ms, info.format_id, info.width, info.height, info.dynamic_range) == (
        2_000, "137", 1920, 1080, None)  # fmt: skip
    assert "137" in caplog.text
    for secret in ("SECRET", "media.invalid", "User-Agent", str(tmp_path)):
        assert secret not in caplog.text


def test_real_respects_the_short_side_cap(ydl: type[CaptureYDL], tmp_path: Path) -> None:
    ydl.info = {"id": BBB, "live_status": "not_live",
                "formats": [_format(), _format(format_id="401", width=3840, height=2160, vcodec="av01.0.12M.08")]}  # fmt: skip
    assert YtDlpExtractor().fetch_frame_piece(BBB, 0, None, tmp_path / "a.mp4").format_id == "401"
    assert YtDlpExtractor().fetch_frame_piece(BBB, 0, 1080, tmp_path / "b.mp4").format_id == "137"


def test_real_without_an_mp4_format_is_unsupported_and_requests_nothing(ydl: type[CaptureYDL], tmp_path: Path) -> None:
    ydl.info = {"id": BBB, "live_status": "not_live", "formats": [_format(ext="webm", vcodec="vp9")]}
    with pytest.raises(YtError) as info:
        YtDlpExtractor().fetch_frame_piece(BBB, 0, None, tmp_path / "p.mp4")
    assert info.value.code == "E_CAPTURE_UNSUPPORTED"
    assert ydl.instances[0].requests == []


def test_real_live_clip_is_refused(ydl: type[CaptureYDL], tmp_path: Path) -> None:
    ydl.info = {"id": BBB, "live_status": "is_live", "formats": [_format()]}
    with pytest.raises(YtError) as info:
        YtDlpExtractor().fetch_frame_piece(BBB, 0, None, tmp_path / "p.mp4")
    assert info.value.code == "E_LIVE_NOT_READY"


@pytest.mark.parametrize(("status", "code"), [(429, "E_BOT_CHECK"), (403, "E_YT_REFUSED"), (503, "E_NETWORK")])
def test_real_http_errors_map_without_the_url(ydl: type[CaptureYDL], tmp_path: Path, status: int, code: str) -> None:
    ydl.fail = HTTPError(Response(io.BytesIO(b""), MEDIA_URL, {}, status=status))
    dest = tmp_path / "p.mp4"
    with pytest.raises(YtError) as info:
        YtDlpExtractor().fetch_frame_piece(BBB, 0, None, dest)
    assert info.value.code == code and info.value.detail == f"HTTP Error {status}"
    assert not dest.exists()


def test_real_closes_the_response_held_by_an_http_error(ydl: type[CaptureYDL], tmp_path: Path) -> None:
    response = Response(io.BytesIO(b""), MEDIA_URL, {}, status=503)
    ydl.fail = HTTPError(response)
    with pytest.raises(YtError):
        YtDlpExtractor().fetch_frame_piece(BBB, 0, None, tmp_path / "p.mp4")
    assert response.closed


def test_real_a_failing_close_does_not_mask_the_error(
    ydl: type[CaptureYDL], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    error = HTTPError(Response(io.BytesIO(b""), MEDIA_URL, {}, status=429))

    def broken_close() -> None:
        raise OSError("close failed")

    monkeypatch.setattr(error, "close", broken_close)
    ydl.fail = error
    with pytest.raises(YtError) as info:
        YtDlpExtractor().fetch_frame_piece(BBB, 0, None, tmp_path / "p.mp4")
    assert info.value.code == "E_BOT_CHECK" and info.value.detail == "HTTP Error 429"


def test_real_connection_errors_are_network_errors(ydl: type[CaptureYDL], tmp_path: Path) -> None:
    ydl.fail = TransportError("connection reset by media.invalid")
    with pytest.raises(YtError) as info:
        YtDlpExtractor().fetch_frame_piece(BBB, 0, None, tmp_path / "p.mp4")
    assert info.value.code == "E_NETWORK" and info.value.detail == "TransportError"


def test_real_a_server_that_ignores_range_is_a_network_error(ydl: type[CaptureYDL], tmp_path: Path) -> None:
    ydl.status = 200  # ตอบ 200 พร้อมทั้งไฟล์: ห้ามใช้ข้อมูลนั้นเป็นท่อน
    dest = tmp_path / "p.mp4"
    with pytest.raises(YtError) as info:
        YtDlpExtractor().fetch_frame_piece(BBB, 2_550, None, dest)
    assert info.value.code == "E_NETWORK" and info.value.detail == "range not honoured (HTTP 200)"
    assert len(ydl.instances[0].requests) == 1
    assert not dest.exists()


def test_real_probe_errors_are_classified(ydl: type[CaptureYDL], tmp_path: Path) -> None:
    ydl.info = DownloadError("ERROR: [youtube] aqz-KE-bpKQ: Sign in to confirm you're not a bot")
    with pytest.raises(YtError) as info:
        YtDlpExtractor().fetch_frame_piece(BBB, 0, None, tmp_path / "p.mp4")
    assert info.value.code == "E_BOT_CHECK"


def test_real_rejects_a_bad_video_id(ydl: type[CaptureYDL], tmp_path: Path) -> None:
    with pytest.raises(YtError) as info:
        YtDlpExtractor().fetch_frame_piece("../etc", 0, None, tmp_path / "p.mp4")
    assert info.value.code == "E_INVALID_INPUT" and ydl.instances == []


def test_real_probe_returning_nothing_is_unknown(ydl: type[CaptureYDL], tmp_path: Path) -> None:
    ydl.info = None
    with pytest.raises(YtError) as info:
        YtDlpExtractor().fetch_frame_piece(BBB, 0, None, tmp_path / "p.mp4")
    assert info.value.code == "E_UNKNOWN"
    assert ydl.instances[0].requests == []


def test_real_a_short_segment_read_is_a_network_error(ydl: type[CaptureYDL], tmp_path: Path) -> None:
    data, index = _index()
    last = index.sidx.refs[-1]
    ydl.body = data[: last.offset + last.size - 10]  # ท่อนสุดท้ายขาดท้าย 10 ไบต์ (หัวไฟล์ยังอ่านครบ)
    dest = tmp_path / "p.mp4"
    with pytest.raises(YtError) as info:
        YtDlpExtractor().fetch_frame_piece(BBB, 3_500, None, dest)
    assert info.value.code == "E_NETWORK" and info.value.detail == "short read"
    assert len(ydl.instances[0].requests) == 2
    assert not dest.exists()


class _SpySession:
    """แทน VisitorSession: jar ก้อนเดียว (เหมือน test_extractor.py)"""

    def __init__(self, folder: Path) -> None:
        self.path = folder / "visitor-session.txt"
        self._jar = CookieJar()
        self.saved: list[object] = []

    def jar(self) -> object:
        return self._jar

    def save(self, source: object = None) -> None:
        self.saved.append(source)


def test_real_probe_uses_the_visitor_session(ydl: type[CaptureYDL], tmp_path: Path) -> None:
    session = _SpySession(tmp_path)
    YtDlpExtractor(session=session).fetch_frame_piece(BBB, 0, None, tmp_path / "p.mp4")  # type: ignore[arg-type]
    (inst,) = ydl.instances
    assert inst.params["cookiefile"] == str(tmp_path / "visitor-session.txt")
    assert inst.__dict__["cookiejar"] is session.jar()


def test_real_without_a_session_passes_no_cookiefile(ydl: type[CaptureYDL], tmp_path: Path) -> None:
    YtDlpExtractor().fetch_frame_piece(BBB, 0, None, tmp_path / "p.mp4")
    assert "cookiefile" not in ydl.instances[0].params
