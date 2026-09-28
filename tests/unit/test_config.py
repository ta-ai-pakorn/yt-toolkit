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
