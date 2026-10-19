from __future__ import annotations

import ctypes
import functools
import logging
import msvcrt
import os
import subprocess
import sys
import threading
import uuid
from ctypes import wintypes
from pathlib import Path

from ..children import run_adopted
from .base import LockFileError, report_lock_open_failure

log = logging.getLogger("yttoolkit")

_FOLDERID_DOWNLOADS = uuid.UUID("{374DE290-123F-4565-9164-39C4925E467B}")
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259
# Job Object (M6 รอบ D1): ลูกทุกตัวของแอพอยู่ใน job เดียว แอพตาย (End task, แครช) = handle ของ job ปิด = ลูกตายตาม
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_TERMINATE = 0x0001


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


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


@functools.cache
def _job_kernel32() -> ctypes.WinDLL:
    """kernel32 สำหรับ Job Object (โหลดตอนใช้ครั้งแรก ไม่โหลดตอน import เพื่อให้ import บน macOS ได้)"""
    k32 = _kernel32()
    k32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
    k32.SetInformationJobObject.restype = wintypes.BOOL
    k32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    k32.AssignProcessToJobObject.restype = wintypes.BOOL
    k32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    k32.TerminateJobObject.restype = wintypes.BOOL
    return k32


class _ChildJob:
    """Job Object หนึ่งตัวต่อโปรเซสของแอพ สร้างตอนผูกลูกตัวแรก แล้วเปิด handle ค้างไว้ตลอดอายุแอพ (ห้ามปิดเอง:
    ปิดเมื่อไรลูกทุกตัวโดน kill) handle สร้างแบบสืบทอดไม่ได้ ลูกจึงไม่ถือ handle ไว้จน job ไม่ยอมปิด
    สร้างหรือผูกไม่ได้ (เช่นแอพอยู่ใน job ของโปรแกรมอื่นที่ห้ามซ้อน) บันทึก log บรรทัดเดียวแล้วทำงานต่อแบบไม่ผูก"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._handle: int | None = None
        self._created = False
        self._reported = False

    def _report(self, step: str, code: int) -> None:
        if self._reported:
            log.debug("ผูกโปรเซสลูกกับแอพไม่ได้ (ซ้ำ): %s (WinError %s)", step, code)
            return
        self._reported = True
        log.warning("ผูกโปรเซสลูกกับแอพไม่ได้ ถ้าแอพโดนปิดกลางคัน โปรเซสลูกอาจค้าง: %s (WinError %s)", step, code)

    def handle(self) -> int | None:
        with self._lock:
            if self._created:
                return self._handle
            self._created = True
            try:
                k32 = _job_kernel32()
                job = k32.CreateJobObjectW(None, None)
                if not job:
                    self._report("CreateJobObject", ctypes.get_last_error())
                    return None
                info = _ExtendedLimitInformation()
                info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                if not k32.SetInformationJobObject(
                    job, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(info), ctypes.sizeof(info)
                ):
                    self._report("SetInformationJobObject", ctypes.get_last_error())
                    k32.CloseHandle(job)
                    return None
            except (OSError, AttributeError):
                self._report("kernel32", 0)
                return None
            self._handle = job
            return job

    def assign(self, pid: int) -> bool:
        job = self.handle()
        if job is None:
            return False
        k32 = _job_kernel32()
        process = k32.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, pid)
        if not process:
            self._report("OpenProcess", ctypes.get_last_error())
            return False
        try:
            if not k32.AssignProcessToJobObject(job, process):
                self._report("AssignProcessToJobObject", ctypes.get_last_error())
                return False
            return True
        finally:
            k32.CloseHandle(process)

    def close(self) -> None:
        """ปิด handle ของ job (ลูกที่ยังผูกอยู่โดน kill) แอพไม่เรียก ปล่อยให้ Windows ปิดตอนแอพตาย มีไว้ให้เทสเก็บกวาด"""
        with self._lock:
            job, self._handle = self._handle, None
        if job is not None:
            _job_kernel32().CloseHandle(job)

    def terminate(self) -> None:
        with self._lock:
            job = self._handle
        if job is not None and not _job_kernel32().TerminateJobObject(job, 1):
            log.warning("ปิดโปรเซสลูกของแอพไม่สำเร็จ (WinError %s)", ctypes.get_last_error())


_CHILD_JOB = _ChildJob()  # ตัวเดียวทั้งโปรเซส (current() สร้าง WindowsPlatform ใหม่ทุกครั้ง แต่ทุกตัวใช้ job นี้)


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
        run_adopted(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            self.adopt_child,
            capture_output=True,
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

    def adopt_child(self, proc: subprocess.Popen) -> None:
        """ผูกลูกไว้กับ Job Object ของแอพ (ลูกที่จบไปแล้วข้าม) ผูกไม่ได้ = log บรรทัดเดียวแล้วทำงานต่อ

        ข้อจำกัด: ผูกหลัง Popen คืนค่า ลูกที่เป็น shim (ffmpeg.exe ของ Chocolatey/Scoop, Git/cmd/git.exe)
        อาจเปิด exe ตัวจริงก่อนผูกทัน หลานตัวนั้นอยู่นอก job และค้างได้ถ้าแอพโดนปิดกลางคัน
        (ffmpeg ใน bin/ ของแอพและลิงก์ของ winget เป็นตัวจริง ไม่โดน) Python เปิดแบบ CREATE_SUSPENDED แล้วปล่อยเองไม่ได้ง่ายๆ จึงยอมรับไว้"""
        if proc.poll() is not None:
            return
        _CHILD_JOB.assign(proc.pid)

    def kill_children(self) -> None:
        _CHILD_JOB.terminate()

