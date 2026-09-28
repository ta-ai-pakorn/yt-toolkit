# M1 โครงพื้นฐาน (YT Toolkit) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ได้แอพที่ติดตั้งด้วย `git clone` + ดับเบิลคลิก `start.bat` แล้วเปิดเว็บที่ `127.0.0.1` ได้ มีไอคอน tray, ปิดได้ 3 ทาง, มี middleware ความปลอดภัย, หน้าตรวจสุขภาพระบบที่ใช้งานได้จริง และ CI บน Windows + macOS

**Architecture:** Python package `yttoolkit` (src layout, จัดการด้วย uv) รัน FastAPI + uvicorn ใน thread แยก ส่วน main thread เป็นไอคอน tray (pystray) ข้อมูลสถานะการรันเก็บใน `run/app.json` โค้ดที่ผูกกับระบบปฏิบัติการอยู่ใน `yttoolkit/platform/` ที่เดียว หน้าเว็บเป็น React + Vite + shadcn (Base UI) build ออกมาเป็น `web/dist` แล้ว FastAPI เสิร์ฟพร้อมฝัง token ลงใน `index.html`

**Tech Stack:** Python 3.13, uv, FastAPI, uvicorn, httpx, pystray, Pillow, yt-dlp[default], deno (PyPI) · React 19, Vite 8, TypeScript, Tailwind 4, shadcn CLI v4 (Base UI, preset nova), React Router, TanStack Query, Vitest, Playwright · GitHub Actions

## Global Constraints

อ้างอิงจาก [BRD.md](../../../BRD.md) และ [PRD.md](../../../PRD.md) ทุก task ต้องทำตามข้อเหล่านี้เสมอ

