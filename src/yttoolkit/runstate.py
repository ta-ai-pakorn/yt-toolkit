"""สถานะของแอพที่กำลังรัน (run/app.json) ใช้ร่วมกันระหว่าง start, stop และ tray"""

from __future__ import annotations

import json
import secrets
import socket
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import HOST, PORT_RANGE


@dataclass(frozen=True)
class RunInfo:
    port: int
    pid: int
    token: str
    started_at: str


def new_token() -> str:
    return secrets.token_urlsafe(32)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write(path: Path, info: RunInfo) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(info)), encoding="utf-8")
    tmp.replace(path)


def read(path: Path) -> RunInfo | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return RunInfo(
            port=int(raw["port"]),
            pid=int(raw["pid"]),
            token=str(raw["token"]),
            started_at=str(raw["started_at"]),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def clear(path: Path) -> None:
    path.unlink(missing_ok=True)


def port_is_free(port: int, host: str = HOST) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
        except OSError:
            return False
        return True


def pick_port(ports: Iterable[int] = PORT_RANGE, host: str = HOST) -> int:
    for port in ports:
        if port_is_free(port, host):
            return port
    raise RuntimeError("ไม่มี port ว่างในช่วงที่กำหนด")
