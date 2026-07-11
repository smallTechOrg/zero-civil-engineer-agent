"""MachineElementParams / geometry / intake schema — validation and defaults."""

import pytest
from pydantic import ValidationError

from components.machine_element.params import (
    CLARIFICATION_QUESTIONS,
    CRITICAL_FIELDS,
    MachineElementExtractionResult,
    MachineElementParams,
    unusual_value_warnings,
)

MINIMAL = dict(power_kw=20.0)


def test_critical_field_is_power_only():
    assert CRITICAL_FIELDS == ("power_kw",)


def test_defaults_are_applied_for_non_critical_fields():
    params = MachineElementParams(**MINIMAL)
    assert params.speed_rpm == 1450.0
    assert params.element_kind == "shaft"
    assert params.material_grade == "40C8"
    assert params.required_factor_of_safety == 2.0
    assert params.mounting_pcd_mm == 200.0
    assert params.overhang_mm == 150.0
    assert params.has_keyway is True
    assert params.hub_diameter_mm == 120.0
    # Overrides default to None (auto-size).
    assert params.diameter_mm is None
    assert params.weld_size_mm is None


def test_power_is_required():
    with pytest.raises(ValidationError):
        MachineElementParams()


@pytest.mark.parametrize(
    "field,value",
    [
        ("power_kw", 0.01),       # below 0.05 hard min
        ("power_kw", 6000.0),     # above 5000 hard max
        ("speed_rpm", 5.0),       # below 10
        ("speed_rpm", 40000.0),   # above 30000
        ("required_factor_of_safety", 1.0),   # below 1.1
        ("required_factor_of_safety", 7.0),   # above 6
        ("material_grade", "S355"),   # not a permitted grade
        ("element_kind", "gear"),     # not a permitted kind
    ],
)
def test_out_of_range_values_are_rejected(field, value):
    with pytest.raises(ValidationError):
        MachineElementParams(**{**MINIMAL, field: value})


def test_negative_override_rejected():
    with pytest.raises(ValidationError):
        MachineElementParams(**{**MINIMAL, "diameter_mm": -50.0})
    with pytest.raises(ValidationError):
        MachineElementParams(**{**MINIMAL, "weld_size_mm": -6.0})


def test_extra_field_forbidden():
    with pytest.raises(ValidationError):
        MachineElementParams(**{**MINIMAL, "unexpected": 1.0})


def test_unusual_value_warnings_flag_high_power_and_speed():
    heavy = unusual_value_warnings(MachineElementParams(**{**MINIMAL, "power_kw": 1500.0}))
    assert any("power" in w.lower() for w in heavy)
    fast = unusual_value_warnings(MachineElementParams(**{**MINIMAL, "speed_rpm": 8000.0}))
    assert any("speed" in w.lower() for w in fast)
    # Ordinary drives raise no flag.
    assert unusual_value_warnings(MachineElementParams(**MINIMAL)) == []


def test_extraction_schema_covers_every_param_field_and_is_all_optional():
    param_fields = set(MachineElementParams.model_fields)
    schema_fields = set(MachineElementExtractionResult.model_fields)
    assert param_fields <= schema_fields
    empty = MachineElementExtractionResult()
    assert all(getattr(empty, f) is None for f in schema_fields)


def test_clarification_question_exists_for_the_critical_field():
    for field in CRITICAL_FIELDS:
        assert CLARIFICATION_QUESTIONS[field].strip()