- Python `3.13` (ระบุใน `.python-version`) จัดการด้วย `uv` เท่านั้น
- เซิร์ฟเวอร์ผูกกับ `127.0.0.1` เท่านั้น ห้าม `0.0.0.0` (NFR-SEC-1)
- Port เริ่มที่ `8787` ถ้าไม่ว่างลอง `8788`-`8797` (PRD ข้อ 13 / AC-LIFE-06)
- `Host` ต้องเป็น `127.0.0.1:<port>` หรือ `localhost:<port>` ไม่งั้นตอบ `421` (AC-SEC-02)
- POST/PUT/PATCH/DELETE ต้องมี header `X-Toolkit-Token` ตรง และ `Origin` ตรง ไม่งั้นตอบ `403` (AC-SEC-03)
- รูปแบบ error ของ API: `{"error": {"code": "E_...", "message": "<ภาษาไทย>", "detail": "<เทคนิค>|null"}}`
- เรียกโปรแกรมภายนอกด้วย argument เป็นลิสต์เสมอ ห้าม `shell=True` (NFR-SEC-4)
- ใช้ `pathlib` จัดการ path ทุกที่ (BRD ข้อ 6.4)
- โมดูลอื่นห้ามเช็คระบบปฏิบัติการเอง ให้เรียกผ่าน `yttoolkit.platform` เท่านั้น
- ข้อความที่ผู้ใช้เห็นเป็นภาษาไทย ปุ่มขึ้นต้นด้วยคำกริยา ไม่มีคำว่า "กรุณา" ไม่มีเครื่องหมายตกใจ (BRD ข้อ 10.9)
- ข้อความในหน้าเว็บอยู่ใน `web/src/i18n/th.ts` ไฟล์เดียว
- ธีม Studio Dark ตามตารางสีใน BRD ข้อ 10.2 · ฟอนต์ IBM Plex Sans Thai + IBM Plex Mono (self-host) · ระยะบรรทัดเนื้อหาไทย ≥ 1.6
- ปุ่มหลัก (สีอำพัน) มีได้ปุ่มเดียวต่อหน้า
- ffmpeg บน Windows โหลดจาก `https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip` และต้องตรวจ SHA-256 กับ `checksums.sha256` ในรีลีสเดียวกัน
- ห้ามใช้ Magic UI, Aceternity, Animate UI
- ทุก commit ลงท้ายด้วย `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
- โฟลเดอร์ที่ git ไม่ติดตาม: `.venv/`, `data/`, `work/`, `run/`, `bin/`, `web/node_modules/` · **`web/dist/` ต้อง commit**

### Environment variables ที่แอพรู้จัก
| ตัวแปร | ค่าเริ่มต้น | ผล |
|---|---|---|
| `YT_TOOLKIT_DATA_ROOT` | โฟลเดอร์ repo | ที่เก็บ `data/ work/ run/ bin/` (ใช้ในเทส) |
| `YT_TOOLKIT_FFMPEG_PATH_LOOKUP` | `1` | `0` = ไม่หา ffmpeg ใน PATH (AC-SET-02) |
| `YT_TOOLKIT_TRAY` | `1` | `0` = ไม่สร้างไอคอน tray |
| `YT_TOOLKIT_OPEN_BROWSER` | `1` | `0` = ไม่เปิดเบราว์เซอร์ตอน start |

---

## โครงสร้างไฟล์ของ M1

```
yt-dl/                               (repo: ta-ai-pakorn/yt-toolkit, private)
├─ .gitignore  .gitattributes  .python-version  pyproject.toml  uv.lock
├─ start.bat  stop.bat  README.md  BRD.md  PRD.md
├─ docs/acceptance.md                 checklist ตรวจมือของ M1
├─ docs/superpowers/plans/…           แผนนี้
├─ .github/workflows/ci.yml
├─ src/yttoolkit/
│  ├─ __init__.py                     __version__
│  ├─ __main__.py                     CLI: start | stop | serve
│  ├─ config.py                       Paths, ค่าคงที่, env_flag
│  ├─ runstate.py                     run/app.json, token, เลือก port
│  ├─ lifecycle.py                    start / stop / serve / Server
│  ├─ tray.py                         ไอคอน tray + เมนู
│  ├─ app.py                          AppContext + create_app
│  ├─ api/{__init__,errors,security,static,routes}.py
│  ├─ core/{__init__,tools}.py        ffmpeg, JS runtime, yt-dlp, disk, output, network, health
│  └─ platform/{__init__,base,windows,macos}.py
├─ tests/
│  ├─ conftest.py                     FakePlatform + fixture paths
│  ├─ unit/ test_config.py test_runstate.py test_platform.py test_tools_status.py test_tools_install.py test_tray.py test_lifecycle.py
│  ├─ api/  conftest.py test_security.py test_static.py test_routes.py
│  └─ integration/ test_serve.py
└─ web/                               สร้างด้วย shadcn init
   ├─ index.html  vite.config.ts  playwright.config.ts  package.json  components.json
   ├─ public/favicon.svg
   ├─ e2e/health.spec.ts  e2e/home.spec.ts
   ├─ src/index.css  src/main.tsx  src/App.tsx(ลบ)  src/router.tsx
   ├─ src/i18n/th.ts
   ├─ src/lib/{api.ts,api.test.ts,types.ts,platform.ts}
   ├─ src/components/{layout.tsx,theme-provider.tsx(มีอยู่แล้ว),ui/*}
   ├─ src/pages/{home.tsx,settings.tsx,shutdown.tsx}
   ├─ src/pages/settings/{health-panel.tsx,about-panel.tsx}
   └─ dist/                           build แล้ว commit
```

---

### Task 1: ตั้งต้น repo + โปรเจกต์ Python

**Files:**
- Create: `.gitignore`, `.gitattributes`, `pyproject.toml` (ผ่าน uv), `.python-version`, `src/yttoolkit/__init__.py`, `tests/conftest.py`, `tests/unit/test_smoke.py`

**Interfaces:**
- Produces: package `yttoolkit` ติดตั้งแบบ editable ใน `.venv` · `yttoolkit.__version__: str` · fixture `paths` (ชนิด `Paths` จาก Task 2 — ใน Task นี้ยังไม่ใช้) · class `FakePlatform` ใน `tests/conftest.py`

- [ ] **Step 1: เริ่ม git และสร้างโปรเจกต์ uv**

รันที่ `C:\Users\khumj\yt-dl` (มี `BRD.md` `PRD.md` `docs/` อยู่แล้ว)

```bash
git init -b main
uv init --package --name yttoolkit --python 3.13 --vcs none --no-readme .
uv add fastapi "uvicorn[standard]" httpx "yt-dlp[default]" deno pystray pillow
uv add --dev pytest
```
Expected: มี `pyproject.toml`, `uv.lock`, `.python-version` (ค่า `3.13`), `src/yttoolkit/__init__.py`

- [ ] **Step 2: แก้ `pyproject.toml`**

แก้ส่วน `[project.scripts]` และเพิ่ม pytest config (ส่วนอื่นที่ uv สร้างไว้คงไว้)

```toml
[project.scripts]
yttoolkit = "yttoolkit.__main__:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["network: ต้องต่อเน็ตจริง (รันเอง ไม่รันใน CI)"]
addopts = "-m 'not network'"
```

- [ ] **Step 3: เขียน `src/yttoolkit/__init__.py`**

```python
"""YT Toolkit: เครื่องมือจัดการสื่อจากยูทูปที่รันบนเครื่องผู้ใช้"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("yttoolkit")
except PackageNotFoundError:  # รันจาก source ที่ยังไม่ติดตั้ง
    __version__ = "0.0.0"
```

- [ ] **Step 4: เขียน `.gitignore` และ `.gitattributes`**

`.gitignore`
```gitignore
.venv/
__pycache__/
*.pyc
.pytest_cache/
data/
work/
run/
bin/
web/node_modules/
web/test-results/
web/playwright-report/
```

`.gitattributes`
```gitattributes
* text=auto eol=lf
*.bat text eol=crlf
*.png binary
*.jpg binary
*.woff binary
*.woff2 binary
*.ico binary
```

- [ ] **Step 5: เขียน `tests/conftest.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest


@dataclass
class FakePlatform:
    """แทน yttoolkit.platform ในเทส บันทึกทุกการเรียกไว้ให้ตรวจ"""

    name: str = "windows"
    ffmpeg_exe: str = "ffmpeg.exe"
    ffprobe_exe: str = "ffprobe.exe"
    downloads: Path = Path("Downloads")
    alive: set[int] = field(default_factory=set)
    killed: list[int] = field(default_factory=list)
    opened: list[Path] = field(default_factory=list)
    revealed: list[Path] = field(default_factory=list)

    def downloads_dir(self) -> Path:
        return self.downloads

    def open_folder(self, path: Path) -> None:
        self.opened.append(path)

    def reveal(self, path: Path) -> None:
        self.revealed.append(path)

    def pid_alive(self, pid: int) -> bool:
        return pid in self.alive

    def kill(self, pid: int) -> None:
        self.killed.append(pid)
        self.alive.discard(pid)


@pytest.fixture
def fake_platform(tmp_path: Path) -> FakePlatform:
    return FakePlatform(downloads=tmp_path / "Downloads")
```

- [ ] **Step 6: เขียนเทส smoke** (ยืนยันว่า package ติดตั้งแบบ editable และอ่านเวอร์ชันได้ `uv init` ตั้ง `version = "0.1.0"` ไว้แล้ว)

`tests/unit/test_smoke.py`
```python
import yttoolkit


def test_version_is_set():
    assert yttoolkit.__version__ == "0.1.0"
```

- [ ] **Step 7: รันเทสให้ผ่าน**

Run: `uv run pytest -v`
Expected: `1 passed`

- [ ] **Step 8: Commit และสร้าง repo private บน GitHub**

```bash
git add .gitignore .gitattributes .python-version pyproject.toml uv.lock src tests BRD.md PRD.md docs
git commit -m "chore: bootstrap yttoolkit python project

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
gh repo create yt-toolkit --private --source . --remote origin --push
```
Expected: `https://github.com/ta-ai-pakorn/yt-toolkit` ถูกสร้างเป็น private และมี commit แรก

---

### Task 2: `config.py` (ตำแหน่งไฟล์และค่าคงที่)

**Files:**
- Create: `src/yttoolkit/config.py`
- Test: `tests/unit/test_config.py`
- Modify: `tests/conftest.py` (เพิ่ม fixture `paths`)

**Interfaces:**
- Produces:
  - `APP_NAME: str = "YT Toolkit"`, `HOST: str = "127.0.0.1"`, `PORT_RANGE: range = range(8787, 8798)`, `CODE_ROOT: Path`
  - `@dataclass(frozen=True) class Paths(data_root: Path, code_root: Path = CODE_ROOT)` มี property `data, work, run, logs, bin, app_json, web_dist` และเมธอด `ensure() -> None`
  - `default_paths() -> Paths`
  - `env_flag(name: str, default: bool) -> bool`

- [ ] **Step 1: เขียนเทสที่ fail**

`tests/unit/test_config.py`
```python
from pathlib import Path

from yttoolkit.config import CODE_ROOT, HOST, PORT_RANGE, Paths, default_paths, env_flag


def test_constants():
    assert HOST == "127.0.0.1"
    assert PORT_RANGE[0] == 8787
    assert PORT_RANGE[-1] == 8797
    assert (CODE_ROOT / "pyproject.toml").is_file()


def test_paths_layout(tmp_path: Path):
    p = Paths(data_root=tmp_path)
    assert p.data == tmp_path / "data"
    assert p.work == tmp_path / "work"
    assert p.run == tmp_path / "run"
    assert p.logs == tmp_path / "run" / "logs"
    assert p.bin == tmp_path / "bin"
    assert p.app_json == tmp_path / "run" / "app.json"
    assert p.web_dist == CODE_ROOT / "web" / "dist"


def test_ensure_creates_dirs(tmp_path: Path):
    p = Paths(data_root=tmp_path)
    p.ensure()
    for d in (p.data, p.work, p.run, p.logs, p.bin):
        assert d.is_dir()


def test_default_paths_uses_code_root(monkeypatch):
    monkeypatch.delenv("YT_TOOLKIT_DATA_ROOT", raising=False)
    assert default_paths().data_root == CODE_ROOT


def test_default_paths_env_override(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("YT_TOOLKIT_DATA_ROOT", str(tmp_path))
    assert default_paths().data_root == tmp_path


def test_env_flag(monkeypatch):
    monkeypatch.delenv("X_FLAG", raising=False)
    assert env_flag("X_FLAG", True) is True
    assert env_flag("X_FLAG", False) is False
    for off in ("0", "false", "No", "off", ""):
        monkeypatch.setenv("X_FLAG", off)
        assert env_flag("X_FLAG", True) is False
    monkeypatch.setenv("X_FLAG", "1")
    assert env_flag("X_FLAG", False) is True
```

- [ ] **Step 2: รันให้เห็นว่า fail**

Run: `uv run pytest tests/unit/test_config.py -v`
Expected: FAIL `ModuleNotFoundError: No module named 'yttoolkit.config'`

- [ ] **Step 3: เขียน `src/yttoolkit/config.py`**

```python
"""ค่าคงที่และตำแหน่งไฟล์ของแอพ"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "YT Toolkit"
HOST = "127.0.0.1"
PORT_RANGE = range(8787, 8798)
CODE_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Paths:
    """data_root เก็บของที่เปลี่ยนตามการใช้งาน ส่วน code_root คือโฟลเดอร์ repo"""

    data_root: Path
    code_root: Path = CODE_ROOT

    @property
    def data(self) -> Path:
        return self.data_root / "data"

    @property
    def work(self) -> Path:
        return self.data_root / "work"

    @property
    def run(self) -> Path:
        return self.data_root / "run"

    @property
    def logs(self) -> Path:
        return self.run / "logs"

    @property
    def bin(self) -> Path:
        return self.data_root / "bin"

    @property
    def app_json(self) -> Path:
        return self.run / "app.json"

    @property
    def web_dist(self) -> Path:
        return self.code_root / "web" / "dist"

    def ensure(self) -> None:
        for d in (self.data, self.work, self.run, self.logs, self.bin):
            d.mkdir(parents=True, exist_ok=True)


def default_paths() -> Paths:
    override = os.environ.get("YT_TOOLKIT_DATA_ROOT")
    return Paths(data_root=Path(override) if override else CODE_ROOT)


def env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off", "")
```

- [ ] **Step 4: เพิ่ม fixture `paths` ใน `tests/conftest.py`** (ต่อท้ายไฟล์)

```python
from yttoolkit.config import Paths


@pytest.fixture
def paths(tmp_path: Path) -> Paths:
    p = Paths(data_root=tmp_path)
    p.ensure()
    return p
```

- [ ] **Step 5: รันให้ผ่าน**

Run: `uv run pytest -v`
Expected: ทุกเทสผ่าน

- [ ] **Step 6: Commit**

```bash
git add src/yttoolkit/config.py tests/unit/test_config.py tests/conftest.py
git commit -m "feat: add config paths and env flags

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `runstate.py` (สถานะการรัน, token, เลือก port)

**Files:**
- Create: `src/yttoolkit/runstate.py`
- Test: `tests/unit/test_runstate.py`

**Interfaces:**
- Consumes: `HOST`, `PORT_RANGE` จาก `config`
- Produces:
  - `@dataclass(frozen=True) class RunInfo(port: int, pid: int, token: str, started_at: str)`
  - `new_token() -> str` · `now_iso() -> str`
  - `write(path: Path, info: RunInfo) -> None` · `read(path: Path) -> RunInfo | None` · `clear(path: Path) -> None`
  - `port_is_free(port: int, host: str = HOST) -> bool` · `pick_port(ports: Iterable[int] = PORT_RANGE, host: str = HOST) -> int` (ไม่มี port ว่าง → `RuntimeError`)

- [ ] **Step 1: เขียนเทสที่ fail**

`tests/unit/test_runstate.py`
```python
import socket

import pytest

from yttoolkit import runstate
from yttoolkit.runstate import RunInfo


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_token_is_long_and_random():
    a, b = runstate.new_token(), runstate.new_token()
    assert a != b
    assert len(a) >= 40


def test_write_then_read_roundtrip(tmp_path):
    path = tmp_path / "run" / "app.json"
    info = RunInfo(port=8787, pid=1234, token="t", started_at="2026-09-28T00:00:00+00:00")
    runstate.write(path, info)
    assert runstate.read(path) == info


def test_read_missing_or_corrupt_returns_none(tmp_path):
    path = tmp_path / "app.json"
    assert runstate.read(path) is None
    path.write_text("{not json", encoding="utf-8")
    assert runstate.read(path) is None
    path.write_text('{"port": 1}', encoding="utf-8")
    assert runstate.read(path) is None


def test_clear_is_idempotent(tmp_path):
    path = tmp_path / "app.json"
    runstate.clear(path)
    runstate.write(path, RunInfo(1, 2, "t", "x"))
    runstate.clear(path)
    assert not path.exists()


def test_pick_port_skips_busy_port():
    busy = socket.socket()
    busy.bind(("127.0.0.1", 0))
    busy.listen()
    try:
        busy_port = busy.getsockname()[1]
        free_port = _free_port()
        assert runstate.port_is_free(busy_port) is False
        assert runstate.pick_port([busy_port, free_port]) == free_port
    finally:
        busy.close()


def test_pick_port_raises_when_none_free():
    busy = socket.socket()
    busy.bind(("127.0.0.1", 0))
    busy.listen()
    try:
        with pytest.raises(RuntimeError):
            runstate.pick_port([busy.getsockname()[1]])
    finally:
        busy.close()
```

- [ ] **Step 2: รันให้เห็นว่า fail**

Run: `uv run pytest tests/unit/test_runstate.py -v`
Expected: FAIL `ImportError: cannot import name 'runstate'`

- [ ] **Step 3: เขียน `src/yttoolkit/runstate.py`**

```python
"""สถานะของแอพที่กำลังรัน (run/app.json) ใช้ร่วมกันระหว่าง start, stop และ tray"""

from __future__ import annotations

import json
import secrets
import socket
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import HOST, PORT_RANGE


@dataclass(frozen=True)
class RunInfo:
    port: int
    pid: int
    token: str
    started_at: str


def new_token() -> str:
    return secrets.token_urlsafe(32)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write(path: Path, info: RunInfo) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(info)), encoding="utf-8")
    tmp.replace(path)


def read(path: Path) -> RunInfo | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return RunInfo(
            port=int(raw["port"]),
            pid=int(raw["pid"]),
            token=str(raw["token"]),
            started_at=str(raw["started_at"]),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def clear(path: Path) -> None:
    path.unlink(missing_ok=True)


def port_is_free(port: int, host: str = HOST) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
        except OSError:
            return False
        return True


def pick_port(ports: Iterable[int] = PORT_RANGE, host: str = HOST) -> int:
    for port in ports:
        if port_is_free(port, host):
            return port
    raise RuntimeError("ไม่มี port ว่างในช่วงที่กำหนด")
```

- [ ] **Step 4: รันให้ผ่าน**

Run: `uv run pytest tests/unit/test_runstate.py -v`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add src/yttoolkit/runstate.py tests/unit/test_runstate.py
git commit -m "feat: add run state file, token and port picking

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: `platform/` (ส่วนที่ต่างกันระหว่าง Windows กับ macOS)

**Files:**
- Create: `src/yttoolkit/platform/__init__.py`, `base.py`, `windows.py`, `macos.py`
- Test: `tests/unit/test_platform.py`

**Interfaces:**
- Produces:
  - `class Platform(Protocol)`: attributes `name: str`, `ffmpeg_exe: str`, `ffprobe_exe: str` · methods `downloads_dir() -> Path`, `open_folder(path: Path) -> None`, `reveal(path: Path) -> None`, `pid_alive(pid: int) -> bool`, `kill(pid: int) -> None`
  - `current() -> Platform` (`name` = `"windows"` หรือ `"macos"`)

- [ ] **Step 1: เขียนเทสที่ fail** (รันกับระบบจริงของเครื่องที่รัน ทั้ง Windows และ macOS)

`tests/unit/test_platform.py`
```python
import os
import subprocess
import sys

from yttoolkit.platform import current


def test_current_matches_os():
    expected = {"win32": "windows", "darwin": "macos"}[sys.platform]
    assert current().name == expected


def test_ffmpeg_names():
    plat = current()
    if plat.name == "windows":
        assert (plat.ffmpeg_exe, plat.ffprobe_exe) == ("ffmpeg.exe", "ffprobe.exe")
    else:
        assert (plat.ffmpeg_exe, plat.ffprobe_exe) == ("ffmpeg", "ffprobe")


def test_downloads_dir_is_absolute():
    assert current().downloads_dir().is_absolute()


def test_pid_alive_for_self():
    assert current().pid_alive(os.getpid()) is True


def test_pid_not_alive_after_exit():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    assert current().pid_alive(proc.pid) is False


def test_pid_alive_rejects_non_positive():
    assert current().pid_alive(0) is False
    assert current().pid_alive(-1) is False


def test_kill_stops_process():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    plat = current()
    assert plat.pid_alive(proc.pid) is True
    plat.kill(proc.pid)
    proc.wait(timeout=10)
    assert plat.pid_alive(proc.pid) is False
```

- [ ] **Step 2: รันให้เห็นว่า fail**

Run: `uv run pytest tests/unit/test_platform.py -v`
Expected: FAIL `ModuleNotFoundError: No module named 'yttoolkit.platform'`

- [ ] **Step 3: เขียน `src/yttoolkit/platform/base.py`**

```python
from __future__ import annotations

from pathlib import Path
from typing import Protocol


class Platform(Protocol):
    name: str
    ffmpeg_exe: str
    ffprobe_exe: str

    def downloads_dir(self) -> Path: ...

    def open_folder(self, path: Path) -> None: ...

    def reveal(self, path: Path) -> None: ...

    def pid_alive(self, pid: int) -> bool: ...

    def kill(self, pid: int) -> None: ...
```

- [ ] **Step 4: เขียน `src/yttoolkit/platform/windows.py`**

```python
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
```

- [ ] **Step 5: เขียน `src/yttoolkit/platform/macos.py`**

```python
from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path


class MacPlatform:
    name = "macos"
    ffmpeg_exe = "ffmpeg"
    ffprobe_exe = "ffprobe"

    def downloads_dir(self) -> Path:
        return Path.home() / "Downloads"

    def open_folder(self, path: Path) -> None:
        subprocess.run(["open", str(path)], check=False)

    def reveal(self, path: Path) -> None:
        subprocess.run(["open", "-R", str(path)], check=False)

    def pid_alive(self, pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def kill(self, pid: int) -> None:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
```

- [ ] **Step 6: เขียน `src/yttoolkit/platform/__init__.py`**

```python
"""จุดเดียวที่รู้ว่ากำลังรันบนระบบปฏิบัติการไหน"""

from __future__ import annotations

import sys

from .base import Platform


def current() -> Platform:
    if sys.platform == "win32":
        from .windows import WindowsPlatform

        return WindowsPlatform()
    if sys.platform == "darwin":
        from .macos import MacPlatform

        return MacPlatform()
    raise RuntimeError(f"ยังไม่รองรับระบบปฏิบัติการนี้: {sys.platform}")


__all__ = ["Platform", "current"]
```

- [ ] **Step 7: รันให้ผ่าน**

Run: `uv run pytest tests/unit/test_platform.py -v`
Expected: `7 passed` (บนเครื่อง Windows ของพิธ · macOS ตรวจใน CI ของ Task 18)

- [ ] **Step 8: Commit**

```bash
git add src/yttoolkit/platform tests/unit/test_platform.py
git commit -m "feat: add platform layer for windows and macos

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: `core/tools.py` ส่วนตรวจสถานะเครื่องมือ

**Files:**
- Create: `src/yttoolkit/core/__init__.py` (ว่าง), `src/yttoolkit/core/tools.py`
- Test: `tests/unit/test_tools_status.py`

**Interfaces:**
- Consumes: `Paths`, `env_flag` (Task 2), `Platform` (Task 4)
- Produces:
  - `@dataclass(frozen=True) class ToolStatus(status: Literal["ok","warn","error"], name: str | None = None, version: str | None = None, message: str | None = None, path: str | None = None)`
  - `class ToolInstallError(RuntimeError)`
  - `scripts_dir() -> Path`
  - `find_ffmpeg(paths: Paths, plat: Platform) -> Path | None`
  - `parse_ffmpeg_version(line: str | None) -> str | None`
  - `ffmpeg_status(paths: Paths, plat: Platform) -> ToolStatus`
  - `find_js_runtime() -> ToolStatus`
  - `ytdlp_status(version: str | None = None, today: date | None = None) -> ToolStatus`
  - `disk_status(path: Path) -> ToolStatus`
  - `output_status(output_dir: Path) -> ToolStatus`
  - `network_status(opener: Callable[[str], int] | None = None) -> ToolStatus`
  - `collect_health(paths: Paths, plat: Platform, output_dir: Path, *, network: Callable[[], ToolStatus] = network_status) -> dict`

- [ ] **Step 1: เขียนเทสที่ fail**

`tests/unit/test_tools_status.py`
```python
import sys
import urllib.error
from datetime import date
from pathlib import Path

from yttoolkit.core import tools
from yttoolkit.core.tools import ToolStatus


def test_find_ffmpeg_prefers_bin(paths, fake_platform):
    exe = paths.bin / "ffmpeg.exe"
    exe.write_bytes(b"x")
    assert tools.find_ffmpeg(paths, fake_platform) == exe


def test_find_ffmpeg_path_lookup_can_be_disabled(paths, fake_platform, monkeypatch):
    monkeypatch.setattr(tools.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setenv("YT_TOOLKIT_FFMPEG_PATH_LOOKUP", "0")
    assert tools.find_ffmpeg(paths, fake_platform) is None
    monkeypatch.setenv("YT_TOOLKIT_FFMPEG_PATH_LOOKUP", "1")
    assert tools.find_ffmpeg(paths, fake_platform) == Path("/usr/bin/ffmpeg")


def test_parse_ffmpeg_version():
    line = "ffmpeg version 8.1-full_build-www.gyan.dev Copyright (c) 2000-2026"
    assert tools.parse_ffmpeg_version(line) == "8.1-full_build-www.gyan.dev"
    assert tools.parse_ffmpeg_version("garbage") is None
    assert tools.parse_ffmpeg_version(None) is None


def test_ffmpeg_status_missing(paths, fake_platform, monkeypatch):
    monkeypatch.setenv("YT_TOOLKIT_FFMPEG_PATH_LOOKUP", "0")
    status = tools.ffmpeg_status(paths, fake_platform)
    assert status.status == "error"
    assert status.name == "ffmpeg"


def test_ffmpeg_status_ok(paths, fake_platform, monkeypatch):
    (paths.bin / "ffmpeg.exe").write_bytes(b"x")
    monkeypatch.setattr(tools, "_run_version", lambda exe, arg="--version": "ffmpeg version 8.1 Copyright")
    status = tools.ffmpeg_status(paths, fake_platform)
    assert status == ToolStatus("ok", name="ffmpeg", version="8.1", path=str(paths.bin / "ffmpeg.exe"))


def test_find_js_runtime_prefers_bundled_deno():
    # deno ติดตั้งมากับ dependency ของโปรเจกต์ จึงต้องเจอเสมอ (ยืนยัน PRD Q4 บนทุกระบบใน CI)
    status = tools.find_js_runtime()
    assert status.status == "ok"
    assert status.name == "deno"
    assert status.version and status.version[0].isdigit()


def test_find_js_runtime_falls_back_to_node(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "scripts_dir", lambda: tmp_path)
    monkeypatch.setattr(tools.shutil, "which", lambda name: "node" if name == "node" else None)
    monkeypatch.setattr(tools, "_run_version", lambda exe, arg="--version": "v24.14.0")
    status = tools.find_js_runtime()
    assert status.status == "warn"
    assert status.name == "node"
    assert status.version == "24.14.0"


def test_find_js_runtime_none(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "scripts_dir", lambda: tmp_path)
    monkeypatch.setattr(tools.shutil, "which", lambda name: None)
    assert tools.find_js_runtime().status == "warn"


def test_ytdlp_status_age():
    fresh = tools.ytdlp_status(version="2026.09.20", today=date(2026, 9, 28))
    assert fresh.status == "ok"
    assert "8 วัน" in (fresh.message or "")
    old = tools.ytdlp_status(version="2026.08.01", today=date(2026, 9, 28))
    assert old.status == "warn"


def test_ytdlp_status_real_version_is_ok_shape():
    status = tools.ytdlp_status()
    assert status.name == "yt-dlp"
    assert status.version


def test_disk_status(tmp_path, monkeypatch):
    class Usage:
        free = 1 * 1024**3

    monkeypatch.setattr(tools.shutil, "disk_usage", lambda p: Usage())
    assert tools.disk_status(tmp_path).status == "warn"
    Usage.free = 50 * 1024**3
    assert tools.disk_status(tmp_path).status == "ok"


def test_output_status(tmp_path):
    assert tools.output_status(tmp_path / "out").status == "ok"
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert tools.output_status(blocker / "sub").status == "error"


def test_network_status():
    assert tools.network_status(lambda url: 200).status == "ok"

    def boom(url):
        raise urllib.error.URLError("offline")

    assert tools.network_status(boom).status == "error"

    def http_error(url):
        raise urllib.error.HTTPError(url, 405, "Method Not Allowed", {}, None)

    assert tools.network_status(http_error).status == "ok"


def test_collect_health_shape(paths, fake_platform, monkeypatch):
    monkeypatch.setenv("YT_TOOLKIT_FFMPEG_PATH_LOOKUP", "0")
    health = tools.collect_health(
        paths, fake_platform, paths.data_root / "out", network=lambda: ToolStatus("ok", name="network")
    )
    assert set(health) == {"tools", "disk", "output", "network"}
    assert set(health["tools"]) == {"ffmpeg", "ytdlp", "jsRuntime"}
    assert health["tools"]["ffmpeg"]["status"] == "error"
    assert health["network"] == {"status": "ok", "name": "network", "version": None, "message": None, "path": None}
```

- [ ] **Step 2: รันให้เห็นว่า fail**

Run: `uv run pytest tests/unit/test_tools_status.py -v`
Expected: FAIL `ModuleNotFoundError: No module named 'yttoolkit.core'`

- [ ] **Step 3: เขียน `src/yttoolkit/core/tools.py`**

```python
"""ตรวจและเตรียมเครื่องมือภายนอกที่แอพต้องใช้ (ffmpeg, JS runtime, yt-dlp)"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import sysconfig
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from ..config import Paths, env_flag
from ..platform import Platform

Status = Literal["ok", "warn", "error"]

YTDLP_MAX_AGE_DAYS = 30
MIN_FREE_BYTES = 2 * 1024**3
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass(frozen=True)
class ToolStatus:
    status: Status
    name: str | None = None
    version: str | None = None
    message: str | None = None
    path: str | None = None


class ToolInstallError(RuntimeError):
    pass


def _run_version(exe: Path | str, arg: str = "--version") -> str | None:
    try:
        out = subprocess.run(
            [str(exe), arg], capture_output=True, text=True, timeout=10, creationflags=_NO_WINDOW
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (out.stdout or out.stderr or "").strip()
    return text.splitlines()[0] if text else None


def scripts_dir() -> Path:
    return Path(sysconfig.get_path("scripts"))


def find_ffmpeg(paths: Paths, plat: Platform) -> Path | None:
    local = paths.bin / plat.ffmpeg_exe
    if local.is_file():
        return local
    if env_flag("YT_TOOLKIT_FFMPEG_PATH_LOOKUP", True):
        found = shutil.which("ffmpeg")
        if found:
            return Path(found)
    return None


def parse_ffmpeg_version(line: str | None) -> str | None:
    if not line:
        return None
    match = re.match(r"ffmpeg version (\S+)", line)
    return match.group(1) if match else None


def ffmpeg_status(paths: Paths, plat: Platform) -> ToolStatus:
    exe = find_ffmpeg(paths, plat)
    if exe is None:
        return ToolStatus("error", name="ffmpeg", message="ยังไม่มีโปรแกรมแปลงไฟล์ (ffmpeg)")
    version = parse_ffmpeg_version(_run_version(exe, "-version"))
    if version is None:
        return ToolStatus("error", name="ffmpeg", path=str(exe), message="มี ffmpeg แต่เรียกใช้งานไม่ได้")
    return ToolStatus("ok", name="ffmpeg", version=version, path=str(exe))


def find_js_runtime() -> ToolStatus:
    suffix = ".exe" if sys.platform == "win32" else ""
    bundled = scripts_dir() / f"deno{suffix}"
    candidates = [
        ("deno", str(bundled) if bundled.is_file() else shutil.which("deno")),
        ("node", shutil.which("node")),
    ]
    for name, exe in candidates:
        if not exe:
            continue
        line = _run_version(exe)
        if line is None:
            continue
        if name == "deno":
            parts = line.split()
            version = parts[1] if len(parts) > 1 else line
            return ToolStatus("ok", name="deno", version=version, path=exe)
        return ToolStatus("warn", name="node", version=line.lstrip("v"), path=exe, message="ใช้ node แทน deno")
    return ToolStatus(
        "warn", message="บางคุณภาพอาจไม่แสดง เพราะเครื่องยังไม่มีตัวช่วยที่ yt-dlp ต้องใช้"
    )


def ytdlp_status(version: str | None = None, today: date | None = None) -> ToolStatus:
    if version is None:
        from yt_dlp.version import __version__ as version
    today = today or date.today()
    try:
        released = datetime.strptime(version[:10], "%Y.%m.%d").date()
    except ValueError:
        return ToolStatus("ok", name="yt-dlp", version=version)
    age = (today - released).days
    if age > YTDLP_MAX_AGE_DAYS:
        return ToolStatus(
            "warn", name="yt-dlp", version=version, message=f"อัปเดตล่าสุด {age} วันก่อน ลองกดตรวจหาอัปเดต"
        )
    return ToolStatus("ok", name="yt-dlp", version=version, message=f"อัปเดตล่าสุด {age} วันก่อน")


def disk_status(path: Path) -> ToolStatus:
    free = shutil.disk_usage(path).free
    gb = free / 1024**3
    if free < MIN_FREE_BYTES:
        return ToolStatus("warn", name="disk", message=f"เหลือ {gb:.1f} GB")
    return ToolStatus("ok", name="disk", message=f"เหลือ {gb:.0f} GB")


def output_status(output_dir: Path) -> ToolStatus:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        probe = output_dir / ".yt-toolkit-write-test"
        probe.write_bytes(b"")
        probe.unlink()
    except OSError:
        return ToolStatus("error", name="output", path=str(output_dir), message="บันทึกลงโฟลเดอร์นี้ไม่ได้")
    return ToolStatus("ok", name="output", path=str(output_dir))


def _head_status(url: str) -> int:
    request = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status


def network_status(opener: Callable[[str], int] | None = None) -> ToolStatus:
    try:
        code = (opener or _head_status)("https://www.youtube.com/")
    except urllib.error.HTTPError:
        return ToolStatus("ok", name="network")  # ได้คำตอบกลับมา แปลว่าต่อถึง
    except OSError:
        return ToolStatus("error", name="network", message="ต่อยูทูปไม่ได้ ตรวจเน็ตอีกครั้ง")
    return ToolStatus("ok" if code < 500 else "warn", name="network")


def collect_health(
    paths: Paths,
    plat: Platform,
    output_dir: Path,
    *,
    network: Callable[[], ToolStatus] = network_status,
) -> dict:
    return {
        "tools": {
            "ffmpeg": asdict(ffmpeg_status(paths, plat)),
            "ytdlp": asdict(ytdlp_status()),
            "jsRuntime": asdict(find_js_runtime()),
        },
        "disk": asdict(disk_status(paths.data_root)),
        "output": asdict(output_status(output_dir)),
        "network": asdict(network()),
    }
```

- [ ] **Step 4: รันให้ผ่าน**

Run: `uv run pytest tests/unit/test_tools_status.py -v`
Expected: `14 passed`

- [ ] **Step 5: Commit**

```bash
git add src/yttoolkit/core tests/unit/test_tools_status.py
git commit -m "feat: add tool status checks for health page

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: `core/tools.py` ส่วนติดตั้ง ffmpeg (Windows)

**Files:**
- Modify: `src/yttoolkit/core/tools.py` (ต่อท้ายไฟล์)
- Test: `tests/unit/test_tools_install.py`

**Interfaces:**
- Consumes: `Paths`, `Platform`, `ToolInstallError` (Task 5)
- Produces:
  - `FFMPEG_RELEASE: str`, `FFMPEG_WIN_ZIP: str`
  - `Downloader = Callable[[str, Path], None]`
  - `parse_checksums(text: str, filename: str) -> str | None`
  - `sha256_file(path: Path) -> str`
  - `install_ffmpeg_windows(paths: Paths, download: Downloader = _download) -> Path`
  - `install_ffmpeg(paths: Paths, plat: Platform, download: Downloader = _download) -> Path` (macOS → `ToolInstallError` จนถึง M7)

- [ ] **Step 1: เขียนเทสที่ fail**

`tests/unit/test_tools_install.py`
```python
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
```

- [ ] **Step 2: รันให้เห็นว่า fail**

Run: `uv run pytest tests/unit/test_tools_install.py -v`
Expected: FAIL `AttributeError: module 'yttoolkit.core.tools' has no attribute 'FFMPEG_WIN_ZIP'`

- [ ] **Step 3: เพิ่ม import และโค้ดท้าย `src/yttoolkit/core/tools.py`**

เพิ่มบรรทัดนี้ในกลุ่ม import ด้านบน
```python
import hashlib
import zipfile
```

ต่อท้ายไฟล์
```python
FFMPEG_RELEASE = "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest"
FFMPEG_WIN_ZIP = "ffmpeg-master-latest-win64-gpl.zip"
_FFMPEG_WIN_FILES = frozenset({"ffmpeg.exe", "ffprobe.exe"})

Downloader = Callable[[str, Path], None]


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as response, dest.open("wb") as out:
        shutil.copyfileobj(response, out, 1024 * 1024)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_checksums(text: str, filename: str) -> str | None:
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == filename:
            return parts[0].lower()
    return None


def install_ffmpeg_windows(paths: Paths, download: Downloader = _download) -> Path:
    zip_path = paths.work / FFMPEG_WIN_ZIP
    sums_path = paths.work / "ffmpeg-checksums.sha256"
    try:
        download(f"{FFMPEG_RELEASE}/checksums.sha256", sums_path)
        expected = parse_checksums(sums_path.read_text(encoding="utf-8"), FFMPEG_WIN_ZIP)
        if expected is None:
            raise ToolInstallError("ไม่พบ checksum ของ ffmpeg ในรีลีส")
        download(f"{FFMPEG_RELEASE}/{FFMPEG_WIN_ZIP}", zip_path)
        if sha256_file(zip_path) != expected:
            raise ToolInstallError("checksum ของ ffmpeg ไม่ตรง")
        paths.bin.mkdir(parents=True, exist_ok=True)
        found: set[str] = set()
        with zipfile.ZipFile(zip_path) as archive:
            for member in archive.namelist():
                base = member.rsplit("/", 1)[-1]
                if base in _FFMPEG_WIN_FILES and "/bin/" in member:
                    (paths.bin / base).write_bytes(archive.read(member))
                    found.add(base)
        if found != _FFMPEG_WIN_FILES:
            for name in found:
                (paths.bin / name).unlink(missing_ok=True)
            raise ToolInstallError("ไฟล์ ffmpeg ใน zip ไม่ครบ")
    except (OSError, zipfile.BadZipFile) as error:
        raise ToolInstallError(f"โหลด ffmpeg ไม่สำเร็จ: {error}") from error
    finally:
        zip_path.unlink(missing_ok=True)
        sums_path.unlink(missing_ok=True)
    return paths.bin / "ffmpeg.exe"


def install_ffmpeg(paths: Paths, plat: Platform, download: Downloader = _download) -> Path:
    if plat.name == "windows":
        return install_ffmpeg_windows(paths, download)
    raise ToolInstallError("ยังไม่รองรับการโหลด ffmpeg อัตโนมัติบนระบบนี้")
```

- [ ] **Step 4: รันให้ผ่าน**

Run: `uv run pytest tests/unit/ -v`
Expected: ทุกเทสผ่าน

- [ ] **Step 5: Commit**

```bash
git add src/yttoolkit/core/tools.py tests/unit/test_tools_install.py
git commit -m "feat: install ffmpeg on windows with sha256 verification

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: `api/security.py` (middleware ความปลอดภัย)

**Files:**
- Create: `src/yttoolkit/api/__init__.py` (ว่าง), `src/yttoolkit/api/errors.py`, `src/yttoolkit/api/security.py`
- Test: `tests/api/test_security.py`

**Interfaces:**
- Produces:
  - `error_response(status: int, code: str, message: str, detail: str | None = None) -> JSONResponse`
  - `error_body(code: str, message: str, detail: str | None = None) -> dict`
  - `class LocalOnlyMiddleware(app, *, port: int, token: str, extra_origins: Iterable[str] = ())` (pure ASGI)

- [ ] **Step 1: เขียนเทสที่ fail**

`tests/api/test_security.py`
```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from yttoolkit.api.security import LocalOnlyMiddleware

PORT = 8787
BASE = f"http://127.0.0.1:{PORT}"
TOKEN = "secret-token"


def _client(extra_origins=()) -> TestClient:
    app = FastAPI()

    @app.get("/ping")
    def get_ping():
        return {"ok": True}

    @app.post("/ping")
    def post_ping():
        return {"ok": True}

    app.add_middleware(LocalOnlyMiddleware, port=PORT, token=TOKEN, extra_origins=extra_origins)
    return TestClient(app, base_url=BASE)


def test_get_allowed_on_127():
    assert _client().get("/ping").status_code == 200


def test_get_allowed_on_localhost():
    assert _client().get("/ping", headers={"host": f"localhost:{PORT}"}).status_code == 200


def test_foreign_host_rejected_with_421():  # AC-SEC-02
    resp = _client().get("/ping", headers={"host": "evil.example:8787"})
    assert resp.status_code == 421
    assert resp.json()["error"]["code"] == "E_FORBIDDEN"


def test_wrong_port_in_host_rejected():
    assert _client().get("/ping", headers={"host": "127.0.0.1:9999"}).status_code == 421


def test_post_without_token_rejected():  # AC-SEC-03
    resp = _client().post("/ping", headers={"origin": BASE})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "E_FORBIDDEN"


def test_post_with_token_but_no_origin_rejected():
    assert _client().post("/ping", headers={"x-toolkit-token": TOKEN}).status_code == 403


def test_post_with_wrong_origin_rejected():
    headers = {"x-toolkit-token": TOKEN, "origin": "https://evil.example"}
    assert _client().post("/ping", headers=headers).status_code == 403


def test_post_with_non_ascii_token_rejected_cleanly():
    # เรียก middleware ตรง ๆ เพราะ httpx ไม่ยอมส่ง header ที่ไม่ใช่ ASCII
    import asyncio

    sent = []

    async def app(scope, receive, send):
        raise AssertionError("ต้องไม่ถึง app")

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "headers": [
            (b"host", b"127.0.0.1:8787"),
            (b"origin", BASE.encode()),
            (b"x-toolkit-token", "ไม่ใช่".encode("utf-8")),
        ],
    }
    asyncio.run(LocalOnlyMiddleware(app, port=PORT, token=TOKEN)(scope, receive, send))
    assert sent[0]["status"] == 403


def test_post_with_token_and_origin_allowed():
    headers = {"x-toolkit-token": TOKEN, "origin": BASE}
    assert _client().post("/ping", headers=headers).status_code == 200


def test_extra_origin_allowed_for_dev():
    client = _client(extra_origins=("http://localhost:5173",))
    headers = {"x-toolkit-token": TOKEN, "origin": "http://localhost:5173"}
    assert client.post("/ping", headers=headers).status_code == 200
```

- [ ] **Step 2: รันให้เห็นว่า fail**

Run: `uv run pytest tests/api/test_security.py -v`
Expected: FAIL `ModuleNotFoundError: No module named 'yttoolkit.api'`

- [ ] **Step 3: เขียน `src/yttoolkit/api/errors.py`**

```python
from __future__ import annotations

from fastapi.responses import JSONResponse


def error_body(code: str, message: str, detail: str | None = None) -> dict:
    return {"error": {"code": code, "message": message, "detail": detail}}


def error_response(status: int, code: str, message: str, detail: str | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content=error_body(code, message, detail))
```

- [ ] **Step 4: เขียน `src/yttoolkit/api/security.py`**

```python
"""ป้องกันไม่ให้เว็บอื่นหรือเครื่องอื่นสั่งงานแอพ (NFR-SEC-1..3)"""

from __future__ import annotations

import json
import secrets
from collections.abc import Iterable

from .errors import error_body

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
FORBIDDEN_MESSAGE = "คำขอนี้ไม่ได้รับอนุญาต ลองรีเฟรชหน้าเว็บ"


class LocalOnlyMiddleware:
    def __init__(self, app, *, port: int, token: str, extra_origins: Iterable[str] = ()) -> None:
        self.app = app
        self._token = token.encode("latin-1")
        self._hosts = frozenset({f"127.0.0.1:{port}", f"localhost:{port}"})
        self._origins = frozenset({f"http://{h}" for h in self._hosts} | set(extra_origins))

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        if headers.get("host") not in self._hosts:
            await _send_json(send, 421)
            return
        if scope["method"] not in SAFE_METHODS:
            origin_ok = headers.get("origin") in self._origins
            token_ok = secrets.compare_digest(headers.get("x-toolkit-token", "").encode("latin-1"), self._token)
            if not (origin_ok and token_ok):
                await _send_json(send, 403)
                return
        await self.app(scope, receive, send)


async def _send_json(send, status: int) -> None:
    body = json.dumps(error_body("E_FORBIDDEN", FORBIDDEN_MESSAGE), ensure_ascii=False).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
```

หมายเหตุ: header ภาษาไทยที่ส่งมาจะถูก decode เป็น latin-1 แล้ว encode กลับเป็น bytes เดิม เปรียบเทียบได้โดยไม่ error (เทส `non_ascii`)

- [ ] **Step 5: รันให้ผ่าน**

Run: `uv run pytest tests/api/test_security.py -v`
Expected: `10 passed`

- [ ] **Step 6: Commit**

```bash
git add src/yttoolkit/api tests/api/test_security.py
git commit -m "feat: add local-only security middleware (host, origin, token)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: `api/static.py` (เสิร์ฟหน้าเว็บ + ฝัง token)

**Files:**
- Create: `src/yttoolkit/api/static.py`
- Test: `tests/api/test_static.py`

**Interfaces:**
- Produces: `inject_token(index_html: str, token: str) -> str` · `mount_web(app: FastAPI, dist: Path, token: str) -> None` (ต้องเรียก **หลัง** include API router เพราะเป็น catch-all)

- [ ] **Step 1: เขียนเทสที่ fail**

`tests/api/test_static.py`
```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from yttoolkit.api.static import inject_token, mount_web

BASE = "http://127.0.0.1:8787"
INDEX = "<!doctype html><html><head><title>x</title></head><body></body></html>"


def _client(dist) -> TestClient:
    app = FastAPI()

    @app.get("/api/ping")
    def ping():
        return {"ok": True}

    mount_web(app, dist, token="tok<&>")
    return TestClient(app, base_url=BASE)


def _dist(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX, encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    return dist


def test_inject_token_escapes_value():
    out = inject_token(INDEX, 'a"b')
    assert '<meta name="yt-token" content="a&quot;b"></head>' in out


def test_root_serves_index_with_token(tmp_path):
    resp = _client(_dist(tmp_path)).get("/")
    assert resp.status_code == 200
    assert 'name="yt-token" content="tok&lt;&amp;&gt;"' in resp.text
    assert resp.headers["cache-control"] == "no-store"


def test_spa_route_falls_back_to_index(tmp_path):
    resp = _client(_dist(tmp_path)).get("/settings/health")
    assert resp.status_code == 200
    assert "yt-token" in resp.text


def test_asset_is_served(tmp_path):
    resp = _client(_dist(tmp_path)).get("/assets/app.js")
    assert resp.status_code == 200
    assert resp.text == "console.log(1)"


def test_api_routes_win_and_unknown_api_is_404(tmp_path):
    client = _client(_dist(tmp_path))
    assert client.get("/api/ping").json() == {"ok": True}
    assert client.get("/api/nope").status_code == 404


def test_missing_dist_returns_503(tmp_path):
    resp = _client(tmp_path / "missing").get("/")
    assert resp.status_code == 503
```

- [ ] **Step 2: รันให้เห็นว่า fail**

Run: `uv run pytest tests/api/test_static.py -v`
Expected: FAIL `ModuleNotFoundError: No module named 'yttoolkit.api.static'`

- [ ] **Step 3: เขียน `src/yttoolkit/api/static.py`**

```python
"""เสิร์ฟหน้าเว็บที่ build แล้ว (web/dist) และฝัง token ลงใน index.html"""

from __future__ import annotations

import html
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse


def inject_token(index_html: str, token: str) -> str:
    meta = f'<meta name="yt-token" content="{html.escape(token, quote=True)}">'
    return index_html.replace("</head>", f"{meta}</head>", 1)


def mount_web(app: FastAPI, dist: Path, token: str) -> None:
    root = dist.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        index = root / "index.html"
        if not index.is_file():
            return PlainTextResponse("ยังไม่ได้ build หน้าเว็บ (web/dist)", status_code=503)
        if full_path:
            candidate = (root / full_path).resolve()
            if candidate.is_relative_to(root) and candidate.is_file():
                return FileResponse(candidate)
        page = inject_token(index.read_text(encoding="utf-8"), token)
        return HTMLResponse(page, headers={"Cache-Control": "no-store"})
```

- [ ] **Step 4: รันให้ผ่าน**

Run: `uv run pytest tests/api/test_static.py -v`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add src/yttoolkit/api/static.py tests/api/test_static.py
git commit -m "feat: serve built web app with injected session token

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: `api/routes.py` + `app.py` (ping, health, ติดตั้ง ffmpeg, shutdown)

**Files:**
- Create: `src/yttoolkit/api/routes.py`, `src/yttoolkit/app.py`
- Test: `tests/api/conftest.py`, `tests/api/test_routes.py`

**Interfaces:**
- Consumes: `Paths`, `Platform`, `tools.*`, `LocalOnlyMiddleware`, `mount_web`, `error_response`
- Produces:
  - `@dataclass class AppContext(paths: Paths, plat: Platform, port: int, token: str, version: str, commit: str | None, output_dir: Path, request_shutdown: Callable[[], None], pending_jobs: Callable[[], int] = <คืน 0>, health: Callable[[], dict] | None = None, extra_origins: tuple[str, ...] = ())`
  - `create_app(ctx: AppContext) -> FastAPI`
  - `build_router(ctx: AppContext) -> APIRouter`
  - Endpoints: `GET /api/ping → {"ok": true, "pid": int}` · `GET /api/health` · `POST /api/tools/ffmpeg/install` · `POST /api/shutdown {force?: bool}` → 200 `{"ok": true}` หรือ 409 `{"pendingJobs": n}`

- [ ] **Step 1: เขียน fixture `tests/api/conftest.py`**

```python
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from yttoolkit.app import AppContext, create_app

TOKEN = "test-token"
PORT = 8787
BASE = f"http://127.0.0.1:{PORT}"
AUTH = {"X-Toolkit-Token": TOKEN, "Origin": BASE}


@pytest.fixture
def make_client(paths, fake_platform):
    def _make(**overrides) -> TestClient:
        calls = {"shutdown": 0}

        def request_shutdown() -> None:
            calls["shutdown"] += 1

        ctx = AppContext(
            paths=paths,
            plat=fake_platform,
            port=PORT,
            token=TOKEN,
            version="0.1.0",
            commit="abc1234",
            output_dir=paths.data_root / "out",
            request_shutdown=request_shutdown,
        )
        for key, value in overrides.items():
            setattr(ctx, key, value)
        client = TestClient(create_app(ctx), base_url=BASE)
        client.calls = calls  # type: ignore[attr-defined]
        return client

    return _make
```

- [ ] **Step 2: เขียนเทสที่ fail**

`tests/api/test_routes.py`
```python
import os

from yttoolkit.core import tools
from yttoolkit.core.tools import ToolStatus

# ค่าเดียวกับ tests/api/conftest.py (import conftest ตรง ๆ ไม่ได้)
BASE = "http://127.0.0.1:8787"
AUTH = {"X-Toolkit-Token": "test-token", "Origin": BASE}


def test_ping(make_client):
    body = make_client().get("/api/ping").json()
    assert body == {"ok": True, "pid": os.getpid()}


def test_health_includes_version_and_commit(make_client):
    fake = {"tools": {}, "disk": {}, "output": {}, "network": {}}
    body = make_client(health=lambda: fake).get("/api/health").json()
    assert body["version"] == "0.1.0"
    assert body["commit"] == "abc1234"
    assert set(body) == {"version", "commit", "tools", "disk", "output", "network"}


def test_shutdown_requires_token(make_client):
    assert make_client().post("/api/shutdown", json={}).status_code == 403


def test_shutdown_ok_when_no_pending(make_client):
    client = make_client()
    resp = client.post("/api/shutdown", json={"force": False}, headers=AUTH)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert client.calls["shutdown"] == 1


def test_shutdown_without_body(make_client):
    client = make_client()
    assert client.post("/api/shutdown", headers=AUTH).status_code == 200


def test_shutdown_conflict_when_pending(make_client):
    client = make_client(pending_jobs=lambda: 2)
    resp = client.post("/api/shutdown", json={"force": False}, headers=AUTH)
    assert resp.status_code == 409
    assert resp.json() == {"pendingJobs": 2}
    assert client.calls["shutdown"] == 0


def test_shutdown_force_when_pending(make_client):
    client = make_client(pending_jobs=lambda: 2)
    resp = client.post("/api/shutdown", json={"force": True}, headers=AUTH)
    assert resp.status_code == 200
    assert client.calls["shutdown"] == 1


def test_install_ffmpeg_success(make_client, monkeypatch):
    monkeypatch.setattr(tools, "install_ffmpeg", lambda paths, plat: paths.bin / "ffmpeg.exe")
    monkeypatch.setattr(tools, "ffmpeg_status", lambda paths, plat: ToolStatus("ok", name="ffmpeg", version="8.1"))
    resp = make_client().post("/api/tools/ffmpeg/install", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_install_ffmpeg_failure(make_client, monkeypatch):
    def boom(paths, plat):
        raise tools.ToolInstallError("checksum mismatch")

    monkeypatch.setattr(tools, "install_ffmpeg", boom)
    resp = make_client().post("/api/tools/ffmpeg/install", headers=AUTH)
    assert resp.status_code == 502
    assert resp.json()["error"] == {
        "code": "E_TOOL_INSTALL_FAILED",
        "message": "โหลดโปรแกรมที่ต้องใช้ไม่สำเร็จ ตรวจเน็ตแล้วกดลองใหม่",
        "detail": "checksum mismatch",
    }
```

- [ ] **Step 3: รันให้เห็นว่า fail**

Run: `uv run pytest tests/api/test_routes.py -v`
Expected: FAIL `ModuleNotFoundError: No module named 'yttoolkit.app'`

- [ ] **Step 4: เขียน `src/yttoolkit/api/routes.py`**

```python
from __future__ import annotations

import os
from dataclasses import asdict
from typing import TYPE_CHECKING

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..core import tools
from .errors import error_response

if TYPE_CHECKING:
    from ..app import AppContext


class ShutdownBody(BaseModel):
    force: bool = False


def build_router(ctx: AppContext) -> APIRouter:
    router = APIRouter()

    def _health() -> dict:
        if ctx.health is not None:
            return ctx.health()
        return tools.collect_health(ctx.paths, ctx.plat, ctx.output_dir)

    @router.get("/ping")
    def ping() -> dict:
        return {"ok": True, "pid": os.getpid()}

    @router.get("/health")
    def health() -> dict:
        return {"version": ctx.version, "commit": ctx.commit, **_health()}

    @router.post("/tools/ffmpeg/install")
    def install_ffmpeg():
        try:
            tools.install_ffmpeg(ctx.paths, ctx.plat)
        except tools.ToolInstallError as error:
            return error_response(
                502, "E_TOOL_INSTALL_FAILED", "โหลดโปรแกรมที่ต้องใช้ไม่สำเร็จ ตรวจเน็ตแล้วกดลองใหม่", str(error)
            )
        return asdict(tools.ffmpeg_status(ctx.paths, ctx.plat))

    @router.post("/shutdown")
    def shutdown(background: BackgroundTasks, body: ShutdownBody | None = None):
        force = body.force if body else False
        pending = ctx.pending_jobs()
        if pending and not force:
            return JSONResponse(status_code=409, content={"pendingJobs": pending})
        background.add_task(ctx.request_shutdown)
        return {"ok": True}

    return router
```

- [ ] **Step 5: เขียน `src/yttoolkit/app.py`**

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI

from .api.routes import build_router
from .api.security import LocalOnlyMiddleware
from .api.static import mount_web
from .config import APP_NAME, Paths
from .platform import Platform


def _no_pending_jobs() -> int:
    return 0  # คิวงานมาใน M4


@dataclass
class AppContext:
    paths: Paths
    plat: Platform
    port: int
    token: str
    version: str
    commit: str | None
    output_dir: Path
    request_shutdown: Callable[[], None]
    pending_jobs: Callable[[], int] = _no_pending_jobs
    health: Callable[[], dict] | None = None
    extra_origins: tuple[str, ...] = ()


def create_app(ctx: AppContext) -> FastAPI:
    app = FastAPI(title=APP_NAME, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.ctx = ctx
    app.include_router(build_router(ctx), prefix="/api")
    mount_web(app, ctx.paths.web_dist, ctx.token)
    app.add_middleware(LocalOnlyMiddleware, port=ctx.port, token=ctx.token, extra_origins=ctx.extra_origins)
    return app
```

- [ ] **Step 6: รันให้ผ่าน**

Run: `uv run pytest -v`
Expected: ทุกเทสผ่าน

- [ ] **Step 7: Commit**

```bash
git add src/yttoolkit/app.py src/yttoolkit/api/routes.py tests/api
git commit -m "feat: add ping, health, ffmpeg install and shutdown endpoints

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: `tray.py` (ไอคอน tray)

**Files:**
- Create: `src/yttoolkit/tray.py`
- Test: `tests/unit/test_tray.py`

**Interfaces:**
- Produces: `ACCENT: tuple`, `MENU_LABELS: tuple[str, str, str]`, `make_icon_image(size: int = 64) -> PIL.Image.Image`, `build_menu(open_app, open_output, quit_app) -> pystray.Menu`, `build_tray(open_app, open_output, quit_app) -> pystray.Icon` (callback ทั้งสามเป็น `Callable[[], None]`)

- [ ] **Step 1: เขียนเทสที่ fail**

`tests/unit/test_tray.py`
```python
from yttoolkit.tray import ACCENT, MENU_LABELS, build_menu, make_icon_image


def test_icon_image_is_amber_square():
    img = make_icon_image(64)
    assert img.size == (64, 64)
    assert img.getpixel((5, 32)) == ACCENT


def test_menu_labels_and_actions():
    calls = []
    menu = build_menu(lambda: calls.append("open"), lambda: calls.append("folder"), lambda: calls.append("quit"))
    items = [item for item in menu.items if item.text]
    assert tuple(item.text for item in items) == MENU_LABELS
    assert items[0].default is True
    for item in items:
        item(None)
    assert calls == ["open", "folder", "quit"]
```

- [ ] **Step 2: รันให้เห็นว่า fail**

Run: `uv run pytest tests/unit/test_tray.py -v`
Expected: FAIL `ModuleNotFoundError: No module named 'yttoolkit.tray'`

- [ ] **Step 3: เขียน `src/yttoolkit/tray.py`**

```python
"""ไอคอนที่ system tray (Windows) / menu bar (macOS) ต้องรันที่ main thread"""

from __future__ import annotations

from collections.abc import Callable

import pystray
from PIL import Image, ImageDraw

ACCENT = (245, 185, 66, 255)  # --accent #F5B942
ON_ACCENT = (26, 20, 5, 255)  # --on-accent #1A1405
MENU_LABELS = ("เปิดแอพ", "เปิดโฟลเดอร์ผลลัพธ์", "ปิดโปรแกรม")


def make_icon_image(size: int = 64) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=size // 5, fill=ACCENT)
    draw.polygon(
        [(size * 0.38, size * 0.28), (size * 0.38, size * 0.72), (size * 0.74, size * 0.5)],
        fill=ON_ACCENT,
    )
    return image


def build_menu(
    open_app: Callable[[], None], open_output: Callable[[], None], quit_app: Callable[[], None]
) -> pystray.Menu:
    return pystray.Menu(
        pystray.MenuItem(MENU_LABELS[0], lambda icon, item: open_app(), default=True),
        pystray.MenuItem(MENU_LABELS[1], lambda icon, item: open_output()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(MENU_LABELS[2], lambda icon, item: quit_app()),
    )


def build_tray(
    open_app: Callable[[], None], open_output: Callable[[], None], quit_app: Callable[[], None]
) -> pystray.Icon:
    return pystray.Icon(
        "yt-toolkit", make_icon_image(), "YT Toolkit", menu=build_menu(open_app, open_output, quit_app)
    )
```

- [ ] **Step 4: รันให้ผ่าน**

Run: `uv run pytest tests/unit/test_tray.py -v`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add src/yttoolkit/tray.py tests/unit/test_tray.py
git commit -m "feat: add tray icon and menu

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: `lifecycle.py` + `__main__.py` (start / stop / serve)

**Files:**
- Create: `src/yttoolkit/lifecycle.py`, `src/yttoolkit/__main__.py`
- Test: `tests/unit/test_lifecycle.py`, `tests/integration/test_serve.py`

**Interfaces:**
- Consumes: ทุกอย่างจาก Task 2-10
- Produces:
  - `base_url(port: int) -> str`
  - `is_alive(port: int, get=httpx.get) -> bool` (เรียก `/api/ping`)
  - `find_running(paths: Paths, plat: Platform, alive=is_alive) -> RunInfo | None`
  - `default_output_dir(plat: Platform) -> Path`
  - `prepare_environment() -> None` (ใส่ `scripts_dir()` ไว้หน้า PATH)
  - `class Server(ctx: AppContext)`: `config: uvicorn.Config`, `start()`, `stop()`, `join(timeout)`, `wait_until_ready(timeout=15.0) -> bool`
  - `run_app(*, paths, plat, port, with_tray: bool, open_browser: bool, auto_ffmpeg: bool, extra_origins=()) -> int`
  - `start(paths=None, plat=None) -> int` · `serve(port: int | None = None, dev: bool = False) -> int`
  - `stop(paths=None, plat=None, *, post=httpx.post, ask=input, sleep=time.sleep, out=print) -> int`
  - CLI: `python -m yttoolkit start|stop|serve [--port N] [--dev]`

- [ ] **Step 1: เขียนเทส unit ที่ fail**

`tests/unit/test_lifecycle.py`
```python
import os

import httpx

from yttoolkit import lifecycle, runstate
from yttoolkit.core import tools
from yttoolkit.runstate import RunInfo


class FakeResponse:
    def __init__(self, status_code: int, body: dict | None = None):
        self.status_code = status_code
        self._body = body or {}

    def json(self) -> dict:
        return self._body


def _running(paths, fake_platform, pid=4242, port=8787) -> RunInfo:
    info = RunInfo(port=port, pid=pid, token="tok", started_at="x")
    runstate.write(paths.app_json, info)
    fake_platform.alive.add(pid)
    return info


def test_base_url():
    assert lifecycle.base_url(8787) == "http://127.0.0.1:8787"


def test_is_alive_handles_errors():
    def boom(url, timeout):
        raise httpx.ConnectError("refused")

    assert lifecycle.is_alive(8787, get=boom) is False
    assert lifecycle.is_alive(8787, get=lambda url, timeout: FakeResponse(200)) is True


def test_find_running_ignores_stale_file(paths, fake_platform):
    runstate.write(paths.app_json, RunInfo(8787, 999, "t", "x"))
    assert lifecycle.find_running(paths, fake_platform, alive=lambda port: True) is None


def test_find_running_detects_live_instance(paths, fake_platform):
    info = _running(paths, fake_platform)
    assert lifecycle.find_running(paths, fake_platform, alive=lambda port: True) == info
    assert lifecycle.find_running(paths, fake_platform, alive=lambda port: False) is None


def test_default_output_dir(fake_platform):
    assert lifecycle.default_output_dir(fake_platform) == fake_platform.downloads / "YT-Toolkit"


def test_prepare_environment_puts_scripts_first(monkeypatch):
    monkeypatch.setenv("PATH", "somewhere")
    lifecycle.prepare_environment()
    assert os.environ["PATH"].split(os.pathsep)[0] == str(tools.scripts_dir())


def test_server_binds_localhost_only(paths, fake_platform):  # AC-SEC-01
    from yttoolkit.app import AppContext

    ctx = AppContext(paths, fake_platform, 8787, "t", "0.1.0", None, paths.data_root, lambda: None)
    assert lifecycle.Server(ctx).config.host == "127.0.0.1"


def test_stop_when_not_running(paths, fake_platform):
    out = []
    assert lifecycle.stop(paths, fake_platform, out=out.append) == 0
    assert out == ["YT Toolkit ไม่ได้เปิดอยู่"]


def test_stop_graceful(paths, fake_platform):
    info = _running(paths, fake_platform)
    posts = []

    def post(url, json, headers, timeout):
        posts.append((url, json, headers))
        fake_platform.alive.discard(info.pid)  # แอพปิดตัวเอง
        return FakeResponse(200, {"ok": True})

    out = []
    assert lifecycle.stop(paths, fake_platform, post=post, sleep=lambda s: None, out=out.append) == 0
    url, body, headers = posts[0]
    assert url == "http://127.0.0.1:8787/api/shutdown"
    assert body == {"force": False}
    assert headers == {"X-Toolkit-Token": "tok", "Origin": "http://127.0.0.1:8787"}
    assert fake_platform.killed == []
    assert not paths.app_json.exists()
    assert out == ["ปิดโปรแกรมแล้ว"]


def test_stop_pending_user_declines(paths, fake_platform):
    _running(paths, fake_platform)
    result = lifecycle.stop(
        paths,
        fake_platform,
        post=lambda url, json, headers, timeout: FakeResponse(409, {"pendingJobs": 2}),
        ask=lambda prompt: "n",
        sleep=lambda s: None,
        out=lambda msg: None,
    )
    assert result == 1
    assert fake_platform.killed == []
    assert paths.app_json.exists()


def test_stop_pending_user_confirms_forces(paths, fake_platform):
    info = _running(paths, fake_platform)
    bodies = []

    def post(url, json, headers, timeout):
        bodies.append(json)
        if json["force"]:
            fake_platform.alive.discard(info.pid)
            return FakeResponse(200, {"ok": True})
        return FakeResponse(409, {"pendingJobs": 1})

    prompts = []

    def ask(prompt):
        prompts.append(prompt)
        return "Y"

    assert lifecycle.stop(paths, fake_platform, post=post, ask=ask, sleep=lambda s: None, out=lambda m: None) == 0
    assert bodies == [{"force": False}, {"force": True}]
    assert prompts == ["มีงานค้าง 1 งาน ปิดเลยไหม (Y/N) "]


def test_stop_kills_when_app_does_not_exit(paths, fake_platform):
    info = _running(paths, fake_platform)
    result = lifecycle.stop(
        paths,
        fake_platform,
        post=lambda url, json, headers, timeout: FakeResponse(200, {"ok": True}),
        sleep=lambda s: None,
        out=lambda m: None,
    )
    assert result == 0
    assert fake_platform.killed == [info.pid]


def test_stop_kills_when_api_unreachable(paths, fake_platform):
    info = _running(paths, fake_platform)

    def refused(url, json, headers, timeout):
        raise httpx.ConnectError("refused")

    lifecycle.stop(paths, fake_platform, post=refused, sleep=lambda s: None, out=lambda m: None)
    assert fake_platform.killed == [info.pid]
```

- [ ] **Step 2: เขียนเทส integration ที่ fail** (AC-LIFE-03, 06 และการปิดผ่านไฟล์ปิดโปรแกรม)

`tests/integration/test_serve.py`
```python
import os
import subprocess
import sys
import time

from yttoolkit import lifecycle, runstate
from yttoolkit.config import Paths
from yttoolkit.platform import current


def test_serve_then_stop(tmp_path):
    port = runstate.pick_port(range(8850, 8870))
    env = {**os.environ, "YT_TOOLKIT_DATA_ROOT": str(tmp_path), "YT_TOOLKIT_FFMPEG_PATH_LOOKUP": "0"}
    proc = subprocess.Popen([sys.executable, "-m", "yttoolkit", "serve", "--port", str(port)], env=env)
    paths = Paths(data_root=tmp_path)
    plat = current()
    try:
        deadline = time.monotonic() + 30
        info = None
        while time.monotonic() < deadline and info is None:
            info = lifecycle.find_running(paths, plat)
            time.sleep(0.2)
        assert info is not None, "serve ไม่ขึ้นภายใน 30 วินาที"
        assert info.port == port
        assert info.pid == proc.pid
        assert lifecycle.stop(paths, plat, out=lambda m: None) == 0
        assert proc.wait(timeout=15) == 0
        assert not paths.app_json.exists()
    finally:
        if proc.poll() is None:
            proc.kill()
```

- [ ] **Step 3: รันให้เห็นว่า fail**

Run: `uv run pytest tests/unit/test_lifecycle.py tests/integration -v`
Expected: FAIL `ImportError: cannot import name 'lifecycle'`

- [ ] **Step 4: เขียน `src/yttoolkit/lifecycle.py`**

```python
"""เปิด ปิด และดูแลวงจรชีวิตของแอพ (FR-LIFE-*)"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
import webbrowser
from collections.abc import Callable, Iterable
from pathlib import Path

import httpx
import uvicorn

from . import __version__, runstate
from .app import AppContext, create_app
from .config import HOST, Paths, default_paths, env_flag
from .core import tools
from .platform import Platform, current

log = logging.getLogger("yttoolkit")

DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


def base_url(port: int) -> str:
    return f"http://{HOST}:{port}"


def is_alive(port: int, get=httpx.get) -> bool:
    try:
        return get(f"{base_url(port)}/api/ping", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


def find_running(paths: Paths, plat: Platform, alive=is_alive) -> runstate.RunInfo | None:
    info = runstate.read(paths.app_json)
    if info and plat.pid_alive(info.pid) and alive(info.port):
        return info
    return None


def default_output_dir(plat: Platform) -> Path:
    return plat.downloads_dir() / "YT-Toolkit"


def prepare_environment() -> None:
    scripts = str(tools.scripts_dir())
    parts = os.environ.get("PATH", "").split(os.pathsep)
    if not parts or parts[0] != scripts:
        os.environ["PATH"] = os.pathsep.join([scripts, *[p for p in parts if p != scripts]])


def git_commit(root: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() or None


def setup_file_logging(paths: Paths) -> None:
    paths.logs.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(paths.logs / "app.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if sys.stdout is None or sys.stderr is None:  # pythonw.exe ไม่มี console
        stream = open(paths.logs / "console.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
        sys.stdout = sys.stdout or stream
        sys.stderr = sys.stderr or stream


class Server:
    """uvicorn ที่รันใน thread แยก เพื่อให้ main thread ว่างไว้ให้ tray"""

    def __init__(self, ctx: AppContext) -> None:
        self.config = uvicorn.Config(
            create_app(ctx), host=HOST, port=ctx.port, log_config=None, access_log=False
        )
        self._server = uvicorn.Server(self.config)
        self._thread = threading.Thread(target=self._server.run, name="uvicorn", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.should_exit = True

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout)

    def wait_until_ready(self, timeout: float = 15.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._server.started:
                return True
            if not self._thread.is_alive():
                return False
            time.sleep(0.1)
        return False


def ensure_ffmpeg(paths: Paths, plat: Platform) -> None:
    if tools.find_ffmpeg(paths, plat) is not None or plat.name != "windows":
        return
    try:
        tools.install_ffmpeg(paths, plat)
        log.info("ติดตั้ง ffmpeg อัตโนมัติสำเร็จ")
    except tools.ToolInstallError:
        log.exception("ติดตั้ง ffmpeg อัตโนมัติไม่สำเร็จ")


def run_app(
    *,
    paths: Paths,
    plat: Platform,
    port: int,
    with_tray: bool,
    open_browser: bool,
    auto_ffmpeg: bool,
    extra_origins: Iterable[str] = (),
) -> int:
    token = runstate.new_token()
    stop_event = threading.Event()
    tray_holder: list = []

    def request_shutdown() -> None:
        stop_event.set()
        if tray_holder:
            tray_holder[0].stop()

    ctx = AppContext(
        paths=paths,
        plat=plat,
        port=port,
        token=token,
        version=__version__,
        commit=git_commit(paths.code_root),
        output_dir=default_output_dir(plat),
        request_shutdown=request_shutdown,
        extra_origins=tuple(extra_origins),
    )
    server = Server(ctx)
    server.start()
    if not server.wait_until_ready():
        log.error("เปิดเซิร์ฟเวอร์ไม่สำเร็จที่ port %s", port)
        return 1
    runstate.write(
        paths.app_json, runstate.RunInfo(port=port, pid=os.getpid(), token=token, started_at=runstate.now_iso())
    )
    if auto_ffmpeg:
        threading.Thread(target=ensure_ffmpeg, args=(paths, plat), name="ffmpeg-setup", daemon=True).start()
    url = base_url(port)
    if open_browser:
        webbrowser.open(url)

    def open_output() -> None:
        ctx.output_dir.mkdir(parents=True, exist_ok=True)
        plat.open_folder(ctx.output_dir)

    def quit_from_tray() -> None:
        if ctx.pending_jobs() > 0:
            webbrowser.open(f"{url}/?confirmShutdown=1")  # หน้าเว็บถามยืนยัน (FR-LIFE-4, ทำใน M4)
        else:
            request_shutdown()

    try:
        if with_tray:
            from .tray import build_tray

            icon = build_tray(lambda: webbrowser.open(url), open_output, quit_from_tray)
            tray_holder.append(icon)
            icon.run()  # บล็อก main thread จนกว่าจะเรียก icon.stop()
        else:
            while not stop_event.wait(0.5):
                pass
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
        server.join(timeout=10)
        runstate.clear(paths.app_json)
    return 0


def start(paths: Paths | None = None, plat: Platform | None = None) -> int:
    paths = paths or default_paths()
    plat = plat or current()
    paths.ensure()
    setup_file_logging(paths)
    prepare_environment()
    running = find_running(paths, plat)
    if running:
        webbrowser.open(base_url(running.port))
        return 0
    return run_app(
        paths=paths,
        plat=plat,
        port=runstate.pick_port(),
        with_tray=env_flag("YT_TOOLKIT_TRAY", True),
        open_browser=env_flag("YT_TOOLKIT_OPEN_BROWSER", True),
        auto_ffmpeg=True,
    )


def serve(port: int | None = None, dev: bool = False) -> int:
    """รันแบบไม่มี tray และไม่เปิดเบราว์เซอร์ ใช้ตอนพัฒนา เทส และ E2E"""
    paths = default_paths()
    plat = current()
    paths.ensure()
    logging.basicConfig(level=logging.INFO)
    prepare_environment()
    return run_app(
        paths=paths,
        plat=plat,
        port=port or runstate.pick_port(),
        with_tray=False,
        open_browser=False,
        auto_ffmpeg=False,
        extra_origins=DEV_ORIGINS if dev else (),
    )


def stop(
    paths: Paths | None = None,
    plat: Platform | None = None,
    *,
    post=httpx.post,
    ask: Callable[[str], str] = input,
    sleep: Callable[[float], None] = time.sleep,
    out: Callable[[str], None] = print,
) -> int:
    paths = paths or default_paths()
    plat = plat or current()
    info = runstate.read(paths.app_json)
    if info is None or not plat.pid_alive(info.pid):
        runstate.clear(paths.app_json)
        out("YT Toolkit ไม่ได้เปิดอยู่")
        return 0
    url = f"{base_url(info.port)}/api/shutdown"
    headers = {"X-Toolkit-Token": info.token, "Origin": base_url(info.port)}
    try:
        response = post(url, json={"force": False}, headers=headers, timeout=5)
        if response.status_code == 409:
            pending = response.json().get("pendingJobs", 0)
            answer = ask(f"มีงานค้าง {pending} งาน ปิดเลยไหม (Y/N) ").strip().lower()
            if answer not in ("y", "yes"):
                out("ยกเลิกการปิดโปรแกรม")
                return 1
            post(url, json={"force": True}, headers=headers, timeout=5)
    except httpx.HTTPError:
        pass
    for _ in range(100):  # รอสูงสุด 10 วินาที (FR-LIFE-5)
        if not plat.pid_alive(info.pid):
            break
        sleep(0.1)
    else:
        plat.kill(info.pid)
    runstate.clear(paths.app_json)
    out("ปิดโปรแกรมแล้ว")
    return 0
```

- [ ] **Step 5: เขียน `src/yttoolkit/__main__.py`**

```python
from __future__ import annotations

import argparse
import sys

from . import lifecycle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="yttoolkit")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("start", help="เปิดโปรแกรม (tray + เบราว์เซอร์)")
    sub.add_parser("stop", help="ปิดโปรแกรม")
    serve = sub.add_parser("serve", help="รันเซิร์ฟเวอร์อย่างเดียว (พัฒนา/เทส)")
    serve.add_argument("--port", type=int)
    serve.add_argument("--dev", action="store_true", help="อนุญาต origin ของ Vite dev server")
    args = parser.parse_args(argv)
    if args.command == "start":
        return lifecycle.start()
    if args.command == "stop":
        return lifecycle.stop()
    return lifecycle.serve(port=args.port, dev=args.dev)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: รันให้ผ่าน**

Run: `uv run pytest -v`
Expected: ทุกเทสผ่าน รวม `tests/integration/test_serve.py::test_serve_then_stop`

- [ ] **Step 7: ลองมือบนเครื่องจริง**

```bash
uv run python -m yttoolkit start
```
Expected: ไอคอนอำพันขึ้นที่ tray · เบราว์เซอร์เปิด `http://127.0.0.1:8787` (หน้า 503 "ยังไม่ได้ build หน้าเว็บ" ถือว่าถูกต้องในขั้นนี้) · คลิกขวาไอคอน → "ปิดโปรแกรม" แล้วไอคอนหาย และ `run/app.json` ถูกลบ

- [ ] **Step 8: Commit**

```bash
git add src/yttoolkit/lifecycle.py src/yttoolkit/__main__.py tests/unit/test_lifecycle.py tests/integration
git commit -m "feat: add start, stop and serve lifecycle with single instance

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: `start.bat`, `stop.bat`, README และ checklist ตรวจมือ

**Files:**
- Create: `start.bat`, `stop.bat`, `README.md`, `docs/acceptance.md`

**Interfaces:**
- Consumes: CLI `yttoolkit start|stop` (Task 11) · `.venv\Scripts\pythonw.exe` ที่ `uv sync` สร้าง

- [ ] **Step 1: เขียน `start.bat`** (บันทึกเป็น UTF-8 ไม่มี BOM, บรรทัดแบบ CRLF ตาม `.gitattributes`)

```bat
@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "GIT_TERMINAL_PROMPT=0"
set "GCM_INTERACTIVE=never"
set "GIT_HTTP_LOW_SPEED_LIMIT=1000"
set "GIT_HTTP_LOW_SPEED_TIME=15"

echo [1/4] กำลังตรวจหาอัปเดต...
git pull --ff-only --quiet
if errorlevel 1 echo       ข้ามการอัปเดต ใช้เวอร์ชันเดิม

where uv >nul 2>nul
if errorlevel 1 set "PATH=%USERPROFILE%\.local\bin;%PATH%"
where uv >nul 2>nul
if errorlevel 1 (
  echo [2/4] กำลังติดตั้ง uv...
  powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
  if errorlevel 1 goto fail
) else (
  echo [2/4] มี uv แล้ว
)

echo [3/4] กำลังเตรียม Python และไลบรารี (ครั้งแรกใช้เวลา 1-2 นาที)...
uv sync --frozen --no-dev --quiet
if errorlevel 1 goto fail

echo [4/4] กำลังเปิด YT Toolkit...
start "" ".venv\Scripts\pythonw.exe" -m yttoolkit start
exit /b 0

:fail
echo.
echo เปิดโปรแกรมไม่สำเร็จ ถ่ายภาพหน้าจอนี้ส่งให้ผู้ดูแล แล้วกดปุ่มใดก็ได้เพื่อปิดหน้าต่าง
pause >nul
exit /b 1
```

- [ ] **Step 2: เขียน `stop.bat`**

```bat
@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo YT Toolkit ยังไม่ได้ติดตั้ง
  timeout /t 3 >nul
  exit /b 0
)
".venv\Scripts\python.exe" -m yttoolkit stop
timeout /t 3 >nul
```

- [ ] **Step 3: เขียน `README.md`** (ฉบับ M1 ฉบับเต็มพร้อมภาพทำใน M6)

````markdown
# YT Toolkit

เครื่องมือจัดการสื่อจากยูทูปที่รันบนเครื่องของคุณ เปิดผ่านเบราว์เซอร์ที่ `http://127.0.0.1:8787`
เอกสาร: [BRD.md](BRD.md) · [PRD.md](PRD.md)

## ติดตั้งบน Windows (ทำครั้งเดียว)
1. ลง Git: เปิด PowerShell แล้ววาง `winget install Git.Git`
2. รับคำเชิญเข้า repo นี้ที่ GitHub
3. วางคำสั่งนี้ใน PowerShell (ครั้งแรกจะเด้งให้ล็อกอิน GitHub ผ่านเบราว์เซอร์)
   ```powershell
   git clone https://github.com/ta-ai-pakorn/yt-toolkit.git "$env:USERPROFILE\YT-Toolkit"
   ```
4. เปิดโฟลเดอร์ `YT-Toolkit` แล้วดับเบิลคลิก `start.bat`

## เปิดและปิดโปรแกรม
- เปิด: ดับเบิลคลิก `start.bat` (อัปเดตเวอร์ชันใหม่ให้เองทุกครั้ง)
- ปิด: ดับเบิลคลิก `stop.bat` หรือคลิกขวาไอคอนสีอำพันที่มุมขวาล่าง → "ปิดโปรแกรม" หรือกดปุ่ม "ปิดโปรแกรม" ในหน้าตั้งค่า

## สำหรับผู้พัฒนา
```bash
uv sync                                   # ลง dependency รวมชุดเทส
uv run pytest                             # เทส Python
uv run python -m yttoolkit serve --dev    # backend (port 8787)
cd web && npm install && npm run dev      # หน้าเว็บ (port 5173) ต่อกับ backend ข้างบน
cd web && npm test && npm run e2e         # เทสหน้าเว็บ
cd web && npm run build                   # build แล้ว commit web/dist ด้วยทุกครั้ง
```
````

- [ ] **Step 4: เขียน `docs/acceptance.md`**

```markdown
# Checklist ตรวจมือ

## M1 (ทำบน Windows 10/11)
| AC | ขั้นตอน | ผ่าน |
|---|---|---|
| AC-LIFE-01 | สร้างบัญชีผู้ใช้ Windows ใหม่ ลงแค่ Git ทำตาม README ข้อ 1-4 จับเวลาจาก clone ถึงเบราว์เซอร์เปิดหน้าแรก ต้อง ≤ 10 นาที | ☐ |
| AC-LIFE-02 | ปิดแล้วดับเบิลคลิก `start.bat` อีกครั้ง หน้าแรกต้องขึ้นภายใน 5 วินาที | ☐ |
| AC-LIFE-03 | ขณะเปิดอยู่ ดับเบิลคลิก `start.bat` ซ้ำ ใน Task Manager ต้องมี `pythonw.exe` ของแอพตัวเดียว และเบราว์เซอร์เปิดแท็บไปที่ตัวเดิม | ☐ |
| AC-LIFE-04 | ปิดได้ทั้ง 3 ทาง: `stop.bat` / เมนู tray / ปุ่มในหน้าตั้งค่า ทุกทางแล้วไอคอนหายและ `run/app.json` ถูกลบ | ☐ |
| AC-LIFE-05 | ถอดเน็ตแล้วเปิด `start.bat` ขั้น 1/4 ต้องข้ามภายใน 15 วินาที แล้วแอพเปิดได้ | ☐ |
| AC-SEC-01 | จากเครื่องอื่นในวงเดียวกัน เปิด `http://<IP เครื่องนี้>:8787` ต้องเชื่อมต่อไม่ได้ | ☐ |
| ffmpeg | เครื่องใหม่ (ไม่มี ffmpeg) หลังเปิดแอพ 2-3 นาที หน้าตรวจสุขภาพต้องแสดง ffmpeg "พร้อม" | ☐ |
```

- [ ] **Step 5: ตรวจด้วยมือบนเครื่องพัฒนา**

ดับเบิลคลิก `start.bat` → เห็นขั้น 1/4 ถึง 4/4 เป็นภาษาไทยอ่านออก → tray ขึ้น → ดับเบิลคลิก `stop.bat` → ขึ้น "ปิดโปรแกรมแล้ว"
ถ้าข้อความภาษาไทยในหน้าต่างดำเพี้ยน: ตรวจว่าไฟล์เป็น UTF-8 ไม่มี BOM และบรรทัดแรกคือ `@echo off` ตามด้วย `chcp 65001`

- [ ] **Step 6: Commit**

```bash
git add start.bat stop.bat README.md docs/acceptance.md
git commit -m "feat: add windows start/stop scripts and install guide

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: สร้างโปรเจกต์หน้าเว็บ + ธีม Studio Dark

**Files:**
- Create: `web/` ทั้งโฟลเดอร์ (ผ่าน shadcn init), `web/public/favicon.svg`
- Modify: `web/index.html`, `web/src/index.css`, `web/src/components/ui/sonner.tsx`, `web/package.json`
- Delete: `web/.git`, `web/src/App.tsx`, `web/public/vite.svg` (ถ้ามี)

**Interfaces:**
- Produces: Tailwind tokens `bg-background text-foreground bg-card bg-primary text-primary-foreground text-muted-foreground border-border` + สีเพิ่ม `text-success text-warning text-info text-accent-text bg-surface-raised bg-surface-sunken` · ฟอนต์ `font-sans` (IBM Plex Sans Thai) `font-mono` (IBM Plex Mono) · คอมโพเนนต์ `@/components/ui/{button,card,badge,item,tabs,sonner,alert,spinner,skeleton,kbd,input-group,textarea,empty,separator,input}`

- [ ] **Step 1: สร้างโปรเจกต์และคอมโพเนนต์**

รันที่โฟลเดอร์ repo
```bash
npx -y shadcn@latest init -t vite -b base -p nova -n web --no-monorepo -y
rm -rf web/.git web/src/App.tsx web/public/vite.svg
cd web
npm uninstall @fontsource-variable/geist
npm install @fontsource/ibm-plex-sans-thai @fontsource/ibm-plex-mono react-router @tanstack/react-query
npm install -D vitest @playwright/test
npx shadcn@latest add card badge item tabs sonner alert spinner skeleton kbd input-group textarea empty -y
npm uninstall next-themes
```
Expected: `web/components.json` มี `"style": "base-nova"` และ `web/src/components/ui/` มีไฟล์ตามรายการ Interfaces

- [ ] **Step 2: แก้ `web/src/components/ui/sonner.tsx` ให้ใช้ theme provider ของเรา**

เปลี่ยนบรรทัด import
```tsx
import { useTheme } from "next-themes"
```
เป็น
```tsx
import { useTheme } from "@/components/theme-provider"
```

- [ ] **Step 3: เขียน `web/src/index.css` ใหม่ทั้งไฟล์** (ค่าตาม BRD ข้อ 10.2)

```css
@import "tailwindcss";
@import "tw-animate-css";
@import "shadcn/tailwind.css";
@import "@fontsource/ibm-plex-sans-thai/thai-400.css";
@import "@fontsource/ibm-plex-sans-thai/thai-500.css";
@import "@fontsource/ibm-plex-sans-thai/thai-600.css";
@import "@fontsource/ibm-plex-sans-thai/latin-400.css";
@import "@fontsource/ibm-plex-sans-thai/latin-500.css";
@import "@fontsource/ibm-plex-sans-thai/latin-600.css";
@import "@fontsource/ibm-plex-mono/latin-400.css";
@import "@fontsource/ibm-plex-mono/latin-500.css";

@custom-variant dark (&:is(.dark *));

@theme inline {
  --font-sans: "IBM Plex Sans Thai", ui-sans-serif, system-ui, sans-serif;
  --font-heading: var(--font-sans);
  --font-mono: "IBM Plex Mono", ui-monospace, monospace;
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-card: var(--card);
  --color-card-foreground: var(--card-foreground);
  --color-popover: var(--popover);
  --color-popover-foreground: var(--popover-foreground);
  --color-primary: var(--primary);
  --color-primary-foreground: var(--primary-foreground);
  --color-secondary: var(--secondary);
  --color-secondary-foreground: var(--secondary-foreground);
  --color-muted: var(--muted);
  --color-muted-foreground: var(--muted-foreground);
  --color-accent: var(--accent);
  --color-accent-foreground: var(--accent-foreground);
  --color-destructive: var(--destructive);
  --color-border: var(--border);
  --color-input: var(--input);
  --color-ring: var(--ring);
  --color-success: var(--success);
  --color-warning: var(--warning);
  --color-info: var(--info);
  --color-accent-text: var(--accent-text);
  --color-surface-raised: var(--surface-raised);
  --color-surface-sunken: var(--surface-sunken);
  --color-chart-1: var(--chart-1);
  --color-chart-2: var(--chart-2);
  --color-chart-3: var(--chart-3);
  --color-chart-4: var(--chart-4);
  --color-chart-5: var(--chart-5);
  --color-sidebar: var(--sidebar);
  --color-sidebar-foreground: var(--sidebar-foreground);
  --color-sidebar-primary: var(--sidebar-primary);
  --color-sidebar-primary-foreground: var(--sidebar-primary-foreground);
  --color-sidebar-accent: var(--sidebar-accent);
  --color-sidebar-accent-foreground: var(--sidebar-accent-foreground);
  --color-sidebar-border: var(--sidebar-border);
  --color-sidebar-ring: var(--sidebar-ring);
  --radius-sm: calc(var(--radius) * 0.75);
  --radius-md: var(--radius);
  --radius-lg: calc(var(--radius) * 1.25);
  --radius-xl: calc(var(--radius) * 1.5);
  --radius-2xl: calc(var(--radius) * 2);
  --radius-3xl: calc(var(--radius) * 2.5);
  --radius-4xl: calc(var(--radius) * 3);
}

/* ธีมสว่าง */
:root {
  --radius: 0.5rem;
  --background: #f7f6f3;
  --foreground: #1b1b1d;
  --card: #ffffff;
  --card-foreground: #1b1b1d;
  --popover: #ffffff;
  --popover-foreground: #1b1b1d;
  --primary: #f5b942;
  --primary-foreground: #1a1405;
  --secondary: #f0eeea;
  --secondary-foreground: #1b1b1d;
  --muted: #f0eeea;
  --muted-foreground: #5f6068;
  --accent: #f0eeea;
  --accent-foreground: #1b1b1d;
  --destructive: #c9373c;
  --border: rgb(0 0 0 / 0.08);
  --input: rgb(0 0 0 / 0.16);
  --ring: #f5b942;
  --success: #1f8a5b;
  --warning: #b85c12;
  --info: #2563c9;
  --accent-text: #9a6200;
  --surface-raised: #ffffff;
  --surface-sunken: #f0eeea;
  --chart-1: #f5b942;
  --chart-2: #2563c9;
  --chart-3: #1f8a5b;
  --chart-4: #b85c12;
  --chart-5: #5f6068;
  --sidebar: #ffffff;
  --sidebar-foreground: #1b1b1d;
  --sidebar-primary: #f5b942;
  --sidebar-primary-foreground: #1a1405;
  --sidebar-accent: #f0eeea;
  --sidebar-accent-foreground: #1b1b1d;
  --sidebar-border: rgb(0 0 0 / 0.08);
  --sidebar-ring: #f5b942;
}

/* ธีมมืด (Studio Dark เป็นหน้าตาหลัก) */
.dark {
  --background: #0e0f11;
  --foreground: #ececee;
  --card: #17181c;
  --card-foreground: #ececee;
  --popover: #1d1e23;
  --popover-foreground: #ececee;
  --primary: #f5b942;
  --primary-foreground: #1a1405;
  --secondary: #1d1e23;
  --secondary-foreground: #ececee;
  --muted: #1d1e23;
  --muted-foreground: #9a9ba3;
  --accent: #23242a;
  --accent-foreground: #ececee;
  --destructive: #f2555a;
  --border: rgb(255 255 255 / 0.08);
  --input: rgb(255 255 255 / 0.16);
  --ring: #f5b942;
  --success: #4cc38a;
  --warning: #f08c3a;
  --info: #6ca8f0;
  --accent-text: #f5b942;
  --surface-raised: #1d1e23;
  --surface-sunken: #0e0f11;
  --chart-1: #f5b942;
  --chart-2: #6ca8f0;
  --chart-3: #4cc38a;
  --chart-4: #f08c3a;
  --chart-5: #9a9ba3;
  --sidebar: #17181c;
  --sidebar-foreground: #ececee;
  --sidebar-primary: #f5b942;
  --sidebar-primary-foreground: #1a1405;
  --sidebar-accent: #23242a;
  --sidebar-accent-foreground: #ececee;
  --sidebar-border: rgb(255 255 255 / 0.08);
  --sidebar-ring: #f5b942;
}

@layer base {
  * {
    @apply border-border outline-ring/50;
  }
  html {
    @apply font-sans;
  }
  body {
    @apply bg-background text-foreground;
    line-height: 1.65;
  }
  .tabular {
    font-variant-numeric: tabular-nums;
  }
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
      animation-duration: 0.01ms !important;
      transition-duration: 0.01ms !important;
    }
  }
}
```

- [ ] **Step 4: เขียน `web/index.html` และ `web/public/favicon.svg`**

`web/index.html`
```html
<!doctype html>
<html lang="th">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>YT Toolkit</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`web/public/favicon.svg`
```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="13" fill="#F5B942"/><path d="M24 18v28l23-14z" fill="#1A1405"/></svg>
```

