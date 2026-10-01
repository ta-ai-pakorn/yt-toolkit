from __future__ import annotations

import ast
import io
import json
import re
import threading
from http.cookiejar import CookieJar
from pathlib import Path
from typing import ClassVar, Self

import httpx
import pytest
import yt_dlp
from PIL import Image
from yt_dlp.networking.common import Response
from yt_dlp.networking.exceptions import HTTPError, RequestError, TransportError
from yt_dlp.utils import DownloadError, ExtractorError, UnsupportedError

from yttoolkit.core import extractor as extractor_mod
from yttoolkit.core import inputs
from yttoolkit.core.extractor import (
    Extractor,
    FakeExtractor,
    YtDlpExtractor,
    check_live,
)
from yttoolkit.core.yterrors import YtError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SRC = Path(__file__).resolve().parents[2] / "src" / "yttoolkit"
BBB = "aqz-KE-bpKQ"
ZOO = "jNQXAC9IVRw"
PLAYLIST = "PLfakeplaylist250"


@pytest.fixture
def fake() -> FakeExtractor:
    return FakeExtractor(FIXTURES)


def _storyboards(info: dict) -> list[dict]:
    return [f for f in info["formats"] if f.get("format_note") == "storyboard"]


def _sb0(info: dict) -> dict:
    return next(f for f in info["formats"] if f["format_id"] == "sb0")


# ---------- FakeExtractor: probe ----------


def test_fake_probe_returns_trimmed_real_info(fake: FakeExtractor) -> None:
    info = fake.probe(BBB)
    assert info["id"] == BBB
    assert info["duration"] == 635
    assert info["live_status"] == "not_live"
    sb0 = _sb0(info)
    assert (sb0["width"], sb0["height"], sb0["rows"], sb0["columns"]) == (
        320,
        180,
        3,
        3,
    )
    assert [frag["url"] for frag in sb0["fragments"]] == [
        f"https://fake.invalid/storyboard/{BBB}/M{n}.jpg" for n in range(15)
    ]
    frames = sum(
        min(9, round(frag["duration"] * sb0["fps"])) for frag in sb0["fragments"]
    )
    assert frames == 128


def test_fake_probe_short_video_has_no_storyboard(fake: FakeExtractor) -> None:
    info = fake.probe(ZOO)
    assert info["id"] == ZOO
    assert _storyboards(info) == []
    assert info["chapters"]


def test_fake_probe_returns_a_fresh_copy(fake: FakeExtractor) -> None:
    fake.probe(BBB)["title"] = "changed"
    assert fake.probe(BBB)["title"] != "changed"


def test_fake_probe_records_calls(fake: FakeExtractor) -> None:
    fake.probe(BBB)
    fake.probe(BBB)
    with pytest.raises(YtError):
        fake.probe("missingvid1")
    assert fake.calls == [("probe", BBB), ("probe", BBB), ("probe", "missingvid1")]


def test_fake_probe_missing_id_is_unavailable(fake: FakeExtractor) -> None:
    with pytest.raises(YtError) as exc:
        fake.probe("missingvid1")
    assert exc.value.code == "E_VIDEO_UNAVAILABLE"


def test_fake_probe_private_id(fake: FakeExtractor) -> None:
    with pytest.raises(YtError) as exc:
        fake.probe("PRIVATEVID1")
    assert exc.value.code == "E_VIDEO_PRIVATE"


def test_fake_probe_live_fixture_goes_through_live_check(fake: FakeExtractor) -> None:
    # live_upcoming.json หาเจอจาก id 11 ตัวในไฟล์ (UPCOMINGLV1)
    with pytest.raises(YtError) as exc:
        fake.probe("UPCOMINGLV1")
    assert exc.value.code == "E_LIVE_NOT_READY"


@pytest.mark.parametrize(
    "video_id",
    ["live_upcoming", "../playlist/x", "..\\probe\\x", "/etc/passwd", "", "."],
)
def test_fake_probe_uses_the_same_id_rule(fake: FakeExtractor, video_id: str) -> None:
    with pytest.raises(YtError) as exc:
        fake.probe(video_id)
    assert exc.value.code == "E_INVALID_INPUT"
    assert fake.calls == [("probe", video_id)]


# ---------- FakeExtractor: playlist ----------


def test_fake_playlist_reads_at_most_limit_plus_one(fake: FakeExtractor) -> None:
    info = fake.playlist(PLAYLIST, 200)
    assert info["title"]
    assert info["playlist_count"] == 250
    assert len(info["entries"]) == 201
    first = info["entries"][0]
    assert {"id", "title", "duration"} <= first.keys()
    assert first.get("thumbnails") or first.get("thumbnail")
    assert fake.calls == [("playlist", PLAYLIST)]


def test_fake_playlist_under_limit_returns_everything(fake: FakeExtractor) -> None:
    assert len(fake.playlist(PLAYLIST, 300)["entries"]) == 250


def test_fake_playlist_missing(fake: FakeExtractor) -> None:
    with pytest.raises(YtError) as exc:
        fake.playlist("PLdoesnotexist", 200)
    assert exc.value.code == "E_VIDEO_UNAVAILABLE"


@pytest.mark.parametrize("playlist_id", ["PLfake250", "PL/../x", "", "PL x" * 5])
def test_fake_playlist_uses_the_same_id_rule(
    fake: FakeExtractor, playlist_id: str
) -> None:
    with pytest.raises(YtError) as exc:
        fake.playlist(playlist_id, 200)
    assert exc.value.code == "E_INVALID_INPUT"


# ---------- FakeExtractor: fetch ----------


def test_fake_fetch_maps_storyboard_urls_to_fixture_files(fake: FakeExtractor) -> None:
    data = fake.fetch(f"https://fake.invalid/storyboard/{BBB}/M0.jpg")
    assert data == (FIXTURES / "storyboard" / BBB / "M0.jpg").read_bytes()
    assert fake.calls == [("fetch", f"https://fake.invalid/storyboard/{BBB}/M0.jpg")]


