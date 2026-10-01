from datetime import UTC, datetime
from pathlib import Path

import pytest

from yttoolkit.core import files
from yttoolkit.core.yterrors import YtError

ID = "dQw4w9WgXcQ"


def test_ac_out_01_forbidden_characters(tmp_path):
    p = files.plan_output(tmp_path, 'ทดสอบ: "A/B" <ภาค 1>?', ID, "", "mp4")
    assert p.parent.name == f"ทดสอบ AB ภาค 1 [{ID}]"
    assert p.name == "ทดสอบ AB ภาค 1.mp4"
    assert not set('\\/:*?"<>|') & set(p.parent.name + p.name)


def test_ac_out_02_long_title_fits_240(tmp_path):
    p = files.plan_output(tmp_path, "ก" * 300, ID, " (ไม่มีเสียง)", "mp4")
    assert len(str(p)) + files.UNIQUE_RESERVE <= files.PATH_LIMIT
    assert p.name.endswith(" (ไม่มีเสียง).mp4") and p.parent.name.endswith(f" [{ID}]")


def test_folder_is_shared_by_every_kind(tmp_path):
    title = "ก" * 300
    names = {
        files.plan_output(tmp_path, title, ID, s, e).parent.name
        for s, e in [("", "mp4"), (".th", "srt"), (" - contact sheet", "jpg"), ("", "wav")]
    }
    assert len(names) == 1


def test_truncation_never_splits_thai_marks():
    assert files.truncate_title("กี่", 1) == ""  # "ก" + mark: cut before the base, not between
    assert files.truncate_title("ทดสอบที่", 6) == "ทดสอบ"


def test_truncate_keeps_short_text_and_strips_tail():
    assert files.truncate_title("abc", 10) == "abc"
    assert files.truncate_title("ab. cd", 3) == "ab"


def test_reserved_and_trailing(tmp_path):
    assert files.safe_component("CON", ID) == "_CON"
    assert files.safe_component("  ชื่อ...  ", ID) == "ชื่อ"
    assert files.safe_component("‮\x00", ID) == ID


def test_safe_component_reserved_with_extension_and_whitespace():
    assert files.safe_component("lpt1.txt", ID) == "_lpt1.txt"
    assert files.safe_component("a\t\n  b", ID) == "a b"
    assert files.safe_component("CONSOLE", ID) == "CONSOLE"


def test_short_title_keeps_its_name(tmp_path):
    p = files.plan_output(tmp_path, "Hi", ID, "", "mp4")
    assert p.parent.name == f"Hi [{ID}]" and p.name == "Hi.mp4"


def test_ac_out_03_unique_suffix(tmp_path):
    first = tmp_path / "a.mp4"
    first.write_bytes(b"1")
    (tmp_path / "a (2).mp4").write_bytes(b"2")
    assert files.unique_path(first).name == "a (3).mp4"


def test_unique_path_free_name_unchanged(tmp_path):
    assert files.unique_path(tmp_path / "a.mp4") == tmp_path / "a.mp4"


def test_unique_path_exhausted(tmp_path):
    first = tmp_path / "a.mp4"
    first.write_bytes(b"1")
    for n in range(2, 100):
        (tmp_path / f"a ({n}).mp4").write_bytes(b"x")
    with pytest.raises(YtError) as err:
        files.unique_path(first)
    assert err.value.code == "E_OUTPUT_NOT_WRITABLE"


def test_root_too_long_falls_back_to_id(tmp_path):
    deep = tmp_path / ("x" * max(1, 190 - len(str(tmp_path))))  # root of about 190 characters
    p = files.plan_output(deep, "ชื่อคลิปยาวพอสมควร", ID, "", "mp4")
    assert p.parent.name == ID and p.name == f"{ID}.mp4"


def test_root_far_too_long_is_not_writable(tmp_path):
    deep = tmp_path / ("x" * max(1, 232 - len(str(tmp_path))))
    with pytest.raises(YtError) as err:
        files.plan_output(deep, "ชื่อ", ID, "", "mp4")
    assert err.value.code == "E_OUTPUT_NOT_WRITABLE"


