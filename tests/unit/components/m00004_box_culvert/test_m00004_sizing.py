"""Geometry derivation + PROVISIONAL provenance from sizing.size."""

import pytest

from components.m00004_box_culvert.params import M00004Params
from components.m00004_box_culvert.sizing import size


def _params(**kw):
    base = {"clear_span_m": 4.0, "clear_height_m": 4.0, "cushion_m": 2.0}
    base.update(kw)
    return M00004Params(**base)


def test_geometry_outer_dims_and_barrel_length():
    result = size(_params())
    g = result.geometry
    assert g.config_id == "F2_4x4"
    assert g.thickness_mm == 500          # 50 cm PROVISIONAL catalogue thickness
    assert g.haunch_mm == 450
    assert g.clear_span_mm == 4000
    assert g.clear_height_mm == 4000
    assert g.outer_width_mm == 5000       # 4000 + 2*500
    assert g.outer_height_mm == 5000
    # barrel = 6850 + 2*(2000 + 5000)*2 = 34850
    assert g.barrel_length_mm == pytest.approx(34850.0)
    assert g.provisional_flags == []


def test_bar_schedule_copied_from_selected_config():
    g = size(_params()).geometry
    assert set(g.bar_schedule) == {
        "a1", "a2", "b", "c", "d", "e", "f1", "f2", "g1", "g2", "g3", "h"
    }
    assert g.bar_schedule["a1"] == {"dia_mm": 16, "spacing_mm": 150}


def test_appendage_constants_recorded_as_provisional_assumptions():
    result = size(_params())
    fields = {a.field for a in result.assumptions}
    for f in ("config_id", "thickness_mm", "haunch_mm", "bar_schedule",
              "wing_len_mm", "apron_len_mm", "curtain_depth_mm"):
        assert f in fields
    # every catalogue/appendage assumption carries the PROVISIONAL verify tag
    for a in result.assumptions:
        if a.field in {"config_id", "thickness_mm", "haunch_mm", "bar_schedule",
                       "wing_len_mm", "apron_len_mm", "apron_thickness_mm",
                       "curtain_thickness_mm", "curtain_depth_mm"}:
            assert "PROVISIONAL" in a.note


def test_calc_trail_is_recorded_with_s_ids():
    result = size(_params())
    assert result.trail
    assert all(step.step_id.startswith("S") for step in result.trail)


def test_out_of_catalogue_flags_flow_into_geometry_and_warnings():
    result = size(_params(clear_span_m=7.0, clear_height_m=7.0, cushion_m=3.0, surcharge_kn_m2=10.0))
    g = result.geometry
    assert g.config_id == "F2_6x6"
    assert len(g.provisional_flags) >= 3          # fill + box + surcharge (+ nearest)
    assert result.warnings == g.provisional_flags  # surfaced to the UI