@pytest.mark.parametrize(
    "url",
    [
        f"https://fake.invalid/storyboard/{BBB}/M99.jpg",
        f"https://fake.invalid/storyboard/{BBB}/sb1/M0.jpg",
        "https://fake.invalid/storyboard/../probe/aqz-KE-bpKQ.json",
        "https://fake.invalid/storyboard/..%2Fprobe%2Faqz-KE-bpKQ.json",
        "https://fake.invalid/storyboard/",
        "https://i.ytimg.com/sb/aqz-KE-bpKQ/storyboard3_L3/M0.jpg",
        "file:///etc/passwd",
    ],
)
def test_fake_fetch_unknown_urls_are_network_errors(
    fake: FakeExtractor, url: str
) -> None:
    with pytest.raises(YtError) as exc:
        fake.fetch(url)
    assert exc.value.code == "E_NETWORK"


def test_every_sb0_fragment_has_a_decodable_grid(fake: FakeExtractor) -> None:
    sb0 = _sb0(fake.probe(BBB))
    for frag in sb0["fragments"]:
        with Image.open(io.BytesIO(fake.fetch(frag["url"]))) as img:
            img.load()
            # ช่องละ 320x180 ตาราง 3x3 (แผ่นสุดท้ายเล็กกว่าเพราะมีแค่ 2 ช่อง)
            assert img.width % sb0["width"] == 0 and img.height % sb0["height"] == 0
            assert img.width <= 3 * sb0["width"] and img.height <= 3 * sb0["height"]


# ---------- fixture hygiene ----------

_ALLOWED_TOP = {
    "id",
    "title",
    "channel",
    "uploader",
    "duration",
    "upload_date",
    "timestamp",
    "live_status",
    "availability",
    "thumbnail",
    "chapters",
    "playlist_count",
    "formats",
    "description",
    "subtitles",
    "automatic_captions",
    # owner round 2 (C-A1): ข้อมูลคลิป
    "view_count",
    "like_count",
    "comment_count",
    "channel_follower_count",
    "tags",
    "categories",
    "heatmap",
}
_ALLOWED_FORMAT = {
    "format_id",
    "format_note",
    "ext",
    "vcodec",
    "acodec",
    "height",
    "width",
    "fps",
    "abr",
    "tbr",
    "filesize",
    "filesize_approx",
    "language",
    "language_preference",
    "rows",
    "columns",
    "fragments",
}


@pytest.mark.parametrize(
    "path", sorted((FIXTURES / "probe").glob("*.json")), ids=lambda p: p.stem
)
def test_probe_fixtures_are_trimmed(path: Path) -> None:
    info = json.loads(path.read_text(encoding="utf-8"))
    assert info.keys() <= _ALLOWED_TOP
    for fmt in info["formats"]:
        assert fmt.keys() <= _ALLOWED_FORMAT, fmt["format_id"]
        assert "url" not in fmt
        if fmt.get("format_note") == "storyboard":
            for frag in fmt["fragments"]:
                assert frag.keys() == {"url", "duration"}
                assert frag["url"].startswith(
                    f"https://fake.invalid/storyboard/{info['id']}/"
                )
        else:
            assert "fragments" not in fmt


_TEXT_SUFFIXES = {".json", ".txt", ".md"}
# พารามิเตอร์ของลิงก์ที่มีลายเซ็น/วันหมดอายุ/ผูก IP ห้ามหลุดเข้า repo
_SIGNED_PARAM = re.compile(r"(?:sig|sigh|sqp|expire|rs)=|[?&/]ip[=/]")


def test_no_signed_urls_in_fixtures() -> None:
    files = [p for p in FIXTURES.rglob("*") if p.suffix in _TEXT_SUFFIXES]
    assert len(files) > 30
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "googlevideo.com" not in text, path
        assert "i.ytimg.com/sb/" not in text, path
        assert not _SIGNED_PARAM.search(text), path


# ---------- check_live ----------


@pytest.mark.parametrize("status", ["is_live", "is_upcoming"])
def test_check_live_rejects_live_and_upcoming(status: str) -> None:
    with pytest.raises(YtError) as exc:
        check_live({"live_status": status})
    assert exc.value.code == "E_LIVE_NOT_READY"


@pytest.mark.parametrize("status", ["not_live", "was_live", "post_live", None])
def test_check_live_passes_other_statuses(status: str | None) -> None:
    info = {"live_status": status}
    assert check_live(info) is info


# ---------- YtDlpExtractor (yt-dlp is replaced, no network) ----------


class FakeYDL:
    """แทน yt_dlp.YoutubeDL บันทึก options/URL แล้วคืนผลหรือโยน error ที่ตั้งไว้"""

    instances: ClassVar[list[FakeYDL]] = []
    result: ClassVar[object] = None

    def __init__(self, params: dict) -> None:
        self.params = params
        self.urls: list[str] = []
        FakeYDL.instances.append(self)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        # yt-dlp จริงเรียก save_cookies ตอนปิด (_attach_session แทนด้วยของเซสชัน)
        save = self.__dict__.get("save_cookies")
        if save is not None:
            save()

    def extract_info(self, url: str, download: bool = True) -> dict | None:
        assert download is False
        self.urls.append(url)
        if isinstance(FakeYDL.result, BaseException):
            raise FakeYDL.result
        return FakeYDL.result

    def sanitize_info(self, info: dict) -> dict:
        return info


@pytest.fixture
def ydl(monkeypatch: pytest.MonkeyPatch) -> type[FakeYDL]:
    FakeYDL.instances = []
    FakeYDL.result = {"id": BBB, "live_status": "not_live", "formats": []}
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    return FakeYDL


def test_ytdlp_probe_options_and_url(ydl: type[FakeYDL]) -> None:
    info = YtDlpExtractor().probe(BBB)
    assert info["id"] == BBB
    (inst,) = ydl.instances
    expected = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": 10,
    }
    assert expected.items() <= inst.params.items()
    assert inst.urls == [f"https://www.youtube.com/watch?v={BBB}"]