def test_ac_out_06_source_note_bytes(tmp_path):
    info = files.SourceInfo("คลิป", "ช่อง", ID, "2026-09-01", None)
    path = files.write_source_note(tmp_path, info, datetime(2026, 10, 5, 7, 32, tzinfo=UTC))
    data = path.read_bytes()
    assert not data.startswith(b"\xef\xbb\xbf") and b"\r\n" in data and b"\n" not in data.replace(b"\r\n", b"")
    text = data.decode("utf-8")
    assert "ลิงก์: https://www.youtube.com/watch?v=dQw4w9WgXcQ\r\n" in text
    assert "วันที่โหลด: 2026-10-05 14:32 (+07:00)\r\n" in text
    assert "สัญญาอนุญาต: ไม่ระบุ\r\n" in text  # AC-OUT-07 (no license)
    assert "ที่มา: คลิป — ช่อง (YouTube) https://youtu.be/dQw4w9WgXcQ\r\n" in text
    assert "วันที่เผยแพร่: 2026-09-01\r\n" in text
    assert text.endswith("ไม่ได้แปลว่าได้รับอนุญาตให้ใช้เนื้อหา\r\n")
    assert path.name == files.SOURCE_NOTE_NAME


def test_source_note_unknown_published_and_multiline_title():
    info = files.SourceInfo("บรรทัด\nสอง", "ช่อง", ID, None, None)
    text = files.source_note_text(info, datetime(2026, 10, 5, tzinfo=UTC))
    assert "วันที่เผยแพร่: ไม่ระบุ\r\n" in text
    assert "ชื่อคลิป: บรรทัด สอง\r\n" in text


def test_ac_out_06_second_job_updates_one_file(tmp_path):
    lic = "Creative Commons Attribution license (reuse allowed)"
    files.write_source_note(tmp_path, files.SourceInfo("ค", "ช", ID, None, lic), datetime(2026, 10, 1, tzinfo=UTC))
    files.write_source_note(tmp_path, files.SourceInfo("ค", "ช", ID, None, lic), datetime(2026, 10, 2, tzinfo=UTC))
    notes = list(tmp_path.glob("แหล่งที่มา*.txt"))
    assert len(notes) == 1 and "2026-10-02" in notes[0].read_text("utf-8") and lic in notes[0].read_text("utf-8")
    assert list(tmp_path.iterdir()) == notes  # no temp file left behind


def test_move_into_place_creates_folder_and_uniquifies(tmp_path):
    src = tmp_path / "w" / "final.mp4"
    src.parent.mkdir()
    src.write_bytes(b"x")
    planned = tmp_path / "out" / "a [id]" / "a.mp4"
    planned.parent.mkdir(parents=True)
    planned.write_bytes(b"old")
    assert files.move_into_place(src, planned).name == "a (2).mp4"


def test_move_into_place_makes_missing_folder(tmp_path):
    src = tmp_path / "final.mp4"
    src.write_bytes(b"x")
    final = files.move_into_place(src, tmp_path / "out" / "b [id]" / "b.mp4")
    assert final.read_bytes() == b"x" and not src.exists()


def test_ensure_output_root(tmp_path):
    root = tmp_path / "new" / "root"
    files.ensure_output_root(root)
    assert root.is_dir() and list(root.iterdir()) == []


def test_ensure_output_root_not_writable(tmp_path):
    blocker = tmp_path / "file.txt"
    blocker.write_text("x")
    with pytest.raises(YtError) as err:
        files.ensure_output_root(blocker / "sub")
    assert err.value.code == "E_OUTPUT_NOT_WRITABLE"


def test_credit_line():
    assert files.credit_line("ก", "ข", ID) == f"ที่มา: ก — ข (YouTube) https://youtu.be/{ID}"


def test_plan_output_returns_path_under_root(tmp_path):
    assert isinstance(files.plan_output(tmp_path, "x", ID, "", "mp4"), Path)
