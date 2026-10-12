"""รายงานแจ้งปัญหา (M6 รอบ B · core/diagnostics.py · PRD ข้อ 7.1): แม่แบบ ค่าที่ไม่มี log ล่าสุด และเพดานความยาว"""

from __future__ import annotations

import logging
import logging.handlers
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path, PureWindowsPath

import pytest

from yttoolkit import redact
from yttoolkit.core import diagnostics
from yttoolkit.core.diagnostics import (
    DETAIL_MAX,
    LOG_LINE_MAX,
    REPORT_MAX,
    ErrorSection,
    ReportInputs,
    build_report,
)
from yttoolkit.core.tools import ToolStatus

BANGKOK = timezone(timedelta(hours=7))
NOW = datetime(2026, 10, 5, 14, 32, 9, tzinfo=BANGKOK)
TOKEN = "tok-5d4c3b2a1f0e"


def inputs(log_dir: Path, **over) -> ReportInputs:
    base = ReportInputs(
        now=NOW,
        version="0.1.0",
        commit="abc1234",
        os_version="Windows 11 (10.0.26200)",
        ytdlp=ToolStatus("ok", name="yt-dlp", version="2026.09.20"),
        ffmpeg=ToolStatus("ok", name="ffmpeg", version="8.1", path="C:/tools/ffmpeg.exe"),
        js_runtime=ToolStatus("ok", name="deno", version="2.9.7", path="C:/tools/deno.exe"),
        account_active=False,
        error=ErrorSection(code="E_BOT_CHECK", detail="ERROR: [youtube] dQw4w9WgXcQ: Sign in to confirm", kind="video",
                           video_id="dQw4w9WgXcQ"),  # fmt: skip
        log_dir=log_dir,
        token=TOKEN,
        titles=(),
    )
    return replace(base, **over)


def write_log(log_dir: Path, name: str, lines: list[str]) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / name).write_text("".join(f"{line}\n" for line in lines), encoding="utf-8", newline="\n")


def log_block(report: str) -> list[str]:
    body = report.split("### log ล่าสุด (50 บรรทัด)\n", 1)[1]
    lines = body.rstrip("\n").split("\n")
    return lines[1:-1]  # ไม่เอาบรรทัดเปิดและปิดรั้ว


# ---------- แม่แบบ ----------


def test_job_report_matches_the_prd_template_exactly(tmp_path: Path) -> None:
    write_log(tmp_path, "app.log", ["2026-10-05 14:31:58,120 INFO yttoolkit: งาน j1 (video) จบด้วย E_BOT_CHECK"])
    assert build_report(inputs(tmp_path)) == (
        "## รายงานปัญหา YT Toolkit\n"
        "- เวลา: 2026-10-05 14:32 (+07:00)\n"
        "- แอพ: 0.1.0 (commit abc1234) · ระบบ: Windows 11 (10.0.26200)\n"
        "- yt-dlp: 2026.09.20 · ffmpeg: 8.1 · JS runtime: deno 2.9.7\n"
        "- บัญชียูทูป: ไม่ได้ใช้บัญชี\n"
        "### error\n"
        "- รหัส: E_BOT_CHECK · งาน: video (videoId dQw4w9WgXcQ)\n"
        "- รายละเอียด: ERROR: [youtube] dQw4w9WgXcQ: Sign in to confirm\n"
        "### log ล่าสุด (50 บรรทัด)\n"
        "```text\n"
        "2026-10-05 14:31:58,120 INFO yttoolkit: งาน j1 (video) จบด้วย E_BOT_CHECK\n"
        "```\n"
    )


def test_time_uses_the_local_offset_with_a_colon(tmp_path: Path) -> None:
    utc = build_report(inputs(tmp_path, now=datetime(2026, 1, 2, 3, 4, tzinfo=UTC)))
    assert "- เวลา: 2026-01-02 03:04 (+00:00)\n" in utc
    minus = build_report(inputs(tmp_path, now=datetime(2026, 1, 2, 3, 4, tzinfo=timezone(timedelta(hours=-3, minutes=-30)))))
    assert "(-03:30)" in minus


def test_a_naive_time_is_a_programming_error(tmp_path: Path) -> None:
    with pytest.raises(AssertionError):
        build_report(inputs(tmp_path, now=datetime(2026, 10, 5, 14, 32)))