@pytest.mark.parametrize("status", ["is_live", "is_upcoming"])
def test_ytdlp_probe_live_check(ydl: type[FakeYDL], status: str) -> None:
    ydl.result = {"id": BBB, "live_status": status}
    with pytest.raises(YtError) as exc:
        YtDlpExtractor().probe(BBB)
    assert exc.value.code == "E_LIVE_NOT_READY"


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (
            DownloadError("ERROR: [youtube] yZIXLfi8CZQ: Private video"),
            "E_VIDEO_PRIVATE",
        ),
        (
            DownloadError(
                "\x1b[0;31mERROR:\x1b[0m [youtube] x: Sign in to confirm you’re not a bot"
            ),
            "E_BOT_CHECK",
        ),
        (
            ExtractorError("This live event will begin in 3 hours.", expected=True),
            "E_LIVE_NOT_READY",
        ),
        (DownloadError("ERROR: something odd"), "E_UNKNOWN"),
    ],
)
def test_ytdlp_errors_are_wrapped(
    ydl: type[FakeYDL], error: Exception, code: str
) -> None:
    ydl.result = error
    with pytest.raises(YtError) as exc:
        YtDlpExtractor().probe(BBB)
    assert exc.value.code == code
    assert exc.value.detail
    assert "\x1b" not in exc.value.detail  # ตัดรหัสสีของเทอร์มินัลออก
    assert exc.value.__cause__ is error


def test_ytdlp_playlist_options_and_truncation(ydl: type[FakeYDL]) -> None:
    ydl.result = {
        "id": PLAYLIST,
        "title": "t",
        "entries": iter([{"id": f"v{n:010d}", "title": str(n)} for n in range(10)]),
    }
    info = YtDlpExtractor().playlist("PLt5yu3-wZAlSLRHmI1qNm0wjyVNWw1pCU", 3)
    (inst,) = ydl.instances
    assert inst.params["extract_flat"] == "in_playlist"
    assert inst.params["playlistend"] == 4
    assert inst.params["quiet"] is True
    assert inst.params["socket_timeout"] == 10
    assert "noplaylist" not in inst.params
    assert inst.urls == [
        "https://www.youtube.com/playlist?list=PLt5yu3-wZAlSLRHmI1qNm0wjyVNWw1pCU"
    ]
    assert isinstance(info["entries"], list)
    assert len(info["entries"]) == 4


def test_ytdlp_playlist_without_entries(ydl: type[FakeYDL]) -> None:
    ydl.result = {"id": "PLempty0000", "title": "t", "entries": None}
    assert YtDlpExtractor().playlist("PLempty0000", 200)["entries"] == []


_UNEXPECTED = [
    (UnsupportedError("https://www.youtube.com/x"), "E_UNKNOWN"),
    (RequestError("Connection to www.youtube.com timed out."), "E_NETWORK"),
    (TransportError("getaddrinfo failed"), "E_NETWORK"),
    (RuntimeError("boom inside yt-dlp"), "E_UNKNOWN"),
    (KeyError("formats"), "E_UNKNOWN"),
]


@pytest.mark.parametrize(("error", "code"), _UNEXPECTED)
def test_ytdlp_probe_wraps_every_error(
    ydl: type[FakeYDL], error: Exception, code: str
) -> None:
    ydl.result = error
    with pytest.raises(YtError) as exc:
        YtDlpExtractor().probe(BBB)
    assert exc.value.code == code
    assert exc.value.detail
    assert exc.value.__cause__ is error


@pytest.mark.parametrize(("error", "code"), _UNEXPECTED)
def test_ytdlp_playlist_wraps_every_error(
    ydl: type[FakeYDL], error: Exception, code: str
) -> None:
    ydl.result = error
    with pytest.raises(YtError) as exc:
        YtDlpExtractor().playlist(PLAYLIST, 200)
    assert exc.value.code == code
    assert exc.value.__cause__ is error


def test_unexpected_error_detail_names_the_type(ydl: type[FakeYDL]) -> None:
    ydl.result = RuntimeError("boom")
    with pytest.raises(YtError) as exc:
        YtDlpExtractor().probe(BBB)
    assert exc.value.detail == "RuntimeError: boom"


def test_ytdlp_none_result_is_unknown(ydl: type[FakeYDL]) -> None:
    ydl.result = None
    with pytest.raises(YtError) as exc:
        YtDlpExtractor().probe(BBB)
    assert exc.value.code == "E_UNKNOWN"
    with pytest.raises(YtError) as exc:
        YtDlpExtractor().playlist(PLAYLIST, 200)
    assert exc.value.code == "E_UNKNOWN"


def test_ytdlp_playlist_errors_are_wrapped(ydl: type[FakeYDL]) -> None:
    ydl.result = DownloadError(
        "ERROR: [youtube:tab] PLx: YouTube said: The playlist does not exist."
    )
    with pytest.raises(YtError) as exc:
        YtDlpExtractor().playlist("PLaaaaaaaaaa", 200)
    assert exc.value.code == "E_VIDEO_UNAVAILABLE"


@pytest.mark.parametrize(
    "video_id", ["short", "aqz-KE-bpKQ&list=x", "aqz-KE-bpK/", "../../etc/pw"]
)
def test_ytdlp_probe_rejects_malformed_ids_without_calling_ytdlp(
    ydl: type[FakeYDL], video_id: str
) -> None:
    with pytest.raises(YtError) as exc:
        YtDlpExtractor().probe(video_id)
    assert exc.value.code == "E_INVALID_INPUT"
    assert ydl.instances == []


@pytest.mark.parametrize(
    "playlist_id", ["", "PL&x=1", "PL/../x", "PL x", "PLfake250", "P" * 65]
)
def test_ytdlp_playlist_rejects_malformed_ids(
    ydl: type[FakeYDL], playlist_id: str
) -> None:
    with pytest.raises(YtError) as exc:
        YtDlpExtractor().playlist(playlist_id, 200)
    assert exc.value.code == "E_INVALID_INPUT"
    assert ydl.instances == []


# ---------- YtDlpExtractor.fetch (httpx transport is replaced, no network) ----------

