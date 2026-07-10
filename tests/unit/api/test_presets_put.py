"""PUT /api/presets/{preset_id} — preset editing per spec/api.md.

Values are whitelisted to NON-critical CulvertParams fields and range/enum-checked
by the real CulvertParams validators. Editing a preset never rewrites run history.
"""

import json

from sqlalchemy.orm import Session


def _db_preset(engine, preset_id):
    """(name, is_default, values, updated_at) straight from the DB."""
    from db.models import PresetRow

    with Session(engine) as s:
        row = s.get(PresetRow, preset_id)
        return row.name, row.is_default, json.loads(row.values_json), row.updated_at


# --- Happy paths ----------------------------------------------------------------


def test_put_merges_values_renames_and_bumps_updated_at(
    api_client, make_preset_row, _isolated_db, utc
):
    preset_id = make_preset_row(
        name="IR standard defaults",
        values={"concrete_grade": "M30", "clear_cover_mm": 50},
        updated_at=utc(0),
    )
    _, _, _, updated_before = _db_preset(_isolated_db, preset_id)

    r = api_client.put(
        f"/api/presets/{preset_id}",
        json={"name": "IR defaults v2", "values": {"clear_cover_mm": 40, "soil_unit_weight_kn_m3": 19.0}},
    )
    assert r.status_code == 200
    data = r.json()["data"]

    # Same shape as a GET /api/presets item.
    assert set(data.keys()) == {"preset_id", "name", "is_default", "values"}
    assert data["preset_id"] == preset_id
    assert data["name"] == "IR defaults v2"
    assert data["is_default"] is True
    # Merged: untouched key kept, edited key updated, new key added.
    assert data["values"] == {
        "concrete_grade": "M30",
        "clear_cover_mm": 40,
        "soil_unit_weight_kn_m3": 19.0,
    }

    name, is_default, values, updated_after = _db_preset(_isolated_db, preset_id)
    assert (name, is_default, values) == ("IR defaults v2", True, data["values"])
    assert updated_after > updated_before

    # GET reflects the edit with the identical entry.
    listed = api_client.get("/api/presets").json()["data"]["presets"]
    assert data in listed


def test_put_values_only_partial_update(api_client, make_preset_row, _isolated_db):
    preset_id = make_preset_row(name="Keep me", values={"clear_cover_mm": 50})

    r = api_client.put(f"/api/presets/{preset_id}", json={"values": {"clear_cover_mm": 45}})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["name"] == "Keep me"
    assert data["values"] == {"clear_cover_mm": 45}


