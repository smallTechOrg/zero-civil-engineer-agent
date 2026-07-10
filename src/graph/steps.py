"""The six fixed UI steps — SSE `step` events + the steps_json audit snapshot.

Mapping per spec/agent.md: Understand=understand · Extract=extract/clarify ·
Analyse=analyse · Check=check · Draw=draw+model3d · Review=review.
"""

import time
from datetime import datetime, timezone

from observability.progress import publish

STEP_NAMES = ("Understand", "Extract", "Analyse", "Check", "Draw", "Review")

_CLOSING_STATUSES = frozenset({"done", "skipped", "failed"})


def initial_steps() -> list[dict]:
    return [
        {"name": name, "status": "pending", "detail": None, "started_at": None, "ended_at": None}
        for name in STEP_NAMES
    ]


def elapsed_ms(state: dict) -> int:
    started = state.get("started_monotonic")
    if started is None:
        return 0
    return max(0, int((time.monotonic() - started) * 1000))


def duration_ms(state: dict) -> int:
    return elapsed_ms(state)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class StepTracker:
    """Per-node view of the step list: mutates a copy and publishes `step` events."""

    def __init__(self, state: dict) -> None:
        self._run_id = state.get("run_id", "")
        self._state = state
        self._steps = [dict(step) for step in (state.get("steps") or initial_steps())]

    @property
    def steps(self) -> list[dict]:
        return [dict(step) for step in self._steps]

    def mark(self, name: str, status: str, detail: str | None = None) -> None:
        publish(
            self._run_id,
            "step",
            {
                "step": name,
                "status": status,
                "detail": detail or "",
                "elapsed_ms": elapsed_ms(self._state),
            },
        )
        entry = next(step for step in self._steps if step["name"] == name)
        if status == "skipped" and entry["status"] == "done":
            # Never downgrade a completed step — a late "skipped" tag after the
            # real work is done is recorded as an event but not as state.
            return
        entry["status"] = status
        if detail:
            entry["detail"] = detail
        now = _now_iso()
        if status == "active" and entry["started_at"] is None:
            entry["started_at"] = now
        if status in _CLOSING_STATUSES:
            if entry["started_at"] is None:
                entry["started_at"] = now
            entry["ended_at"] = now
