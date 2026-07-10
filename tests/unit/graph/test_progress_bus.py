"""Progress event bus — the SSE endpoint consumes this API blind (pinned contract)."""

import threading
from uuid import uuid4

from observability import progress


def _rid() -> str:
    return f"test-{uuid4()}"


def test_publish_before_register_is_silent_noop():
    run_id = _rid()
    progress.publish(run_id, "narration", {"text": "nobody listening"})
    assert progress.is_active(run_id) is False
    assert list(progress.stream(run_id)) == []


def test_stream_yields_events_in_order_and_ends_on_done():
    run_id = _rid()
    progress.register(run_id)
    progress.publish(run_id, "step", {"step": "Understand", "status": "active"})
    progress.publish(run_id, "narration", {"text": "planning"})
    progress.publish(run_id, "done", {"status": "completed", "verdict": None})

    events = list(progress.stream(run_id))

    assert [e["event"] for e in events] == ["step", "narration", "done"]
    assert events[0]["data"]["step"] == "Understand"
    assert events[-1]["data"] == {"status": "completed", "verdict": None}


def test_stream_ends_on_error_event():
    run_id = _rid()
    progress.register(run_id)
    progress.publish(run_id, "error", {"code": "RUN_FAILED", "message": "boom"})

    events = list(progress.stream(run_id))

    assert [e["event"] for e in events] == ["error"]


def test_late_subscriber_replays_all_earlier_events():
    run_id = _rid()
    progress.register(run_id)
    for i in range(5):
        progress.publish(run_id, "narration", {"text": f"event {i}"})
    progress.publish(run_id, "done", {"status": "completed", "verdict": None})

    events = list(progress.stream(run_id))

    assert len(events) == 6
    assert [e["data"]["text"] for e in events[:5]] == [f"event {i}" for i in range(5)]


def test_is_active_lifecycle():
    run_id = _rid()
    assert progress.is_active(run_id) is False
    progress.register(run_id)
    assert progress.is_active(run_id) is True
    progress.publish(run_id, "done", {"status": "completed", "verdict": None})
    assert progress.is_active(run_id) is False


def test_publish_after_terminal_event_is_dropped():
    run_id = _rid()
    progress.register(run_id)
    progress.publish(run_id, "done", {"status": "completed", "verdict": None})
    progress.publish(run_id, "narration", {"text": "too late"})

    events = list(progress.stream(run_id))

    assert [e["event"] for e in events] == ["done"]


def test_channel_dropped_after_stream_of_finished_run():
    run_id = _rid()
    progress.register(run_id)
    progress.publish(run_id, "done", {"status": "completed", "verdict": None})
    assert len(list(progress.stream(run_id))) == 1
    # A second subscriber after the drop sees a closed, inactive run.
    assert list(progress.stream(run_id)) == []
    assert progress.is_active(run_id) is False


def test_concurrent_producer_consumer_delivers_all_in_order():
    run_id = _rid()
    progress.register(run_id)
    total = 200

    def produce():
        for i in range(total):
            progress.publish(run_id, "narration", {"text": f"n{i}"})
        progress.publish(run_id, "done", {"status": "completed", "verdict": None})

    collected: list[dict] = []

    def consume():
        collected.extend(progress.stream(run_id))

    consumer = threading.Thread(target=consume)
    consumer.start()
    producer = threading.Thread(target=produce)
    producer.start()
    producer.join(timeout=10)
    consumer.join(timeout=10)

    assert not consumer.is_alive(), "consumer must terminate after the done event"
    assert len(collected) == total + 1
    assert [e["data"]["text"] for e in collected[:-1]] == [f"n{i}" for i in range(total)]
    assert collected[-1]["event"] == "done"