- [ ] **Step 5: ตั้ง script ใน `web/package.json`** (แก้เฉพาะส่วน `"scripts"`)

```json
"scripts": {
  "dev": "vite",
  "build": "tsc -b && vite build",
  "lint": "eslint .",
  "format": "prettier --write \"**/*.{ts,tsx}\"",
  "typecheck": "tsc --noEmit",
  "test": "vitest run",
  "e2e": "playwright test",
  "preview": "vite preview"
}
```

- [ ] **Step 6: Commit** (ยังไม่ build เพราะ `main.tsx` ยังอ้าง `App.tsx` ที่ลบไป จะแก้ใน Task 15)

```bash
git add web ':!web/node_modules'
git commit -m "feat(web): scaffold vite + shadcn base ui with studio dark tokens

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: ข้อความ, ชนิดข้อมูล และ API client ของหน้าเว็บ

**Files:**
- Create: `web/src/i18n/th.ts`, `web/src/lib/types.ts`, `web/src/lib/api.ts`, `web/src/lib/platform.ts`
- Test: `web/src/lib/api.test.ts`

**Interfaces:**
- Produces:
  - `th` (object ข้อความทั้งหมด)
  - `type ToolState = "ok" | "warn" | "error"` · `type ToolStatus` · `type Health` (ตรงกับ JSON ของ `/api/health`)
  - `class ApiError extends Error { status: number; code: string; detail: string | null; body: unknown }`
  - `readToken(doc?: Document): string`
  - `api<T>(path: string, init?: RequestInit, deps?: { fetch?: typeof fetch; token?: string }): Promise<T>`
  - `isMac(ua?: string): boolean` · `pasteShortcut(ua?: string): string`

- [ ] **Step 1: เขียน `web/src/i18n/th.ts`**

```ts
export const th = {
  app: { name: "YT Toolkit" },
  nav: { settings: "ตั้งค่า", home: "หน้าแรก" },
  home: {
    title: "วางลิงก์ยูทูป แล้วเลือกสิ่งที่อยากได้",
    subtitle: "วางได้หลายลิงก์ บรรทัดละลิงก์ หรือลิงก์เพลย์ลิสต์",
    pasteHint: "กด {key} ที่ไหนก็ได้",
    placeholder: "https://youtube.com/watch?v=...",
    analyze: "วิเคราะห์",
    notReady: "ระบบวิเคราะห์ลิงก์จะเปิดใช้ในเวอร์ชันถัดไป (M2)",
    usage: "ใช้กับคลิปขององค์กร คลิปที่ได้รับอนุญาต หรือเพื่อการศึกษาภายใน",
  },
  settings: {
    title: "ตั้งค่า",
    tabs: { health: "ตรวจสุขภาพระบบ", about: "เกี่ยวกับ" },
  },
  health: {
    status: { ok: "พร้อม", warn: "เตือน", error: "ใช้ไม่ได้" },
    rows: {
      ffmpeg: "โปรแกรมแปลงไฟล์ (ffmpeg)",
      ytdlp: "ตัวโหลด (yt-dlp)",
      jsRuntime: "ตัวช่วยของ yt-dlp",
      disk: "พื้นที่ดิสก์",
      output: "โฟลเดอร์ผลลัพธ์",
      network: "การเชื่อมต่อยูทูป",
    },
    reinstallFfmpeg: "โหลด ffmpeg ใหม่",
    installing: "กำลังโหลด ffmpeg อาจใช้เวลา 1-3 นาที",
    installed: "ติดตั้ง ffmpeg แล้ว",
    recheck: "ตรวจอีกครั้ง",
    shutdown: "ปิดโปรแกรม",
    loadError: "โหลดข้อมูลสุขภาพระบบไม่สำเร็จ",
    retry: "ลองใหม่",
  },
  about: {
    version: "เวอร์ชัน",
    commit: "รหัสเวอร์ชันโค้ด",
    usage: "ใช้กับคลิปขององค์กร คลิปที่ได้รับอนุญาต หรือเพื่อการศึกษาภายใน ห้ามนำไฟล์ไปเผยแพร่ซ้ำถ้าไม่มีสิทธิ์",
  },
  shutdown: {
    done: "ปิดโปรแกรมแล้ว",
    hint: "ปิดแท็บนี้ได้เลย ครั้งหน้าเปิดใหม่ได้จาก start.bat",
    pending: "มีงานค้าง {n} งาน ปิดตอนนี้งานจะหยุดกลางคัน",
  },
  errors: {
    unknown: 'มีบางอย่างผิดพลาด กด "คัดลอก" แล้วส่งให้ผู้ดูแล',
  },
} as const

