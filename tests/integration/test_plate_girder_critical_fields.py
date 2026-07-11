"""Plate girder — steel_grade is now a SECOND critical field alongside span_m
(spec/capabilities/plate-girder.md). Real Gemini + tmp DB, full graph runs.

Regression coverage:
  - both missing -> span asked first (critical_fields tuple order)
  - span given, grade missing -> exactly one clarifying question naming E250/E350
  - answering the clarification with the grade completes the design
  - a fully-specified prompt (both critical fields stated) never clarifies
"""

VERDICTS = {"recommended_for_approval", "return_for_revision"}


def test_both_critical_fields_missing_asks_span_first(
    require_gemini, drawing_ready, make_session, run_and_wait, get_run, _integration_settings,
):
    session_id = make_session()
    run_id, events = run_and_wait(session_id, "design a plate girder bridge, BG single line")

    assert events[-1]["data"] == {"status": "needs_input", "verdict": None}
    row = get_run(run_id)
    assert row["status"] == "needs_input"
    question = (row["clarification_question"] or "").lower()
    assert "span" in question
    assert "steel" not in question and "grade" not in question


def test_only_steel_grade_missing_asks_one_question_naming_both_grades(
    require_gemini, drawing_ready, make_session, run_and_wait, get_run, _integration_settings,
):
    session_id = make_session()
    run_id, events = run_and_wait(
        session_id, "design a plate girder bridge, 30 m span, BG single line"
    )

    assert events[-1]["data"] == {"status": "needs_input", "verdict": None}
    row = get_run(run_id)
    assert row["status"] == "needs_input"
    question = row["clarification_question"] or ""
    assert "E250" in question
    assert "E350" in question


def test_answering_steel_grade_clarification_completes_the_design(
    require_gemini, drawing_ready, make_session, run_and_wait, get_run, _integration_settings,
):
    session_id = make_session()
    first_id, first_events = run_and_wait(
        session_id, "design a plate girder bridge, 30 m span, BG single line"
    )
    assert first_events[-1]["data"] == {"status": "needs_input", "verdict": None}

    second_id, second_events = run_and_wait(session_id, "E350")

    done = second_events[-1]["data"]
    assert done["status"] == "completed"
    assert done["verdict"] in VERDICTS
    row = get_run(second_id)
    import json

    params = json.loads(row["params_json"])
    assert params["steel_grade"] == "E350"
    assert params["span_m"] == 30.0


def test_fully_specified_prompt_never_clarifies(
    require_gemini, drawing_ready, make_session, run_and_wait, get_run, _integration_settings,
):
    session_id = make_session()
    run_id, events = run_and_wait(
        session_id, "30 m span plate girder in E250 steel, BG single line"
    )

    assert events[-1]["event"] != "clarification"
    row = get_run(run_id)
    assert row["status"] == "completed"
    assert row["verdict"] in VERDICTS

    import json

    params = json.loads(row["params_json"])
    assert params["span_m"] == 30.0
    assert params["steel_grade"] == "E250"
