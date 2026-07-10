"""The real check node — IRS CBC rows in state, calc sheet streamed immediately.

Deterministic end to end (no LLM): real sizing + frame analysis feed the node;
assertions cover the state contract, the artefact row/event, and the
FAIL-rows-never-fail-the-run rule that the under-design demo depends on.
"""

import json
import time
from pathlib import Path
from uuid import uuid4

import pytest

from domain.culvert import CulvertParams
from engine import size_culvert
from engine.analysis import analyse_frame
from graph.nodes import _CHECK_ROW_KEYS, check
from graph.steps import initial_steps
from observability import progress

CANONICAL = {"clear_span_m": 4.0, "clear_height_m": 3.0, "cushion_m": 2.5}


def _engine_state(**overrides) -> dict:
    params = CulvertParams(**{**CANONICAL, **overrides})
    sizing = size_culvert(params)
    analysis = analyse_frame(params, sizing.geometry)
    return {
        "run_id": f"test-{uuid4()}",
        "session_id": "unit-session",
        "params": params.model_dump(mode="json"),
        "geometry": sizing.geometry.model_dump(),
        "analysis": analysis.model_dump(),
        "assumptions": [a.model_dump() for a in sizing.assumptions]
        + [a.model_dump() for a in analysis.assumptions],
        "trail_segments": [
            [s.model_dump() for s in sizing.trail],
            [s.model_dump() for s in analysis.trail],
        ],
        "warnings": list(sizing.warnings),
        "artefacts": [],
        "steps": initial_steps(),
        "started_monotonic": time.monotonic(),
    }


@pytest.fixture
def artifacts_root(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("AGENT_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    return tmp_path / "artifacts"


def _drain(run_id: str) -> list[dict]:
    progress.publish(run_id, "done", {"status": "completed", "verdict": None})
    return list(progress.stream(run_id))


def test_check_runs_real_cbc_checks_and_streams_the_calc_sheet(artifacts_root):
    state = _engine_state()
    progress.register(state["run_id"])

    updates = check(state)

    assert updates.get("error") is None
    # 13 rows: 4 per member (flexure/shear/min_steel/crack) x 3 members + cover.
    assert len(updates["checks"]) == 13
    for row in updates["checks"]:
        assert set(_CHECK_ROW_KEYS) <= set(row)
        assert row["status"] == "PASS"

    sheet = artifacts_root / state["run_id"] / "calc_sheet.json"
    assert sheet.is_file()
    doc = json.loads(sheet.read_text(encoding="utf-8"))
    assert [s["id"] for s in doc["sections"]] == [
        "design_basis", "loading", "analysis", "member_checks",
    ]

    events = _drain(state["run_id"])
    artefact_events = [e["data"] for e in events if e["event"] == "artefact"]
    assert [a["kind"] for a in artefact_events] == ["calc_sheet"]
    assert artefact_events[0]["filename"] == "calc_sheet.json"
    entry = next(s for s in updates["steps"] if s["name"] == "Check")
    assert entry["status"] == "done"
    assert "PASS" in entry["detail"]


def test_check_fail_rows_flow_to_the_proof_check_not_to_handle_error(artifacts_root):
    """The deliberate under-design: FAIL rows recorded, run NOT errored."""
    state = _engine_state(top_slab_thickness_mm=200)
    progress.register(state["run_id"])

    updates = check(state)

    assert updates.get("error") is None  # FAIL rows never fail the run
    failing = [row for row in updates["checks"] if row["status"] == "FAIL"]
    assert failing
    assert all("Top slab" in row["requirement"] for row in failing)
    assert (artifacts_root / state["run_id"] / "calc_sheet.json").is_file()
    entry = next(s for s in updates["steps"] if s["name"] == "Check")
    assert entry["status"] == "done"
    assert "FAIL" in entry["detail"]


def test_check_with_a_broken_record_routes_to_handle_error(artifacts_root):
    """A genuinely broken input (no analysis) is fatal-transparent."""
    state = _engine_state()
    state["analysis"] = None
    progress.register(state["run_id"])

    updates = check(state)

    assert updates["error"]
    assert "check" in updates["error"].lower()
    entry = next(s for s in updates["steps"] if s["name"] == "Check")
    assert entry["status"] == "failed"
