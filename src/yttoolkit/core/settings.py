"""ตั้งค่าของแอพ (PRD 6.4) เก็บเป็น JSON ทีละ key ในตาราง settings

PATCH เป็นแบบ all-or-nothing: key ไหนผิด ไม่เก็บอะไรเลย (ไม่เขียนครึ่งๆ กลางๆ)
core ไม่รู้จัก HTTP: ผิดเงื่อนไขโยน SettingsError พร้อมรหัสให้ชั้น api แปลงเป็น 422
"""

from __future__ import annotations

import copy
import json
import os
import re
import threading
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .jobs import SPONSORBLOCK_CATEGORIES
from .srt_builder import PRESETS, SubOptions, options_from_dict

if TYPE_CHECKING:
    from .db import Database

WRITE_TEST_PREFIX = ".yt-toolkit-write-test-"
# ชื่ออุปกรณ์ที่ Windows สงวนไว้ (ใช้เป็นชื่อโฟลเดอร์ไม่ได้ แม้ต่อท้ายด้วยนามสกุล)
RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{n}" for n in range(1, 10)), *(f"LPT{n}" for n in range(1, 10))}
)
LANGUAGE_TAG = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$")

VIDEO_DEFAULTS = ("compat-1080", "compat-720", "max")
# M5 รอบ B2 (E2): ความละเอียดภาพคมตรงจุด เพดานนับที่ด้านสั้น "max" = สูงสุดที่มี (ถึง 4K)
CAPTURE_QUALITIES = ("max", "1080", "720")
AUDIO_FORMATS = ("m4a", "mp3", "wav")
MP3_KBPS = (128, 192, 320)
SUB_PRESETS = ("short", "medium", "long", "word", "custom")
CONCURRENCY = (1, 2, 3)
THEMES = ("system", "dark", "light")
FILENAME_STYLES = ("title", "title-channel", "title-quality")
READ_ONLY = ("statsResetAt",)
# key ที่เลิกใช้แล้ว: แถวเก่าในฐานข้อมูลถูกข้ามตอนอ่าน (ไม่อยู่ในค่าเริ่มต้น) และถูกลบตอนบันทึกครั้งถัดไป
# "cookies" = สถานะคุกกี้ของ PRD เดิม M5 รอบ C ใช้บัญชีชั่วคราวในหน่วยความจำแทน (C8)
RETIRED_KEYS = ("cookies",)


class SettingsError(Exception):
    """code: E_BAD_REQUEST | E_OUTPUT_NOT_WRITABLE"""

    def __init__(self, code: str, detail: str, *, key: str | None = None) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.key = key  # key ของตั้งค่าที่ผิด (E_BAD_REQUEST) ให้ชั้น api เลือกข้อความที่ตรงกับช่องนั้น


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
        # ชื่อไม่ซ้ำกันทุกครั้ง: สองคำขอพร้อมกันจะไม่ลบไฟล์ทดสอบของกันและกัน
        probe = folder / f"{WRITE_TEST_PREFIX}{uuid.uuid4().hex}"
        probe.write_bytes(b"")
        probe.unlink()
    except (OSError, ValueError) as error:
        raise SettingsError("E_OUTPUT_NOT_WRITABLE", str(error)) from error


def _bad(key: str, why: str) -> SettingsError:
    return SettingsError("E_BAD_REQUEST", f"{key}: {why}", key=key)


def _one_of(key: str, value: Any, allowed: tuple) -> Any:
    # ชนิดต้องตรงเป๊ะ: True == 1 และ 2.0 == 2 ใน Python จึงห้ามให้ bool หรือ float ผ่านเป็น int
    if type(value) is not type(allowed[0]) or value not in allowed:
        raise _bad(key, f"must be one of {list(allowed)}")
    return value


