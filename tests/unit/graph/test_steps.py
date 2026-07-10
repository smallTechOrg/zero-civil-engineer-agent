"""Step tracker — the six fixed UI steps, their events, and steps_json state."""

import time
from uuid import uuid4

from graph.steps import STEP_NAMES, StepTracker, initial_steps
from observability import progress


def _state(run_id: str | None = None) -> dict:
    return {
        "run_id": run_id or f"test-{uuid4()}",
        "started_monotonic": time.monotonic(),
        "steps": initial_steps(),
    }


def test_initial_steps_are_the_six_fixed_steps_pending():
    steps = initial_steps()
    assert [s["name"] for s in steps] == list(STEP_NAMES)
    assert [s["name"] for s in steps] == [
        "Understand", "Extract", "Analyse", "Check", "Draw", "Review",
    ]
    assert all(s["status"] == "pending" for s in steps)
    assert all(s["started_at"] is None and s["ended_at"] is None for s in steps)


def test_mark_active_then_done_records_timestamps():
    tracker = StepTracker(_state())
    tracker.mark("Understand", "active")
    entry = next(s for s in tracker.steps if s["name"] == "Understand")
    assert entry["status"] == "active"
    assert entry["started_at"] is not None

    tracker.mark("Understand", "done")
    entry = next(s for s in tracker.steps if s["name"] == "Understand")
    assert entry["status"] == "done"
    assert entry["ended_at"] is not None


def test_skipped_never_downgrades_a_done_step():
    """The guard stays post-Phase 3: a late 'skipped' tag never undoes real work."""
    tracker = StepTracker(_state())
    tracker.mark("Draw", "active")
    tracker.mark("Draw", "done")
    tracker.mark("Draw", "skipped", detail="a late skipped tag")
    entry = next(s for s in tracker.steps if s["name"] == "Draw")
    assert entry["status"] == "done"


def test_skipped_applies_to_a_pending_step():
    tracker = StepTracker(_state())
    tracker.mark("Check", "skipped", detail="Coming in Phase 2")
    entry = next(s for s in tracker.steps if s["name"] == "Check")
    assert entry["status"] == "skipped"
    assert entry["detail"] == "Coming in Phase 2"


def test_mark_publishes_step_event_with_exact_payload_shape():
    state = _state()
    run_id = state["run_id"]
    progress.register(run_id)

    tracker = StepTracker(state)
    tracker.mark("Extract", "active", detail="Extracting parameters")
    progress.publish(run_id, "done", {"status": "completed", "verdict": None})

    events = list(progress.stream(run_id))
    step_events = [e for e in events if e["event"] == "step"]
    assert len(step_events) == 1
    payload = step_events[0]["data"]
    assert set(payload) == {"step", "status", "detail", "elapsed_ms"}
    assert payload["step"] == "Extract"
    assert payload["status"] == "active"
    assert payload["detail"] == "Extracting parameters"
    assert isinstance(payload["elapsed_ms"], int) and payload["elapsed_ms"] >= 0


def test_skipped_event_still_published_even_when_state_keeps_done():
    state = _state()
    run_id = state["run_id"]
    progress.register(run_id)

    tracker = StepTracker(state)
    tracker.mark("Draw", "done")
    tracker.mark("Draw", "skipped", detail="a late skipped tag")
    progress.publish(run_id, "done", {"status": "completed", "verdict": None})

    statuses = [
        e["data"]["status"] for e in progress.stream(run_id) if e["event"] == "step"
    ]
    assert statuses == ["done", "skipped"]