def test_missing_values_say_none(tmp_path: Path) -> None:
    report = build_report(inputs(
        tmp_path,
        commit=None,
        ytdlp=ToolStatus("ok", name="yt-dlp", version=None),
        ffmpeg=ToolStatus("error", name="ffmpeg", message="ยังไม่มีโปรแกรมแปลงไฟล์ (ffmpeg)"),
        js_runtime=ToolStatus("warn", name=None, message="x"),
    ))  # fmt: skip
    assert "- แอพ: 0.1.0 (commit ไม่มี) · ระบบ: Windows 11 (10.0.26200)\n" in report
    assert "- yt-dlp: ไม่มี · ffmpeg: ไม่มี · JS runtime: ไม่มี\n" in report


@pytest.mark.parametrize("status", ["warn", "error"])
def test_ffmpeg_version_only_when_ready(tmp_path: Path, status: str) -> None:
    report = build_report(inputs(tmp_path, ffmpeg=ToolStatus(status, name="ffmpeg", version="8.1")))
    assert "· ffmpeg: ไม่มี ·" in report


def test_node_fallback_shows_node_and_its_version(tmp_path: Path) -> None:
    report = build_report(inputs(tmp_path, js_runtime=ToolStatus("warn", name="node", version="22.11.0")))
    assert "JS runtime: node 22.11.0\n" in report


def test_tool_paths_never_appear(tmp_path: Path) -> None:
    report = build_report(inputs(tmp_path))
    assert "C:/tools" not in report and "ffmpeg.exe" not in report


@pytest.mark.parametrize(("active", "line"), [(False, "ไม่ได้ใช้บัญชี"), (True, "ใช้บัญชีชั่วคราวอยู่")])
def test_account_line_has_only_the_two_prd_phrases(tmp_path: Path, active: bool, line: str) -> None:
    report = build_report(inputs(tmp_path, account_active=active))
    assert f"- บัญชียูทูป: {line}\n" in report
    assert [x for x in report.splitlines() if "บัญชี" in x] == [f"- บัญชียูทูป: {line}"]  # ไม่มีเวลา ชื่อ หรือค่าคุกกี้


# ---------- หัวข้อ error ----------


def test_non_job_error_line_with_context_and_video_id(tmp_path: Path) -> None:
    error = ErrorSection(code="E_NETWORK", detail=None, context="video-header", video_id="dQw4w9WgXcQ")
    report = build_report(inputs(tmp_path, error=error))
    assert "- รหัส: E_NETWORK · หน้าจอ: video-header (videoId dQw4w9WgXcQ)\n- รายละเอียด: ไม่มี\n" in report


def test_non_job_error_line_without_context_or_video_id(tmp_path: Path) -> None:
    report = build_report(inputs(tmp_path, error=ErrorSection(code=None, detail="")))
    assert "### error\n- รหัส: ไม่มี\n- รายละเอียด: ไม่มี\n" in report


def test_non_job_error_with_context_only(tmp_path: Path) -> None:
    report = build_report(inputs(tmp_path, error=ErrorSection(code="E_UNKNOWN", detail="x", context="crash")))
    assert "- รหัส: E_UNKNOWN · หน้าจอ: crash\n" in report


def test_no_error_section_for_the_health_report(tmp_path: Path) -> None:
    report = build_report(inputs(tmp_path, error=None))
    assert "### error" not in report and "- รหัส:" not in report
    assert "- บัญชียูทูป: ไม่ได้ใช้บัญชี\n### log ล่าสุด (50 บรรทัด)\n" in report


def test_multi_line_detail_is_a_list_continuation_and_crlf_collapses(tmp_path: Path) -> None:
    error = ErrorSection(code="E_UNKNOWN", detail="TypeError: x\r\n    at a (app.js:1)\n    at b (app.js:2)", context="crash")
    report = build_report(inputs(tmp_path, error=error))
    assert "- รายละเอียด: TypeError: x\n      at a (app.js:1)\n      at b (app.js:2)\n### log" in report
    assert "\r" not in report


