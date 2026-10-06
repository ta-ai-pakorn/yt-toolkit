"""M5 รอบ C กับยูทูปจริง: คลิปจำกัดอายุกับบัญชียูทูปชั่วคราว (spec 6 "Network test" · AC-CK-09)

ต้องได้รับอนุญาตจากพิธก่อนรัน และใช้ไฟล์ cookies.txt ของบัญชีสำรองของพิธเอง (ส่งออกจากหน้าต่างไม่ระบุตัวตนตามขั้นตอนใน dialog):
  - path ของไฟล์มาจาก env YT_TOOLKIT_TEST_COOKIES เท่านั้น ห้ามคัดลอกไฟล์เข้า repo ห้าม commit · ไม่ตั้ง = ข้ามทั้งไฟล์
  - id ของคลิปอยู่ใน tests/network_videos.toml ([account] age_restricted) · ว่าง = ข้ามทั้งไฟล์
  - โหลดเสียงไฟล์เล็กที่สุดของคลิปหนึ่งไฟล์ (ราว 1-5 MB) ลง temp ของ pytest · ไฟล์ cookies.txt ถูกอ่านเข้าหน่วยความจำครั้งเดียว
รันเองด้วย: YT_TOOLKIT_TEST_COOKIES=<path ของ cookies.txt> uv run pytest -m network -q tests/network/test_account_network.py -s
รันเสร็จแล้ว: ออกจากระบบในหน้าต่างไม่ระบุตัวตนแล้วปิดหน้าต่าง (แบบเดียวกับที่แอพบอกผู้ใช้) แล้วลบไฟล์ cookies.txt
ยูทูปตอบ 429 หรือขอยืนยันว่าไม่ใช่บอท = เทสตก ให้รายงานผล ห้ามแก้เทสให้หลวมลง
"""

from __future__ import annotations

import os
import time
import tomllib
from pathlib import Path
from typing import Any

import pytest

from yttoolkit.core.account_scope import signed_in
from yttoolkit.core.download import DownloadChoice, DownloadHooks
from yttoolkit.core.extractor import YtDlpExtractor, parse_account_cookies
from yttoolkit.core.yterrors import YtError

pytestmark = pytest.mark.network

COOKIES_ENV = "YT_TOOLKIT_TEST_COOKIES"
_TOML = Path(__file__).resolve().parents[1] / "network_videos.toml"
CLIP: str = tomllib.loads(_TOML.read_text(encoding="utf-8")).get("account", {}).get("age_restricted", "")
GAP_S = 2  # เว้นช่วงระหว่างคำขอไปยูทูป (แบบเดียวกับ network test อื่น)
MAX_AUDIO_BYTES = 20_000_000


@pytest.fixture(scope="module")
def jar() -> Any:
    path = os.environ.get(COOKIES_ENV, "")
    if not path:
        pytest.skip(f"ตั้ง {COOKIES_ENV} เป็น path ของ cookies.txt ของบัญชีสำรองก่อนรัน")
    if not CLIP:
        pytest.skip("ใส่ id คลิปจำกัดอายุใน tests/network_videos.toml [account] age_restricted ก่อนรัน")
    return parse_account_cookies(Path(path).read_text(encoding="utf-8"))


def _smallest_audio(info: dict) -> DownloadChoice:
    return DownloadChoice("worstaudio[ext=m4a]/worstaudio", False, None, (), None)


def _hooks() -> DownloadHooks:
    return DownloadHooks(on_stage=lambda s: None, on_progress=lambda *a: None, is_cancelled=lambda: False,
                         ffmpeg_location=None)  # fmt: skip


def _a_cookie_value(jar: Any) -> bytes:
    """ค่าคุกกี้หนึ่งค่าจาก jar (ยาวที่สุด) ไว้ค้นในไฟล์ · ห้ามพิมพ์ค่านี้ ห้ามใส่ในข้อความ assert"""
    values = [c.value for c in jar if c.value and len(c.value) >= 8]
    assert values, "jar has no cookie value long enough to search for"
    return max(values, key=len).encode("utf-8")


def _ytdlp_cachedir(ext: YtDlpExtractor, jar: Any) -> Path | None:
    """โฟลเดอร์ cache ของ yt-dlp ที่ตัวดึงข้อมูลใช้ (ถามผ่าน YoutubeDL ของ extractor เทสไม่ import yt_dlp เอง)"""
    with ext._ydl({"quiet": True, "no_warnings": True}, with_account=jar) as ydl:
        if not ydl.cache.enabled:
            return None
        return Path(ydl.cache._get_root_dir())


def _files_with(needle: bytes, roots: list[Path]) -> list[str]:
    """ชื่อไฟล์ (เทียบกับโฟลเดอร์ที่ค้น) ที่มี needle อยู่ คืนแค่ชื่อไฟล์ ไม่คืนเนื้อหา"""
    found = []
    for root in roots:
        for path in root.rglob("*"):
            if path.is_file() and needle in path.read_bytes():
                found.append(f"{root.name}/{path.relative_to(root).as_posix()}")
    return found


def test_without_the_account_the_clip_is_age_restricted(jar: Any) -> None:
    with pytest.raises(YtError) as info:
        YtDlpExtractor().probe(CLIP)
    assert info.value.code == "E_AGE_RESTRICTED"
    time.sleep(GAP_S)


def test_signed_in_probe_and_a_small_download(jar: Any, tmp_path: Path) -> None:
    ext = YtDlpExtractor()
    workdir = tmp_path / "work"
    workdir.mkdir()
    with signed_in(jar):
        info = ext.probe(CLIP)
        assert info["id"] == CLIP
        time.sleep(GAP_S)
        result = ext.download(CLIP, _smallest_audio, workdir, _hooks())
    size = result.path.stat().st_size
    assert 0 < size < MAX_AUDIO_BYTES
    media = [p for p in tmp_path.rglob("media.*") if p.is_file() and p.stat().st_size > 0]
    assert [p.name for p in media] == [result.path.name]  # ไฟล์เสียงหนึ่งไฟล์ (yt-dlp อาจทิ้งไฟล์ข้างเคียงอื่นได้ แต่ห้ามมีค่าคุกกี้)
    roots = [tmp_path]
    cachedir = _ytdlp_cachedir(ext, jar)
    if cachedir is not None and cachedir.is_dir():
        roots.append(cachedir)
    leaks = _files_with(_a_cookie_value(jar), roots)
    assert leaks == []  # ไม่มีค่าคุกกี้ลงดิสก์ ทั้งใน temp ของเทสและ cache ของ yt-dlp (รายการนี้มีแค่ชื่อไฟล์)
    print(f"{CLIP}: {result.path.name} {size / 1e6:.1f} MB")
    time.sleep(GAP_S)