export function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => String(values[key] ?? `{${key}}`))
}
```

- [ ] **Step 2: เขียน `web/src/lib/types.ts` และ `web/src/lib/platform.ts`**

`web/src/lib/types.ts`
```ts
export type ToolState = "ok" | "warn" | "error"

export type ToolStatus = {
  status: ToolState
  name: string | null
  version: string | null
  message: string | null
  path: string | null
}

export type Health = {
  version: string
  commit: string | null
  tools: { ffmpeg: ToolStatus; ytdlp: ToolStatus; jsRuntime: ToolStatus }
  disk: ToolStatus
  output: ToolStatus
  network: ToolStatus
}
```

`web/src/lib/platform.ts`
```ts
export function isMac(ua: string = navigator.userAgent): boolean {
  return /Mac OS X|Macintosh/.test(ua)
}

export function pasteShortcut(ua?: string): string {
  return isMac(ua) ? "⌘V" : "Ctrl+V"
}
```

- [ ] **Step 3: เขียนเทสที่ fail** `web/src/lib/api.test.ts`

```ts
import { describe, expect, it, vi } from "vitest"

import { ApiError, api } from "./api"
import { pasteShortcut } from "./platform"

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })
}

describe("api", () => {
  it("GET ไม่แนบ token", async () => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }))
    await api("/ping", {}, { fetch, token: "tok" })
    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe("/api/ping")
    expect(new Headers(init.headers).get("X-Toolkit-Token")).toBeNull()
  })

  it("POST แนบ token และ Content-Type", async () => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }))
    await api("/shutdown", { method: "POST", body: JSON.stringify({ force: false }) }, { fetch, token: "tok" })
    const headers = new Headers(fetch.mock.calls[0][1].headers)
    expect(headers.get("X-Toolkit-Token")).toBe("tok")
    expect(headers.get("Content-Type")).toBe("application/json")
  })

  it("แปลง error ของ backend เป็น ApiError", async () => {
    const body = { error: { code: "E_TOOL_INSTALL_FAILED", message: "โหลดไม่สำเร็จ", detail: "x" } }
    const fetch = vi.fn().mockResolvedValue(jsonResponse(502, body))
    const error = await api("/tools/ffmpeg/install", { method: "POST" }, { fetch, token: "t" }).catch((e) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(502)
    expect(error.code).toBe("E_TOOL_INSTALL_FAILED")
    expect(error.message).toBe("โหลดไม่สำเร็จ")
    expect(error.detail).toBe("x")
  })

  it("ตอบ 409 แบบไม่มี error object ยังได้ ApiError พร้อม body", async () => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse(409, { pendingJobs: 2 }))
    const error = await api("/shutdown", { method: "POST" }, { fetch, token: "t" }).catch((e) => e)
    expect(error.status).toBe(409)
    expect(error.code).toBe("E_UNKNOWN")
    expect(error.body).toEqual({ pendingJobs: 2 })
  })
})

