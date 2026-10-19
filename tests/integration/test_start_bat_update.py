"""ขั้น [1/4] ของ start.bat ต้องซ่อมเองได้เมื่อรอบก่อนถูกปิดหน้าต่างกลางการอัปเดต และต้องไม่ทิ้งงานที่แก้ค้างไว้ถ้าไม่มีหลักฐาน

รัน start.bat ตัวจริงใน clone ทิ้งได้ที่ชี้ไป origin แบบ bare บนเครื่อง ตั้ง YT_START_TEST_UPDATE_ONLY ให้หยุดหลังขั้นอัปเดต
สภาพ "ถูกตัดกลางทาง" จำลองด้วยมือ (index.lock + run/update-in-progress + ไฟล์ใหม่ปนเก่า) เพราะการฆ่า git ให้ตรงจังหวะช้าและไม่นิ่ง
การฆ่าจริงระหว่าง checkout 3,300 ไฟล์อยู่ในรายงาน abrupt-a-report.md
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.skipif(sys.platform != "win32", reason="รัน start.bat ด้วย cmd จริง"),
    pytest.mark.skipif(shutil.which("git") is None, reason="ต้องมี git"),
]

START_BAT = Path(__file__).resolve().parents[2] / "start.bat"
REPAIR_LINE = "อัปเดตครั้งก่อนค้างกลางทาง กำลังซ่อม..."
SKIP_LINE = "ข้ามการอัปเดต ใช้เวอร์ชันเดิม"
GIT_ENV = {
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_CONFIG_NOSYSTEM": "1",
}


def _git(cwd: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(
        ["git", *args], cwd=cwd, env={**os.environ, **GIT_ENV}, capture_output=True, encoding="utf-8", timeout=60
    )
    if check:
        assert r.returncode == 0, f"git {args}: {r.stderr}"
    return r.stdout.strip()


def _files(ver: str) -> dict[str, str]:
    files = {f"src/f{i}.txt": f"{ver} {i}\n" for i in range(20)}
    if ver == "v2":
        del files["src/f0.txt"]  # v2 ลบไฟล์นี้
        files.update({f"new/n{i}.txt": f"new {i}\n" for i in range(5)})  # v2 เพิ่มไฟล์ใหม่
    return files


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


class Repo:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.origin = tmp_path / "origin.git"
        _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(self.origin))
        pub = tmp_path / "pub"
        _git(tmp_path, "clone", "-q", str(self.origin), str(pub))
        (pub / ".gitattributes").write_text("*.bat text eol=crlf\n", encoding="utf-8")
        (pub / ".gitignore").write_text("run/\n", encoding="utf-8")
        shutil.copyfile(START_BAT, pub / "start.bat")
        _write(pub, _files("v1"))
        _git(pub, "add", "-A")
        _git(pub, "commit", "-q", "-m", "v1")
        _git(pub, "push", "-q", "-u", "origin", "main")
        self.v1 = _git(pub, "rev-parse", "HEAD")
        shutil.rmtree(pub / "src")
        _write(pub, _files("v2"))
        _git(pub, "add", "-A")
        _git(pub, "commit", "-q", "-m", "v2")
        _git(pub, "push", "-q", "origin", "main")
        self.v2 = _git(pub, "rev-parse", "HEAD")
        # เครื่องพนักงานยังอยู่ที่ v1 และรู้จัก origin/main ที่ v1
        self.clone = tmp_path / "YT-Toolkit"
        _git(tmp_path, "clone", "-q", str(self.origin), str(self.clone))
        _git(self.clone, "reset", "-q", "--hard", self.v1)
        _git(self.clone, "update-ref", "refs/remotes/origin/main", self.v1)

    @property
    def marker(self) -> Path:
        return self.clone / "run" / "update-in-progress"

    @property
    def index_lock(self) -> Path:
        return self.clone / ".git" / "index.lock"

    def head(self) -> str:
        return _git(self.clone, "rev-parse", "HEAD")

    def status(self, *extra: str) -> str:
        return _git(self.clone, "status", "--porcelain", *extra)

    def interrupted(self, phase: str, root: Path | None = None, lock: Path | None = None) -> None:
        """สภาพหลังปิดหน้าต่างตอน git merge เขียนไฟล์ไปได้ครึ่งทาง: lock ค้าง HEAD ยังเก่า ไฟล์ปนกัน"""
        root = root or self.clone
        if phase.startswith("merge"):  # ขั้น merge เริ่มหลัง fetch จบ origin/main จึงชี้ v2 แล้ว
            _git(self.clone, "update-ref", "refs/remotes/origin/main", self.v2)
        v2 = _files("v2")
        _write(root, {k: v2[k] for k in ("src/f1.txt", "src/f2.txt", "new/n0.txt", "new/n1.txt")})
        (root / "src" / "f0.txt").unlink()
        (lock or self.index_lock).write_bytes(b"")
        marker = root / "run" / "update-in-progress"
        marker.parent.mkdir(exist_ok=True)
        marker.write_text(f"{phase}\n", encoding="ascii")

    def capture_phase(self) -> Path:
        """hook post-merge จดว่า start.bat เขียนอะไรลงไฟล์ marker ไว้ตอนเริ่ม merge"""
        seen = self.clone / "run" / "phase-seen"
        hook = self.clone / ".git" / "hooks" / "post-merge"
        hook.write_text("#!/bin/sh\ncp run/update-in-progress run/phase-seen\n", encoding="ascii", newline="\n")
        return seen

    def run(self, root: Path | None = None) -> tuple[int, str]:
        tmp = self.tmp / "temp"
        tmp.mkdir(exist_ok=True)
        env = {**os.environ, **GIT_ENV, "YT_START_TEST_UPDATE_ONLY": "1", "TEMP": str(tmp), "TMP": str(tmp)}
        env.pop("YT_START_RELAUNCHED", None)
        r = subprocess.run(
            ["cmd", "/d", "/c", str((root or self.clone) / "start.bat")],
            cwd=self.tmp,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=120,
        )
        # ส่วนใหญ่ cmd เขียนลง pipe เป็น UTF-8 ตาม chcp 65001 แต่บางสภาพแวดล้อมใช้ code page ANSI ของเครื่องแทน
        raw = r.stdout + r.stderr
        try:
            return r.returncode, raw.decode("utf-8")
        except UnicodeDecodeError:
            return r.returncode, raw.decode("mbcs", "replace")


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    return Repo(tmp_path)


def test_normal_update_fast_forwards_and_leaves_no_marker(repo: Repo) -> None:
    seen = repo.capture_phase()
    rc, out = repo.run()
    assert rc == 0, out
    assert repo.head() == repo.v2
    assert repo.status() == ""
    assert not repo.marker.exists()
    assert SKIP_LINE not in out and REPAIR_LINE not in out
    assert seen.read_text(encoding="ascii").strip() == "merge"


def test_tracked_edit_marks_merge_dirty_and_survives_update(repo: Repo) -> None:
    seen = repo.capture_phase()
    gitignore = repo.clone / ".gitignore"
    gitignore.write_text("run/\n# แก้ค้างไว้\n", encoding="utf-8")  # ไฟล์ที่ v2 ไม่แตะ
    rc, out = repo.run()
    assert rc == 0, out
    assert seen.read_text(encoding="ascii").strip() == "merge-dirty"
    assert repo.head() == repo.v2
    assert gitignore.read_text(encoding="utf-8") == "run/\n# แก้ค้างไว้\n"
    assert not repo.marker.exists()


def test_cut_during_merge_dirty_clears_locks_but_keeps_edits(repo: Repo) -> None:
    # เครื่องนักพัฒนา: แก้ไฟล์ค้างไว้ตั้งแต่ก่อนอัปเดต (.gitignore) และหลังถูกตัด (src/f3.txt ซึ่ง v2 แก้ด้วย)
    edits = {".gitignore": "run/\n# แก้ค้างไว้\n", "src/f3.txt": "งานที่ยังไม่ commit\n"}
    _write(repo.clone, edits)
    repo.interrupted("merge-dirty")
    ref_lock = repo.clone / ".git" / "refs" / "heads" / "main.lock"
    ref_lock.write_bytes(b"")
    rc, out = repo.run()
    assert rc == 0, out
    assert REPAIR_LINE in out
    for rel, text in edits.items():
        assert (repo.clone / rel).read_text(encoding="utf-8") == text
    # ไม่ reset จึงยังปนกันอยู่ และ merge ไม่ยอมเขียนทับงานที่แก้ จึงข้ามการอัปเดตเหมือนก่อนแก้
    assert repo.head() == repo.v1
    assert SKIP_LINE in out
    assert not repo.index_lock.exists() and not ref_lock.exists()
    assert not repo.marker.exists()


def test_failed_reset_keeps_marker_and_retries_next_start(repo: Repo) -> None:
    repo.interrupted("merge")
    # โปรแกรมอื่นเปิดไฟล์ที่ v2 แก้ค้างไว้ git จึงเขียนทับไม่ได้ และ reset ล้มเหลว
    with open(repo.clone / "src" / "f3.txt", "rb"):
        rc, out = repo.run()
    assert rc == 0, out
    assert REPAIR_LINE in out and SKIP_LINE in out
    assert repo.head() == repo.v1
    assert repo.marker.read_text(encoding="ascii").strip() == "merge"
    # ปิดไฟล์แล้ว รอบถัดไปซ่อมต่อจนจบ
    rc, out = repo.run()
    assert REPAIR_LINE in out and SKIP_LINE not in out
    assert repo.head() == repo.v2
    assert repo.status() == ""
    assert not repo.marker.exists()


def test_linked_worktree_cut_during_merge_is_repaired(repo: Repo) -> None:
    # ใน worktree ที่แยกออกมา .git เป็นไฟล์ และ index.lock อยู่ใต้ .git/worktrees/<ชื่อ> ของ clone หลัก
    wt = repo.tmp / "wt"
    _git(repo.clone, "worktree", "add", "-q", "--track", "-b", "staff", str(wt), "origin/main")
    gitdir = Path(_git(wt, "rev-parse", "--absolute-git-dir"))
    assert (wt / ".git").is_file()
    repo.interrupted("merge", root=wt, lock=gitdir / "index.lock")
    ref_lock = repo.clone / ".git" / "refs" / "heads" / "staff.lock"
    ref_lock.write_bytes(b"")
    rc, out = repo.run(wt)
    assert rc == 0, out
    assert REPAIR_LINE in out and SKIP_LINE not in out
    assert _git(wt, "rev-parse", "HEAD") == repo.v2
    assert _git(wt, "status", "--porcelain") == ""
    assert not (gitdir / "index.lock").exists() and not ref_lock.exists()
    assert not (wt / "run" / "update-in-progress").exists()


def test_cut_during_merge_is_repaired_and_updated(repo: Repo) -> None:
    repo.interrupted("merge")
    rc, out = repo.run()
    assert rc == 0, out
    assert REPAIR_LINE in out
    assert SKIP_LINE not in out
    assert repo.head() == repo.v2
    assert repo.status() == ""  # รวมไฟล์ใหม่ที่รอบก่อนเขียนค้างไว้ด้วย
    assert not repo.index_lock.exists()
    assert not repo.marker.exists()
    # รอบถัดไปเป็นการเปิดปกติ ไม่ซ่อมซ้ำ
    rc, out = repo.run()
    assert REPAIR_LINE not in out and SKIP_LINE not in out


def test_cut_during_merge_while_offline_finishes_from_fetched_copy(repo: Repo) -> None:
    repo.interrupted("merge")
    _git(repo.clone, "remote", "set-url", "origin", str(repo.tmp / "missing.git"))
    rc, out = repo.run()
    assert rc == 0, out
    assert REPAIR_LINE in out
    assert SKIP_LINE not in out  # ไม่ต้องใช้เน็ต เพราะรอบก่อนโหลด v2 มาครบแล้ว
    assert repo.head() == repo.v2
    assert repo.status() == ""
    assert not repo.index_lock.exists()
    assert not repo.marker.exists()
    # เปิดรอบถัดไปตอนยังไม่มีเน็ต: ข้ามการอัปเดตตามปกติ ไม่ซ่อมซ้ำ
    rc, out = repo.run()
    assert SKIP_LINE in out and REPAIR_LINE not in out
    assert repo.head() == repo.v2
    assert repo.status() == ""


def test_cut_during_merge_without_fast_forward_restores_old_version(repo: Repo) -> None:
    repo.interrupted("merge")
    # origin/main ไม่ใช่ลูกหลานของ HEAD (เช่นมีคน force-push) จึงห้ามเดินหน้า ให้กลับไป v1 ครบชุด
    side = _git(repo.clone, "commit-tree", "-m", "side", f"{repo.v2}^{{tree}}")
    _git(repo.clone, "update-ref", "refs/remotes/origin/main", side)
    _git(repo.clone, "remote", "set-url", "origin", str(repo.tmp / "missing.git"))
    rc, out = repo.run()
    assert rc == 0, out
    assert REPAIR_LINE in out and SKIP_LINE in out
    assert repo.head() == repo.v1
    assert repo.status("--untracked-files=no") == ""  # ไฟล์ของ v1 ครบชุด ไม่ปนกัน
    assert not repo.index_lock.exists()
    assert not repo.marker.exists()


def test_cut_during_fetch_clears_lock_but_keeps_edits(repo: Repo) -> None:
    gitignore = repo.clone / ".gitignore"
    gitignore.write_text("run/\n# แก้ค้างไว้\n", encoding="utf-8")  # ไฟล์ที่ v2 ไม่แตะ
    repo.index_lock.write_bytes(b"")
    repo.marker.parent.mkdir(exist_ok=True)
    repo.marker.write_text("fetch\n", encoding="ascii")
    rc, out = repo.run()
    assert rc == 0, out
    assert REPAIR_LINE in out
    assert repo.head() == repo.v2
    assert gitignore.read_text(encoding="utf-8") == "run/\n# แก้ค้างไว้\n"
    assert not repo.index_lock.exists()
    assert not repo.marker.exists()


def test_no_marker_never_touches_edits_or_lock(repo: Repo) -> None:
    edited = repo.clone / "src" / "f1.txt"  # ไฟล์ที่ v2 แก้ จึง merge ไม่ได้
    edited.write_text("งานที่ยังไม่ commit\n", encoding="utf-8")
    repo.index_lock.write_bytes(b"")
    rc, out = repo.run()
    assert rc == 0, out
    assert SKIP_LINE in out and REPAIR_LINE not in out
    assert repo.head() == repo.v1
    assert edited.read_text(encoding="utf-8") == "งานที่ยังไม่ commit\n"
    assert repo.index_lock.exists()
    # ไม่มี lock แล้วก็ยังเหมือนเดิม: ข้ามการอัปเดต แต่ไม่ทิ้งงานที่แก้
    repo.index_lock.unlink()
    rc, out = repo.run()
    assert SKIP_LINE in out and REPAIR_LINE not in out
    assert repo.head() == repo.v1
    assert edited.read_text(encoding="utf-8") == "งานที่ยังไม่ commit\n"
    assert not repo.marker.exists()


def test_update_lock_held_by_another_run_skips_without_repair(repo: Repo) -> None:
    repo.interrupted("merge")
    before = repo.status()
    # อีกหน้าต่างของ start.bat (หรือ git ที่มันเปิด) ยังถือ run/update.lock อยู่
    with open(repo.clone / "run" / "update.lock", "ab"):
        rc, out = repo.run()
    assert rc == 0, out
    assert SKIP_LINE in out and REPAIR_LINE not in out
    assert "cannot access" not in out
    assert repo.head() == repo.v1
    assert repo.status() == before
    assert repo.index_lock.exists() and repo.marker.exists()
    # พออีกฝั่งปล่อย lock รอบถัดไปก็ซ่อมได้ตามปกติ
    rc, out = repo.run()
    assert REPAIR_LINE in out
    assert repo.head() == repo.v2
    assert repo.status() == ""