@pytest.mark.parametrize("brk", ["\r", "\x85", " ", " ", "\r\n"])
def test_every_line_break_kind_becomes_lf(tmp_path: Path, brk: str) -> None:
    error = ErrorSection(code="E_UNKNOWN", detail=f"first{brk}second", context=f"crash{brk}x")
    report = build_report(inputs(tmp_path, error=error))
    assert "- รายละเอียด: first\n  second\n### log" in report
    assert "- รหัส: E_UNKNOWN · หน้าจอ: crash\nx\n" in report
    assert not any(c in report for c in "\r\x85  ")


# ---------- log ล่าสุด ----------


def test_tail_spans_rotation_in_order(tmp_path: Path) -> None:
    write_log(tmp_path, "app.log.1", [f"old {i}" for i in range(40)])
    write_log(tmp_path, "app.log", [f"new {i}" for i in range(20)])
    lines = log_block(build_report(inputs(tmp_path)))
    assert lines == [f"old {i}" for i in range(10, 40)] + [f"new {i}" for i in range(20)]


def test_tail_reads_at_most_three_files_and_ignores_an_old_fourth(tmp_path: Path) -> None:
    write_log(tmp_path, "app.log.3", ["ancient"])
    write_log(tmp_path, "app.log.2", ["two"])
    write_log(tmp_path, "app.log.1", ["one"])
    write_log(tmp_path, "app.log", ["zero"])
    assert log_block(build_report(inputs(tmp_path))) == ["two", "one", "zero"]


def test_no_log_files_say_none_inside_the_fence(tmp_path: Path) -> None:
    report = build_report(inputs(tmp_path / "missing"))
    assert report.endswith("### log ล่าสุด (50 บรรทัด)\n```text\nไม่มี\n```\n")


def test_invalid_utf8_bytes_become_replacement_characters(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "app.log").write_bytes(b"ok \xff\xfe bytes\n")
    assert log_block(build_report(inputs(tmp_path))) == ["ok \ufffd\ufffd bytes"]


def test_a_big_app_log_drops_the_partial_first_line_and_never_pulls_from_older_files(tmp_path: Path) -> None:
    write_log(tmp_path, "app.log.1", ["older file"])
    filler = "x" * 2000
    write_log(tmp_path, "app.log", [f"{i:03d} {filler}" for i in range(40)] + [f"tail {i}" for i in range(3)])
    lines = log_block(build_report(inputs(tmp_path, error=None)))
    assert "older file" not in lines
    assert lines[-3:] == ["tail 0", "tail 1", "tail 2"]
    assert all(line.startswith(("tail", "0")) for line in lines)  # ไม่มีเศษบรรทัดที่ถูกตัดหัว


def test_a_small_app_log_with_few_lines_pulls_the_rest_from_older_files(tmp_path: Path) -> None:
    write_log(tmp_path, "app.log.1", [f"a {i}" for i in range(60)])
    write_log(tmp_path, "app.log", ["b 0"])
    lines = log_block(build_report(inputs(tmp_path, error=None)))
    assert len(lines) == 50 and lines[0] == "a 11" and lines[-1] == "b 0"