describe("pasteShortcut", () => {
  it("แสดงตามระบบ", () => {
    expect(pasteShortcut("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)")).toBe("⌘V")
    expect(pasteShortcut("Mozilla/5.0 (Windows NT 10.0; Win64; x64)")).toBe("Ctrl+V")
  })
})
```

Run: `cd web && npm test`
Expected: FAIL `Failed to resolve import "./api"`

- [ ] **Step 4: เขียน `web/src/lib/api.ts`**

```ts
import { th } from "@/i18n/th"

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly detail: string | null
  readonly body: unknown

  constructor(status: number, code: string, message: string, detail: string | null, body: unknown) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.code = code
    this.detail = detail
    this.body = body
  }
}

export function readToken(doc: Document = document): string {
  return doc.querySelector<HTMLMetaElement>('meta[name="yt-token"]')?.content ?? ""
}

type Deps = { fetch?: typeof fetch; token?: string }

export async function api<T>(path: string, init: RequestInit = {}, deps: Deps = {}): Promise<T> {
  const doFetch = deps.fetch ?? fetch
  const method = (init.method ?? "GET").toUpperCase()
  const headers = new Headers(init.headers)
  if (method !== "GET" && method !== "HEAD") {
    headers.set("X-Toolkit-Token", deps.token ?? readToken())
    if (init.body !== undefined) headers.set("Content-Type", "application/json")
  }
  const res = await doFetch(`/api${path}`, { ...init, method, headers })
  const body: unknown = await res.json().catch(() => null)
  if (!res.ok) {
    const err = (body as { error?: { code?: string; message?: string; detail?: string | null } } | null)?.error
    throw new ApiError(res.status, err?.code ?? "E_UNKNOWN", err?.message ?? th.errors.unknown, err?.detail ?? null, body)
  }
  return body as T
}
```

- [ ] **Step 5: รันให้ผ่าน**

Run: `cd web && npm test`
Expected: `5 passed`

- [ ] **Step 6: Commit**

```bash
git add web/src/i18n web/src/lib
git commit -m "feat(web): add thai strings, api client and types

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 15: โครงหน้าเว็บ, router และหน้าแรก (W1)

