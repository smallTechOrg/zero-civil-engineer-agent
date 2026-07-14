"""POST /api/sessions/{id}/designs — the params-direct submit path.

The M-00004 module (sibling slice a) is not imported here: these unit tests
patch the component resolver + availability accessor with a fake standard-driven
module, exactly as the existing submit tests patch `_start_design_run`. They
pin the wiring contract (spec/api.md + capability doc): synchronous param
validation, `422 PARAMS_INVALID` / `422 PARAMS_REQUIRED`, component_type is
required with params, and the validated dict is threaded to the runner.
"""

import pytest
from pydantic import BaseModel, Field

from api.designs import ARTIFACT_FILES

M00004_TYPE = "m00004_box_culvert"


class _FakeM00004Params(BaseModel):
    """A minimal stand-in for the sibling slice's M00004Params (same criticals)."""

    clear_span_m: float = Field(ge=1.0, le=8.0)
    clear_height_m: float = Field(ge=1.0, le=8.0)
    cushion_m: float = Field(ge=0.0, le=6.0)
    surcharge_kn_m2: float = 0.0


class _FakeModule:
    type_id = M00004_TYPE
    param_model = _FakeM00004Params
    params_direct_only = True


def _patch_registry(monkeypatch):
    monkeypatch.setattr(
        "api.designs._component_is_available",
        lambda t: t in {M00004_TYPE, "box_culvert"},
    )
    monkeypatch.setattr("api.designs._resolve_component", lambda t: _FakeModule())


def test_valid_params_submit_threads_the_validated_dict(
    api_client, make_session_row, monkeypatch
):
    session_id = make_session_row()
    calls = {}

    def fake_start(sess_id, prompt, preset_id=None, requested_component=None, params=None):
        calls.update(
            sess_id=sess_id,
            prompt=prompt,
            requested_component=requested_component,
            params=params,
        )
        return "run-m4-1"

    _patch_registry(monkeypatch)
    monkeypatch.setattr("api.designs._start_design_run", fake_start)

    r = api_client.post(
        f"/api/sessions/{session_id}/designs",
        json={
            "component_type": M00004_TYPE,
            "params": {
                "clear_span_m": 4.0,
                "clear_height_m": 4.0,
                "cushion_m": 2.0,
                "surcharge_kn_m2": 0.0,
            },
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["run_id"] == "run-m4-1"
    assert calls["requested_component"] == M00004_TYPE
    # Threaded params are the VALIDATED dict (plain JSON dict), not the raw body.
    assert calls["params"] == {
        "clear_span_m": 4.0,
        "clear_height_m": 4.0,
        "cushion_m": 2.0,
        "surcharge_kn_m2": 0.0,
    }
    # A synthetic audit prompt was generated (no prompt supplied).
    assert "M-00004" in calls["prompt"] and "4" in calls["prompt"]


def test_params_without_component_type_is_422(api_client, make_session_row, monkeypatch):
    session_id = make_session_row()
    _patch_registry(monkeypatch)
    monkeypatch.setattr(
        "api.designs._start_design_run", lambda *a, **k: _never_start()
    )

    r = api_client.post(
        f"/api/sessions/{session_id}/designs",
        json={"params": {"clear_span_m": 4.0, "clear_height_m": 4.0, "cushion_m": 2.0}},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "COMPONENT_REQUIRED"


def test_invalid_params_out_of_range_is_422_params_invalid(
    api_client, make_session_row, monkeypatch
):
    session_id = make_session_row()
    _patch_registry(monkeypatch)
    monkeypatch.setattr(
        "api.designs._start_design_run", lambda *a, **k: _never_start()
    )

    r = api_client.post(
        f"/api/sessions/{session_id}/designs",
        json={
            "component_type": M00004_TYPE,
            # clear_span_m 20 is beyond the 1.0–8.0 hard range.
            "params": {"clear_span_m": 20.0, "clear_height_m": 4.0, "cushion_m": 2.0},
        },
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["code"] == "PARAMS_INVALID"
    assert "clear_span_m" in detail["message"]


def test_params_direct_only_component_without_params_is_422_params_required(
    api_client, make_session_row, monkeypatch
):
    session_id = make_session_row()
    _patch_registry(monkeypatch)
    monkeypatch.setattr(
        "api.designs._start_design_run", lambda *a, **k: _never_start()
    )

    r = api_client.post(
        f"/api/sessions/{session_id}/designs",
        json={"prompt": "make me the standard box culvert", "component_type": M00004_TYPE},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "PARAMS_REQUIRED"


def test_empty_params_dict_is_treated_as_missing(api_client, make_session_row, monkeypatch):
    """An empty `params` object is not a params-direct submit — a form-only
    component still rejects it with PARAMS_REQUIRED."""
    session_id = make_session_row()
    _patch_registry(monkeypatch)
    monkeypatch.setattr(
        "api.designs._start_design_run", lambda *a, **k: _never_start()
    )

    r = api_client.post(
        f"/api/sessions/{session_id}/designs",
        json={"prompt": "std box culvert", "component_type": M00004_TYPE, "params": {}},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "PARAMS_REQUIRED"


def test_m00004_sheet_pdf_is_whitelisted_inline():
    assert ARTIFACT_FILES["m00004_sheet.pdf"] == ("application/pdf", "inline")


def test_non_whitelisted_artefact_filename_still_400(api_client):
    # The filename whitelist is checked before run existence — a bogus filename
    # is rejected 400 regardless of run.
    r = api_client.get("/api/designs/any-run/artifacts/evil.exe")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "INVALID_FILENAME"


def _never_start():  # pragma: no cover - guards the 422-before-run paths
    raise AssertionError("the run must not start when the submit is rejected")
