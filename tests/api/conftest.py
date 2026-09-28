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