**Files:**
- Create: `web/src/router.tsx`, `web/src/components/layout.tsx`, `web/src/pages/home.tsx`
- Modify: `web/src/main.tsx`
- Test: `web/e2e/home.spec.ts` (รันใน Task 17)

**Interfaces:**
- Consumes: `th`, `pasteShortcut`, คอมโพเนนต์ ui (Task 13-14)
- Produces: `router` (`createBrowserRouter`) มี route `/`, `/settings` (redirect → `/settings/health`), `/settings/health`, `/settings/about`, `*` (redirect → `/`) · `queryClient` · `Layout` (มี `<Outlet/>` และ `<Toaster/>`) · `HomePage` · `SettingsPage` (สร้างใน Task 16)

- [ ] **Step 1: เขียน `web/src/components/layout.tsx`**

```tsx
import { Settings } from "lucide-react"
import { Link, NavLink, Outlet } from "react-router"

import { Button } from "@/components/ui/button"
import { Toaster } from "@/components/ui/sonner"
import { th } from "@/i18n/th"

export function Layout() {
  return (
    <div className="min-h-svh">
      <header className="mx-auto flex max-w-[960px] items-center justify-between px-4 py-3">
        <Link to="/" className="flex items-center gap-2 font-medium" aria-label={th.nav.home}>
          <img src="/favicon.svg" alt="" className="size-6" />
          {th.app.name}
        </Link>
        <nav>
          <Button variant="ghost" size="sm" nativeButton={false} render={<NavLink to="/settings/health" />}>
            <Settings aria-hidden />
            {th.nav.settings}
          </Button>
        </nav>
      </header>
      <main className="mx-auto max-w-[960px] px-4 pb-16">
        <Outlet />
      </main>
      <Toaster position="bottom-right" />
    </div>
  )
}
```

