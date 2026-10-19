"""M6 รอบ D1: โปรเซสลูกที่ yt-dlp เปิดเอง (ffmpeg ตอนรวม/ซ่อมไฟล์, ffprobe, deno) ต้องผูกกับแอพด้วย

yt-dlp เปิดลูกทุกตัวผ่าน yt_dlp.utils.Popen ตัวห่อใน core/extractor.py ส่งลูกให้ Platform.adopt_child ทันทีหลังเปิด
"""

from __future__ import annotations

import subprocess
import sys

import pytest
import yt_dlp.utils

from yttoolkit.core import extractor
from yttoolkit.platform import current

QUICK = [sys.executable, "-c", "pass"]
SLEEP = [sys.executable, "-c", "import time; time.sleep(60)"]


def test_ytdlp_still_spawns_through_utils_popen():
    """ตัวห่อพึ่ง API ภายในของ yt-dlp: อัปเดต yt-dlp แล้วคลาสนี้หาย/ไม่ใช่ Popen = เทสนี้แดง"""
    assert issubclass(yt_dlp.utils.Popen, subprocess.Popen)
    from yt_dlp.postprocessor import ffmpeg

    assert ffmpeg.Popen is yt_dlp.utils.Popen  # ตัวรวม/ซ่อมไฟล์ใช้คลาสเดียวกัน (ห่อที่คลาส = โดนทุกที่)


def test_popen_made_by_ytdlp_is_adopted():
    adopted: list[subprocess.Popen] = []
    extractor.adopt_ytdlp_children(adopted.append)
    with yt_dlp.utils.Popen(QUICK) as proc:
        proc.wait(timeout=30)
    assert adopted == [proc]


def test_wrapping_is_done_once_and_the_hook_can_be_swapped():
    first: list[int] = []
    second: list[int] = []
    extractor.adopt_ytdlp_children(lambda p: first.append(p.pid))
    wrapped = yt_dlp.utils.Popen.__init__
    extractor.adopt_ytdlp_children(lambda p: second.append(p.pid))
    assert yt_dlp.utils.Popen.__init__ is wrapped  # ไม่ห่อซ้อน
    assert not getattr(wrapped.__wrapped__, extractor._ADOPT_MARK, False)
    with yt_dlp.utils.Popen(QUICK) as proc:
        proc.wait(timeout=30)
    assert first == [] and second == [proc.pid]


def test_no_hook_means_nothing_is_adopted():
    extractor.adopt_ytdlp_children(None)
    with yt_dlp.utils.Popen(QUICK) as proc:
        assert proc.wait(timeout=30) == 0


def test_a_failing_hook_never_breaks_the_spawn():
    def broken(proc):
        raise OSError("boom")

    extractor.adopt_ytdlp_children(broken)
    out, _, code = yt_dlp.utils.Popen.run([sys.executable, "-c", "print('ok')"], text=True, stdout=subprocess.PIPE)
    assert code == 0 and out.strip() == "ok"


@pytest.mark.skipif(sys.platform != "win32", reason="Job Object มีแค่บน Windows")
def test_ytdlp_child_joins_the_app_job_on_windows():
    """ของจริง: ลูกที่เปิดผ่าน yt_dlp.utils.Popen อยู่ใน job ของแอพ kill_children ปิดมันได้"""
    plat = current()
    extractor.adopt_ytdlp_children(plat.adopt_child)
    proc = yt_dlp.utils.Popen(SLEEP, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        assert proc.poll() is None
        plat.kill_children()
        assert proc.wait(timeout=5) is not None
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)
