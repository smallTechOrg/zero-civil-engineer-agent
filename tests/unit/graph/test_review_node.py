"""The real review node — narration-rejection fallback and LLM-transport fatality.

The engineering chain is REAL (sizing, analysis, checks, GA drawing, anaStruct
FE re-solve, 12-item checklist). Only the Gemini transport is replaced, because
these tests pin MY wiring policy around it: a grounding-rejected narration is
never fatal (deterministic memo stands), while a transport failure after the
provider's retry IS fatal-transparent. The real-LLM memo path is gated by
tests/integration/test_design_pipeline.py.
"""

import time
from uuid import uuid4

import pytest

import graph.nodes as nodes_module
from domain.culvert import CulvertParams
from drawing.ga import generate_ga
from engine import size_culvert
from engine.analysis import analyse_frame
from engine.checks import run_member_checks
from graph.steps import initial_steps
from llm.client import LLMResult
from observability import progress

CANONICAL = {"clear_span_m": 4.0, "clear_height_m": 3.0, "cushion_m": 2.5}
INVENTED = "The governing top-slab moment of 347.2 kN·m is acceptable."


class _FakeLLMClient:
    """Stands in for the Gemini transport only — behaviour set per test."""

    narration: str | None = None
    error: Exception | None = None

    def __init__(self) -> None:  # mirrors LLMClient() in the node
        pass

    def generate(self, prompt, *, system=None, schema=None, temperature=None):
        if type(self).error is not None:
            raise type(self).error
        return LLMResult(
            text=type(self).narration or "",
            parsed=None,
            prompt_tokens=100,
            completion_tokens=50,
            latency_ms=10,
        )


@pytest.fixture
def review_state(tmp_path, monkeypatch) -> dict:
    monkeypatch.setenv("AGENT_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    run_id = f"test-{uuid4()}"
    params = CulvertParams(**CANONICAL)
    sizing = size_culvert(params)
    analysis = analyse_frame(params, sizing.geometry)
    checks = run_member_checks(analysis, sizing.geometry, params)
    out_dir = tmp_path / "artifacts" / run_id
    out_dir.mkdir(parents=True)
    generate_ga(sizing.geometry, params, out_dir, run_id=run_id)  # review reads ga.dxf back
    monkeypatch.setattr(nodes_module, "LLMClient", _FakeLLMClient)
    _FakeLLMClient.narration = None
    _FakeLLMClient.error = None
    progress.register(run_id)
    return {
        "run_id": run_id,
        "session_id": "unit-session",
        "params": params.model_dump(mode="json"),
        "geometry": sizing.geometry.model_dump(),
        "analysis": analysis.model_dump(),
        "checks": [c.model_dump() for c in checks.checks],
        "assumptions": [a.model_dump() for a in sizing.assumptions],
        "warnings": [],
        "artefacts": [],
        "token_usage": [],
        "steps": initial_steps(),
        "started_monotonic": time.monotonic(),
    }


def _drain(run_id: str) -> list[dict]:
    progress.publish(run_id, "done", {"status": "completed", "verdict": None})
    return list(progress.stream(run_id))


def test_rejected_narration_falls_back_to_the_deterministic_memo(review_state, tmp_path):
    _FakeLLMClient.narration = INVENTED  # invented number -> grounding rejection

    updates = nodes_module.review(review_state)

    assert updates.get("error") is None  # rejection is NEVER fatal
    assert updates["verdict"] == "recommended_for_approval"
    assert len(updates["checklist"]) == 12
    assert updates["fe_comparison"]["within_tolerance"] is True

    memo = (
        tmp_path / "artifacts" / review_state["run_id"] / "proof_memo.md"
    ).read_text(encoding="utf-8")
    assert "347.2" not in memo  # the invented number never reaches the memo
    assert "RECOMMENDED FOR APPROVAL" in memo

    events = _drain(review_state["run_id"])
    kinds = [e["data"]["kind"] for e in events if e["event"] == "artefact"]
    assert kinds == ["bmd_svg", "sfd_svg", "compliance", "proof_memo"]
    warnings = [e["data"]["message"] for e in events if e["event"] == "warning"]
    assert any("grounding" in message for message in warnings)
    # The LLM call still registered its usage (tokens event published).
    assert any(e["event"] == "tokens" for e in events)
    entry = next(s for s in updates["steps"] if s["name"] == "Review")
    assert entry["status"] == "done"


def test_llm_transport_failure_is_fatal_transparent(review_state):
    _FakeLLMClient.error = RuntimeError("Gemini call failed after one retry")

    updates = nodes_module.review(review_state)

    assert updates["error"]
    assert "proof-check" in updates["error"].lower()
    entry = next(s for s in updates["steps"] if s["name"] == "Review")
    assert entry["status"] == "failed"