หมายเหตุ: ปุ่มของ shadcn แบบ Base UI ใช้ prop `render` แทน `asChild` ถ้า `nativeButton` ไม่มีในเวอร์ชันที่ติดตั้ง ให้ลบ prop นั้นออก (ตรวจด้วย `npm run typecheck`)

- [ ] **Step 2: เขียน `web/src/pages/home.tsx`**

```tsx
import { useEffect, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import { InputGroup, InputGroupAddon, InputGroupTextarea } from "@/components/ui/input-group"
import { Kbd } from "@/components/ui/kbd"
import { th } from "@/i18n/th"
import { pasteShortcut } from "@/lib/platform"

export function HomePage() {
  const [text, setText] = useState("")
  const [note, setNote] = useState<string | null>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  function analyze(value: string) {
    if (!value.trim()) {
      inputRef.current?.focus()
      return
    }
    setNote(th.home.notReady)
  }

  useEffect(() => {
    function onPaste(event: ClipboardEvent) {
      const target = event.target as HTMLElement | null
      if (target && (target.tagName === "TEXTAREA" || target.tagName === "INPUT" || target.isContentEditable)) return
      const pasted = event.clipboardData?.getData("text") ?? ""
      if (!/youtu\.?be/.test(pasted)) return
      event.preventDefault()
      setText(pasted)
      analyze(pasted)
    }
    window.addEventListener("paste", onPaste)
    return () => window.removeEventListener("paste", onPaste)
  }, [])

  const [before, after] = th.home.pasteHint.split("{key}")

  return (
    <section className="mx-auto flex max-w-[560px] flex-col items-center gap-6 pt-16 text-center">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold leading-snug">{th.home.title}</h1>
        <p className="text-muted-foreground">
          {th.home.subtitle} · {before}
          <Kbd>{pasteShortcut()}</Kbd>
          {after}
        </p>
      </div>
      <form
        className="w-full text-left"
        onSubmit={(event) => {
          event.preventDefault()
          analyze(text)
        }}
      >
        <InputGroup>
          <InputGroupTextarea
            ref={inputRef}
            aria-label={th.home.placeholder}
            placeholder={th.home.placeholder}
            className="min-h-24"
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                event.preventDefault()
                analyze(text)
              }
            }}
          />
          <InputGroupAddon align="block-end" className="justify-end">
            <Button type="submit">{th.home.analyze}</Button>
          </InputGroupAddon>
        </InputGroup>
        {note && (
          <p role="status" className="mt-2 text-sm text-muted-foreground">
            {note}
          </p>
        )}
      </form>
      <p className="text-xs text-muted-foreground">{th.home.usage}</p>
    </section>
  )
}
```

- [ ] **Step 3: เขียน `web/src/router.tsx`** (ตัว `SettingsPage` สร้างใน Task 16 ให้สร้างไฟล์ชั่วคราวตาม Step 4 ก่อน)

```tsx
import { QueryClient } from "@tanstack/react-query"
import { Navigate, createBrowserRouter } from "react-router"

import { Layout } from "@/components/layout"
import { HomePage } from "@/pages/home"
import { SettingsPage } from "@/pages/settings"

export const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

export const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: "/", element: <HomePage /> },
      { path: "/settings", element: <Navigate to="/settings/health" replace /> },
      { path: "/settings/:tab", element: <SettingsPage /> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
])
```

- [ ] **Step 4: สร้าง `web/src/pages/settings.tsx` ขั้นต่ำให้ build ผ่าน** (Task 16 เขียนทับทั้งไฟล์)

```tsx
export function SettingsPage() {
  return null
}
```

- [ ] **Step 5: เขียน `web/src/main.tsx` ใหม่**

```tsx
import { QueryClientProvider } from "@tanstack/react-query"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { RouterProvider } from "react-router"

import "./index.css"
import { ThemeProvider } from "@/components/theme-provider"
import { queryClient, router } from "@/router"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider defaultTheme="system">
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>
)
```

- [ ] **Step 6: ตรวจ type และ build**

Run: `cd web && npm run typecheck && npm run build`
Expected: ไม่มี error · มี `web/dist/index.html`

- [ ] **Step 7: ตรวจด้วยตา**

```bash
uv run python -m yttoolkit serve
```
เปิด `http://127.0.0.1:8787` → เห็นหัวข้อภาษาไทย, Kbd `Ctrl+V`, ช่องวางลิงก์, ปุ่มอำพัน "วิเคราะห์" ปุ่มเดียว · ธีมตามเครื่อง · ภาษาไทยไม่ถูกตัดสระ

- [ ] **Step 8: Commit**

```bash
git add web/src web/dist
git commit -m "feat(web): add layout, router and home page shell (W1)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 16: หน้าตั้งค่า W6 (ตรวจสุขภาพระบบ + เกี่ยวกับ) และหน้าปิดโปรแกรม

**Files:**
- Create: `web/src/pages/settings/health-panel.tsx`, `web/src/pages/settings/about-panel.tsx`, `web/src/pages/shutdown.tsx`
- Modify: `web/src/pages/settings.tsx` (เขียนทับทั้งไฟล์)

**Interfaces:**
- Consumes: `api`, `ApiError`, `Health`, `ToolStatus`, `th`, `fill`
- Produces: `SettingsPage` · `HealthPanel` · `AboutPanel` · `ShutdownScreen` · `useHealth()` (query key `["health"]`) · แต่ละแถวสุขภาพมี `data-testid="tool-<key>"` โดย key ∈ `ffmpeg ytdlp jsRuntime disk output network`

- [ ] **Step 1: เขียน `web/src/pages/shutdown.tsx`**

```tsx
import { Power } from "lucide-react"

import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { th } from "@/i18n/th"

