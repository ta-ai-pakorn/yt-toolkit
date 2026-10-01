"""ตั้งค่าของแอพ (PRD 6.4) เก็บเป็น JSON ทีละ key ในตาราง settings

PATCH เป็นแบบ all-or-nothing: key ไหนผิด ไม่เก็บอะไรเลย (ไม่เขียนครึ่งๆ กลางๆ)
core ไม่รู้จัก HTTP: ผิดเงื่อนไขโยน SettingsError พร้อมรหัสให้ชั้น api แปลงเป็น 422
"""

from __future__ import annotations

import copy
import json
import re
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .srt_builder import PRESETS, SubOptions, options_from_dict

if TYPE_CHECKING:
    from .db import Database

WRITE_TEST_NAME = ".yt-toolkit-write-test"
LANGUAGE_TAG = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
SPONSOR_CATEGORY = re.compile(r"^[a-z][a-z_]{0,31}$")

VIDEO_DEFAULTS = ("compat-1080", "compat-720", "max")
AUDIO_FORMATS = ("m4a", "mp3", "wav")
MP3_KBPS = (128, 192, 320)
SUB_PRESETS = ("short", "medium", "long", "word", "custom")
CONCURRENCY = (1, 2, 3)
THEMES = ("system", "dark", "light")
FILENAME_STYLES = ("title", "title-channel", "title-quality")
READ_ONLY = ("cookies", "statsResetAt")


class SettingsError(Exception):
    """code: E_BAD_REQUEST | E_OUTPUT_NOT_WRITABLE"""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def options_to_dict(opts: SubOptions) -> dict[str, Any]:
    """SubOptions -> camelCase (รูปเดียวกับที่ options_from_dict รับ) tokensPerCue มีเฉพาะโหมด tokens"""
    out: dict[str, Any] = {
        "maxChars": opts.max_chars,
        "lines": opts.lines,
        "minMs": opts.min_ms,
        "maxMs": opts.max_ms,
        "mode": opts.mode,
    }
    if opts.mode == "tokens":
        out["tokensPerCue"] = opts.tokens_per_cue
    return out


def ensure_writable(folder: Path) -> None:
    """สร้างโฟลเดอร์ (ถ้ายังไม่มี) แล้วลองเขียน-ลบไฟล์ทดสอบ ไม่ได้ = SettingsError E_OUTPUT_NOT_WRITABLE"""
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / WRITE_TEST_NAME
        probe.write_bytes(b"")
        probe.unlink()
    except OSError as error:
        raise SettingsError("E_OUTPUT_NOT_WRITABLE", str(error)) from error


def _bad(key: str, why: str) -> SettingsError:
    return SettingsError("E_BAD_REQUEST", f"{key}: {why}")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _one_of(key: str, value: Any, allowed: tuple) -> Any:
    # bool เป็น int ใน Python: True == 1 จึงต้องกันไว้ ไม่ให้ concurrency เป็น true
    if isinstance(value, bool) or value not in allowed:
        raise _bad(key, f"must be one of {list(allowed)}")
    return value


def _validate_output_dir(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _bad("outputDir", "must be a non-empty string")
    path = Path(value)
    if not path.is_absolute():
        raise _bad("outputDir", "must be an absolute path")
    return str(path)


def _validate_audio_language(value: Any) -> str:
    if not isinstance(value, str) or not (value == "original" or LANGUAGE_TAG.fullmatch(value)):
        raise _bad("audioLanguage", "must be 'original' or a language tag")
    return value


def _validate_sub_custom(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise _bad("subCustom", "must be an object")
    try:
        return options_to_dict(options_from_dict(value))
    except ValueError as error:
        raise _bad("subCustom", str(error)) from error


def _validate_sponsorblock(value: Any) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) and SPONSOR_CATEGORY.fullmatch(v) for v in value):
        raise _bad("sponsorblockDefault", "must be a list of category names")
    return list(dict.fromkeys(value))


def _validate_last_used(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise _bad("lastUsed", "must be an object")
    try:
        json.dumps(value)
    except (TypeError, ValueError) as error:
        raise _bad("lastUsed", "must be JSON serialisable") from error
    return dict(value)


_VALIDATORS: dict[str, Any] = {
    "outputDir": _validate_output_dir,
    "videoDefault": lambda v: _one_of("videoDefault", v, VIDEO_DEFAULTS),
    "audioDefault": lambda v: _one_of("audioDefault", v, AUDIO_FORMATS),
    "audioLanguage": _validate_audio_language,
    "mp3Kbps": lambda v: _one_of("mp3Kbps", v, MP3_KBPS),
    "subPreset": lambda v: _one_of("subPreset", v, SUB_PRESETS),
    "subCustom": _validate_sub_custom,
    "concurrency": lambda v: _one_of("concurrency", v, CONCURRENCY),
    "sponsorblockDefault": _validate_sponsorblock,
    "theme": lambda v: _one_of("theme", v, THEMES),
    "filenameStyle": lambda v: _one_of("filenameStyle", v, FILENAME_STYLES),
    "lastUsed": _validate_last_used,
}


class SettingsStore:
    def __init__(self, db: Database, default_output_dir: Path) -> None:
        self._db = db
        self._lock = threading.RLock()
        self._defaults: dict[str, Any] = {
            "outputDir": str(default_output_dir),
            "videoDefault": "compat-1080",
            "audioDefault": "m4a",
            "audioLanguage": "original",
            "mp3Kbps": 192,
            "subPreset": "medium",
            "subCustom": options_to_dict(PRESETS["medium"]),
            "concurrency": 2,
            "sponsorblockDefault": ["sponsor", "selfpromo", "interaction"],
            "theme": "system",
            "filenameStyle": "title",
            "cookies": {"enabled": False, "source": None, "warningAccepted": False},
            "statsResetAt": None,
            "lastUsed": {},
        }

    def _stored(self) -> dict[str, Any]:
        stored: dict[str, Any] = {}
        for row in self._db.execute("SELECT key, value_json FROM settings"):
            if row["key"] not in self._defaults:
                continue
            try:
                stored[row["key"]] = json.loads(row["value_json"])
            except ValueError:
                continue  # แถวเสีย ใช้ค่าเริ่มต้นของ key นั้นแทน
        return stored

    def get(self) -> dict:
        with self._lock:
            return copy.deepcopy({**self._defaults, **self._stored()})

    def patch(self, partial: Mapping[str, Any]) -> dict:
        if not isinstance(partial, Mapping):
            raise SettingsError("E_BAD_REQUEST", "body must be an object")
        with self._lock:
            clean: dict[str, Any] = {}
            for key, value in partial.items():
                if key in READ_ONLY:
                    raise _bad(str(key), "is read-only")
                validator = _VALIDATORS.get(key)
                if validator is None:
                    raise _bad(str(key), "unknown setting")
                clean[key] = validator(value)
            if "outputDir" in clean:  # ตรวจเขียนได้หลังตรวจทุก key ผ่านแล้ว จะได้ไม่สร้างโฟลเดอร์ทั้งที่ patch ล้ม
                ensure_writable(Path(clean["outputDir"]))
            if clean:
                with self._db.transaction() as tx:
                    for key, value in clean.items():
                        tx.execute(
                            "INSERT INTO settings (key, value_json) VALUES (?, ?) "
                            "ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json",
                            (key, json.dumps(value, ensure_ascii=False)),
                        )
            return self.get()

    def output_dir(self) -> Path:
        return Path(self.get()["outputDir"])

    def concurrency(self) -> int:
        return int(self.get()["concurrency"])
