"""ช่วงโฆษณาจาก SponsorBlock (C4): ตัวจริงห่อ SponsorBlockPP ของ yt-dlp (ไม่ต่อเน็ต: แทน _download_json) และตัวปลอม"""

from __future__ import annotations

from pathlib import Path

import pytest
from yt_dlp.postprocessor.sponsorblock import SponsorBlockPP

from yttoolkit.core.download import SponsorBlockError, SponsorSource
from yttoolkit.core.extractor import FakeExtractor, YtDlpExtractor
from yttoolkit.core.yterrors import YtError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
BBB = "aqz-KE-bpKQ"


def _answer(segments: list[dict]) -> list[dict]:
    return [{"videoID": "other", "segments": []}, {"videoID": BBB, "segments": segments}]


def _segment(start: float, end: float, category: str, action: str = "skip") -> dict:
    return {"segment": [start, end], "category": category, "actionType": action,
            "videoDuration": 635.0, "description": ""}


def test_both_extractors_are_sponsor_sources() -> None:
    assert isinstance(YtDlpExtractor(), SponsorSource)
    assert isinstance(FakeExtractor(FIXTURES), SponsorSource)


def test_real_maps_skip_segments_to_milliseconds(monkeypatch) -> None:
    urls: list[str] = []

    def fake_json(self, url, **kwargs):
        urls.append(url)
        return _answer([_segment(60.0, 90.25, "sponsor"), _segment(100.0, 101.0, "selfpromo", action="mute"),
                        _segment(0.4, 12.0, "intro")])

    monkeypatch.setattr(SponsorBlockPP, "_download_json", fake_json)
    got = YtDlpExtractor().sponsor_segments(BBB, ["sponsor", "selfpromo", "intro"], 635.0)
    assert got == [(0, 12_000, "intro"), (60_000, 90_250, "sponsor")]  # mute dropped; start <= 1 s snapped to 0
    assert BBB not in urls[0] and "/api/skipSegments/" in urls[0]  # only a hash prefix leaves the machine


def test_real_no_data_is_empty(monkeypatch) -> None:
    monkeypatch.setattr(SponsorBlockPP, "_download_json", lambda self, url, **kw: None)  # HTTP 404
    assert YtDlpExtractor().sponsor_segments(BBB, ["sponsor"], 635.0) == []


def test_real_failure_is_a_sponsorblock_error_not_a_yt_error(monkeypatch) -> None:
    def boom(self, url, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(SponsorBlockPP, "_download_json", boom)
    with pytest.raises(SponsorBlockError) as info:
        YtDlpExtractor().sponsor_segments(BBB, ["sponsor"], 635.0)
    assert not isinstance(info.value, YtError)


def test_real_needs_a_duration_and_a_valid_id() -> None:
    with pytest.raises(SponsorBlockError):
        YtDlpExtractor().sponsor_segments(BBB, ["sponsor"], None)
    with pytest.raises(YtError):
        YtDlpExtractor().sponsor_segments("bad id", ["sponsor"], 635.0)


def test_fake_reads_fixtures_and_filters_categories() -> None:
    fake = FakeExtractor(FIXTURES)
    assert fake.sponsor_segments("ADSCUTCLIP1", ["sponsor"], 635.0) == [(60_000, 90_000, "sponsor")]
    assert fake.sponsor_segments("ADSCUTCLIP1", ["intro", "outro"], 635.0) == [
        (0, 12_000, "intro"), (600_000, 635_000, "outro")]
    assert fake.sponsor_segments("ADSNODATA01", ["sponsor"], 635.0) == []
    with pytest.raises(SponsorBlockError):
        fake.sponsor_segments("ADSOFFLINE1", ["sponsor"], 635.0)
    assert ("sponsor_segments", "ADSNODATA01") in fake.calls


def test_fake_m5a_clips_probe_as_their_sources() -> None:
    fake = FakeExtractor(FIXTURES)
    chapters = fake.probe("CHAPTERS001")
    assert chapters["title"] == "คลิปมี 3 chapter" and len(chapters["chapters"]) == 3
    assert fake.probe("RANGECLIP01")["duration"] == 635