URL = "https://i.ytimg.com/sb/x/M0.jpg"


def _mock(handler) -> YtDlpExtractor:
    return YtDlpExtractor(transport=httpx.MockTransport(handler))


def test_ytdlp_fetch_ok() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"img")

    extractor = _mock(handler)
    try:
        assert extractor.fetch(URL) == b"img"
    finally:
        extractor.close()
    assert [str(r.url) for r in seen] == [URL]
    assert seen[0].method == "GET"


def test_ytdlp_fetch_keeps_timeout_and_follows_redirects() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("M0.jpg"):
            return httpx.Response(302, headers={"Location": "https://i.ytimg.com/sb/x/M0b.jpg"})
        return httpx.Response(200, content=b"moved")

    extractor = _mock(handler)
    try:
        assert extractor.fetch(URL) == b"moved"
        client = extractor._http()
        assert client.timeout == httpx.Timeout(10)
        assert client.follow_redirects is True
    finally:
        extractor.close()


@pytest.mark.parametrize(
    "outcome",
    [
        httpx.ConnectError("getaddrinfo failed"),
        httpx.ReadTimeout("timed out"),
        404,
        503,
    ],
    ids=["connect", "timeout", "404", "503"],
)
def test_ytdlp_fetch_failure_is_network_error(outcome: object) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if isinstance(outcome, Exception):
            raise outcome
        return httpx.Response(outcome)

    extractor = _mock(handler)
    try:
        with pytest.raises(YtError) as exc:
            extractor.fetch(URL)
    finally:
        extractor.close()
    assert exc.value.code == "E_NETWORK"
    assert exc.value.detail


class _CountingClient(httpx.Client):
    created: ClassVar[int] = 0
    closed: ClassVar[int] = 0

    def __init__(self, *args: object, **kwargs: object) -> None:
        type(self).created += 1
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    def close(self) -> None:
        type(self).closed += 1
        super().close()


@pytest.fixture
def counting(monkeypatch: pytest.MonkeyPatch) -> type[_CountingClient]:
    _CountingClient.created = _CountingClient.closed = 0
    monkeypatch.setattr(extractor_mod.httpx, "Client", _CountingClient)
    return _CountingClient


def test_ytdlp_fetch_reuses_one_client(counting: type[_CountingClient]) -> None:
    extractor = _mock(lambda request: httpx.Response(200, content=b"x"))
    assert counting.created == 0  # สร้างเมื่อใช้ครั้งแรกเท่านั้น
    for _ in range(5):
        extractor.fetch(URL)
    assert counting.created == 1
    extractor.close()
    assert counting.closed == 1


def test_ytdlp_fetch_is_thread_safe_and_creates_one_client(
    counting: type[_CountingClient],
) -> None:
    import threading
    import time

    def handler(request: httpx.Request) -> httpx.Response:
        time.sleep(0.01)
        return httpx.Response(200, content=request.url.path.encode())

    extractor = _mock(handler)
    barrier = threading.Barrier(16)
    results: list[bytes] = []
    errors: list[BaseException] = []

    def worker(n: int) -> None:
        try:
            barrier.wait(5)
            results.append(extractor.fetch(f"https://i.ytimg.com/sb/x/M{n}.jpg"))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    extractor.close()
    assert not errors
    assert sorted(results) == sorted(f"/sb/x/M{n}.jpg".encode() for n in range(16))
    assert counting.created == 1


def test_ytdlp_close_is_safe_to_repeat_and_before_use(
    counting: type[_CountingClient],
) -> None:
    extractor = _mock(lambda request: httpx.Response(200, content=b"x"))
    extractor.close()  # ยังไม่เคยสร้าง client
    assert counting.created == 0
    extractor.fetch(URL)
    extractor.close()
    extractor.close()
    assert counting.closed == 1


def test_ytdlp_fetch_after_close_opens_a_new_client(
    counting: type[_CountingClient],
) -> None:
    extractor = _mock(lambda request: httpx.Response(200, content=b"x"))
    extractor.fetch(URL)
    extractor.close()
    assert extractor.fetch(URL) == b"x"
    extractor.close()
    assert (counting.created, counting.closed) == (2, 2)


# ---------- protocol and module boundaries ----------


def test_both_implementations_satisfy_the_protocol(fake: FakeExtractor) -> None:
    assert isinstance(fake, Extractor)
    assert isinstance(YtDlpExtractor(), Extractor)


def test_ytdlp_version_is_read_through_the_adapter() -> None:
    assert extractor_mod.ytdlp_version() == yt_dlp.version.__version__


def _imports_yt_dlp(source: str) -> bool:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        else:
            continue
        if any(name == "yt_dlp" or name.startswith("yt_dlp.") for name in names):
            return True
    # นำเข้าแบบไดนามิก
    return bool(re.search(r"""(?:import_module|__import__)\(\s*["']yt_dlp""", source))


def test_import_detector() -> None:
    assert _imports_yt_dlp("def f():\n    from yt_dlp.version import __version__")
    assert _imports_yt_dlp("import os, yt_dlp as y")
    assert _imports_yt_dlp("importlib.import_module('yt_dlp.utils')")
    assert _imports_yt_dlp('__import__("yt_dlp")')
    assert not _imports_yt_dlp("from .extractor import ytdlp_version\nimport yt_dlpx")


def test_only_extractor_imports_yt_dlp() -> None:
    offenders = [
        p.relative_to(SRC).as_posix()
        for p in SRC.rglob("*.py")
        if _imports_yt_dlp(p.read_text(encoding="utf-8"))
    ]
    assert offenders == ["core/extractor.py"]


def test_one_id_rule_everywhere() -> None:
    assert extractor_mod.VIDEO_ID is inputs.VIDEO_ID
    assert extractor_mod.PLAYLIST_ID is inputs.PLAYLIST_ID


def test_extractor_does_not_import_api_or_platform() -> None:
    text = (SRC / "core" / "extractor.py").read_text(encoding="utf-8")
    assert not re.search(
        r"^\s*(?:from|import)\s+(?:yttoolkit\.|\.\.)(?:api|platform)",
        text,
        re.MULTILINE,
    )


