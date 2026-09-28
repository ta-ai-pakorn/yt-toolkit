from __future__ import annotations

import ctypes
import os
import subprocess
import uuid
from ctypes import wintypes
from pathlib import Path

_FOLDERID_DOWNLOADS = uuid.UUID("{374DE290-123F-4565-9164-39C4925E467B}")
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid(value: uuid.UUID) -> _GUID:
    guid = _GUID()
    ctypes.memmove(ctypes.byref(guid), value.bytes_le, 16)
    return guid


def _kernel32() -> ctypes.WinDLL:
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    k32.GetExitCodeProcess.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    k32.CloseHandle.restype = wintypes.BOOL
    return k32


class WindowsPlatform:
    name = "windows"
    ffmpeg_exe = "ffmpeg.exe"
    ffprobe_exe = "ffprobe.exe"

    def downloads_dir(self) -> Path:
        try:
            shell32 = ctypes.WinDLL("shell32")
            ole32 = ctypes.WinDLL("ole32")
            out = ctypes.c_wchar_p()
            guid = _guid(_FOLDERID_DOWNLOADS)
            if shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(out)) == 0:
                try:
                    return Path(out.value)
                finally:
                    ole32.CoTaskMemFree(out)
        except OSError:
            pass
        return Path.home() / "Downloads"

    def open_folder(self, path: Path) -> None:
        os.startfile(path)  # noqa: S606 (เปิดโฟลเดอร์ที่แอพสร้างเอง)

    def reveal(self, path: Path) -> None:
        subprocess.run(["explorer", f"/select,{path}"], check=False)

    def pid_alive(self, pid: int) -> bool:
        if pid <= 0:
            return False
        k32 = _kernel32()
        handle = k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == _STILL_ACTIVE
        finally:
            k32.CloseHandle(handle)

    def kill(self, pid: int) -> None:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
