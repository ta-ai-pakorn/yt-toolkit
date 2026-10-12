from __future__ import annotations

import ctypes
import functools
import msvcrt
import os
import subprocess
import sys
import uuid
from ctypes import wintypes
from pathlib import Path

from .base import LockFileError, report_lock_open_failure

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


@functools.cache
def _shell_libs() -> tuple[ctypes.WinDLL, ctypes.WinDLL]:
    """โหลด shell32/ole32 ครั้งเดียวตอนใช้ครั้งแรก (ไม่โหลดตอน import เพื่อให้ import บน macOS ได้)"""
    shell32 = ctypes.WinDLL("shell32")
    shell32.SHGetKnownFolderPath.argtypes = (
        ctypes.POINTER(_GUID),
        wintypes.DWORD,
        wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_wchar_p),
    )
    shell32.SHGetKnownFolderPath.restype = ctypes.HRESULT
    ole32 = ctypes.WinDLL("ole32")
    ole32.CoTaskMemFree.argtypes = (ctypes.c_void_p,)
    ole32.CoTaskMemFree.restype = None
    return shell32, ole32


@functools.cache
def _short_path_name():
    """โหลด GetShortPathNameW ครั้งเดียวตอนใช้ครั้งแรก (ไม่โหลดตอน import เพื่อให้ import บน macOS ได้)"""
    fn = ctypes.WinDLL("kernel32", use_last_error=True).GetShortPathNameW
    fn.argtypes = (wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD)
    fn.restype = wintypes.DWORD
    return fn


class WindowsPlatform:
    name = "windows"
    popen_flags = subprocess.CREATE_NO_WINDOW
    ffmpeg_auto_install = True

    def exe_name(self, name: str) -> str:
        return f"{name}.exe"

    def downloads_dir(self) -> Path:
        try:
            shell32, ole32 = _shell_libs()
            out = ctypes.c_wchar_p()
            guid = _guid(_FOLDERID_DOWNLOADS)
            try:
                shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(out))
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
            creationflags=self.popen_flags,
        )

    def try_lock(self, path: Path) -> object | None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            handle = open(path, "a+b")  # noqa: SIM115 (ตัวจัดการเก็บไว้ให้ release_lock ปิดเอง)
        except OSError as error:
            report_lock_open_failure(path)
            raise LockFileError(f"เปิดไฟล์ lock ไม่ได้: {path}") from error
        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            handle.close()
            return None
        return handle

    def release_lock(self, handle: object) -> None:
        f = handle
        try:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        f.close()

    def path_aliases(self, path: Path) -> list[str]:
        """ชื่อสั้นแบบ 8.3 (เช่น C:/Users/SOMCHA~1) ถ้าต่างจากชื่อเต็ม หาไม่ได้คืนลิสต์ว่าง"""
        full = str(path)
        try:
            get_short = _short_path_name()
            size = get_short(full, None, 0)
            if not size:
                return []
            buffer = ctypes.create_unicode_buffer(size)
            written = get_short(full, buffer, size)
        except (OSError, AttributeError):
            return []
        if not written or written >= size:
            return []
        short = buffer.value
        return [short] if short.casefold() != full.casefold() else []

    def os_version(self) -> str:
        """ชื่อและเลขรุ่นของระบบปฏิบัติการสำหรับรายงานแจ้งปัญหา เช่น Windows 11 (10.0.26200) (M6 รอบ B)

        Windows 11 ยังรายงาน major 10 จึงดูเลข build ≥ 22000 · ไม่ใช้ platform.release() เพราะ Python รุ่นเก่าบอก 10
        บน Windows 11 · อ่านไม่ได้ = คืนแค่ Windows
        """
        try:
            v = sys.getwindowsversion()
            if v.major == 10 and v.build >= 22000:
                name = "Windows 11"
            elif v.major == 10:
                name = "Windows 10"
            else:
                name = f"Windows {v.major}"
            return f"{name} ({v.major}.{v.minor}.{v.build})"
        except Exception:
            return "Windows"
