"""GET /api/components catalogue + component_type on POST designs (picker override).

The catalogue powers the picker/gallery; `component_type` on submit forces a
component (validated against the registry) and is threaded to the run as
`requested_component`. An unregistered/unavailable type is a 422 UNKNOWN_COMPONENT.
"""


# --------------------------------------------------------------------------- catalogue


def test_components_catalogue_lists_the_box_culvert(api_client):
    r = api_client.get("/api/components")
    assert r.status_code == 200
    components = r.json()["data"]["components"]
    by_id = {c["type_id"]: c for c in components}
    assert "box_culvert" in by_id
    culvert = by_id["box_culvert"]
    assert culvert["status"] == "available"
    assert culvert["display_name"] == "Box Culvert"
    # Exactly the spec/api.md GET /api/components row shape.
    assert set(culvert) == {
        "type_id", "display_name", "domain", "summary", "status", "codes", "example_prompt",
    }
    assert isinstance(culvert["codes"], list) and culvert["codes"]


def test_components_catalogue_envelope_is_the_ok_shape(api_client):
    body = api_client.get("/api/components").json()
    assert body["error"] is None
    assert "components" in body["data"]


# --------------------------------------------------------------------------- submit


def test_submit_with_valid_component_type_threads_requested_component(
    api_client, make_session_row, monkeypatch
):
    session_id = make_session_row()
    calls = {}

    def fake_start(sess_id, prompt, preset_id=None, requested_component=None, parent_run_id=None):
        calls["requested_component"] = requested_component
        return "run-rc-1"

    monkeypatch.setattr("api.designs._start_design_run", fake_start)

    r = api_client.post(
        f"/api/sessions/{session_id}/designs",
        json={"prompt": "single box culvert, 4 m span, 3 m height, 2.5 m cushion",
              "component_type": "box_culvert"},
    )
    assert r.status_code == 200
    assert calls["requested_component"] == "box_culvert"


def test_submit_with_unknown_component_type_is_422(api_client, make_session_row, monkeypatch):
    session_id = make_session_row()
    monkeypatch.setattr("api.designs._start_design_run", lambda *a, **k: "never")

    r = api_client.post(
        f"/api/sessions/{session_id}/designs",
        json={"prompt": "design something", "component_type": "no_such_component"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "UNKNOWN_COMPONENT"


def test_submit_without_component_type_auto_detects(api_client, make_session_row, monkeypatch):
    """Omitting component_type keeps the auto-detect path (no requested_component)."""
    session_id = make_session_row()
    calls = {}

    def fake_start(sess_id, prompt, preset_id=None):
        calls["args"] = (sess_id, prompt, preset_id)
        return "run-auto-1"

    monkeypatch.setattr("api.designs._start_design_run", fake_start)

    r = api_client.post(
        f"/api/sessions/{session_id}/designs",
        json={"prompt": "single box culvert, 4 m span, 3 m height, 2.5 m cushion"},
    )
    assert r.status_code == 200
    assert calls["args"][0] == session_id
