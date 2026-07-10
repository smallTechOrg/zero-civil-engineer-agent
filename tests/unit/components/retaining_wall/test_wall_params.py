"""RetainingWallParams / geometry / intake schema — validation and defaults."""

import pytest
from pydantic import ValidationError

from components.retaining_wall.params import (
    CLARIFICATION_QUESTIONS,
    CRITICAL_FIELDS,
    RetainingWallParams,
    RWExtractionResult,
    unusual_value_warnings,
)

MINIMAL = dict(
    retained_height_m=5.0, safe_bearing_capacity_kn_m2=200.0, backfill_friction_angle_deg=30.0
)


def test_critical_field_order_is_height_then_sbc_then_phi():
    assert CRITICAL_FIELDS == (
        "retained_height_m",
        "safe_bearing_capacity_kn_m2",
        "backfill_friction_angle_deg",
    )


def test_defaults_are_applied_for_non_critical_fields():
    params = RetainingWallParams(**MINIMAL)
    assert params.backfill_unit_weight_kn_m3 == 18.0
    assert params.backfill_slope_deg == 0.0
    assert params.track_surcharge is True
    assert params.surcharge_kn_m2 == 0.0
    assert params.base_friction_coeff == 0.5
    assert params.concrete_grade.value == "M30"
    assert params.steel_grade.value == "Fe500"
    assert params.clear_cover_mm == 50.0
    # Thickness/length overrides default to None (auto-size).
    assert params.stem_base_thickness_mm is None
    assert params.toe_length_mm is None


def test_critical_fields_are_required():
    with pytest.raises(ValidationError):
        RetainingWallParams(safe_bearing_capacity_kn_m2=200.0, backfill_friction_angle_deg=30.0)


@pytest.mark.parametrize(
    "field,value",
    [
        ("retained_height_m", 0.5),   # below 1.5 hard min
        ("retained_height_m", 9.0),   # above 8.0 hard max
        ("safe_bearing_capacity_kn_m2", 40.0),  # below 50
        ("backfill_friction_angle_deg", 20.0),  # below 25
        ("backfill_friction_angle_deg", 45.0),  # above 40
        ("backfill_slope_deg", 25.0),           # above 20
        ("clear_cover_mm", 30.0),               # below 40
    ],
)
def test_out_of_range_values_are_rejected(field, value):
    with pytest.raises(ValidationError):
        RetainingWallParams(**{**MINIMAL, field: value})


def test_negative_override_rejected():
    with pytest.raises(ValidationError):
        RetainingWallParams(**{**MINIMAL, "stem_base_thickness_mm": -100.0})


def test_unusual_value_warnings_flag_tall_wall_and_weak_soil():
    tall = unusual_value_warnings(RetainingWallParams(**{**MINIMAL, "retained_height_m": 7.0}))
    assert any("retained height" in w.lower() for w in tall)
    weak = unusual_value_warnings(
        RetainingWallParams(**{**MINIMAL, "safe_bearing_capacity_kn_m2": 80.0})
    )
    assert any("bearing" in w.lower() for w in weak)
    # Ordinary values raise no flag.
    assert unusual_value_warnings(RetainingWallParams(**MINIMAL)) == []


def test_extraction_schema_covers_every_param_field_and_is_all_optional():
    param_fields = set(RetainingWallParams.model_fields)
    schema_fields = set(RWExtractionResult.model_fields)
    assert param_fields <= schema_fields
    # Every extraction field defaults to None (never invented).
    empty = RWExtractionResult()
    assert all(getattr(empty, f) is None for f in schema_fields)


def test_clarification_questions_exist_for_every_critical_field():
    for field in CRITICAL_FIELDS:
        assert CLARIFICATION_QUESTIONS[field].strip()
