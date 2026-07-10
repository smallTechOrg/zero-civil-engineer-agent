"""Phase-3 refinement suggestions — deterministic sanitisation + finalize wiring.

The Gemini transport is faked (the real-LLM path is gated by the integration
suite); these tests pin the policy: ONE structured call on COMPLETED runs only,
deterministic trim/validation of whatever comes back, `tokens` before `done`,
an unchanged `done` payload, and total swallowing of any failure (spec:
suggestions failure is invisible-degrading — the run stays `completed`).
"""

import json
import time

import pytest

import graph.nodes as nodes_module
from domain.culvert import CulvertParams
from engine import size_culvert
from graph import persistence
from graph.steps import initial_steps
from graph.suggestions import (
    MAX_SUGGESTIONS,
    SUGGESTION_MAX_CHARS,
    SuggestionsResult,
    sanitize_suggestions,
    run_summary,
)
from llm.client import LLMResult
from observability import progress

# --------------------------------------------------------------- sanitisation


def test_sanitize_strips_list_prefixes_and_whitespace():
    raw = [
        "1. Increase the clear cover to 60 mm",
        "2) Try a 5 m clear span variant  ",
        " - Reduce the cushion to 2 m",
        "(4) Use M35 concrete",
        "• Increase the haunch to 200 mm",
    ]
    cleaned = sanitize_suggestions(raw)
    assert cleaned[:3] == [
        "Increase the clear cover to 60 mm",
        "Try a 5 m clear span variant",
        "Reduce the cushion to 2 m",
    ]
    assert len(cleaned) == MAX_SUGGESTIONS  # capped at 3


def test_sanitize_keeps_a_leading_numeric_value_intact():
    # "450 mm" is a value, not a list prefix — it must survive untouched.
    assert sanitize_suggestions(["450 mm top slab economy check"]) == [
        "450 mm top slab economy check"
    ]


def test_sanitize_drops_empty_overlong_and_duplicate_items():
    raw = [
        "",
        "   ",
        "x" * (SUGGESTION_MAX_CHARS + 1),
        "Increase the cushion to 3 m",
        "increase the cushion to 3 M",  # case-insensitive duplicate
        "Try a 5 m clear span variant",
    ]
    assert sanitize_suggestions(raw) == [
        "Increase the cushion to 3 m",
        "Try a 5 m clear span variant",
    ]


def test_sanitize_boundary_length_and_empty_input():
    exactly_max = "y" * SUGGESTION_MAX_CHARS
    assert sanitize_suggestions([exactly_max]) == [exactly_max]
    assert sanitize_suggestions([]) == []


# ---------------------------------------------------------------- run summary


def _pipeline_state(run_id: str = "run-x", session_id: str = "sess-x") -> dict:
    params = CulvertParams(clear_span_m=4.0, clear_height_m=3.0, cushion_m=2.5)
    geometry = size_culvert(params).geometry
    return {
        "run_id": run_id,
        "session_id": session_id,
        "in_scope": True,
        "plan_text": "Design plan.",
        "params": params.model_dump(mode="json"),
        "geometry": geometry.model_dump(),
        "assumptions": [],
        "warnings": ["Top slab 200 mm is thinner than the sized 400 mm"],
        "checks": [],
        "checklist": [
            {"item": 7, "title": "Flexure — top slab", "severity": "NON_CONFORMITY_MAJOR"},
            {"item": 1, "title": "Loading standard & ACS level", "severity": "PASS"},
        ],
        "verdict": "return_for_revision",
        "artefacts": [],
        "token_usage": [
            {"node": "understand", "prompt_tokens": 100, "completion_tokens": 20, "latency_ms": 5}
        ],
        "steps": initial_steps(),
        "started_monotonic": time.monotonic(),
    }


def test_run_summary_carries_params_thicknesses_verdict_warnings_and_nonpass():
    summary = run_summary(_pipeline_state())
    assert "clear_span_m: 4.0" in summary
    assert "cushion_m: 2.5" in summary
    assert "top_slab_thickness_mm" in summary
    assert "Verdict: return_for_revision" in summary
    assert "thinner than the sized" in summary
    assert "Flexure — top slab" in summary  # non-PASS title surfaces
    assert "Loading standard & ACS level" not in summary  # PASS items stay out


# ------------------------------------------------------------ finalize wiring


class _FakeLLMClient:
    """Stands in for the Gemini transport only — behaviour set per test."""

    result: SuggestionsResult | None = None
    error: Exception | None = None
    calls: list[dict] = []

    def __init__(self) -> None:  # mirrors LLMClient() in the node
        pass

    def generate(self, prompt, *, system=None, schema=None, temperature=None):
        type(self).calls.append({"prompt": prompt, "system": system, "schema": schema})
        if type(self).error is not None:
            raise type(self).error
        return LLMResult(
            text="",
            parsed=type(self).result,
            prompt_tokens=200,
            completion_tokens=40,
            latency_ms=12,
        )


