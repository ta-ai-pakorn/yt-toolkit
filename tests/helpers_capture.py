"""ตัวช่วยเทสของการถ่ายภาพคมตรงจุด (M5 รอบ B2): ตัวดึงชิ้นภาพจาก fixture และบริการปลอมที่ CaptureService ใช้"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from yttoolkit.core.frame_piece import PieceInfo, fetch_piece, read_index, write_piece
from yttoolkit.core.yterrors import YtError

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PIECE = FIXTURES / "capture" / "piece.mp4"
MEDIA = FIXTURES / "media"
BBB = "aqz-KE-bpKQ"
TITLE = "Big Buck Bunny"


class FixtureFetcher:
    """fetch_frame_piece จาก piece.mp4 ด้วยตัวอ่าน sidx ตัวจริง (เวลาวนทุก 4 วินาทีแบบ FakeExtractor)
    error = โยนแทน · gate = รอจนถูก set (เทสการถ่ายซ้อน) · calls = (video_id, t_ms, max_short_side)"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int | None]] = []
        self.error: YtError | None = None
        self.gate: threading.Event | None = None
        self.started = threading.Event()

    def fetch_frame_piece(self, video_id: str, t_ms: int, max_short_side: int | None, dest: Path) -> PieceInfo:
        self.calls.append((video_id, t_ms, max_short_side))
        self.started.set()
        if self.gate is not None:
            assert self.gate.wait(10)
        if self.error is not None:
            raise self.error
        data = PIECE.read_bytes()

        def read_range(first: int, last: int) -> bytes:
            return data[first : last + 1]

        index = read_index(read_range)
        local = t_ms % index.sidx.end_ms
        piece, ref = fetch_piece(read_range, index, local)
        write_piece(dest, piece)
        return PieceInfo(dest, t_ms - (local - index.sidx.to_ms(ref.start)), 1920, 1080, "fixture", None)


def clip_info(duration_s: int = 635, title: str = TITLE, live: bool = False) -> dict:
    return {"videoId": BBB, "title": title, "durationS": duration_s, "isLive": live}


class FakeVideos:
    """VideoService.get / peek_cached จาก dict (ไม่มีคลิป = E_VIDEO_UNAVAILABLE) · error = get โยนแทน (เช่นติดบอทตอนอ่านคลิป)"""

    def __init__(self, infos: dict[str, dict]) -> None:
        self.infos = infos
        self.error: YtError | None = None

    def get(self, video_id: str, refresh: bool = False, peek: bool = False) -> dict:
        if self.error is not None:
            raise self.error
        if video_id not in self.infos:
            raise YtError("E_VIDEO_UNAVAILABLE", video_id)
        return dict(self.infos[video_id])

    def peek_cached(self, video_id: str) -> dict | None:
        info = self.infos.get(video_id)
        return dict(info) if info is not None else None


@dataclass
class StubSettings:
    output: Path
    quality: str = "max"

    def get(self) -> dict:
        return {"captureQuality": self.quality}

    def output_dir(self) -> Path:
        return self.output


@dataclass
class StubQueue:
    paused_until: datetime | None = None
    brakes: list[str] = field(default_factory=list)

    def pause_state(self) -> SimpleNamespace | None:
        return None if self.paused_until is None else SimpleNamespace(until=self.paused_until, reason="E_BOT_CHECK")

    def brake(self, reason: str = "E_BOT_CHECK") -> None:
        self.brakes.append(reason)
