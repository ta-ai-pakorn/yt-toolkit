from __future__ import annotations

import threading

from yttoolkit.core.events import CLOSED, Event, EventBus


class Clock:
    def __init__(self):
        self.t = 0.0
        self.jobs = []

    def __call__(self):
        return self.t

    def schedule(self, delay, fn):
        self.jobs.append((self.t + delay, fn))

    def advance(self, dt):
        self.t += dt
        due = [j for j in self.jobs if j[0] <= self.t]
        self.jobs = [j for j in self.jobs if j[0] > self.t]
        for _, fn in due:
            fn()


def drain(sub):
    out = []
    while (e := sub.get(0)) is not None and e is not CLOSED:
        out.append(e)
    return out


def test_ac_q_08_at_most_four_updates_per_second():
    clock = Clock()
    bus = EventBus(monotonic=clock, schedule=clock.schedule)
    sub = bus.subscribe()
    for i in range(100):
        bus.job_updated("j1", {"progress": i / 100})
        clock.advance(0.01)
    events = drain(sub)
    assert 1 <= len(events) <= 5  # 1 s window: first emit + at most 4 flushes
    clock.advance(1.0)
    # the flush due at t = 1.0 may already be in the first drain (C6: last_emit + 0.25), so look at both
    last = (events + drain(sub))[-1]
    assert last.data == {"id": "j1", "progress": 0.99}  # nothing lost: the final value arrives


def test_other_jobs_are_independent():
    clock = Clock()
    bus = EventBus(monotonic=clock, schedule=clock.schedule)
    sub = bus.subscribe()
    bus.job_updated("a", {"progress": 0.1})
    bus.job_updated("b", {"progress": 0.2})
    assert [e.data["id"] for e in drain(sub)] == ["a", "b"]


def test_publish_is_immediate_and_close_wakes():
    bus = EventBus()
    sub = bus.subscribe()
    bus.publish("queue.paused", {"until": "x", "reason": "E_BOT_CHECK"})
    assert sub.get(0).name == "queue.paused"
    bus.close()
    assert sub.get(1) is CLOSED


def test_publish_keeps_its_own_copy_of_the_data():
    bus = EventBus()
    sub = bus.subscribe()
    data = {"id": "j1", "title": "คลิป"}
    bus.publish("job.created", data)
    data["title"] = "changed"
    data["extra"] = object()  # would break json.dumps in format_event if shared
    assert sub.get(0).data == {"id": "j1", "title": "คลิป"}


def test_pending_fields_merge_into_one_patch():
    clock = Clock()
    bus = EventBus(monotonic=clock, schedule=clock.schedule)
    sub = bus.subscribe()
    bus.job_updated("j", {"status": "running", "progress": 0.0})
    bus.job_updated("j", {"stage": "downloading_video", "progress": 0.1})
    bus.job_updated("j", {"progress": 0.2, "speedBps": 1000})
    assert [e.data for e in drain(sub)] == [{"id": "j", "status": "running", "progress": 0.0}]
    clock.advance(0.25)
    assert [e.data for e in drain(sub)] == [
        {"id": "j", "stage": "downloading_video", "progress": 0.2, "speedBps": 1000}
    ]
    assert clock.jobs == []  # one flush per window, not one per call


def test_update_after_quiet_period_is_immediate():
    clock = Clock()
    bus = EventBus(monotonic=clock, schedule=clock.schedule)
    sub = bus.subscribe()
    bus.job_updated("j", {"progress": 0.1})
    clock.advance(0.3)
    bus.job_updated("j", {"progress": 0.2})
    assert [e.data["progress"] for e in drain(sub)] == [0.1, 0.2]
    assert clock.jobs == []


def test_every_subscriber_gets_every_event_in_order():
    bus = EventBus()
    a, b = bus.subscribe(), bus.subscribe()
    bus.publish("job.created", {"id": "1"})
    bus.publish("queue.resumed", {})
    assert [e.name for e in drain(a)] == ["job.created", "queue.resumed"]
    assert [e.name for e in drain(b)] == ["job.created", "queue.resumed"]


def test_get_times_out_with_none():
    sub = EventBus().subscribe()
    assert sub.get(0) is None
    assert sub.get(0.01) is None


def test_events_queued_before_close_are_delivered_first():
    bus = EventBus()
    sub = bus.subscribe()
    bus.publish("app.shutdown", {})
    bus.close()
    assert sub.get(0) == Event("app.shutdown", {})
    assert sub.get(0) is CLOSED
    assert sub.get(0) is CLOSED


def test_closed_subscription_stops_receiving():
    bus = EventBus()
    sub = bus.subscribe()
    sub.close()
    bus.publish("queue.resumed", {})
    assert sub.get(0) is CLOSED
    assert bus.subscriber_count == 0


def test_subscribe_after_close_is_already_closed_and_publish_is_ignored():
    bus = EventBus()
    bus.close()
    sub = bus.subscribe()
    bus.publish("queue.resumed", {})
    bus.job_updated("j", {"progress": 1.0})
    assert sub.get(0) is CLOSED


def test_flush_after_close_emits_nothing():
    clock = Clock()
    bus = EventBus(monotonic=clock, schedule=clock.schedule)
    sub = bus.subscribe()
    bus.job_updated("j", {"progress": 0.1})
    bus.job_updated("j", {"progress": 0.2})
    assert len(drain(sub)) == 1
    bus.close()
    clock.advance(1.0)
    assert sub.get(0) is CLOSED


def test_slow_subscriber_is_closed_instead_of_growing_forever():
    bus = EventBus()
    slow = bus.subscribe()
    for i in range(EventBus.MAX_PENDING + 1):
        bus.publish("job.created", {"id": str(i)})
    # the client reconnects and refetches (C12), so dropping it loses nothing
    assert len(drain(slow)) == EventBus.MAX_PENDING
    assert slow.get(0) is CLOSED
    assert bus.subscriber_count == 0


def test_close_wakes_a_waiting_thread():
    bus = EventBus()
    sub = bus.subscribe()
    got = []
    t = threading.Thread(target=lambda: got.append(sub.get(10)))
    t.start()
    threading.Timer(0.05, bus.close).start()
    t.join(5)
    assert not t.is_alive()
    assert got == [CLOSED]


def test_default_scheduler_flushes_on_a_timer():
    bus = EventBus()
    sub = bus.subscribe()
    bus.job_updated("j", {"progress": 0.1})
    bus.job_updated("j", {"progress": 0.2})
    assert sub.get(0).data == {"id": "j", "progress": 0.1}
    later = sub.get(2)
    assert later is not None and later is not CLOSED
    assert later.data == {"id": "j", "progress": 0.2}
    bus.close()
