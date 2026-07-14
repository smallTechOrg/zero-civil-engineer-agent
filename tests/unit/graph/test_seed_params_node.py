"""The seed_params node — deterministic params-direct entry, ZERO LLM calls.

The M-00004 module (sibling slice a) is not imported: the node is exercised with
a fake standard-driven module patched onto `_module`, and `LLMClient` is patched
with a guard that fails if the node ever touches it. That proves the params
form bypasses the LLM understand/extract intake.
"""

import time
from uuid import uuid4

from pydantic import BaseModel, Field

from graph import nodes
from graph.nodes import seed_params
from graph.steps import initial_steps


class _FakeParams(BaseModel):
    clear_span_m: float = Field(ge=1.0, le=8.0)
    clear_height_m: float = Field(ge=1.0, le=8.0)
    cushion_m: float = Field(ge=0.0, le=6.0)
    surcharge_kn_m2: float = 0.0


class _FakeModule:
    display_name = "M-00004 Standard Box Culvert (RDSO)"
    param_model = _FakeParams

    def __init__(self, warnings=None):
        self._warnings = warnings or []

    def unusual_value_warnings(self, params):
        # Mirrors the real interface: called with a param_model instance.
        assert isinstance(params, _FakeParams)
        return list(self._warnings)


class _ExplodingLLM:
    def __init__(self, *a, **k):  # pragma: no cover - must never be constructed
        raise AssertionError("seed_params must NOT construct an LLM client")


def _state(**overrides) -> dict:
    base = {
        "run_id": f"seed-{uuid4()}",
        "session_id": "unit-session",
        "params_direct": True,
        "params": {"clear_span_m": 4.0, "clear_height_m": 4.0, "cushion_m": 2.0},
        "warnings": [],
        "steps": initial_steps(),
        "started_monotonic": time.monotonic(),
    }
    base.update(overrides)
    return base


def _steps_by_name(steps: list[dict]) -> dict:
    return {s["name"]: s for s in steps}


def test_seed_params_marks_understand_and_extract_done_without_llm(monkeypatch):
    monkeypatch.setattr(nodes, "LLMClient", _ExplodingLLM)
    monkeypatch.setattr(nodes, "_module", lambda state: _FakeModule())

    updates = seed_params(_state())

    steps = _steps_by_name(updates["steps"])
    assert steps["Understand"]["status"] == "done"
    assert steps["Extract"]["status"] == "done"
    assert "parameter form" in steps["Understand"]["detail"].lower()
    assert updates["in_scope"] is True
    assert updates["plan_text"]
    # No error, and the LLM guard was never triggered (construction would raise).
    assert "error" not in updates


def test_seed_params_surfaces_module_unusual_value_warnings(monkeypatch):
    monkeypatch.setattr(nodes, "LLMClient", _ExplodingLLM)
    warnings = ["fill 3.0 m exceeds digitized range (0–2 m); using 2 m standard config"]
    monkeypatch.setattr(nodes, "_module", lambda state: _FakeModule(warnings=warnings))

    updates = seed_params(_state(params={"clear_span_m": 7.0, "clear_height_m": 7.0, "cushion_m": 3.0}))

    assert updates["warnings"] == warnings
    assert _steps_by_name(updates["steps"])["Extract"]["status"] == "done"


def test_seed_params_reports_error_when_module_raises(monkeypatch):
    monkeypatch.setattr(nodes, "LLMClient", _ExplodingLLM)

    class _Boom:
        display_name = "boom"
        param_model = _FakeParams

        def unusual_value_warnings(self, params):
            raise RuntimeError("module blew up")

    monkeypatch.setattr(nodes, "_module", lambda state: _Boom())

    updates = seed_params(_state())

    assert "error" in updates
    assert _steps_by_name(updates["steps"])["Extract"]["status"] == "failed"
