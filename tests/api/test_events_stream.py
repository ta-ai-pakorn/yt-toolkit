from __future__ import annotations

import threading
import time

import anyio
import pytest

from yttoolkit.api.events import build_events_router, format_event, sse_stream
from yttoolkit.core.events import Event, EventBus


class FakeMonotonic:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_format_event_is_compact_utf8_json():
    assert (
        format_event(Event("job.updated", {"id": "j", "title": "ไทย"}))
        == 'event: job.updated\ndata: {"id":"j","title":"ไทย"}\n\n'
    )


def test_format_event_keeps_newlines_inside_one_data_line():
    text = format_event(Event("job.created", {"title": "a\nb\r\nc"}))
    assert text.count("\n") == 3  # event line, data line, blank line


def test_sse_stream_retry_event_ping_then_ends_on_close():
    bus = EventBus()
    clock = FakeMonotonic()

    async def main() -> list[str]:
        out: list[str] = []
        gen = sse_stream(bus, poll_s=0.01, monotonic=clock)
        out.append(await gen.__anext__())
        bus.publish("job.created", {"id": "j1"})
        out.append(await gen.__anext__())
        clock.t = 15.5
        out.append(await gen.__anext__())
        bus.close()
        async for rest in gen:
            out.append(rest)
        return out

    assert anyio.run(main) == [
        "retry: 3000\n\n",
        'event: job.created\ndata: {"id":"j1"}\n\n',
        ": ping\n\n",
    ]
    assert bus.subscriber_count == 0


def test_sse_stream_does_not_ping_before_15_quiet_seconds():
    bus = EventBus()
    clock = FakeMonotonic()

    async def main() -> list[str]:
        out: list[str] = []
        gen = sse_stream(bus, poll_s=0.01, monotonic=clock)
        out.append(await gen.__anext__())
        clock.t = 14.0
        with anyio.move_on_after(0.1):
            out.append(await gen.__anext__())
        bus.close()
        async for rest in gen:
            out.append(rest)
        return out

    assert anyio.run(main) == ["retry: 3000\n\n"]


def test_sse_stream_closes_its_subscription_when_the_client_leaves():
    bus = EventBus()

    async def main() -> None:
        gen = sse_stream(bus, poll_s=5.0)
        await gen.__anext__()
        assert bus.subscriber_count == 1
        with anyio.move_on_after(0.05):
            await gen.__anext__()  # waits in a worker thread; cancelled like a disconnect
        await gen.aclose()

    started = time.monotonic()
    anyio.run(main)
    assert time.monotonic() - started < 2.0  # abandon_on_cancel: no waiting for poll_s
    assert bus.subscriber_count == 0
    bus.close()


def _publish_when_subscribed(bus: EventBus, name: str, data: dict) -> None:
    def run() -> None:
        deadline = time.monotonic() + 5
        while bus.subscriber_count == 0 and time.monotonic() < deadline:
            time.sleep(0.01)
        bus.publish(name, data)
        threading.Timer(0.2, bus.close).start()

    threading.Thread(target=run, daemon=True).start()


@pytest.fixture
def events_client(make_client, monkeypatch):
    """create_app รวม router นี้เองใน T11 ที่นี่จึงแทรก router ก่อน route หน้าเว็บที่รับทุก path"""
    import yttoolkit.app as app_module

    original = app_module.mount_web

    def mount_with_events(app, dist, token):
        app.include_router(build_events_router(app.state.ctx), prefix="/api")
        original(app, dist, token)

    monkeypatch.setattr(app_module, "mount_web", mount_with_events)
    return make_client


def test_get_events_streams_until_the_bus_closes(events_client):
    bus = EventBus()
    client = events_client(events=bus)
    _publish_when_subscribed(bus, "job.created", {"id": "j1", "title": "คลิป"})
    response = client.get("/api/events")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.text.startswith("retry: 3000\n\n")
    assert 'event: job.created\ndata: {"id":"j1","title":"คลิป"}\n\n' in response.text


def test_get_events_rejects_foreign_sites(events_client):
    bus = EventBus()
    client = events_client(events=bus)
    response = client.get("/api/events", headers={"Sec-Fetch-Site": "cross-site"})
    assert response.status_code == 403
    bus.close()
