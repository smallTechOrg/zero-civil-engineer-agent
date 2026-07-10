"""POST /api/sessions/{id}/designs — happy path (patched runner) + 404/409/422."""

from sqlalchemy.orm import Session


def test_submit_design_happy_path(api_client, make_session_row, monkeypatch):
    session_id = make_session_row()
    calls = {}

    def fake_start(sess_id, prompt, preset_id=None, requested_component=None):
        calls["args"] = (sess_id, prompt, preset_id, requested_component)
        return "run-abc-123"

    monkeypatch.setattr("api.designs._start_design_run", fake_start)

    r = api_client.post(
        f"/api/sessions/{session_id}/designs",
        json={"prompt": "single box culvert, 4 m clear span, 3 m height, 2.5 m cushion"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data == {
        "run_id": "run-abc-123",
        "status": "running",
        "events_url": "/api/designs/run-abc-123/events",
        "snapshot_url": "/api/designs/run-abc-123",
    }
    # component_type omitted → auto-detect (requested_component is None)
    assert calls["args"] == (
        session_id,
        "single box culvert, 4 m clear span, 3 m height, 2.5 m cushion",
        None,
        None,
    )


def test_submit_design_passes_preset_id(api_client, make_session_row, monkeypatch):
    session_id = make_session_row()
    calls = {}
    monkeypatch.setattr(
        "api.designs._start_design_run",
        lambda s, p, preset_id=None, requested_component=None: calls.setdefault(
            "preset", preset_id
        )
        or "run-x",
    )
    r = api_client.post(
        f"/api/sessions/{session_id}/designs",
        json={"prompt": "box culvert 4 x 3, cushion 2.5", "preset_id": "preset-9"},
    )
    assert r.status_code == 200
    assert calls["preset"] == "preset-9"


def test_submit_design_passes_component_type_when_available(
    api_client, make_session_row, monkeypatch
):
    session_id = make_session_row()
    calls = {}
    monkeypatch.setattr(
        "api.designs._start_design_run",
        lambda s, p, preset_id=None, requested_component=None: calls.setdefault(
            "component", requested_component
        )
        or "run-y",
    )
    r = api_client.post(
        f"/api/sessions/{session_id}/designs",
        json={"prompt": "make me one", "component_type": "box_culvert"},
    )
    assert r.status_code == 200
    assert calls["component"] == "box_culvert"


def test_submit_design_unknown_component_type_422(api_client, make_session_row, monkeypatch):
    session_id = make_session_row()
    monkeypatch.setattr(
        "api.designs._start_design_run",
        lambda *a, **k: pytest_fail_never_called(),
    )
    r = api_client.post(
        f"/api/sessions/{session_id}/designs",
        json={"prompt": "design something", "component_type": "not_a_real_component"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "UNKNOWN_COMPONENT"


def pytest_fail_never_called():  # pragma: no cover - guards the 422-before-run path
    raise AssertionError("the run must not start for an unknown component type")


def test_submit_design_sets_title_from_first_prompt(
    api_client, _isolated_db, make_session_row, monkeypatch
):
    from db.models import SessionRow

    monkeypatch.setattr("api.designs._start_design_run", lambda *a, **k: "run-1")
    session_id = make_session_row(title="")
    long_prompt = "single box culvert, 4 m clear span, 3 m height, 2.5 m cushion, BG single line, 25t loading"

    r = api_client.post(f"/api/sessions/{session_id}/designs", json={"prompt": long_prompt})
    assert r.status_code == 200

    with Session(_isolated_db) as s:
        row = s.get(SessionRow, session_id)
        assert row.title == long_prompt[:60]


def test_submit_design_keeps_existing_title(
    api_client, _isolated_db, make_session_row, monkeypatch
):
    from db.models import SessionRow

    monkeypatch.setattr("api.designs._start_design_run", lambda *a, **k: "run-1")
    session_id = make_session_row(title="My culvert study")

    r = api_client.post(f"/api/sessions/{session_id}/designs", json={"prompt": "another turn"})
    assert r.status_code == 200

    with Session(_isolated_db) as s:
        assert s.get(SessionRow, session_id).title == "My culvert study"


def test_submit_design_unknown_session_404(api_client, monkeypatch):
    monkeypatch.setattr("api.designs._start_design_run", lambda *a, **k: "never")
    r = api_client.post("/api/sessions/no-such-session/designs", json={"prompt": "hi"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


def test_submit_design_active_run_409(api_client, make_session_row, make_run_row, monkeypatch):
    monkeypatch.setattr("api.designs._start_design_run", lambda *a, **k: "never")
    session_id = make_session_row()
    make_run_row(session_id, status="running")

    r = api_client.post(f"/api/sessions/{session_id}/designs", json={"prompt": "second turn"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "RUN_ACTIVE"


def test_submit_design_finished_run_does_not_block(
    api_client, make_session_row, make_run_row, monkeypatch
):
    monkeypatch.setattr("api.designs._start_design_run", lambda *a, **k: "run-2")
    session_id = make_session_row()
    make_run_row(session_id, status="completed")

    r = api_client.post(f"/api/sessions/{session_id}/designs", json={"prompt": "refine it"})
    assert r.status_code == 200


def test_submit_design_blank_prompt_422(api_client, make_session_row, monkeypatch):
    monkeypatch.setattr("api.designs._start_design_run", lambda *a, **k: "never")
    session_id = make_session_row()

    for payload in ({"prompt": ""}, {"prompt": "   \n\t"}, {}):
        r = api_client.post(f"/api/sessions/{session_id}/designs", json=payload)
        assert r.status_code == 422, payload
        assert r.json()["detail"]["code"] == "EMPTY_PROMPT"