export function ShutdownScreen() {
  return (
    <Empty className="pt-24">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <Power aria-hidden />
        </EmptyMedia>
        <EmptyTitle>{th.shutdown.done}</EmptyTitle>
        <EmptyDescription>{th.shutdown.hint}</EmptyDescription>
      </EmptyHeader>
    </Empty>
  )
}
```

- [ ] **Step 2: เขียน `web/src/pages/settings/health-panel.tsx`**

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CircleAlert, CircleCheck, CircleX, Power, RefreshCw } from "lucide-react"
import { toast } from "sonner"

import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Item, ItemActions, ItemContent, ItemDescription, ItemGroup, ItemMedia, ItemTitle } from "@/components/ui/item"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { fill, th } from "@/i18n/th"
import { ApiError, api } from "@/lib/api"
import type { Health, ToolState, ToolStatus } from "@/lib/types"

type RowKey = keyof typeof th.health.rows

const ICON: Record<ToolState, typeof CircleCheck> = { ok: CircleCheck, warn: CircleAlert, error: CircleX }
const TONE: Record<ToolState, string> = { ok: "text-success", warn: "text-warning", error: "text-destructive" }

export function useHealth() {
  return useQuery({ queryKey: ["health"], queryFn: () => api<Health>("/health") })
}

function rows(health: Health): [RowKey, ToolStatus][] {
  return [
    ["ffmpeg", health.tools.ffmpeg],
    ["ytdlp", health.tools.ytdlp],
    ["jsRuntime", health.tools.jsRuntime],
    ["disk", health.disk],
    ["output", health.output],
    ["network", health.network],
  ]
}

function detail(key: RowKey, tool: ToolStatus): string {
  const parts = [
    key === "jsRuntime" ? tool.name : null,
    tool.version,
    tool.message,
    key === "output" ? tool.path : null,
  ]
  return parts.filter(Boolean).join(" · ")
}

export function HealthPanel({ onShutdown }: { onShutdown: () => void }) {
  const queryClient = useQueryClient()
  const health = useHealth()

  const install = useMutation({
    mutationFn: () => api<ToolStatus>("/tools/ffmpeg/install", { method: "POST" }),
    onMutate: () => toast.loading(th.health.installing, { id: "ffmpeg" }),
    onSuccess: () => {
      toast.success(th.health.installed, { id: "ffmpeg" })
      void queryClient.invalidateQueries({ queryKey: ["health"] })
    },
    onError: (error) => toast.error(error.message, { id: "ffmpeg", duration: Infinity }),
  })

  const shutdown = useMutation({
    mutationFn: () => api<{ ok: boolean }>("/shutdown", { method: "POST", body: JSON.stringify({ force: false }) }),
    onSuccess: onShutdown,
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) {
        const pending = (error.body as { pendingJobs?: number }).pendingJobs ?? 0
        toast.warning(fill(th.shutdown.pending, { n: pending }))
        return
      }
      toast.error(error.message)
    },
  })

  if (health.isPending) {
    return (
      <div className="flex flex-col gap-2" aria-busy="true">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-14 w-full" />
        ))}
      </div>
    )
  }

  if (health.isError) {
    return (
      <Alert variant="destructive">
        <CircleX aria-hidden />
        <AlertTitle>{th.health.loadError}</AlertTitle>
        <AlertDescription>{health.error.message}</AlertDescription>
        <AlertAction>
          <Button variant="outline" size="sm" onClick={() => void health.refetch()}>
            {th.health.retry}
          </Button>
        </AlertAction>
      </Alert>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <ItemGroup className="gap-2">
        {rows(health.data).map(([key, tool]) => {
          const Icon = ICON[tool.status]
          return (
            <Item key={key} variant="outline" data-testid={`tool-${key}`}>
              <ItemMedia>
                <Icon aria-hidden className={TONE[tool.status]} />
              </ItemMedia>
              <ItemContent>
                <ItemTitle>{th.health.rows[key]}</ItemTitle>
                <ItemDescription className="font-mono text-xs">{detail(key, tool) || " "}</ItemDescription>
              </ItemContent>
              <ItemActions>
                {key === "ffmpeg" && tool.status === "error" && (
                  <Button variant="outline" size="sm" disabled={install.isPending} onClick={() => install.mutate()}>
                    {install.isPending ? <Spinner /> : null}
                    {th.health.reinstallFfmpeg}
                  </Button>
                )}
                <Badge variant={tool.status === "error" ? "destructive" : "outline"}>{th.health.status[tool.status]}</Badge>
              </ItemActions>
            </Item>
          )
        })}
      </ItemGroup>
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="outline" onClick={() => void health.refetch()} disabled={health.isFetching}>
          <RefreshCw aria-hidden />
          {th.health.recheck}
        </Button>
        <Button variant="outline" onClick={() => shutdown.mutate()} disabled={shutdown.isPending}>
          <Power aria-hidden />
          {th.health.shutdown}
        </Button>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: เขียน `web/src/pages/settings/about-panel.tsx`**

```tsx
import { th } from "@/i18n/th"

import { useHealth } from "./health-panel"

export function AboutPanel() {
  const health = useHealth()
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
      <dt className="text-muted-foreground">{th.about.version}</dt>
      <dd className="font-mono">{health.data?.version ?? "…"}</dd>
      <dt className="text-muted-foreground">{th.about.commit}</dt>
      <dd className="font-mono">{health.data?.commit ?? "…"}</dd>
      <dd className="col-span-2 pt-4 text-muted-foreground">{th.about.usage}</dd>
    </dl>
  )
}
```

- [ ] **Step 4: เขียน `web/src/pages/settings.tsx` ทับทั้งไฟล์**

```tsx
import { useState } from "react"
import { useNavigate, useParams } from "react-router"

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { th } from "@/i18n/th"

import { ShutdownScreen } from "./shutdown"
import { AboutPanel } from "./settings/about-panel"
import { HealthPanel } from "./settings/health-panel"

const TABS = ["health", "about"] as const
type Tab = (typeof TABS)[number]

export function SettingsPage() {
  const { tab } = useParams()
  const navigate = useNavigate()
  const [closed, setClosed] = useState(false)
  const current: Tab = TABS.includes(tab as Tab) ? (tab as Tab) : "health"

  if (closed) return <ShutdownScreen />

  return (
    <section className="flex flex-col gap-6 pt-6">
      <h1 className="text-2xl font-semibold">{th.settings.title}</h1>
      <Tabs value={current} onValueChange={(value) => navigate(`/settings/${value}`)}>
        <TabsList>
          <TabsTrigger value="health">{th.settings.tabs.health}</TabsTrigger>
          <TabsTrigger value="about">{th.settings.tabs.about}</TabsTrigger>
        </TabsList>
        <TabsContent value="health" className="pt-4">
          <HealthPanel onShutdown={() => setClosed(true)} />
        </TabsContent>
        <TabsContent value="about" className="pt-4">
          <AboutPanel />
        </TabsContent>
      </Tabs>
    </section>
  )
}
```

- [ ] **Step 5: ตรวจ type, build และดูด้วยตา**

Run: `cd web && npm run typecheck && npm test && npm run build`
Expected: ผ่านทั้งหมด

```bash
uv run python -m yttoolkit serve
```
เปิด `http://127.0.0.1:8787/settings/health` → เห็น 6 แถว มีไอคอนและป้ายสถานะ · แท็บ "เกี่ยวกับ" แสดงเวอร์ชัน `0.1.0` และ commit · กด "ปิดโปรแกรม" → เห็นหน้า "ปิดโปรแกรมแล้ว" และ process ใน terminal จบเอง

- [ ] **Step 6: Commit**

```bash
git add web/src web/dist
git commit -m "feat(web): add settings health and about tabs with shutdown (W6)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 17: E2E (Playwright) + Vite dev proxy

**Files:**
- Create: `web/playwright.config.ts`, `web/e2e/home.spec.ts`, `web/e2e/health.spec.ts`
- Modify: `web/vite.config.ts`

**Interfaces:**
- Consumes: CLI `python -m yttoolkit serve --port 8799` · `data-testid="tool-ffmpeg"` (Task 16)

- [ ] **Step 1: เขียน `web/vite.config.ts` ใหม่**

```ts
import fs from "node:fs"
import path from "node:path"

import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig, type Plugin } from "vite"

const RUN_FILE = path.resolve(__dirname, "../run/app.json")

function readRunInfo(): { port: number; token: string } | null {
  try {
    return JSON.parse(fs.readFileSync(RUN_FILE, "utf8"))
  } catch {
    return null
  }
}

// ตอน dev ใส่ token ของ backend ที่รันด้วย `serve --dev` ลงใน index.html (แทนที่ backend ทำตอน production)
function devToken(): Plugin {
  return {
    name: "yt-dev-token",
    apply: "serve",
    transformIndexHtml(html) {
      const info = readRunInfo()
      return info ? html.replace("</head>", `<meta name="yt-token" content="${info.token}"></head>`) : html
    },
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss(), devToken()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    proxy: {
      "/api": { target: `http://127.0.0.1:${readRunInfo()?.port ?? 8787}`, changeOrigin: true },
    },
  },
})
```

- [ ] **Step 2: เขียน `web/playwright.config.ts`**

```ts
import os from "node:os"
import path from "node:path"

import { defineConfig, devices } from "@playwright/test"

const PORT = 8799
const dataRoot = path.join(os.tmpdir(), "yt-toolkit-e2e")

export default defineConfig({
  testDir: "e2e",
  timeout: 30_000,
  use: { baseURL: `http://127.0.0.1:${PORT}` },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `uv run python -m yttoolkit serve --port ${PORT}`,
    cwd: "..",
    url: `http://127.0.0.1:${PORT}/api/ping`,
    reuseExistingServer: false,
    timeout: 60_000,
    env: { YT_TOOLKIT_DATA_ROOT: dataRoot, YT_TOOLKIT_FFMPEG_PATH_LOOKUP: "0" },
  },
})
```

- [ ] **Step 3: เขียนเทส E2E**

`web/e2e/home.spec.ts`
```ts
import { expect, test } from "@playwright/test"

test("หน้าแรก W1 แสดงหัวข้อ ช่องวางลิงก์ และปุ่มหลักปุ่มเดียว", async ({ page }) => {
  await page.goto("/")
  await expect(page.getByRole("heading", { name: "วางลิงก์ยูทูป แล้วเลือกสิ่งที่อยากได้" })).toBeVisible()
  await expect(page.getByRole("textbox")).toBeVisible()
  await expect(page.getByRole("button", { name: "วิเคราะห์" })).toBeVisible()
  await expect(page.locator('meta[name="yt-token"]')).toHaveAttribute("content", /.{20,}/)
})
```

`web/e2e/health.spec.ts`
```ts
import { expect, test } from "@playwright/test"

test("AC-SET-02: ไม่มี ffmpeg → แสดงใช้ไม่ได้พร้อมปุ่มโหลดใหม่", async ({ page }) => {
  await page.goto("/settings/health")
  const row = page.getByTestId("tool-ffmpeg")
  await expect(row).toContainText("ใช้ไม่ได้", { timeout: 15_000 })
  await expect(row.getByRole("button", { name: "โหลด ffmpeg ใหม่" })).toBeVisible()
})

test("ตัวช่วยของ yt-dlp เป็น deno", async ({ page }) => {
  await page.goto("/settings/health")
  await expect(page.getByTestId("tool-jsRuntime")).toContainText("deno", { timeout: 15_000 })
})

test("แท็บเกี่ยวกับแสดงเวอร์ชัน", async ({ page }) => {
  await page.goto("/settings/about")
  await expect(page.getByText("0.1.0")).toBeVisible()
})
```

- [ ] **Step 4: ติดตั้ง browser แล้วรัน**

Run:
```bash
cd web
npx playwright install chromium
npm run e2e
```
Expected: `4 passed`

- [ ] **Step 5: ตรวจว่า dev proxy ใช้ได้**

Terminal 1: `uv run python -m yttoolkit serve --dev`
Terminal 2: `cd web && npm run dev` → เปิด `http://localhost:5173/settings/health` → ข้อมูลขึ้นครบ · กด "ปิดโปรแกรม" ได้ (ไม่ติด 403)

- [ ] **Step 6: Commit**

```bash
git add web/vite.config.ts web/playwright.config.ts web/e2e web/package.json web/package-lock.json
git commit -m "test(web): add playwright e2e for W1 and health page

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 18: CI บน GitHub Actions + ปิด M1

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `uv run pytest` · `npm run typecheck | test | build | e2e`

- [ ] **Step 1: เขียน `.github/workflows/ci.yml`**

```yaml
name: ci

on:
  push:
  pull_request:

jobs:
  python:
    strategy:
      fail-fast: false
      matrix:
        os: [windows-latest, macos-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v10
      - run: uv sync --frozen
      - run: uv run pytest -v

  web:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: web
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-node@v7
        with:
          node-version: 24
          cache: npm
          cache-dependency-path: web/package-lock.json
      - run: npm ci
      - run: npm run typecheck
      - run: npm test
      - run: npm run build
      - name: web/dist ต้องตรงกับ source
        run: |
          git status --porcelain -- dist
          test -z "$(git status --porcelain -- dist)"

  e2e:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v10
      - uses: actions/setup-node@v7
        with:
          node-version: 24
          cache: npm
          cache-dependency-path: web/package-lock.json
      - run: uv sync --frozen
      - run: npm ci
        working-directory: web
      - run: npx playwright install chromium
        working-directory: web
      - run: npm run e2e
        working-directory: web
```

- [ ] **Step 2: build หน้าเว็บล่าสุด รันเทสทั้งหมดในเครื่อง แล้ว push**

```bash
cd web && npm run build && cd ..
uv run pytest -v
git add .github web/dist
git commit -m "ci: run python tests on windows and macos, web checks and e2e

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push
```

- [ ] **Step 3: ดูผล CI**

Run: `gh run watch --exit-status`
Expected: job `python (windows-latest)`, `python (macos-latest)`, `web`, `e2e` ผ่านทั้งหมด
ถ้า `web` fail ที่ขั้น "web/dist ต้องตรงกับ source" แปลว่า build บน Linux ได้ไฟล์ไม่ตรงกับที่ commit ให้ดู diff ที่พิมพ์ออกมา แล้ว build ใหม่ด้วย `npm ci && npm run build` ก่อน commit

- [ ] **Step 4: ตรวจมือตาม `docs/acceptance.md` ส่วน M1 แล้วติ๊กผล**

ถ้าผ่านครบ commit ไฟล์ checklist ที่ติ๊กแล้ว
```bash
git add docs/acceptance.md
git commit -m "docs: record M1 manual acceptance results

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push
```

---

## ครอบคลุมเกณฑ์ของ M1 (PRD ข้อ 10)

| AC | ตรวจที่ |
|---|---|
| AC-LIFE-01 | ตรวจมือ (Task 18 Step 4) |
| AC-LIFE-02 | ตรวจมือ |
| AC-LIFE-03 | `test_find_running_*` (Task 11) + `test_serve_then_stop` + ตรวจมือ |
| AC-LIFE-04 | `test_stop_*` (Task 11) + ปุ่มปิดใน W6 (Task 16) + ตรวจมือ tray |
| AC-LIFE-05 | ตรวจมือ (`GIT_HTTP_LOW_SPEED_*` ใน `start.bat`) |
| AC-LIFE-06 | `test_pick_port_skips_busy_port` (Task 3) |
| AC-SEC-01 | `test_server_binds_localhost_only` (Task 11) + ตรวจมือจากเครื่องอื่น |
| AC-SEC-02 | `test_foreign_host_rejected_with_421`, `test_wrong_port_in_host_rejected` (Task 7) |
| AC-SEC-03 | `test_post_*` (Task 7) + `test_shutdown_requires_token` (Task 9) |
| AC-SEC-04 | ไม่อยู่ใน M1 (endpoint ส่งไฟล์มาใน M4) · ส่วน SPA ป้องกันด้วย `is_relative_to` (Task 8) |
| AC-SET-02 | `web/e2e/health.spec.ts` (Task 17) |

## สิ่งที่ตั้งใจเลื่อนออกไป
- ไอคอน tray แสดงจำนวนงานที่กำลังทำ (FR-LIFE-6): ทำใน M4 พร้อมคิว
- กล่องยืนยันปิดโปรแกรมในหน้าเว็บเมื่อมีงานค้าง (`?confirmShutdown=1`): ทำใน M4 ตอนนี้ backend เตรียม 409 และ tray เตรียมเปิดหน้านี้ไว้แล้ว
- แท็บ "ทั่วไป" ในหน้าตั้งค่า และปุ่ม "ตรวจหาอัปเดต": M4 / M6
- `start.command` / `stop.command` และ ffmpeg สำหรับ macOS: M7
