"""บริการซับของคลิป: รายการแทร็ก, token (คำพร้อมเวลา) ของแทร็ก และไฟล์ .srt / .txt / .md (M3)

ลำดับการโหลด token ของแทร็กหนึ่ง:
1. cache ในเครื่อง `<cache_root>/<videoId>/subs/<trackId>.tokens.json` (รุ่น parser ตรงกัน = ใช้เลย)
2. โหลด json3 แล้วแปลง ถ้าไฟล์เสีย ไม่มีข้อความ หรือไม่มีลิงก์ json3 ใช้ vtt แทน (AC-SUB-11)
3. ลิงก์ซับที่ยูทูปเซ็นไว้หมดอายุได้ (~6-7 ชม.) โหลดพลาดด้วย E_NETWORK = probe ใหม่หนึ่งครั้ง
   แล้วลองอีกรอบเดียว (แบบเดียวกับ storyboard ใน M2) E_BOT_CHECK โยนต่อทันที
4. ซับแปล (t.*) ที่ยูทูปตอบ 429 / E_BOT_CHECK = E_TRANSLATION_BLOCKED ไม่ใช่การขอยืนยันว่าไม่ใช่บอท
   (ยูทูปปิดเฉพาะคำขอ tlang ซับอื่นยังโหลดได้) จึงไม่ใช้รหัสที่ M4 เอาไปพักทั้งคิว

URL ที่โหลดมาจากผล probe เท่านั้น (fetch_subtitle ไม่มี allowlist) ห้ามรับ URL จากหน้าเว็บ
ไม่ import yt_dlp เอง และไม่ import api/platform (PRD 6.6)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from .note import build_note
from .srt_builder import SubOptions, Token, build_cues, md_sections, to_md, to_srt, to_txt
from .subparse import PARSER_VERSION, ParsedTrack, SubParseError, parse_json3, parse_vtt
from .tracks import TRACK_ID, Track, default_track_id, find_track, list_tracks, original_language, tracks_payload
from .yterrors import YtError

if TYPE_CHECKING:
    from .videos import VideoService

log = logging.getLogger("yttoolkit")

FORMATS = ("srt", "txt", "md")
SUBS_FOLDER = "subs"
_SOURCES = frozenset({"json3", "vtt"})
_ID_ECHO_MAX = 80  # track id จากหน้าเว็บที่ยกไปใส่ใน detail ของ error ตัดไว้ไม่ให้ยาว


class SubtitleExport(NamedTuple):
    """ผลของ export: ชื่อคลิป (ดิบ) + ภาษาของแทร็ก ให้ router ตั้งชื่อไฟล์เอง และเนื้อไฟล์ UTF-8 ไม่มี BOM"""

    title: str
    lang: str
    data: bytes


class NoteExport(NamedTuple):
    """ผลของ note: ชื่อคลิป (ดิบ) ให้ router ตั้งชื่อไฟล์ และเนื้อโน้ต UTF-8 (LF) ไม่มี BOM"""

    title: str
    data: bytes


def _no_subtitles(detail: str) -> YtError:
    return YtError("E_NO_SUBTITLES", detail)


class SubtitleService:
    def __init__(
        self,
        videos: VideoService,
        fetch_subtitle: Callable[[str], bytes],
        cache_root: Path,
    ) -> None:
        self._videos = videos
        self._fetch = fetch_subtitle
        self._cache_root = Path(cache_root)
        self._guard = threading.Lock()
        self._locks: dict[tuple[str, str], threading.Lock] = {}

    # ---------- ข้อมูลคลิป ----------

    def _trimmed(self, video_id: str) -> dict:
        """ผล probe ที่ตัดแล้ว แถวของ M2 ไม่มี captions: probe ใหม่หนึ่งครั้ง (เขียนทับแถวเดิม
        ครั้งหน้าจึงไม่ probe ซ้ำ) error ทุกตัวโยนต่อ"""
        trimmed = self._videos.raw(video_id)
        if "captions" not in trimmed:
            self._videos.get(video_id, refresh=True)
            trimmed = self._videos.raw(video_id)
        return trimmed

    def _track(self, video_id: str, track_id: str) -> Track:
        # id ผิดรูปแบบไม่ต้อง probe ให้เสียเวลา (และไม่เคยถูกใช้เป็นชื่อไฟล์)
        if not isinstance(track_id, str) or not TRACK_ID.match(track_id):
            raise _no_subtitles(f"ไม่มีแทร็ก {track_id!r:.{_ID_ECHO_MAX}}")
        track = find_track(self._trimmed(video_id), track_id)
        if track is None:
            raise _no_subtitles(f"ไม่มีแทร็ก {track_id}")
        return track

    def tracks(self, video_id: str) -> dict:
        """{"tracks": [{id, lang, name, group}], "defaultTrackId"?} คลิปไม่มีซับ = {"tracks": []}"""
        return tracks_payload(self._trimmed(video_id))

    # ---------- token ----------

    def tokens(self, video_id: str, track_id: str) -> ParsedTrack:
        return self._parsed(video_id, self._track(video_id, track_id))

    def _lock(self, video_id: str, track_id: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault((video_id, track_id), threading.Lock())

    def _parsed(self, video_id: str, track: Track) -> ParsedTrack:
        folder = self._cache_root / video_id / SUBS_FOLDER
        with self._lock(video_id, track.id):
            # อ่าน cache ในล็อก: คนที่รอคิวอยู่ได้ผลที่คนแรกเพิ่งเขียน ไม่โหลดซ้ำ
            cached = _read_cache(folder, video_id, track.id)
            if cached is not None:
                return cached
            try:
                parsed, data = self._fetch_and_parse(track)
            except YtError as exc:
                if exc.code != "E_NETWORK":
                    raise
                # ลิงก์ที่เซ็นไว้หมดอายุ: probe ใหม่แล้วลองอีกรอบเดียว รอบสองพลาดก็โยนต่อ
                log.info("โหลดซับ %s/%s ไม่สำเร็จ (%s) probe ใหม่แล้วลองอีกครั้ง", video_id, track.id, exc.detail)
                self._videos.get(video_id, refresh=True)
                track = self._track(video_id, track.id)
                parsed, data = self._fetch_and_parse(track)
            _write_cache(folder, video_id, track.id, parsed, data)
            return parsed

    def _fetch_and_parse(self, track: Track) -> tuple[ParsedTrack, bytes]:
        """json3 ก่อน ไฟล์เสีย/ไม่มีข้อความ/ไม่มีลิงก์ = vtt สองแบบใช้ไม่ได้ = E_NO_SUBTITLES
        YtError ของการโหลด (E_NETWORK, E_BOT_CHECK ฯลฯ) โยนต่อทันที ไม่ลองแบบถัดไป"""
        attempts: tuple[tuple[str | None, Callable[[bytes], ParsedTrack]], ...] = (
            (track.json3, parse_json3),
            (track.vtt, parse_vtt),
        )
        for url, parse in attempts:
            if url is None:
                continue
            data = self._fetch_track(track, url)
            try:
                parsed = parse(data)
            except SubParseError as exc:
                log.info("ไฟล์ซับ %s ใช้ไม่ได้ (%s)", track.id, exc)
                continue
            if parsed.tokens:
                return parsed, data
        raise _no_subtitles(f"แทร็ก {track.id} ไม่มีข้อความที่ใช้ได้")

    def _fetch_track(self, track: Track, url: str) -> bytes:
        """โหลดไฟล์ของแทร็ก ซับแปลที่โดน 429 / E_BOT_CHECK = E_TRANSLATION_BLOCKED (ข้อ 4 ด้านบน)"""
        try:
            return self._fetch(url)
        except YtError as exc:
            if exc.code == "E_BOT_CHECK" and track.group == "translated":
                raise YtError("E_TRANSLATION_BLOCKED", exc.detail) from exc
            raise

    # ---------- ไฟล์ ----------

    def export(self, video_id: str, track_id: str, fmt: str, opts: SubOptions) -> SubtitleExport:
        """ไฟล์ซับแบบ srt/txt/md (CRLF, UTF-8 ไม่มี BOM) ชื่อไฟล์ router ตั้งเองจาก title + lang

        opts ต้องผ่านการตรวจมาแล้ว (options_from_dict) โหมด tokens ที่ไม่มี tokens_per_cue = ValueError
        """
        if fmt not in FORMATS:
            raise ValueError(f"format must be one of {FORMATS}")
        info = self._videos.get(video_id)
        track = self._track(video_id, track_id)
        tokens: list[Token] = list(self._parsed(video_id, track).tokens)
        title = str(info.get("title") or "")
        if fmt == "srt":
            text = to_srt(build_cues(tokens, opts))
        elif fmt == "txt":
            text = to_txt(tokens)
        else:
            text = to_md(tokens, title=title, video_id=video_id, chapters=_chapter_ms(info))
        return SubtitleExport(title, track.lang, text.encode("utf-8"))

    def note(self, video_id: str, track_id: str | None = None) -> NoteExport:
        """โน้ต .md ของคลิป (C-A3): front matter + คำอธิบาย + chapter + ทรานสคริปต์ของแทร็กที่เลือก

        ไม่ส่ง track_id = แทร็กที่เลือกให้เอง (C3) ไม่มีแทร็กเลย หรือแทร็กไม่มีข้อความ = ไม่มีหัวข้อทรานสคริปต์
        track_id ที่ไม่มีในคลิป = E_NO_SUBTITLES เหมือนไฟล์ซับ ซับแปลที่ยูทูปปิด = E_TRANSLATION_BLOCKED
        """
        info = self._videos.get(video_id)
        if track_id is None:
            trimmed = self._trimmed(video_id)
            default = default_track_id(list_tracks(trimmed), original_language(trimmed))
            track = find_track(trimmed, default) if default else None
        else:
            track = self._track(video_id, track_id)
        transcript = None
        if track is not None:
            try:
                tokens = list(self._parsed(video_id, track).tokens)
            except YtError as exc:
                if exc.code != "E_NO_SUBTITLES":
                    raise
                tokens = []
            if tokens:
                transcript = md_sections(tokens, _chapter_ms(info), level=3)
        text = build_note(info, video_id, transcript)
        return NoteExport(str(info.get("title") or ""), text.encode("utf-8"))


def _chapter_ms(info: dict) -> list[tuple[int, str]]:
    """chapter ของ VideoInfo (วินาที อาจมีทศนิยม) -> [(ms จำนวนเต็ม, ชื่อ)]"""
    return [(round(c["startS"] * 1000), str(c["title"])) for c in info.get("chapters") or []]


# ---------- cache ----------


def _cache_name(track_id: str) -> str:
    return f"{track_id}.tokens.json"


def _read_cache(folder: Path, video_id: str, track_id: str) -> ParsedTrack | None:
    """token ที่เก็บไว้ ไฟล์ไม่มี/เสีย/รุ่นเก่า/เป็นของคลิปหรือแทร็กอื่น = None (โหลดใหม่แล้วเขียนทับ)

    เทียบ videoId/trackId ในไฟล์ด้วย เพราะ NTFS ไม่สนตัวพิมพ์ id ที่ต่างกันแค่ตัวพิมพ์จะชี้ไฟล์เดียวกัน
    """
    try:
        doc = json.loads((folder / _cache_name(track_id)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or doc.get("v") != PARSER_VERSION:
        return None
    if doc.get("videoId") != video_id or doc.get("trackId") != track_id:
        return None
    source, word_timing, raw_tokens = doc.get("source"), doc.get("hasWordTiming"), doc.get("tokens")
    if source not in _SOURCES or not isinstance(word_timing, bool) or not isinstance(raw_tokens, list):
        return None
    tokens = []
    for item in raw_tokens:
        if not (isinstance(item, list) and len(item) == 3 and isinstance(item[0], str)):
            return None
        if not all(isinstance(n, int) and not isinstance(n, bool) for n in item[1:]):
            return None
        tokens.append(Token(item[0], item[1], item[2]))
    if not tokens:
        return None
    return ParsedTrack(tuple(tokens), word_timing, source)


def _atomic_write(target: Path, data: bytes) -> None:
    tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _write_cache(folder: Path, video_id: str, track_id: str, parsed: ParsedTrack, data: bytes) -> None:
    """เก็บไฟล์ซับดิบ + token (เขียนไฟล์ชั่วคราวแล้ว replace) เขียนไม่ได้แค่บันทึก log ผู้ใช้ยังได้ซับตามปกติ"""
    doc: dict[str, Any] = {
        "v": PARSER_VERSION,
        "videoId": video_id,
        "trackId": track_id,
        "hasWordTiming": parsed.has_word_timing,
        "source": parsed.source,
        "tokens": [[tok.t, tok.s, tok.e] for tok in parsed.tokens],
    }
    try:
        folder.mkdir(parents=True, exist_ok=True)
        _atomic_write(folder / f"{track_id}.{parsed.source}", data)
        # ไฟล์ token เขียนหลังสุด: มีไฟล์นี้ = เขียนครบแล้ว
        body = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        _atomic_write(folder / _cache_name(track_id), body)
    except OSError:
        log.warning("เก็บซับ %s/%s ลง cache ไม่สำเร็จ (ครั้งหน้าจะโหลดใหม่)", video_id, track_id, exc_info=True)
