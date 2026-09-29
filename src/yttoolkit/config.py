"""ค่าคงที่และตำแหน่งไฟล์ของแอพ"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "YT Toolkit"
HOST = "127.0.0.1"
PORT_RANGE = range(8787, 8798)
CODE_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Paths:
    """data_root เก็บของที่เปลี่ยนตามการใช้งาน ส่วน code_root คือโฟลเดอร์ repo"""

    data_root: Path
    code_root: Path = CODE_ROOT

    @property
    def data(self) -> Path:
        return self.data_root / "data"

    @property
    def db(self) -> Path:
        return self.data / "app.db"

    @property
    def cache(self) -> Path:
        return self.data / "cache"

    @property
    def work(self) -> Path:
        return self.data_root / "work"

    @property
    def run(self) -> Path:
        return self.data_root / "run"

    @property
    def logs(self) -> Path:
        return self.run / "logs"

    @property
    def bin(self) -> Path:
        return self.data_root / "bin"

    @property
    def app_json(self) -> Path:
        return self.run / "app.json"

    @property
    def web_dist(self) -> Path:
        return self.code_root / "web" / "dist"

    def ensure(self) -> None:
        for d in (self.data, self.cache, self.work, self.run, self.logs, self.bin):
            d.mkdir(parents=True, exist_ok=True)


def default_paths() -> Paths:
    override = os.environ.get("YT_TOOLKIT_DATA_ROOT")
    return Paths(data_root=Path(override) if override else CODE_ROOT)


def env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off", "")
