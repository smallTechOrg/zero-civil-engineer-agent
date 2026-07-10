"""GET /api/presets — parsed values (seeding itself is verified by the migration test)."""

import json

from sqlalchemy.orm import Session


def test_list_presets_empty(api_client):
    r = api_client.get("/api/presets")
    assert r.status_code == 200
    assert r.json()["data"]["presets"] == []


def test_list_presets_parses_values(api_client, _isolated_db):
    from db.models import PresetRow

    values = {"concrete_grade": "M30", "clear_cover_mm": 50, "soil_unit_weight_kn_m3": 18.0}
    with Session(_isolated_db) as s:
        s.add(PresetRow(name="IR standard defaults", is_default=True, values_json=json.dumps(values)))
        s.add(PresetRow(name="Custom site", is_default=False, values_json=json.dumps({"clear_cover_mm": 40})))
        s.commit()

    r = api_client.get("/api/presets")
    assert r.status_code == 200
    presets = r.json()["data"]["presets"]
    assert len(presets) == 2

    default = presets[0]  # default preset listed first
    assert default["name"] == "IR standard defaults"
    assert default["is_default"] is True
    assert default["preset_id"]
    assert default["values"] == values

    assert presets[1]["is_default"] is False
    assert presets[1]["values"] == {"clear_cover_mm": 40}
