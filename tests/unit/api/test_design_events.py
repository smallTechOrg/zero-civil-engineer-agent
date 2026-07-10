"""GET /api/designs/{run_id}/events — SSE contract for finished and interrupted runs.

Live streaming from the in-process bus is the graph slice's surface; here we
patch the bus accessors and verify THIS endpoint's framing/relay behaviour.
"""

import json


def test_events_finished_run_snapshot_then_done(api_client, make_session_row, make_run_row, parse_sse, utc):
    session_id = make_session_row()
    run_id = make_run_row(
        session_id,
        status="completed",
        params_json=json.dumps({"clear_span_m": 4.0, "clear_height_m": 3.0, "cushion_m": 2.5}),
        started_at=utc(0),
        completed_at=utc(30),
        duration_ms=30000,
    )

    r = api_client.get(f"/api/designs/{run_id}/events")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["cache-control"] == "no-cache"

    frames = parse_sse(r.text)
    assert [event for event, _ in frames] == ["snapshot", "done"]

    snapshot = frames[0][1]
    assert snapshot["run_id"] == run_id
    assert snapshot["status"] == "completed"
    assert snapshot["params"]["clear_span_m"] == 4.0

    done = frames[1][1]
    assert done == {"status": "completed", "verdict": None}


def test_events_needs_input_run_done_carries_status(api_client, make_session_row, make_run_row, parse_sse):
    session_id = make_session_row()
    run_id = make_run_row(
        session_id, status="needs_input", clarification_question="What is the clear span?"
    )

    r = api_client.get(f"/api/designs/{run_id}/events")
    frames = parse_sse(r.text)
    assert frames[0][0] == "snapshot"
    assert frames[0][1]["clarification_question"] == "What is the clear span?"
    assert frames[1] == ("done", {"status": "needs_input", "verdict": None})


def test_events_failed_run_snapshot_then_error(api_client, make_session_row, make_run_row, parse_sse):
    session_id = make_session_row()
    run_id = make_run_row(session_id, status="failed", error_message="Gemini timed out twice")

    r = api_client.get(f"/api/designs/{run_id}/events")
    frames = parse_sse(r.text)
    assert [event for event, _ in frames] == ["snapshot", "error"]
    assert frames[1][1]["code"] == "RUN_FAILED"
    assert "Gemini timed out twice" in frames[1][1]["message"]


def test_events_running_run_relays_bus_events(
    api_client, make_session_row, make_run_row, parse_sse, monkeypatch
):
    session_id = make_session_row()
    run_id = make_run_row(session_id, status="running")

    bus_events = [
        {"event": "step", "data": {"step": "Draw", "status": "active", "detail": "", "elapsed_ms": 12000}},
        {"event": "narration", "data": {"text": "Drawing the GA sheet"}},
        {"event": "done", "data": {"status": "completed", "verdict": None}},
    ]
    monkeypatch.setattr("api.designs._progress_is_active", lambda rid: rid == run_id)
    monkeypatch.setattr("api.designs._progress_stream", lambda rid: iter(bus_events))

    r = api_client.get(f"/api/designs/{run_id}/events")
    frames = parse_sse(r.text)
    assert [event for event, _ in frames] == ["snapshot", "step", "narration", "done"]
    assert frames[1][1]["step"] == "Draw"
    assert frames[3][1]["status"] == "completed"


def test_events_running_row_but_dead_bus_emits_error(
    api_client, make_session_row, make_run_row, parse_sse, monkeypatch
):
    """Row says running but the bus has no live run (e.g. server restarted mid-run)."""
    session_id = make_session_row()
    run_id = make_run_row(session_id, status="running")

    monkeypatch.setattr("api.designs._progress_is_active", lambda rid: False)

    r = api_client.get(f"/api/designs/{run_id}/events")
    frames = parse_sse(r.text)
    assert [event for event, _ in frames] == ["snapshot", "error"]
    assert frames[1][1]["code"] == "RUN_FAILED"


def test_events_unknown_run_404(api_client):
    r = api_client.get("/api/designs/ghost/events")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"
