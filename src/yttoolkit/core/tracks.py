"""แทร็กซับของคลิป: จัดกลุ่มซับจากผล probe (C2), รายการแทร็ก, id ของแทร็ก (C1)
และเลือกแทร็กเริ่มต้น (C3)

กลุ่มแทร็ก:
- owner (`o.<key>`) ซับที่เจ้าของคลิปทำเอง (`info.subtitles`)
- original (`a.<key>`) ซับอัตโนมัติในภาษาต้นฉบับ
- translated (`t.<key>`) ซับแปลอัตโนมัติ เก็บแค่ key/name แล้วสร้าง URL ตอนใช้
  จาก URL ของต้นฉบับ (`translateFrom`) + `tlang=<key>`

ไม่ import yt_dlp เอง และไม่ import api/platform (PRD 6.6)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .videos import _audio_formats

# C1: <prefix>.<key>  o = เจ้าของคลิป, a = อัตโนมัติภาษาต้นฉบับ, t = แปลอัตโนมัติ
# \Z แทน $ เพื่อไม่ให้ "o.th\n" ผ่าน ใช้ได้ทั้ง match และ fullmatch
TRACK_ID = re.compile(r"^[oat]\.[A-Za-z0-9_-]{1,64}\Z")
_KEY = re.compile(r"[A-Za-z0-9_-]{1,64}")

_EXTS = ("json3", "vtt")
_HOSTS = frozenset({"www.youtube.com", "fake.invalid"})
_ORIG = "-orig"
_GROUPS = (("owner", "o"), ("original", "a"), ("translated", "t"))
_DROPPED_KEYS = frozenset({"live_chat"})


@dataclass(frozen=True)
class Track:
    id: str
    lang: str
    name: str
    group: str
    json3: str | None
    vtt: str | None


def _base(lang: str) -> str:
    return lang.split("-")[0].lower()


def _key_lang(key: str) -> str:
    return key.removesuffix(_ORIG)


def _has_tlang(url: str) -> bool:
    return any(name == "tlang" for name, _ in parse_qsl(urlsplit(url).query))


def _with_tlang(url: str, code: str) -> str:
    """ใส่ tlang=<code> ใน query ของ URL (แทนค่าเดิมถ้ามี) แบบเดียวกับ update_url_query ของ yt-dlp"""
    parts = urlsplit(url)
    query = [
        (name, value)
        for name, value in parse_qsl(parts.query, keep_blank_values=True)
        if name != "tlang"
    ]
    query.append(("tlang", code))
    return urlunsplit(parts._replace(query=urlencode(query)))


def _usable(item: Any) -> bool:
    """C2 ข้อ 1: json3/vtt, โปรโตคอลธรรมดา (ไม่ใช่ HLS) และมาจากโฮสต์ของซับจริง/ของปลอมในเทสต์"""
    if not isinstance(item, dict) or item.get("ext") not in _EXTS:
        return False
    if item.get("protocol") not in (None, "https"):
        return False
    url = item.get("url")
    if not isinstance(url, str):
        return False
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme == "https" and parts.hostname in _HOSTS


def _usable_entries(container: Any) -> dict[str, list[dict]]:
    """key -> entry ที่ใช้ได้ ตามลำดับของ yt-dlp (C2 ข้อ 1-2) key ที่ไม่มี entry ใช้ได้ถูกตัดทิ้ง"""
    if not isinstance(container, dict):
        return {}
    result: dict[str, list[dict]] = {}
    for key, items in container.items():
        if (
            not isinstance(key, str)
            or key in _DROPPED_KEYS
            or not _KEY.fullmatch(key)
            or not isinstance(items, list)
        ):
            continue
        usable = [item for item in items if _usable(item)]
        if usable:
            result[key] = usable
    return result


def _name(entries: list[dict], key: str) -> str:
    for item in entries:
        name = item.get("name")
        if isinstance(name, str) and name.strip():
            return name
    return key


def _plain_track(key: str, entries: list[dict]) -> dict | None:
    """ซับที่โหลดได้ตรง ๆ: URL แรกของแต่ละนามสกุลที่ไม่มี tlang (entry ซ้ำกันใช้ตัวแรก)"""
    urls: dict[str, str | None] = dict.fromkeys(_EXTS)
    for item in entries:
        if urls[item["ext"]] is None and not _has_tlang(item["url"]):
            urls[item["ext"]] = item["url"]
    if not any(urls.values()):
        return None
    return {"key": key, "name": _name(entries, key), **urls}


def _original_language(formats: Any, original_keys: list[str]) -> str | None:
    """C3 original_language จาก format ในผล probe และ key ของกลุ่ม original"""
    fmts = [f for f in formats if isinstance(f, dict)] if isinstance(formats, list) else []
    audio_langs = [
        _base(a["language"])
        for a in _audio_formats(fmts)
        if a["isOriginal"] and a.get("language") and _base(a["language"])
    ]
    key_bases = {_base(_key_lang(k)) for k in original_keys}
    for lang in audio_langs:
        if lang in key_bases:
            return lang
    if audio_langs:
        return audio_langs[0]
    for key in original_keys:
        if key.endswith(_ORIG):
            return _base(_key_lang(key))
    return None


def _translate_from(original_keys: list[str], lang: str | None) -> str | None:
    """C2 ข้อ 7: ต้นฉบับที่ตรงกับ original_language (-orig ก่อน เพราะแปลได้แน่) ไม่งั้นตัวแรก"""
    matching = [k for k in original_keys if lang and _base(_key_lang(k)) == lang]
    orig = [k for k in original_keys if k.endswith(_ORIG)]
    for choices in (
        [k for k in matching if k.endswith(_ORIG)],
        matching,
        orig,
        original_keys,
    ):
        if choices:
            return choices[0]
    return None


def trim_captions(raw: dict) -> dict:
    """C2: จัดซับในผล probe ดิบเป็นกลุ่ม owner / original / translated + translateFrom"""
    owner = []
    for key, entries in _usable_entries(raw.get("subtitles")).items():
        track = _plain_track(key, entries)
        if track is not None:
            owner.append(track)

    auto = _usable_entries(raw.get("automatic_captions"))
    original: list[dict] = []
    translated: list[dict] = []
    for key, entries in auto.items():
        if not key.endswith(_ORIG) and f"{key}{_ORIG}" in auto:
            continue  # C2 ข้อ 6: ซ้ำกับ <key>-orig (หรือปนกันจากเสียงพากย์)
        if key.endswith(_ORIG) or not all(_has_tlang(e["url"]) for e in entries):
            track = _plain_track(key, entries)
            if track is not None:
                original.append(track)
        else:
            translated.append({"key": key, "name": _name(entries, key)})

    original_keys = [t["key"] for t in original]
    lang = _original_language(raw.get("formats"), original_keys)
    return {
        "owner": owner,
        "original": original,
        "translated": translated,
        "translateFrom": _translate_from(original_keys, lang),
    }


# ---------- จากข้อมูลที่ตัดแล้ว (probe_json) ----------


def _captions(trimmed: dict) -> dict:
    captions = trimmed.get("captions") if isinstance(trimmed, dict) else None
    return captions if isinstance(captions, dict) else {}


def _items(captions: dict, group: str) -> list[dict]:
    items = captions.get(group)
    if not isinstance(items, list):
        return []
    return [
        item
        for item in items
        if isinstance(item, dict)
        and isinstance(item.get("key"), str)
        and _KEY.fullmatch(item["key"])
    ]


def _url(item: dict, ext: str) -> str | None:
    value = item.get(ext)
    return value if isinstance(value, str) and value else None


def _tlang_url(source: dict, ext: str, code: str) -> str | None:
    url = _url(source, ext)
    return _with_tlang(url, code) if url else None


def list_tracks(trimmed: dict) -> list[Track]:
    """แทร็กทั้งหมดเรียงกลุ่ม owner, original, translated (URL ของแทร็กแปลสร้างด้วย tlang)

    แถวเก่า (M2) ที่ไม่มี captions ได้รายการว่าง แทร็กแปลที่ไม่มีต้นฉบับให้แปลถูกตัดทิ้ง
    """
    captions = _captions(trimmed)
    originals = _items(captions, "original")
    source = next(
        (o for o in originals if o["key"] == captions.get("translateFrom")), None
    )
    tracks: list[Track] = []
    for group, prefix in _GROUPS:
        for item in _items(captions, group):
            key = item["key"]
            name = item.get("name")
            name = name if isinstance(name, str) and name else key
            if group == "translated":
                if source is None:
                    continue
                json3, vtt = (_tlang_url(source, ext, key) for ext in _EXTS)
                lang = key
            else:
                json3, vtt = _url(item, "json3"), _url(item, "vtt")
                lang = _key_lang(key) if group == "original" else key
            if json3 is None and vtt is None:
                continue
            tracks.append(Track(f"{prefix}.{key}", lang, name, group, json3, vtt))
    return tracks


def original_language(trimmed: dict) -> str | None:
    """C3: ภาษาต้นฉบับของคลิป (ภาษาหลัก เช่น "th", "en") หรือ None ถ้าบอกไม่ได้"""
    if not isinstance(trimmed, dict):
        return None
    keys = [o["key"] for o in _items(_captions(trimmed), "original")]
    return _original_language(trimmed.get("formats"), keys)


def default_track_id(
    tracks: list[Track], original_lang: str | None, prefer: str | None = "th"
) -> str | None:
    """C3: แทร็กที่เลือกให้เอง ไม่เลือกแทร็กแปลอัตโนมัติเด็ดขาด

    1. ซับเจ้าของคลิปภาษา prefer (Q8 = ก: ซับไทยของเจ้าของคลิปมาก่อน)
    2. ซับเจ้าของคลิปภาษาต้นฉบับ
    3. ซับอัตโนมัติ <ภาษาต้นฉบับ>-orig
    4. ซับเจ้าของคลิปตัวแรก
    5. None
    """
    owner = [t for t in tracks if t.group == "owner"]
    prefer = _base(prefer) if prefer else None
    original_lang = _base(original_lang) if original_lang else None
    for lang in (prefer, original_lang):
        if lang:
            for track in owner:
                if _base(track.lang) == lang:
                    return track.id
    if original_lang:
        for track in tracks:
            if (
                track.group == "original"
                and track.id.endswith(_ORIG)
                and _base(track.lang) == original_lang
            ):
                return track.id
    return owner[0].id if owner else None


def tracks_payload(trimmed: dict) -> dict:
    """คำตอบของ API รายการแทร็ก: {"tracks": [{id, lang, name, group}], "defaultTrackId"?}"""
    tracks = list_tracks(trimmed)
    payload: dict[str, Any] = {
        "tracks": [
            {"id": t.id, "lang": t.lang, "name": t.name, "group": t.group}
            for t in tracks
        ]
    }
    default = default_track_id(tracks, original_language(trimmed))
    if default is not None:
        payload["defaultTrackId"] = default
    return payload


def find_track(trimmed: dict, track_id: str) -> Track | None:
    """แทร็กตาม id (C1) id ผิดรูปแบบหรือไม่มีในคลิปนี้ = None"""
    if not isinstance(track_id, str) or not TRACK_ID.match(track_id):
        return None
    return next((t for t in list_tracks(trimmed) if t.id == track_id), None)