def test_put_name_only_partial_update(api_client, make_preset_row):
    preset_id = make_preset_row(name="Old name", values={"clear_cover_mm": 50})

    r = api_client.put(f"/api/presets/{preset_id}", json={"name": "New name"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["name"] == "New name"
    assert data["values"] == {"clear_cover_mm": 50}


def test_put_thickness_set_then_cleared_to_autosize(api_client, make_preset_row):
    preset_id = make_preset_row(values={})

    r = api_client.put(
        f"/api/presets/{preset_id}", json={"values": {"top_slab_thickness_mm": 450}}
    )
    assert r.status_code == 200
    assert r.json()["data"]["values"] == {"top_slab_thickness_mm": 450}

    # null clears the override — key removed, engine auto-sizes again.
    r = api_client.put(
        f"/api/presets/{preset_id}", json={"values": {"top_slab_thickness_mm": None}}
    )
    assert r.status_code == 200
    assert "top_slab_thickness_mm" not in r.json()["data"]["values"]


# --- Error paths ------------------------------------------------------------------


def test_put_unknown_preset_404(api_client):
    r = api_client.put("/api/presets/no-such-preset", json={"name": "x"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


def test_put_empty_body_422(api_client, make_preset_row):
    preset_id = make_preset_row()
    r = api_client.put(f"/api/presets/{preset_id}", json={})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "EMPTY_UPDATE"


def test_put_critical_field_rejected(api_client, make_preset_row, _isolated_db):
    preset_id = make_preset_row(values={"clear_cover_mm": 50})
    r = api_client.put(f"/api/presets/{preset_id}", json={"values": {"clear_span_m": 5.0}})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["code"] == "INVALID_FIELD"
    assert "clear_span_m" in detail["message"]
    # Nothing persisted.
    assert _db_preset(_isolated_db, preset_id)[2] == {"clear_cover_mm": 50}


def test_put_unknown_field_rejected(api_client, make_preset_row):
    preset_id = make_preset_row()
    r = api_client.put(f"/api/presets/{preset_id}", json={"values": {"vent_area_m2": 2.0}})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["code"] == "INVALID_FIELD"
    assert "vent_area_m2" in detail["message"]


def test_put_out_of_range_value_rejected(api_client, make_preset_row, _isolated_db):
    preset_id = make_preset_row(values={"clear_cover_mm": 50})
    r = api_client.put(f"/api/presets/{preset_id}", json={"values": {"clear_cover_mm": 30}})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["code"] == "INVALID_VALUE"
    # Human-readable: names the field, the offending value, and the FULL valid
    # range — BOTH bounds (40–75 per spec/data.md / design-library.md).
    assert "clear_cover_mm" in detail["message"]
    assert "30" in detail["message"]
    assert "40" in detail["message"]
    assert "75" in detail["message"]
    assert "outside the valid range" in detail["message"]
    assert _db_preset(_isolated_db, preset_id)[2] == {"clear_cover_mm": 50}


def test_put_bad_enum_rejected(api_client, make_preset_row):
    preset_id = make_preset_row()
    r = api_client.put(f"/api/presets/{preset_id}", json={"values": {"concrete_grade": "M99"}})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["code"] == "INVALID_VALUE"
    assert "concrete_grade" in detail["message"]
    assert "M25" in detail["message"]  # allowed grades named


def test_put_invalid_thickness_rejected(api_client, make_preset_row):
    # Thickness overrides carry no declared ge/le bounds (None = auto-size); the
    # custom validator's message states the rule, so it passes through unchanged.
    preset_id = make_preset_row()
    r = api_client.put(
        f"/api/presets/{preset_id}", json={"values": {"top_slab_thickness_mm": -100}}
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["code"] == "INVALID_VALUE"
    assert "top_slab_thickness_mm" in detail["message"]
    assert "positive" in detail["message"]


def test_put_null_on_non_nullable_field_rejected(api_client, make_preset_row):
    # Only thickness overrides are clearable; other fields must carry a value.
    preset_id = make_preset_row()
    r = api_client.put(f"/api/presets/{preset_id}", json={"values": {"clear_cover_mm": None}})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["code"] == "INVALID_VALUE"
    assert "clear_cover_mm" in detail["message"]


def test_put_blank_name_rejected(api_client, make_preset_row, _isolated_db):
    preset_id = make_preset_row(name="Keep me")
    r = api_client.put(f"/api/presets/{preset_id}", json={"name": "   "})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "INVALID_VALUE"
    assert _db_preset(_isolated_db, preset_id)[0] == "Keep me"


def test_put_is_default_not_editable(api_client, make_preset_row, _isolated_db):
    # is_default is not part of the whitelisted body — rejected at the DTO level.
    preset_id = make_preset_row(name="Default", is_default=True)
    r = api_client.put(
        f"/api/presets/{preset_id}", json={"name": "Renamed", "is_default": False}
    )
    assert r.status_code == 422
    name, is_default, _, _ = _db_preset(_isolated_db, preset_id)
    assert name == "Default"
    assert is_default is True


# --- History immutability ----------------------------------------------------------


def test_editing_a_preset_never_rewrites_run_history(
    api_client, make_preset_row, make_session_row, make_run_row, _isolated_db
):
    # A completed run snapshotted cover=50 into its params at run time.
    params = {
        "clear_span_m": 4.0,
        "clear_height_m": 3.0,
        "cushion_m": 2.5,
        "clear_cover_mm": 50,
        "loading_standard": "25t-2008",
    }
    session_id = make_session_row()
    run_id = make_run_row(session_id, status="completed", params_json=json.dumps(params))
    preset_id = make_preset_row(values={"clear_cover_mm": 50})

    r = api_client.put(f"/api/presets/{preset_id}", json={"values": {"clear_cover_mm": 40}})
    assert r.status_code == 200

    # The stored run row is byte-for-byte untouched.
    from db.models import DesignRunRow

    with Session(_isolated_db) as s:
        assert json.loads(s.get(DesignRunRow, run_id).params_json) == params

    # The snapshot endpoint still replays the original values...
    snapshot = api_client.get(f"/api/designs/{run_id}").json()["data"]
    assert snapshot["params"]["clear_cover_mm"] == 50
    # ...while the preset itself now carries the new value for future runs.
    presets = api_client.get("/api/presets").json()["data"]["presets"]
    assert presets[0]["values"]["clear_cover_mm"] == 40