# ---------- warm-up (final review: import yt-dlp ตั้งแต่เปิดแอพ ลิงก์แรกจะได้ไม่ต้องรอ) ----------


def test_warm_up_loads_yt_dlp_and_the_youtube_extractor(
    ydl: type[FakeYDL], monkeypatch: pytest.MonkeyPatch
) -> None:
    looked_up: list[str] = []
    monkeypatch.setattr(
        FakeYDL, "get_info_extractor", lambda self, key: looked_up.append(key), raising=False
    )
    YtDlpExtractor().warm_up()
    assert looked_up == ["Youtube"]
    assert ydl.instances[0].params["quiet"] is True  # ใช้ตัวเลือกเดียวกับ probe (ไม่พิมพ์ลงจอ)
    assert all(not i.urls for i in ydl.instances)  # ไม่ดึงข้อมูลจากเน็ต


def test_warm_up_raises_when_yt_dlp_cannot_be_imported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(__import__("sys").modules, "yt_dlp", None)
    with pytest.raises(ImportError):
        YtDlpExtractor().warm_up()


def test_fake_extractor_has_no_warm_up(fake: FakeExtractor) -> None:
    assert not hasattr(fake, "warm_up")  # โหมดข้อมูลปลอมไม่ต้อง import yt-dlp


# ---------- มิกซ์ (list=RD...) ----------

MIX = "RDaqz-KE-bpKQ"


def test_fake_mix_reads_at_most_limit_plus_one(fake: FakeExtractor) -> None:
    info = fake.playlist(MIX, 25, video_id=BBB)
    assert info["id"] == MIX
    assert len(info["entries"]) == 26
    assert info["entries"][0]["id"] == BBB
    assert fake.calls == [("playlist", MIX)]


def test_fake_mix_needs_the_starting_clip(fake: FakeExtractor) -> None:
    with pytest.raises(YtError) as exc:
        fake.playlist(MIX, 25)
    assert exc.value.code == "E_INVALID_INPUT"


def test_ytdlp_mix_is_read_from_the_watch_link(ydl: type[FakeYDL]) -> None:
    ydl.result = {
        "id": MIX,
        "title": "t",
        "entries": iter([{"id": f"v{n:010d}", "title": str(n)} for n in range(40)]),
    }
    info = YtDlpExtractor().playlist(MIX, 25, video_id=BBB)
    (inst,) = ydl.instances
    assert inst.params["extract_flat"] == "in_playlist"
    assert inst.params["playlistend"] == 26
    assert "noplaylist" not in inst.params
    assert inst.urls == [f"https://www.youtube.com/watch?v={BBB}&list={MIX}"]
    assert len(info["entries"]) == 26


def test_ytdlp_normal_playlist_ignores_the_video_id(ydl: type[FakeYDL]) -> None:
    ydl.result = {"id": PLAYLIST, "title": "t", "entries": []}
    YtDlpExtractor().playlist(PLAYLIST, 200, video_id=BBB)
    (inst,) = ydl.instances
    assert inst.urls == [f"https://www.youtube.com/playlist?list={PLAYLIST}"]


@pytest.mark.parametrize("video_id", [None, "", "short", f"{BBB}&x=1"])
def test_ytdlp_mix_needs_a_valid_starting_clip(
    ydl: type[FakeYDL], video_id: str | None
) -> None:
    with pytest.raises(YtError) as exc:
        YtDlpExtractor().playlist(MIX, 25, video_id=video_id)
    assert exc.value.code == "E_INVALID_INPUT"
    assert ydl.instances == []


def test_ytdlp_curated_music_playlist_is_read_as_a_playlist(ydl: type[FakeYDL]) -> None:
    curated = "RDCLAK5uy_abcdefghij"
    ydl.result = {"id": curated, "title": "t", "entries": []}
    YtDlpExtractor().playlist(curated, 200)
    (inst,) = ydl.instances
    assert inst.urls == [f"https://www.youtube.com/playlist?list={curated}"]


# ---------- fetch_subtitle: FakeExtractor ----------

SUBS = "https://fake.invalid/subs/"
SUB_VID = "SUBTEST0001"


def _json3(events: list[dict], **extra: object) -> bytes:
    doc = {"wireMagic": "pb3", **extra, "events": events}
    return json.dumps(doc, ensure_ascii=False).encode("utf-8")


@pytest.fixture
def subs_root(tmp_path: Path) -> Path:
    folder = tmp_path / "subs" / SUB_VID
    folder.mkdir(parents=True)
    (folder / "th.json3").write_bytes(
        _json3(
            [
                {"tStartMs": 0, "dDurationMs": 1500, "segs": [{"utf8": "สวัสดี"}]},
                {"tStartMs": 2000, "dDurationMs": 1200, "segs": [{"utf8": "ครับ"}]},
            ]
        )
    )
    (folder / "th.vtt").write_bytes(b"WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhi\n")
    (folder / "tlang-en.json3").write_bytes(b'{"events": [], "tag": "english"}')
    (tmp_path / "secret.json3").write_bytes(b"do not read")
    return tmp_path


@pytest.fixture
def fake_subs(subs_root: Path) -> FakeExtractor:
    return FakeExtractor(subs_root)


def test_fake_subs_prefix_constant() -> None:
    assert FakeExtractor.SUBS_PREFIX == "https://fake.invalid/subs/"


def test_fake_fetch_subtitle_returns_the_file_bytes_unchanged(
    fake_subs: FakeExtractor, subs_root: Path
) -> None:
    expected = (subs_root / "subs" / SUB_VID / "th.json3").read_bytes()
    assert fake_subs.fetch_subtitle(f"{SUBS}{SUB_VID}/th.json3") == expected
    assert fake_subs.fetch_subtitle(f"{SUBS}{SUB_VID}/th.vtt").startswith(b"WEBVTT")


def test_fake_fetch_subtitle_tlang_maps_to_tlang_file(fake_subs: FakeExtractor) -> None:
    data = fake_subs.fetch_subtitle(f"{SUBS}{SUB_VID}/th-orig.json3?tlang=en")
    assert json.loads(data)["tag"] == "english"


