"""Guard-rail runs — scope gate and the one-clarifying-question rule.

Real Gemini + tmp DB; no drawing needed (these paths never reach `draw`).
"""

import json
from pathlib import Path


def test_out_of_scope_request_gets_a_graceful_scope_statement(
    require_gemini, make_session, run_and_wait, get_run, _integration_settings
):
    session_id = make_session()

    run_id, events = run_and_wait(session_id, "design a suspension bridge")

    assert events[-1]["event"] == "done"
    assert events[-1]["data"] == {"status": "out_of_scope", "verdict": None}

    row = get_run(run_id)
    assert row["status"] == "out_of_scope"
    assert row["scope_message"] and len(row["scope_message"]) > 20
    assert row["error_message"] is None  # informational, never an error
    assert row["suggestions_json"] is None  # chips are for COMPLETED designs only

    # Zero engine/drawing calls: no artefact events, no artefact directory.
    assert [e for e in events if e["event"] == "artefact"] == []
    assert not (Path(_integration_settings.artifacts_dir) / run_id).exists()

    steps = {s["name"]: s["status"] for s in json.loads(row["steps_json"])}
    assert steps["Understand"] == "done"
    assert steps["Analyse"] == "pending"
    assert steps["Draw"] == "pending"


def test_missing_span_asks_exactly_one_pointed_question(
    require_gemini, make_session, run_and_wait, get_run, _integration_settings
):
    session_id = make_session()

    run_id, events = run_and_wait(session_id, "box culvert 3 m height, 2 m cushion")

    assert events[-1]["event"] == "done"
    assert events[-1]["data"] == {"status": "needs_input", "verdict": None}

    clarifications = [e for e in events if e["event"] == "clarification"]
    assert len(clarifications) == 1
    assert clarifications[0]["data"]["missing_param"] == "clear_span_m"
    assert "span" in clarifications[0]["data"]["question"].lower()

    row = get_run(run_id)
    assert row["status"] == "needs_input"
    assert "span" in row["clarification_question"].lower()
    assert row["params_json"] is None  # nothing guessed, nothing defaulted
    assert row["suggestions_json"] is None  # clarify never reaches finalize
    assert row["prompt_tokens"] > 0  # the LLM calls really ran

    # No artefacts were generated for an unanswered run.
    assert [e for e in events if e["event"] == "artefact"] == []
    assert not (Path(_integration_settings.artifacts_dir) / run_id).exists()