@pytest.fixture
def fake_llm(monkeypatch):
    monkeypatch.setattr(nodes_module, "LLMClient", _FakeLLMClient)
    _FakeLLMClient.result = None
    _FakeLLMClient.error = None
    _FakeLLMClient.calls = []
    return _FakeLLMClient


@pytest.fixture
def persisted_run():
    """A real run row in the isolated DB so finalize's persistence path is real."""
    from db.models import SessionRow
    from db.session import create_db_session

    with create_db_session() as session:
        row = SessionRow(title="unit")
        session.add(row)
        session.flush()
        session_id = row.id
    run_id = persistence.create_run_row(session_id, "canonical prompt")
    progress.register(run_id)
    return session_id, run_id


def _suggestions_json(run_id: str) -> str | None:
    from db.models import DesignRunRow
    from db.session import create_db_session

    with create_db_session() as session:
        return session.get(DesignRunRow, run_id).suggestions_json


def test_finalize_persists_sanitized_suggestions_and_orders_tokens_before_done(
    fake_llm, persisted_run
):
    session_id, run_id = persisted_run
    fake_llm.result = SuggestionsResult(
        suggestions=[
            "1. Increase the top slab to 450 mm",
            "Try a 5 m clear span variant",
            "  Reduce the cushion to 2 m  ",
        ]
    )
    state = _pipeline_state(run_id, session_id)

    updates = nodes_module.finalize(state)

    assert updates["status"] == "completed"
    expected = [
        "Increase the top slab to 450 mm",
        "Try a 5 m clear span variant",
        "Reduce the cushion to 2 m",
    ]
    assert updates["suggestions"] == expected
    assert json.loads(_suggestions_json(run_id)) == expected

    # ONE call, fed by suggest.md + the deterministic run summary
    assert len(fake_llm.calls) == 1
    call = fake_llm.calls[0]
    assert call["schema"] is SuggestionsResult
    assert call["system"] and "suggestion" in call["system"].lower()
    assert "Verdict: return_for_revision" in call["prompt"]
    assert "clear_span_m: 4.0" in call["prompt"]

    events = list(progress.stream(run_id))
    # tokens (suggestion call) then tokens (final totals) then done — header live
    kinds = [e["event"] for e in events]
    assert kinds == ["tokens", "tokens", "done"]
    assert events[0]["data"]["prompt_tokens"] == 300  # 100 prior + 200 suggestion call
    assert events[-1]["data"] == {
        "status": "completed",
        "verdict": "return_for_revision",
    }  # done payload unchanged per spec/api.md — no suggestions field


def test_suggestions_failure_is_swallowed_and_run_stays_completed(
    fake_llm, persisted_run
):
    session_id, run_id = persisted_run
    fake_llm.error = RuntimeError("Gemini call failed after one retry")

    updates = nodes_module.finalize(_pipeline_state(run_id, session_id))

    assert updates["status"] == "completed"
    assert updates["suggestions"] == []
    assert json.loads(_suggestions_json(run_id)) == []  # honest empty record

    events = list(progress.stream(run_id))
    assert [e["event"] for e in events] == ["tokens", "done"]  # no error event
    assert events[-1]["data"]["status"] == "completed"


def test_garbage_llm_output_degrades_to_empty_without_failing(fake_llm, persisted_run):
    session_id, run_id = persisted_run
    fake_llm.result = SuggestionsResult(
        suggestions=["", "   ", "z" * (SUGGESTION_MAX_CHARS + 40)]
    )

    updates = nodes_module.finalize(_pipeline_state(run_id, session_id))

    assert updates["status"] == "completed"
    assert updates["suggestions"] == []
    assert json.loads(_suggestions_json(run_id)) == []
    list(progress.stream(run_id))


def test_out_of_scope_run_makes_no_suggestions_call(fake_llm, persisted_run):
    session_id, run_id = persisted_run
    state = _pipeline_state(run_id, session_id)
    state["in_scope"] = False
    state["scope_message"] = "Out of scope."
    state["verdict"] = None
    state["params"] = None
    state["geometry"] = None
    state["checklist"] = []

    updates = nodes_module.finalize(state)

    assert updates["status"] == "out_of_scope"
    assert fake_llm.calls == []  # the LLM was never invoked
    assert _suggestions_json(run_id) is None

    events = list(progress.stream(run_id))
    assert events[-1]["data"] == {"status": "out_of_scope", "verdict": None}