def _validate_output_dir(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _bad("outputDir", "must be a non-empty string")
    value = value.strip()
    if "\x00" in value:
        raise _bad("outputDir", "must not contain a NUL character")
    path = Path(value)
    if not path.is_absolute():
        raise _bad("outputDir", "must be an absolute path")
    normal = Path(os.path.normpath(value))  # ยุบ .. และ . ให้เหลือ path จริง
    for part in normal.parts[1:]:  # ข้ามราก (C:\ หรือ \\server\share\)
        if part.endswith((".", " ")):
            raise _bad("outputDir", "folder names must not end with a dot or a space")
        if part.split(".")[0].rstrip().upper() in RESERVED_NAMES:
            raise _bad("outputDir", "folder name is reserved by Windows")
    return str(normal)


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
    """หมวด SponsorBlock ที่ติ๊กไว้ (D3 จำข้ามคลิป): ต้องมีอย่างน้อย 1 หมวด และเป็นหมวดที่ตัดได้เท่านั้น"""
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(v, str) and v in SPONSORBLOCK_CATEGORIES for v in value)
    ):
        raise _bad("sponsorblockDefault", "must be a non-empty list of SponsorBlock categories")
    return list(dict.fromkeys(value))


def _validate_last_used(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise _bad("lastUsed", "must be an object")
    try:
        # allow_nan=False: NaN / Infinity ไม่ใช่ JSON จริง เก็บแล้วอ่านกลับไม่ได้ ทำให้ทุกคำขอ /settings พัง
        return json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError, RecursionError) as error:
        raise _bad("lastUsed", "must be JSON serialisable") from error


def _validate_bool(key: str, value: Any) -> bool:
    # ชนิดต้องเป็น bool จริง: 1 / "true" ไม่นับ (แบบเดียวกับ _one_of)
    if type(value) is not bool:
        raise _bad(key, "must be true or false")
    return value


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
    "autoSharpFrames": lambda v: _validate_bool("autoSharpFrames", v),
    "captureQuality": lambda v: _one_of("captureQuality", v, CAPTURE_QUALITIES),
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
            "autoSharpFrames": True,  # M5 รอบ B D6: ทำภาพคมอัตโนมัติหลังโหลดวิดีโอ
            "captureQuality": "max",  # M5 รอบ B2 spec 2.4: ภาพคมตรงจุดใช้ format ที่ละเอียดที่สุด
            "theme": "system",
            "filenameStyle": "title",
            "statsResetAt": None,
            "lastUsed": {},
        }

    def _stored(self) -> dict[str, Any]:
        stored: dict[str, Any] = {}
        for row in self._db.execute("SELECT key, value_json FROM settings"):
            if row["key"] not in self._defaults:
                continue
            try:
                value = json.loads(row["value_json"])
                validator = _VALIDATORS.get(row["key"])
                stored[row["key"]] = validator(value) if validator else value
            except (ValueError, SettingsError):
                continue  # แถวเสียหรือค่าไม่ผ่านการตรวจแล้ว ใช้ค่าเริ่มต้นของ key นั้นแทน
        return stored

    def get(self) -> dict:
        with self._lock:
            return copy.deepcopy({**self._defaults, **self._stored()})

    def patch(self, partial: Mapping[str, Any]) -> dict:
        if not isinstance(partial, Mapping):
            raise SettingsError("E_BAD_REQUEST", "body must be an object")
        clean: dict[str, Any] = {}
        for key, value in partial.items():
            if key in READ_ONLY:
                raise _bad(str(key), "is read-only")
            validator = _VALIDATORS.get(key)
            if validator is None:
                raise _bad(str(key), "unknown setting")
            clean[key] = validator(value)
        if "outputDir" in clean:
            # ตรวจเขียนได้หลังตรวจทุก key ผ่านแล้ว จะได้ไม่สร้างโฟลเดอร์ทั้งที่ patch ล้ม
            # และทำนอก lock: โฟลเดอร์เครือข่ายที่ช้าต้องไม่ทำให้การอ่านตั้งค่าค้างตามไปด้วย
            ensure_writable(Path(clean["outputDir"]))
        if clean:
            with self._lock, self._db.transaction() as tx:
                for key in RETIRED_KEYS:
                    tx.execute("DELETE FROM settings WHERE key = ?", (key,))
                for key, value in clean.items():
                    tx.execute(
                        "INSERT INTO settings (key, value_json) VALUES (?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json",
                        (key, json.dumps(value, ensure_ascii=False, allow_nan=False)),
                    )
        return self.get()

    def output_dir(self) -> Path:
        return Path(self.get()["outputDir"])

    def concurrency(self) -> int:
        return int(self.get()["concurrency"])
