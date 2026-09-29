import hashlib
import io
import threading
import time
import zipfile
from pathlib import Path

import pytest

from yttoolkit.core import tools


def _zip_bytes(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)
    return buf.getvalue()


GOOD_ZIP = _zip_bytes(
    {
        "ffmpeg-master-latest-win64-gpl/bin/ffmpeg.exe": b"FFMPEG",
        "ffmpeg-master-latest-win64-gpl/bin/ffprobe.exe": b"FFPROBE",
        "ffmpeg-master-latest-win64-gpl/doc/readme.txt": b"doc",
    }
)


def _fake_download(zip_data: bytes, checksum: str | None = None):
    digest = checksum or hashlib.sha256(zip_data).hexdigest()
    sums = f"{digest}  {tools.FFMPEG_WIN_ZIP}\nabc  other.zip\n"

    def download(url: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if url.endswith("checksums.sha256"):
            dest.write_text(sums, encoding="utf-8")
        elif url.endswith(tools.FFMPEG_WIN_ZIP):
            dest.write_bytes(zip_data)
        else:
            raise AssertionError(f"unexpected url {url}")

    return download


def test_parse_checksums():
    text = "aaa  one.zip\nBBB *two.zip\n"
    assert tools.parse_checksums(text, "one.zip") == "aaa"
    assert tools.parse_checksums(text, "two.zip") == "bbb"
    assert tools.parse_checksums(text, "three.zip") is None


def test_install_extracts_ffmpeg_and_ffprobe(paths):
    exe = tools.install_ffmpeg_windows(paths, download=_fake_download(GOOD_ZIP))
    assert exe == paths.bin / "ffmpeg.exe"
    assert (paths.bin / "ffmpeg.exe").read_bytes() == b"FFMPEG"
    assert (paths.bin / "ffprobe.exe").read_bytes() == b"FFPROBE"
    assert list(paths.work.iterdir()) == []  # ลบไฟล์ชั่วคราวแล้ว


def test_install_rejects_bad_checksum(paths):
    with pytest.raises(tools.ToolInstallError):
        tools.install_ffmpeg_windows(paths, download=_fake_download(GOOD_ZIP, checksum="0" * 64))
    assert not (paths.bin / "ffmpeg.exe").exists()
    assert list(paths.work.iterdir()) == []


def test_install_rejects_incomplete_zip(paths):
    partial = _zip_bytes({"x/bin/ffmpeg.exe": b"FFMPEG"})
    with pytest.raises(tools.ToolInstallError):
        tools.install_ffmpeg_windows(paths, download=_fake_download(partial))
    assert not (paths.bin / "ffmpeg.exe").exists()
    assert list(paths.work.iterdir()) == []


def test_install_wraps_network_errors(paths):
    def offline(url, dest):
        raise OSError("offline")

    with pytest.raises(tools.ToolInstallError):
        tools.install_ffmpeg_windows(paths, download=offline)


def test_install_ffmpeg_dispatch(paths, fake_platform, no_path_ffmpeg):
    assert tools.install_ffmpeg(paths, fake_platform, download=_fake_download(GOOD_ZIP)).name == "ffmpeg.exe"
    fake_platform.ffmpeg_auto_install = False
    with pytest.raises(tools.ToolInstallError):
        tools.install_ffmpeg(paths, fake_platform, download=_fake_download(GOOD_ZIP))


def test_install_ffmpeg_ignores_platform_name(paths, fake_platform, no_path_ffmpeg):
    # ตัดสินจากความสามารถของแพลตฟอร์ม ไม่ใช่ชื่อระบบ
    fake_platform.name = "macos"
    assert tools.install_ffmpeg(paths, fake_platform, download=_fake_download(GOOD_ZIP)).name == "ffmpeg.exe"


def _stored_zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as z:
        for name, data in members.items():
            z.writestr(name, data)
    return buf.getvalue()


@pytest.fixture
def no_path_ffmpeg(monkeypatch):
    # ไม่ให้ ffmpeg ที่อาจมีใน PATH ของเครื่องที่รันเทสมาปนผล
    monkeypatch.setenv("YT_TOOLKIT_FFMPEG_PATH_LOOKUP", "0")


def test_install_rejects_file_that_is_not_a_zip(paths):
    with pytest.raises(tools.ToolInstallError):
        tools.install_ffmpeg_windows(paths, download=_fake_download(b"<html>not a zip</html>"))
    assert list(paths.bin.iterdir()) == []
    assert list(paths.work.iterdir()) == []


def test_partial_extract_failure_leaves_no_ffmpeg(paths):
    good = _stored_zip(
        {
            "x/bin/ffmpeg.exe": b"FFMPEG",
            "x/bin/ffprobe.exe": b"FFPROBE",
        }
    )
    corrupt = good.replace(b"FFPROBE", b"FFPROBX", 1)  # CRC ของ ffprobe ไม่ตรง อ่านได้แค่ ffmpeg
    assert corrupt != good
    with pytest.raises(tools.ToolInstallError):
        tools.install_ffmpeg_windows(paths, download=_fake_download(corrupt))
    assert not (paths.bin / "ffmpeg.exe").exists()
    assert list(paths.bin.iterdir()) == []  # ไม่มีไฟล์ชั่วคราวค้าง
    assert list(paths.work.iterdir()) == []


def test_cleanup_failure_does_not_mask_success(paths, monkeypatch):
    real_unlink = Path.unlink

    def locked_unlink(self, missing_ok=False):
        if self.parent == paths.work:
            raise PermissionError("file is in use")
        return real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", locked_unlink)
    exe = tools.install_ffmpeg_windows(paths, download=_fake_download(GOOD_ZIP))
    assert exe.read_bytes() == b"FFMPEG"


def test_concurrent_installs_download_once(paths, fake_platform, monkeypatch, no_path_ffmpeg):
    monkeypatch.setattr(
        tools,
        "_run_version",
        lambda exe, plat, arg="--version": "ffmpeg version 8.1 Copyright" if Path(exe).is_file() else None,
    )
    inner = _fake_download(GOOD_ZIP)
    zip_downloads = []
    release = threading.Event()

    def slow_download(url, dest):
        if url.endswith(tools.FFMPEG_WIN_ZIP):
            zip_downloads.append(url)
        release.wait(5)
        inner(url, dest)

    results, errors = [], []

    def worker():
        try:
            results.append(tools.install_ffmpeg(paths, fake_platform, download=slow_download))
        except Exception as error:  # noqa: BLE001
            errors.append(error)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    time.sleep(0.3)  # ให้ thread ที่สองมาถึงจุดโหลดก่อน ถ้าไม่มี lock
    release.set()
    for t in threads:
        t.join(10)
    assert errors == []
    assert len(zip_downloads) == 1
    assert results == [paths.bin / "ffmpeg.exe"] * 2


def test_status_is_warn_while_installing(paths, fake_platform, no_path_ffmpeg):
    seen = []
    inner = _fake_download(GOOD_ZIP)

    def download(url, dest):
        seen.append(tools.ffmpeg_status(paths, fake_platform))
        inner(url, dest)

    tools.install_ffmpeg(paths, fake_platform, download=download)
    assert seen[0] == tools.ToolStatus("warn", name="ffmpeg", message="กำลังโหลด ffmpeg อาจใช้เวลา 1-3 นาที")
    assert tools.ffmpeg_status(paths, fake_platform).message != "กำลังโหลด ffmpeg อาจใช้เวลา 1-3 นาที"


def test_install_skips_download_when_ffmpeg_already_ok(paths, fake_platform, monkeypatch, no_path_ffmpeg):
    (paths.bin / "ffmpeg.exe").write_bytes(b"x")
    monkeypatch.setattr(tools, "_run_version", lambda exe, plat, arg="--version": "ffmpeg version 8.1 Copyright")

    def must_not_download(url, dest):
        raise AssertionError("ไม่ควรโหลดซ้ำเมื่อ ffmpeg ใช้งานได้แล้ว")

    assert tools.install_ffmpeg(paths, fake_platform, download=must_not_download) == paths.bin / "ffmpeg.exe"


def test_install_removes_leftover_part_files(paths, fake_platform, no_path_ffmpeg):
    paths.bin.mkdir(parents=True, exist_ok=True)
    (paths.bin / "ffmpeg.exe.part").write_bytes(b"half")
    (paths.bin / "old.part").write_bytes(b"half")
    seen = []
    inner = _fake_download(GOOD_ZIP)

    def download(url, dest):
        seen.append(sorted(p.name for p in paths.bin.glob("*.part")))
        inner(url, dest)

    tools.install_ffmpeg(paths, fake_platform, download=download)
    assert seen[0] == []  # ลบของค้างก่อนเริ่มโหลด
    assert sorted(p.name for p in paths.bin.iterdir()) == ["ffmpeg.exe", "ffprobe.exe"]


def test_install_replaces_ffprobe_before_ffmpeg(paths, monkeypatch):
    # มี ffmpeg แปลว่าติดตั้งครบแล้ว จึงต้องวาง ffmpeg เป็นตัวสุดท้าย (zip นี้มี ffmpeg มาก่อน)
    order = []
    real_replace = tools.os.replace

    def recording_replace(src, dst):
        order.append(Path(dst).name)
        real_replace(src, dst)

    monkeypatch.setattr(tools.os, "replace", recording_replace)
    tools.install_ffmpeg_windows(paths, download=_fake_download(GOOD_ZIP))
    assert order == ["ffprobe.exe", "ffmpeg.exe"]
