"""กฎของโปรเจกต์: ห้าม shell=True และห้าม os.system / os.popen ในโค้ดของแอพ"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "yttoolkit"


def _violations(source: str, name: str) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg == "shell" and not (isinstance(kw.value, ast.Constant) and kw.value.value is False):
                found.append(f"{name}:{node.lineno} shell ที่ไม่ใช่ False")
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "os"
            and func.attr in {"system", "popen"}
        ):
            found.append(f"{name}:{node.lineno} os.{func.attr}")
    return found


def test_no_shell_true_and_no_os_system_in_src() -> None:
    files = sorted(SRC.rglob("*.py"))
    assert files, "ไม่พบไฟล์ใน src/yttoolkit"
    found: list[str] = []
    for path in files:
        found += _violations(path.read_text(encoding="utf-8"), str(path.relative_to(SRC)))
    assert found == []


def test_checker_catches_violations() -> None:
    assert _violations("import subprocess\nsubprocess.run('x', shell=True)", "a.py")
    assert _violations("import subprocess\nsubprocess.run(['x'], shell=flag)", "a.py")
    assert _violations("import os\nos.system('x')", "a.py")
    assert _violations("import os\nos.popen('x')", "a.py")
    assert _violations("import subprocess\nsubprocess.run(['x'], shell=False)", "a.py") == []
