from __future__ import annotations

import io
import json
import re
from pathlib import Path
from typing import ClassVar, Self

import httpx
import pytest
import yt_dlp
from PIL import Image
from yt_dlp.utils import DownloadError, ExtractorError

from yttoolkit.core import extractor as extractor_mod
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


@pytest.mark.parametrize("video_id", ["live_upcoming", "UPCOMINGLV1"])
def test_fake_probe_live_fixture_goes_through_live_check(
    fake: FakeExtractor, video_id: str
) -> None:
    # ใช้ได้ทั้งชื่อไฟล์และ id 11 ตัวในไฟล์ (ให้เทส API ที่ตรวจรูปแบบ id ใช้ได้)
    with pytest.raises(YtError) as exc:
        fake.probe(video_id)
    assert exc.value.code == "E_LIVE_NOT_READY"


@pytest.mark.parametrize(
    "video_id", ["../playlist/PLfake250", "..\\probe\\x", "/etc/passwd", "", "."]
)
def test_fake_probe_rejects_path_like_ids(fake: FakeExtractor, video_id: str) -> None:
    with pytest.raises(YtError) as exc:
        fake.probe(video_id)
    assert exc.value.code == "E_VIDEO_UNAVAILABLE"


# ---------- FakeExtractor: playlist ----------


def test_fake_playlist_reads_at_most_limit_plus_one(fake: FakeExtractor) -> None:
    info = fake.playlist("PLfake250", 200)
    assert info["title"]
    assert info["playlist_count"] == 250
    assert len(info["entries"]) == 201
    first = info["entries"][0]
    assert {"id", "title", "duration"} <= first.keys()
    assert first.get("thumbnails") or first.get("thumbnail")
    assert fake.calls == [("playlist", "PLfake250")]


def test_fake_playlist_under_limit_returns_everything(fake: FakeExtractor) -> None:
    assert len(fake.playlist("PLfake250", 300)["entries"]) == 250


def test_fake_playlist_missing(fake: FakeExtractor) -> None:
    with pytest.raises(YtError) as exc:
        fake.playlist("PLdoesnotexist", 200)
    assert exc.value.code == "E_VIDEO_UNAVAILABLE"


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


def test_no_signed_urls_in_fixtures() -> None:
    for path in FIXTURES.rglob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert "googlevideo" not in text, path
        assert "sigh=" not in text, path
        assert "i.ytimg.com/sb/" not in text, path


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
        return None

    def extract_info(self, url: str, download: bool = True) -> dict:
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
        "id": "PLfake250",
        "title": "t",
        "entries": iter([{"id": f"v{n:010d}", "title": str(n)} for n in range(10)]),
    }
    info = YtDlpExtractor().playlist("PLt5yu3-wZAlSLRHmI1qNm0wjyVNWw1pCU", 3)
    (inst,) = ydl.instances
    assert inst.params["extract_flat"] == "in_playlist"
    assert inst.params["playlistend"] == 4
    assert inst.params["quiet"] is True
    assert "noplaylist" not in inst.params
    assert inst.urls == [
        "https://www.youtube.com/playlist?list=PLt5yu3-wZAlSLRHmI1qNm0wjyVNWw1pCU"
    ]
    assert isinstance(info["entries"], list)
    assert len(info["entries"]) == 4


def test_ytdlp_playlist_without_entries(ydl: type[FakeYDL]) -> None:
    ydl.result = {"id": "PLempty0000", "title": "t", "entries": None}
    assert YtDlpExtractor().playlist("PLempty0000", 200)["entries"] == []


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


@pytest.mark.parametrize("playlist_id", ["", "PL&x=1", "PL/../x", "PL x"])
def test_ytdlp_playlist_rejects_malformed_ids(
    ydl: type[FakeYDL], playlist_id: str
) -> None:
    with pytest.raises(YtError) as exc:
        YtDlpExtractor().playlist(playlist_id, 200)
    assert exc.value.code == "E_INVALID_INPUT"
    assert ydl.instances == []


# ---------- YtDlpExtractor.fetch (httpx is replaced) ----------


def test_ytdlp_fetch_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}

    def get(url: str, **kwargs: object) -> httpx.Response:
        seen.update(url=url, **kwargs)
        return httpx.Response(200, content=b"img", request=httpx.Request("GET", url))

    monkeypatch.setattr(extractor_mod.httpx, "get", get)
    assert YtDlpExtractor().fetch("https://i.ytimg.com/sb/x/M0.jpg") == b"img"
    assert seen == {
        "url": "https://i.ytimg.com/sb/x/M0.jpg",
        "timeout": 10,
        "follow_redirects": True,
    }


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
def test_ytdlp_fetch_failure_is_network_error(
    monkeypatch: pytest.MonkeyPatch, outcome: object
) -> None:
    def get(url: str, **kwargs: object) -> httpx.Response:
        if isinstance(outcome, Exception):
            raise outcome
        return httpx.Response(outcome, request=httpx.Request("GET", url))

    monkeypatch.setattr(extractor_mod.httpx, "get", get)
    with pytest.raises(YtError) as exc:
        YtDlpExtractor().fetch("https://i.ytimg.com/sb/x/M0.jpg")
    assert exc.value.code == "E_NETWORK"
    assert exc.value.detail


# ---------- protocol and module boundaries ----------


def test_both_implementations_satisfy_the_protocol(fake: FakeExtractor) -> None:
    assert isinstance(fake, Extractor)
    assert isinstance(YtDlpExtractor(), Extractor)


def test_ytdlp_version_is_read_through_the_adapter() -> None:
    assert extractor_mod.ytdlp_version() == yt_dlp.version.__version__


def test_only_extractor_imports_yt_dlp() -> None:
    pattern = re.compile(r"^\s*(?:import\s+yt_dlp|from\s+yt_dlp[\s.])", re.MULTILINE)
    offenders = [
        p.relative_to(SRC).as_posix()
        for p in SRC.rglob("*.py")
        if pattern.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == ["core/extractor.py"]


def test_extractor_does_not_import_api_or_platform() -> None:
    text = (SRC / "core" / "extractor.py").read_text(encoding="utf-8")
    assert not re.search(
        r"^\s*(?:from|import)\s+(?:yttoolkit\.|\.\.)(?:api|platform)",
        text,
        re.MULTILINE,
    )
