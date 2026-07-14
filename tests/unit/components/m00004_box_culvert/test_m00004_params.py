"""M00004Params / M00004Geometry validation + ranges."""

import pytest
from pydantic import ValidationError

from components.m00004_box_culvert.params import (
    CRITICAL_FIELDS,
    M00004Geometry,
    M00004Params,
)


def test_critical_fields_declared():
    assert CRITICAL_FIELDS == ("clear_span_m", "clear_height_m", "cushion_m")


def test_minimal_valid_params_apply_standard_defaults():
    p = M00004Params(clear_span_m=4.0, clear_height_m=4.0, cushion_m=2.0)
    assert p.surcharge_kn_m2 == 0.0
    assert p.formation_width_m == pytest.approx(6.85)
    assert p.side_slope_h_per_v == pytest.approx(2.0)
    assert p.concrete_grade.value == "M30"
    assert p.steel_grade.value == "Fe500"


def test_missing_critical_field_is_rejected():
    with pytest.raises(ValidationError):
        M00004Params(clear_span_m=4.0, clear_height_m=4.0)


@pytest.mark.parametrize(
    "field,value",
    [
        ("clear_span_m", 0.5),   # < 1.0 hard min
        ("clear_span_m", 8.5),   # > 8.0 hard max
        ("clear_height_m", 0.9),
        ("cushion_m", -0.1),
        ("cushion_m", 6.5),      # > 6.0 hard max
        ("surcharge_kn_m2", 60.0),
    ],
)
def test_out_of_range_values_rejected(field, value):
    kwargs = {"clear_span_m": 4.0, "clear_height_m": 4.0, "cushion_m": 2.0}
    kwargs[field] = value
    with pytest.raises(ValidationError):
        M00004Params(**kwargs)


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        M00004Params(clear_span_m=4.0, clear_height_m=4.0, cushion_m=2.0, bogus=1)


def test_geometry_model_round_trips():
    g = M00004Geometry(
        clear_span_mm=4000, clear_height_mm=4000, thickness_mm=500, haunch_mm=450,
        outer_width_mm=5000, outer_height_mm=5000, barrel_length_mm=34850,
        config_id="F2_4x4", bar_schedule={"a1": {"dia_mm": 16, "spacing_mm": 150}},
    )
    assert g.wing_len_mm == 2500  # PROVISIONAL default appendage constant
    assert g.provisional_flags == []
