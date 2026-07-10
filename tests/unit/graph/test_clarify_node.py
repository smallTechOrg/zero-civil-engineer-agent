"""Clarify node — one pointed question, needs_input persistence, terminal done event.

Persistence is faked (thin stub) so the node runs without a DB; the real DB path
is covered by the integration suite.
"""

import time
from uuid import uuid4

import pytest

from graph import persistence
from graph.nodes import clarify
from graph.steps import initial_steps
from observability import progress


@pytest.fixture
def persisted(monkeypatch):
    calls: list[dict] = []

    def fake_finish_run(run_id, **kwargs):
        calls.append({"run_id": run_id, **kwargs})

    monkeypatch.setattr(persistence, "finish_run", fake_finish_run)
    monkeypatch.setattr(persistence, "session_cost_sum", lambda session_id: 0.0)
    return calls


def _state() -> dict:
    return {
        "run_id": f"test-{uuid4()}",
        "session_id": "session-1",
        "missing_critical": ["clear_span_m", "clear_height_m"],
        "plan_text": "Design a box culvert.",
        "token_usage": [
            {"node": "understand", "prompt_tokens": 100, "completion_tokens": 20, "latency_ms": 500},
        ],
        "started_monotonic": time.monotonic(),
        "steps": initial_steps(),
    }


def test_clarify_asks_exactly_one_question_and_ends_needs_input(persisted):
    state = _state()
    progress.register(state["run_id"])

    updates = clarify(state)

    events = list(progress.stream(state["run_id"]))
    clarifications = [e for e in events if e["event"] == "clarification"]
    assert len(clarifications) == 1
    assert clarifications[0]["data"]["missing_param"] == "clear_span_m"
    assert "span" in clarifications[0]["data"]["question"].lower()

    assert events[-1]["event"] == "done"
    assert events[-1]["data"] == {"status": "needs_input", "verdict": None}

    assert updates["status"] == "needs_input"
    assert updates["clarification_question"] == clarifications[0]["data"]["question"]


def test_clarify_persists_needs_input_with_question_and_tokens(persisted):
    state = _state()
    progress.register(state["run_id"])

    clarify(state)
    list(progress.stream(state["run_id"]))

    assert len(persisted) == 1
    record = persisted[0]
    assert record["run_id"] == state["run_id"]
    assert record["status"] == "needs_input"
    assert "span" in record["clarification_question"].lower()
    assert record["plan_text"] == "Design a box culvert."
    assert record["prompt_tokens"] == 100
    assert record["completion_tokens"] == 20
    assert record["cost_usd"] > 0
    assert record["duration_ms"] >= 0