def test_fake_fetch_subtitle_ignores_unrelated_query_keys(fake_subs: FakeExtractor) -> None:
    data = fake_subs.fetch_subtitle(f"{SUBS}{SUB_VID}/th.vtt?expire=1&sig=abc")
    assert data.startswith(b"WEBVTT")


def test_fake_fetch_subtitle_repeat_tiles_events_with_shifted_starts(
    fake_subs: FakeExtractor,
) -> None:
    data = fake_subs.fetch_subtitle(f"{SUBS}{SUB_VID}/th.json3?repeat=3")
    doc = json.loads(data)
    events = doc["events"]
    assert len(events) == 6
    assert doc["wireMagic"] == "pb3"
    # span = max(tStartMs + dDurationMs) = 3200 -> ปัดขึ้นเป็น 4000
    assert [e["tStartMs"] for e in events] == [0, 2000, 4000, 6000, 8000, 10000]
    assert [e["dDurationMs"] for e in events] == [1500, 1200] * 3
    assert events[4]["segs"] == [{"utf8": "สวัสดี"}]
    assert "สวัสดี" in data.decode("utf-8")  # ensure_ascii=False


def test_fake_fetch_subtitle_repeat_rounds_span_up_to_a_whole_second(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "subs" / SUB_VID
    folder.mkdir(parents=True)
    (folder / "a.json3").write_bytes(_json3([{"tStartMs": 100, "dDurationMs": 2000}]))
    (folder / "b.json3").write_bytes(_json3([{"tStartMs": 0, "dDurationMs": 3000}]))
    fake = FakeExtractor(tmp_path)
    a = json.loads(fake.fetch_subtitle(f"{SUBS}{SUB_VID}/a.json3?repeat=2"))
    b = json.loads(fake.fetch_subtitle(f"{SUBS}{SUB_VID}/b.json3?repeat=2"))
    assert [e["tStartMs"] for e in a["events"]] == [100, 3100]
    assert [e["tStartMs"] for e in b["events"]] == [0, 3000]


@pytest.mark.parametrize("repeat", ["0", "51", "-1", "abc", ""])
def test_fake_fetch_subtitle_repeat_out_of_range_is_network_error(
    fake_subs: FakeExtractor, repeat: str
) -> None:
    with pytest.raises(YtError) as exc:
        fake_subs.fetch_subtitle(f"{SUBS}{SUB_VID}/th.json3?repeat={repeat}")
    assert exc.value.code == "E_NETWORK"


def test_fake_fetch_subtitle_repeat_limits_are_inclusive(fake_subs: FakeExtractor) -> None:
    one = fake_subs.fetch_subtitle(f"{SUBS}{SUB_VID}/th.json3?repeat=1")
    fifty = fake_subs.fetch_subtitle(f"{SUBS}{SUB_VID}/th.json3?repeat=50")
    assert len(json.loads(one)["events"]) == 2
    assert len(json.loads(fifty)["events"]) == 100


def test_fake_fetch_subtitle_repeat_is_json3_only(fake_subs: FakeExtractor) -> None:
    with pytest.raises(YtError) as exc:
        fake_subs.fetch_subtitle(f"{SUBS}{SUB_VID}/th.vtt?repeat=2")
    assert exc.value.code == "E_NETWORK"


@pytest.mark.parametrize(
    "url",
    [
        f"{SUBS}../secret.json3",
        f"{SUBS}{SUB_VID}/../../secret.json3",
        f"{SUBS}%2e%2e/secret.json3",
        f"{SUBS}{SUB_VID}/%2e%2e%2fsecret.json3",
        f"{SUBS}{SUB_VID}\\th.json3",
        f"{SUBS}..\\secret.json3",
        f"{SUBS}/etc/passwd",
        f"{SUBS}C:/Windows/win.ini",
        "https://fake.invalid/subs//etc/passwd",
        "https://other.example/subs/SUBTEST0001/th.json3",
        "http://fake.invalid/subs/SUBTEST0001/th.json3",
        "file:///etc/passwd",
        "/subs/SUBTEST0001/th.json3",
        f"{SUBS}",
        f"{SUBS}{SUB_VID}",
        f"{SUBS}{SUB_VID}/",
        f"{SUBS}{SUB_VID}/th.json3/extra",
        f"{SUBS}{SUB_VID}/missing.json3",
        f"{SUBS}{SUB_VID}/th.json3?tlang=../x",
        f"{SUBS}{SUB_VID}/th.json3?tlang=%2e%2e",
        f"{SUBS}{SUB_VID}/th.json3?tlang=zz",
        f"{SUBS}NOSUCHVIDEO/th.json3",
    ],
)
def test_fake_fetch_subtitle_bad_or_missing_paths_are_network_errors(
    fake_subs: FakeExtractor, url: str
) -> None:
    with pytest.raises(YtError) as exc:
        fake_subs.fetch_subtitle(url)
    assert exc.value.code == "E_NETWORK"
    assert "fake" in exc.value.detail


def test_fake_fetch_subtitle_records_calls(fake_subs: FakeExtractor) -> None:
    ok = f"{SUBS}{SUB_VID}/th.vtt"
    bad = f"{SUBS}{SUB_VID}/missing.vtt"
    fake_subs.fetch_subtitle(ok)
    with pytest.raises(YtError):
        fake_subs.fetch_subtitle(bad)
    assert fake_subs.calls == [("fetch_subtitle", ok), ("fetch_subtitle", bad)]


# ---------- fetch_subtitle: YtDlpExtractor (urlopen replaced, no network) ----------

TIMEDTEXT = "https://www.youtube.com/api/timedtext?v=x&fmt=json3"


def _http_error(status: int) -> HTTPError:
    return HTTPError(Response(io.BytesIO(b""), TIMEDTEXT, {}, status=status))


class UrlopenYDL:
    """แทน yt_dlp.YoutubeDL ให้ urlopen คืนไบต์หรือโยน error ที่ตั้งไว้ (บันทึก Request ที่ได้ด้วย)"""

    instances: ClassVar[list[UrlopenYDL]] = []
    outcome: ClassVar[object] = None
    impersonate: ClassVar[object] = True  # ผลของ _impersonate_target_available (exception = โยน)

    def __init__(self, params: dict) -> None:
        self.params = params
        self.urls: list[str] = []
        self.requests: list[object] = []
        self.entered = 0
        self.exited = 0
        UrlopenYDL.instances.append(self)

    def __enter__(self) -> Self:
        self.entered += 1
        return self

    def __exit__(self, *exc: object) -> None:
        self.exited += 1
        save = self.__dict__.get("save_cookies")
        if save is not None:
            save()

    def _impersonate_target_available(self, target: object) -> bool:
        if isinstance(UrlopenYDL.impersonate, BaseException):
            raise UrlopenYDL.impersonate
        return bool(UrlopenYDL.impersonate)

    def urlopen(self, req: object) -> io.BytesIO:
        self.requests.append(req)
        url = getattr(req, "url", req)
        assert isinstance(url, str)
        self.urls.append(url)
        if isinstance(UrlopenYDL.outcome, BaseException):
            raise UrlopenYDL.outcome
        assert isinstance(UrlopenYDL.outcome, bytes)
        return io.BytesIO(UrlopenYDL.outcome)


@pytest.fixture
def urlopen_ydl(monkeypatch: pytest.MonkeyPatch) -> type[UrlopenYDL]:
    UrlopenYDL.instances = []
    UrlopenYDL.outcome = b"x"
    UrlopenYDL.impersonate = True
    monkeypatch.setattr(yt_dlp, "YoutubeDL", UrlopenYDL)
    return UrlopenYDL


def test_ytdlp_fetch_subtitle_returns_the_body(urlopen_ydl: type[UrlopenYDL]) -> None:
    assert YtDlpExtractor().fetch_subtitle(TIMEDTEXT) == b"x"
    (inst,) = urlopen_ydl.instances
    assert inst.urls == [TIMEDTEXT]
    assert (inst.entered, inst.exited) == (1, 1)
    expected = {"quiet": True, "skip_download": True, "socket_timeout": 10}
    assert expected.items() <= inst.params.items()
    assert inst.params["logger"] is not None


def test_ytdlp_fetch_subtitle_429_is_bot_check(urlopen_ydl: type[UrlopenYDL]) -> None:
    urlopen_ydl.outcome = _http_error(429)
    with pytest.raises(YtError) as exc:
        YtDlpExtractor().fetch_subtitle(TIMEDTEXT)
    assert exc.value.code == "E_BOT_CHECK"
    assert "429" in exc.value.detail


@pytest.mark.parametrize("status", [403, 404, 410, 500, 502, 401])
def test_ytdlp_fetch_subtitle_other_http_errors_are_network(
    urlopen_ydl: type[UrlopenYDL], status: int
) -> None:
    urlopen_ydl.outcome = _http_error(status)
    with pytest.raises(YtError) as exc:
        YtDlpExtractor().fetch_subtitle(TIMEDTEXT)
    assert exc.value.code == "E_NETWORK"
    assert str(status) in exc.value.detail


@pytest.mark.parametrize("error_type", [TransportError, RequestError])
def test_ytdlp_fetch_subtitle_request_error_is_network(
    urlopen_ydl: type[UrlopenYDL], error_type: type[RequestError]
) -> None:
    urlopen_ydl.outcome = error_type("Connection reset by peer")
    with pytest.raises(YtError) as exc:
        YtDlpExtractor().fetch_subtitle(TIMEDTEXT)
    assert exc.value.code == "E_NETWORK"


def test_ytdlp_fetch_subtitle_other_ytdlp_errors_go_through_classify(
    urlopen_ydl: type[UrlopenYDL],
) -> None:
    urlopen_ydl.outcome = DownloadError("\x1b[0;31mERROR:\x1b[0m Video unavailable")
    with pytest.raises(YtError) as exc:
        YtDlpExtractor().fetch_subtitle(TIMEDTEXT)
    assert exc.value.code == "E_VIDEO_UNAVAILABLE"
    assert "\x1b" not in exc.value.detail


def test_ytdlp_fetch_subtitle_strips_ansi_from_network_details(
    urlopen_ydl: type[UrlopenYDL],
) -> None:
    urlopen_ydl.outcome = TransportError("\x1b[0;31mERROR:\x1b[0m reset")
    with pytest.raises(YtError) as exc:
        YtDlpExtractor().fetch_subtitle(TIMEDTEXT)
    assert exc.value.code == "E_NETWORK"
    assert "\x1b" not in exc.value.detail


def test_ytdlp_fetch_subtitle_unexpected_error_is_unknown(
    urlopen_ydl: type[UrlopenYDL],
) -> None:
    urlopen_ydl.outcome = KeyError("boom")
    with pytest.raises(YtError) as exc:
        YtDlpExtractor().fetch_subtitle(TIMEDTEXT)
    assert exc.value.code == "E_UNKNOWN"
    assert "KeyError" in exc.value.detail


def test_protocol_requires_fetch_subtitle(fake: FakeExtractor) -> None:
    assert isinstance(fake, Extractor)
    assert isinstance(YtDlpExtractor(), Extractor)

    class NoSubs:
        def probe(self, video_id: str) -> dict:
            return {}

        def playlist(self, playlist_id: str, limit: int, video_id: str | None = None) -> dict:
            return {}

        def fetch(self, url: str) -> bytes:
            return b""

    assert not isinstance(NoSubs(), Extractor)


# ---------- owner round 3: impersonation + เซสชันผู้ชม ----------


def test_ytdlp_fetch_subtitle_asks_for_impersonation(urlopen_ydl: type[UrlopenYDL]) -> None:
    from yt_dlp.networking import Request
    from yt_dlp.networking.impersonate import ImpersonateTarget

    assert YtDlpExtractor().fetch_subtitle(TIMEDTEXT) == b"x"
    (inst,) = urlopen_ydl.instances
    (req,) = inst.requests
    assert isinstance(req, Request)
    assert req.url == TIMEDTEXT
    # เป้าหมายว่าง = "เบราว์เซอร์อะไรก็ได้" แบบเดียวกับที่ yt-dlp ใช้กับลิงก์ซับของยูทูป
    assert req.extensions == {"impersonate": ImpersonateTarget()}


@pytest.mark.parametrize("available", [False, AttributeError("gone")])
def test_ytdlp_fetch_subtitle_falls_back_to_a_plain_request_and_warns_once(
    urlopen_ydl: type[UrlopenYDL],
    available: object,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(extractor_mod, "_impersonation_warned", threading.Event())
    urlopen_ydl.impersonate = available
    extractor = YtDlpExtractor()
    with caplog.at_level("WARNING", logger="yttoolkit"):
        assert extractor.fetch_subtitle(TIMEDTEXT) == b"x"
        assert extractor.fetch_subtitle(TIMEDTEXT) == b"x"
    for inst in urlopen_ydl.instances:
        (req,) = inst.requests
        assert req.extensions == {}
    warnings = [r for r in caplog.records if "curl_cffi" in r.getMessage()]
    assert len(warnings) == 1


def test_ytdlp_without_session_passes_no_cookiefile(ydl: type[FakeYDL]) -> None:
    YtDlpExtractor().probe(BBB)
    assert "cookiefile" not in ydl.instances[0].params


class _SpySession:
    """แทน VisitorSession: jar ก้อนเดียว บันทึกว่าถูก save กี่ครั้งด้วย jar อะไร"""

    def __init__(self, folder: Path) -> None:
        self.path = folder / "visitor-session.txt"
        self._jar = CookieJar()
        self.saved: list[object] = []

    def jar(self) -> object:
        return self._jar

    def save(self, source: object = None) -> None:
        self.saved.append(source)


def test_ytdlp_probe_uses_the_visitor_session(ydl: type[FakeYDL], tmp_path: Path) -> None:
    session = _SpySession(tmp_path)
    YtDlpExtractor(session=session).probe(BBB)  # type: ignore[arg-type]
    (inst,) = ydl.instances
    assert inst.params["cookiefile"] == str(tmp_path / "visitor-session.txt")
    assert inst.__dict__["cookiejar"] is session.jar()
    assert session.saved == [session.jar()]


def test_ytdlp_fetch_subtitle_uses_the_same_visitor_session(
    urlopen_ydl: type[UrlopenYDL], tmp_path: Path
) -> None:
    session = _SpySession(tmp_path)
    YtDlpExtractor(session=session).fetch_subtitle(TIMEDTEXT)  # type: ignore[arg-type]
    (inst,) = urlopen_ydl.instances
    assert inst.params["cookiefile"] == str(session.path)
    assert inst.__dict__["cookiejar"] is session.jar()
    assert session.saved == [session.jar()]


def test_ytdlp_fetch_subtitle_saves_the_session_even_after_a_429(
    urlopen_ydl: type[UrlopenYDL], tmp_path: Path
) -> None:
    session = _SpySession(tmp_path)
    urlopen_ydl.outcome = _http_error(429)
    with pytest.raises(YtError):
        YtDlpExtractor(session=session).fetch_subtitle(TIMEDTEXT)  # type: ignore[arg-type]
    assert len(session.saved) == 1


def test_ytdlp_playlist_does_not_use_the_visitor_session(ydl: type[FakeYDL], tmp_path: Path) -> None:
    session = _SpySession(tmp_path)
    ydl.result = {"title": "x", "entries": []}
    YtDlpExtractor(session=session).playlist(PLAYLIST, 10)  # type: ignore[arg-type]
    assert "cookiefile" not in ydl.instances[0].params
    assert session.saved == []


def test_attach_session_on_a_real_youtubedl(tmp_path: Path) -> None:
    """สัญญากับ API ภายในของ yt-dlp (cookiejar = cached_property, save_cookies ตอนปิด) ไม่ต่อเน็ต"""
    from yt_dlp.cookies import YoutubeDLCookieJar

    session = extractor_mod.visitor_session(tmp_path)
    jar = session.jar()
    assert isinstance(jar, YoutubeDLCookieJar)
    params = {"quiet": True, "no_warnings": True, "cookiefile": str(session.path)}
    with yt_dlp.YoutubeDL(params) as ydl:
        assert "cookiejar" not in ydl.__dict__  # __init__ ยังไม่แตะ jar (ใส่ก่อนคำขอแรกได้)
        extractor_mod._attach_session(ydl, session)
        assert ydl.cookiejar is jar
        # ตัวส่งคำขอสร้างทีหลังและถือ jar ก้อนเดียวกัน
        handler = next(iter(ydl._request_director.handlers.values()))
        assert handler.cookiejar is jar
        ydl._load_cookies("VISITOR_INFO1_LIVE=abc; Domain=.youtube.com", autoscope=False)
    # ปิดแล้วบันทึกผ่านเซสชัน: ไฟล์มีคุกกี้ และนาฬิกาเริ่มแล้ว
    assert session.path.is_file()
    assert "VISITOR_INFO1_LIVE" in session.path.read_text(encoding="utf-8")
    assert session.age() is not None


def test_visitor_session_round_trips_through_ytdlp_cookie_files(tmp_path: Path) -> None:
    first = extractor_mod.visitor_session(tmp_path)
    with yt_dlp.YoutubeDL({"quiet": True, "cookiefile": str(first.path)}) as ydl:
        extractor_mod._attach_session(ydl, first)
        ydl._load_cookies("VISITOR_INFO1_LIVE=abc; Domain=.youtube.com", autoscope=False)
    second = extractor_mod.visitor_session(tmp_path)
    assert {c.name for c in second.jar()} == {"VISITOR_INFO1_LIVE"}
    assert second.age() is not None


def test_impersonation_info_reports_curl_cffi() -> None:
    available, version = extractor_mod.impersonation_info()
    assert available is True
    assert version and version.startswith("0.")
