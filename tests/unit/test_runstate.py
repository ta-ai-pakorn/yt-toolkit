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


def test_now_iso_is_utc_iso8601_with_timezone():  # M1 follow-up item 8
    from datetime import datetime, timedelta

    value = runstate.now_iso()
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timedelta(0)
    assert value.endswith("+00:00")
    assert "T" in value
