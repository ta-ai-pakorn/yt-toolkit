import hashlib
import io
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


def test_install_wraps_network_errors(paths):
    def offline(url, dest):
        raise OSError("offline")

    with pytest.raises(tools.ToolInstallError):
        tools.install_ffmpeg_windows(paths, download=offline)


def test_install_ffmpeg_dispatch(paths, fake_platform):
    assert tools.install_ffmpeg(paths, fake_platform, download=_fake_download(GOOD_ZIP)).name == "ffmpeg.exe"
    fake_platform.name = "macos"
    with pytest.raises(tools.ToolInstallError):
        tools.install_ffmpeg(paths, fake_platform, download=_fake_download(GOOD_ZIP))
