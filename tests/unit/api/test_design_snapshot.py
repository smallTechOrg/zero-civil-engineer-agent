"""GET /api/designs/{run_id} — full snapshot shape from a synthetic completed row."""

import json

CANONICAL_PARAMS = {
    "clear_span_m": 4.0,
    "clear_height_m": 3.0,
    "cushion_m": 2.5,
    "gauge": "BG",
    "tracks": 1,
    "loading_standard": "25t-2008",
    "concrete_grade": "M30",
    "steel_grade": "Fe500",
}


def _completed_run(make_session_row, make_run_row, utc) -> str:
    session_id = make_session_row(title="snapshot test")
    return make_run_row(
        session_id,
        prompt="single box culvert, 4 m clear span, 3 m height, 2.5 m cushion",
        status="completed",
        plan_text="Understand the request, extract parameters, size the box, draw the GA.",
        params_json=json.dumps(CANONICAL_PARAMS),
        assumptions_json=json.dumps(
            [{"field": "concrete_grade", "value": "M30", "source": "preset", "note": "IR standard defaults"}]
        ),
        warnings_json=json.dumps(["Cushion of 9.0 m is abnormally high"]),
        steps_json=json.dumps(
            [
                {"name": "Understand", "status": "done", "started_at": "t0", "ended_at": "t1"},
                {"name": "Draw", "status": "done", "started_at": "t1", "ended_at": "t2"},
            ]
        ),
        prompt_tokens=1200,
        completion_tokens=340,
        cost_usd=0.0049,
        started_at=utc(0),
        completed_at=utc(41),
        duration_ms=41500,
    )


def test_snapshot_parses_json_columns(api_client, make_session_row, make_run_row, make_artifact_row, utc):
    run_id = _completed_run(make_session_row, make_run_row, utc)
    make_artifact_row(run_id, kind="ga_dxf", filename="ga.dxf", mime="image/vnd.dxf", size_bytes=12345)
    make_artifact_row(run_id, kind="ga_svg", filename="ga.svg", mime="image/svg+xml", size_bytes=6789)

    r = api_client.get(f"/api/designs/{run_id}")
    assert r.status_code == 200
    d = r.json()["data"]

    assert d["run_id"] == run_id
    assert d["status"] == "completed"
    assert d["prompt"].startswith("single box culvert")
    assert d["plan_text"].startswith("Understand")
    assert d["params"]["clear_span_m"] == 4.0
    assert d["params"]["loading_standard"] == "25t-2008"
    assert d["assumptions"][0]["source"] == "preset"
    assert d["warnings"] == ["Cushion of 9.0 m is abnormally high"]
    assert [s["name"] for s in d["steps"]] == ["Understand", "Draw"]

    # Phase-gated fields stay null/empty in Phase 1
    assert d["checks"] == []
    assert d["checklist"] == []
    assert d["verdict"] is None
    assert d["suggestions"] == []

    artefacts = {a["filename"]: a for a in d["artefacts"]}
    assert artefacts["ga.dxf"]["url"] == f"/api/designs/{run_id}/artifacts/ga.dxf"
    assert artefacts["ga.dxf"]["size_bytes"] == 12345
    assert artefacts["ga.svg"]["kind"] == "ga_svg"

    assert d["tokens"] == {"prompt_tokens": 1200, "completion_tokens": 340, "cost_usd": 0.0049}
    assert d["error_message"] is None
    assert d["started_at"].startswith("2026-07-10T12:00:00")
    assert d["completed_at"].startswith("2026-07-10T12:00:41")
    assert d["duration_ms"] == 41500


def test_snapshot_empty_json_columns_default(api_client, make_session_row, make_run_row):
    session_id = make_session_row()
    run_id = make_run_row(session_id, status="running")

    r = api_client.get(f"/api/designs/{run_id}")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["params"] is None
    assert d["assumptions"] == []
    assert d["warnings"] == []
    assert d["steps"] == []
    assert d["artefacts"] == []
    assert d["tokens"] == {"prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0}
    assert d["completed_at"] is None
    assert d["duration_ms"] is None


def test_snapshot_failed_run_carries_error_message(api_client, make_session_row, make_run_row):
    session_id = make_session_row()
    run_id = make_run_row(session_id, status="failed", error_message="Gemini call failed after retry")

    r = api_client.get(f"/api/designs/{run_id}")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["status"] == "failed"
    assert d["error_message"] == "Gemini call failed after retry"


def test_snapshot_unknown_run_404(api_client):
    r = api_client.get("/api/designs/nope")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"
