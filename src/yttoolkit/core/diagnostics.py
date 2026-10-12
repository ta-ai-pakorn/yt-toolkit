"""รายงานแจ้งปัญหา (M6 รอบ B · PRD ข้อ 7.1 · FR-SET-5): ข้อความ Markdown ที่พนักงานคัดลอกไปส่งผู้ดูแล

เซิร์ฟเวอร์สร้างทั้งรายงานที่นี่ที่เดียว: สถานะเครื่อง + error + log ล่าสุด 50 บรรทัด
ทุกส่วนผ่าน redact.redact_report ที่จุดเดียว (build_report ขั้นที่ 2) แล้วค่อยตัดความยาว จึงไม่มีรอยตัดกลาง path
ไม่ต่อเน็ต ไม่ import FastAPI, yt_dlp หรือ extractor (ผู้เรียกส่งสถานะเครื่องมือเข้ามา) อ่านแค่ไฟล์ log
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..redact import redact_report
from .tools import ToolStatus

log = logging.getLogger("yttoolkit")

NONE = "ไม่มี"
TITLE = "## รายงานปัญหา YT Toolkit"
LOG_HEADING = "### log ล่าสุด (50 บรรทัด)"  # หัวข้อคงที่ตามแม่แบบ แม้ log มีไม่ถึง 50 บรรทัด
ACCOUNT_OFF = "ไม่ได้ใช้บัญชี"
ACCOUNT_ON = "ใช้บัญชีชั่วคราวอยู่"
LOG_FILES = ("app.log", "app.log.1", "app.log.2")  # ใหม่ไปเก่า (หมุนไฟล์เก็บ 3 ไฟล์ probe.LOG_BACKUPS)
TAIL_LINES = 50
TAIL_BYTES = 64 * 1024  # อ่านท้ายไฟล์ละไม่เกินเท่านี้ ไฟล์ใหญ่ 5 MB ก็ไม่ต้องอ่านทั้งไฟล์
DETAIL_MAX = 2000
LOG_LINE_MAX = 300
REPORT_MAX = 8000  # พอดีกับช่องแชตทั่วไป (LINE / Teams / AI) ดู spec Review Focus 1
ELLIPSIS = "…"
_BACKTICKS = re.compile(r"`{3,}")
_LINE_BREAK = re.compile(r"\r\n|[\r\x85  ]")


@dataclass(frozen=True)
class ErrorSection:
    code: str | None  # None = "ไม่มี"
    detail: str | None
    kind: str | None = None  # ชนิดงาน ("video", "audio", ...) มี = error ของงานในคิว
    video_id: str | None = None
    context: str | None = None  # หน้าจอที่เกิด error (error ที่ไม่ใช่งานในคิวเท่านั้น)


@dataclass(frozen=True)
class ReportInputs:
    now: datetime  # เวลาท้องถิ่นที่มี timezone (api ส่ง datetime.now().astimezone() เทสส่งเอง)
    version: str
    commit: str | None
    os_version: str
    ytdlp: ToolStatus
    ffmpeg: ToolStatus
    js_runtime: ToolStatus
    account_active: bool
    error: ErrorSection | None
    log_dir: Path
    token: str  # ใช้ซ่อนเท่านั้น ไม่มีวันอยู่ในรายงาน
    titles: tuple[str, ...]  # ชื่อคลิปที่ต้องปิด (ชื่องาน + ชื่อในตาราง videos)


def build_report(inputs: ReportInputs) -> str:
    """รายงานตามแม่แบบ PRD ข้อ 7.1 ทุกบรรทัดจบด้วย LF

    ลำดับที่อนุญาตลำดับเดียว: 1) รวบรวมส่วนดิบ 2) redact_report ทุกส่วน 3) ตัดความยาว 4) ต่อด้วย \\n
    """
    offset = inputs.now.utcoffset()
    assert offset is not None, "now ต้องมี timezone (datetime.now().astimezone())"
    # 1) ส่วนดิบ
    header = [_lf(line) for line in _header_lines(inputs)]
    code_line = _lf(_code_line(inputs.error)) if inputs.error is not None else None
    detail = _lf(inputs.error.detail or "") if inputs.error is not None else ""
    logs = _tail_lines(inputs.log_dir)
    # 2) ซ่อนข้อมูลส่วนตัว (จุดเดียวของรายงาน · C5)

    def redact(text: str) -> str:
        return redact_report(text, token=inputs.token, titles=inputs.titles)

    header = [redact(line) for line in header]
    code_line = redact(code_line) if code_line is not None else None
    detail = redact(detail)
    logs = [redact(line) for line in logs]
    # 3) ตัดความยาว (หลังซ่อนแล้ว รอยตัดจึงไม่ทำให้ชื่อผู้ใช้หลุดครึ่งหนึ่ง)
    detail = _cut(detail, DETAIL_MAX)
    logs = [_cut(line, LOG_LINE_MAX) for line in logs]
    # 4) ต่อ แล้วทิ้ง log บรรทัดเก่าสุดทีละบรรทัดจนไม่เกิน REPORT_MAX
    text = _assemble(header, code_line, detail, logs)
    while len(text) > REPORT_MAX and logs:
        logs.pop(0)
        text = _assemble(header, code_line, detail, logs)
    if len(text) > REPORT_MAX and code_line is not None:  # กันไว้เผื่อเพดานเปลี่ยนในอนาคต (เพดานปัจจุบันไปไม่ถึงตรงนี้)
        detail = _cut(detail, max(1, len(detail) - (len(text) - REPORT_MAX)))
        text = _assemble(header, code_line, detail, logs)
    return text


def _header_lines(inputs: ReportInputs) -> list[str]:
    z = inputs.now.strftime("%z")  # +0700
    when = f"{inputs.now.strftime('%Y-%m-%d %H:%M')} ({z[:3]}:{z[3:5]})"
    ffmpeg = inputs.ffmpeg.version if inputs.ffmpeg.status == "ok" and inputs.ffmpeg.version else NONE
    runtime = inputs.js_runtime
    js = " ".join(part for part in (runtime.name, runtime.version) if part) if runtime.name else NONE
    return [
        TITLE,
        f"- เวลา: {when}",
        f"- แอพ: {inputs.version} (commit {inputs.commit or NONE}) · ระบบ: {inputs.os_version}",
        f"- yt-dlp: {inputs.ytdlp.version or NONE} · ffmpeg: {ffmpeg} · JS runtime: {js}",
        f"- บัญชียูทูป: {ACCOUNT_ON if inputs.account_active else ACCOUNT_OFF}",
    ]


def _code_line(error: ErrorSection) -> str:
    code = error.code or NONE
    if error.kind is not None:  # งานในคิว: บรรทัดตามแม่แบบตรงตัว
        return f"- รหัส: {code} · งาน: {error.kind} (videoId {error.video_id or NONE})"
    line = f"- รหัส: {code}"
    if error.context:
        line += f" · หน้าจอ: {error.context}"  # ป้ายไทยตาม Pete spec Q1 ตามด้วยแท็ก ASCII ของหน้าจอ
    if error.video_id:
        line += f" (videoId {error.video_id})"
    return line


def _detail_lines(detail: str) -> list[str]:
    if not detail.strip():
        return [f"- รายละเอียด: {NONE}"]
    first, *rest = detail.split("\n")
    return [f"- รายละเอียด: {first}", *(f"  {line}" for line in rest)]  # บรรทัดต่อของรายการ Markdown


def _fence(lines: list[str]) -> str:
    longest = max((len(run) for line in lines for run in _BACKTICKS.findall(line)), default=0)
    return "`" * max(3, longest + 1)


def _assemble(header: list[str], code_line: str | None, detail: str, logs: list[str]) -> str:
    out = list(header)
    if code_line is not None:
        out += ["### error", code_line, *_detail_lines(detail)]
    fence = _fence(logs)
    out += [LOG_HEADING, f"{fence}text", *(logs or [NONE]), fence]
    return "\n".join(out) + "\n"


def _lf(text: str) -> str:
    """ตัวขึ้นบรรทัดทุกแบบ (CRLF, CR, NEL, U+2028, U+2029) กลายเป็น LF ตัวเดียว"""
    return _LINE_BREAK.sub("\n", text)


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + ELLIPSIS


# ---------- log ล่าสุด ----------


def _file_handler(log_dir: Path) -> logging.Handler | None:
    """handler ของ app.log ตัวที่ probe.setup_file_log สร้าง (lock เดียวกับที่ emit → doRollover ใช้) ไม่มี = None"""
    target = os.path.abspath(log_dir / "app.log")
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.handlers.RotatingFileHandler) and handler.baseFilename == target:
            return handler
    return None


def _read_tail(path: Path) -> tuple[list[str], bool] | None:
    """บรรทัดท้ายไฟล์ (ไม่เกิน TAIL_BYTES) และว่าได้อ่านทั้งไฟล์ไหม · ไม่มีไฟล์ = None · อ่านไม่ได้ = OSError"""
    try:
        f = open(path, "rb")  # noqa: SIM115 (ปิดใน finally ด้านล่าง)
    except FileNotFoundError:
        return None
    try:
        size = f.seek(0, os.SEEK_END)
        start = max(0, size - TAIL_BYTES)
        f.seek(start)
        data = f.read()
    finally:
        f.close()
    lines = data.decode("utf-8", errors="replace").splitlines()
    if start > 0 and lines:
        lines = lines[1:]  # บรรทัดแรกหลังจุดที่ seek ถูกตัดกลางบรรทัด
    return lines, start == 0


TailReader = Callable[[Path], "tuple[list[str], bool] | None"]


def _tail_lines(log_dir: Path, want: int = TAIL_LINES, *, read: TailReader = _read_tail) -> list[str]:
    """log ล่าสุดไม่เกิน want บรรทัด เก่าไปใหม่ · อ่านไฟล์เก่ากว่าต่อเมื่อไฟล์ใหม่กว่าอ่านได้ทั้งไฟล์แล้วยังไม่พอ (ไม่มีช่องโหว่)

    ถือ lock ของ handler ของ app.log ระหว่างอ่าน: บน Windows ถ้าหมุนไฟล์ตอนเรากำลังเปิดไฟล์อยู่ การเปลี่ยนชื่อจะล้มและ
    บรรทัดนั้นหาย · ไม่ log อะไรระหว่างถือ lock (บันทึกไฟล์ที่อ่านไม่ได้ไว้ log ทีหลัง)
    """
    handler = _file_handler(log_dir)
    unreadable: list[str] = []
    result: list[str] = []
    if handler is not None:
        handler.acquire()
    try:
        for name in LOG_FILES:
            try:
                got = read(log_dir / name)
            except OSError:
                unreadable.append(name)
                continue
            if got is None:
                continue
            lines, whole = got
            need = want - len(result)
            result = (lines[-need:] if need > 0 else []) + result
            if len(result) >= want or not whole:
                break
    finally:
        if handler is not None:
            handler.release()
    for name in unreadable:
        log.debug("diagnostics_skip file=%s", name)  # ASCII ตาม preflight F5
    return result