def test_an_unreadable_file_is_skipped(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    def read(path: Path):
        if path.name == "app.log":
            raise PermissionError("locked")
        return (["from one"], True) if path.name == "app.log.1" else None

    with caplog.at_level(logging.DEBUG, logger="yttoolkit"):
        assert diagnostics._tail_lines(tmp_path, read=read) == ["from one"]
    assert any("app.log" in r.getMessage() for r in caplog.records)


def test_backticks_in_a_log_line_get_a_longer_fence(tmp_path: Path) -> None:
    write_log(tmp_path, "app.log", ["a ``` b", "c ````` d"])
    report = build_report(inputs(tmp_path, error=None))
    assert "\n``````text\na ``` b\nc ````` d\n``````\n" in report


def test_tail_holds_the_app_log_handler_lock(tmp_path: Path) -> None:
    write_log(tmp_path, "app.log", ["x"])
    handler = logging.handlers.RotatingFileHandler(tmp_path / "app.log", encoding="utf-8")
    root = logging.getLogger()
    root.addHandler(handler)
    held: list[bool] = []

    def read(path: Path):
        held.append(handler.lock._is_owned())  # type: ignore[attr-defined]  # RLock ของ Handler.createLock
        return diagnostics._read_tail(path)

    try:
        assert diagnostics._tail_lines(tmp_path, read=read) == ["x"]
    finally:
        root.removeHandler(handler)
        handler.close()
    assert held and all(held)
    assert not handler.lock._is_owned()  # type: ignore[attr-defined]


# ---------- เพดานความยาว (หลังซ่อนข้อมูล) ----------


def test_a_long_log_line_is_cut_with_an_ellipsis(tmp_path: Path) -> None:
    write_log(tmp_path, "app.log", ["y" * 1000])
    (line,) = log_block(build_report(inputs(tmp_path, error=None)))
    assert len(line) == LOG_LINE_MAX and line.endswith("…")


def test_a_long_detail_is_cut_to_the_detail_cap(tmp_path: Path) -> None:
    error = ErrorSection(code="E_UNKNOWN", detail="d" * 5000, context="crash")
    report = build_report(inputs(tmp_path, error=error))
    detail = report.split("- รายละเอียด: ", 1)[1].split("\n", 1)[0]
    assert len(detail) == DETAIL_MAX and detail.endswith("…")


def test_report_stays_under_the_cap_by_dropping_the_oldest_log_lines(tmp_path: Path) -> None:
    write_log(tmp_path, "app.log", [f"{i:02d} " + "z" * 290 for i in range(50)])
    error = ErrorSection(code="E_UNKNOWN", detail="d" * 1990, context="crash")
    report = build_report(inputs(tmp_path, error=error))
    assert len(report) <= REPORT_MAX
    lines = log_block(report)
    assert 0 < len(lines) < 50
    assert lines[-1].startswith("49 ")  # บรรทัดใหม่สุดยังอยู่ ที่ทิ้งคือบรรทัดเก่า
    assert "### log ล่าสุด (50 บรรทัด)" in report


def test_caps_apply_after_redaction_so_a_cut_never_leaks_half_a_username(tmp_path: Path, monkeypatch) -> None:
    from yttoolkit.api import errors

    monkeypatch.setattr(errors.Path, "home", lambda: PureWindowsPath("C:/Users/somchaijaidee"))
    monkeypatch.setattr(redact, "_home_aliases", lambda home: ())
    # path ยาวคร่อมจุดตัด 300: ถ้าตัดก่อนซ่อน "somchai" จะหลุดครึ่งเดียวและไม่ถูกแทน
    write_log(tmp_path, "app.log", ["p" * 290 + " C:\\Users\\somchaijaidee\\Downloads\\a.mp4"])
    error = ErrorSection(code="E_UNKNOWN", detail="q" * 1995 + " C:\\Users\\somchaijaidee\\x", context="crash")
    report = build_report(inputs(tmp_path, error=error))
    assert "somchai" not in report
    assert " ~\\Downlo" in report and " ~\\x" in report  # ซ่อนก่อนแล้วค่อยตัด: รอยตัดอยู่หลัง ~


def test_token_titles_cookie_names_and_other_drives_are_hidden(tmp_path: Path) -> None:
    title = "สูตรขนมไทยโบราณ ตอนพิเศษ"
    write_log(tmp_path, "app.log", [f"token={TOKEN} SAPISID=sEcReTcOoKiE9 {title} D:\\out\\a.mp4"])
    error = ErrorSection(code="E_DISK_FULL", detail=f"'D:\\\\out\\\\{title}.mp4'", kind="video", video_id="dQw4w9WgXcQ")
    report = build_report(inputs(tmp_path, error=error, titles=(title,)))
    for leaked in (TOKEN, "SAPISID", "sEcReTcOoKiE9", title, "D:\\out"):  # ทั้งชื่อและค่าของคุกกี้
        assert leaked not in report
    assert "videoId dQw4w9WgXcQ" in report and "E_DISK_FULL" in report


def test_the_builder_never_touches_the_network_or_yt_dlp() -> None:
    import ast

    source = Path(diagnostics.__file__).read_text(encoding="utf-8")
    imported = {
        alias.name for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Import) for alias in node.names
    } | {node.module or "" for node in ast.walk(ast.parse(source)) if isinstance(node, ast.ImportFrom)}
    assert not {"yt_dlp", "extractor", "fastapi", "httpx"} & {name.split(".")[0] for name in imported}
    assert "collect_health" not in source
