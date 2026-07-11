"""SteelMemberParams / geometry / intake schema — validation and defaults."""

import pytest
from pydantic import ValidationError

from components.structural_steel_member.params import (
    CLARIFICATION_QUESTIONS,
    CRITICAL_FIELDS,
    SteelMemberExtractionResult,
    SteelMemberParams,
    unusual_value_warnings,
)

MINIMAL = dict(cantilever_length_m=6.0, transverse_load_kn=20.0)


def test_critical_fields_are_length_and_load():
    assert CRITICAL_FIELDS == ("cantilever_length_m", "transverse_load_kn")


def test_defaults_are_applied_for_non_critical_fields():
    params = SteelMemberParams(**MINIMAL)
    assert params.member_type == "gantry_post"
    assert params.axial_load_kn == 80.0
    assert params.steel_grade == "E250"
    # Section/weld overrides default to None (auto-size).
    assert params.web_depth_mm is None
    assert params.flange_thickness_mm is None
    assert params.weld_size_mm is None


def test_both_critical_fields_are_required():
    with pytest.raises(ValidationError):
        SteelMemberParams()
    with pytest.raises(ValidationError):
        SteelMemberParams(cantilever_length_m=6.0)  # missing load
    with pytest.raises(ValidationError):
        SteelMemberParams(transverse_load_kn=20.0)  # missing length


@pytest.mark.parametrize(
    "field,value",
    [
        ("cantilever_length_m", 0.2),   # below 0.5 hard min
        ("cantilever_length_m", 15.0),  # above 12.0 hard max
        ("transverse_load_kn", 0.5),    # below 1.0
        ("transverse_load_kn", 3000.0), # above 2000
        ("axial_load_kn", 6000.0),      # above 5000
        ("steel_grade", "E450"),        # not a permitted grade
        ("member_type", "beam"),        # not a permitted member type
    ],
)
def test_out_of_range_values_are_rejected(field, value):
    with pytest.raises(ValidationError):
        SteelMemberParams(**{**MINIMAL, field: value})


def test_negative_override_rejected():
    with pytest.raises(ValidationError):
        SteelMemberParams(**{**MINIMAL, "flange_thickness_mm": -20.0})
    with pytest.raises(ValidationError):
        SteelMemberParams(**{**MINIMAL, "weld_size_mm": -6.0})


def test_extra_field_forbidden():
    with pytest.raises(ValidationError):
        SteelMemberParams(**{**MINIMAL, "unexpected": 1.0})


def test_unusual_value_warnings_flag_long_and_heavy():
    long = unusual_value_warnings(SteelMemberParams(**{**MINIMAL, "cantilever_length_m": 11.0}))
    assert any("length" in w.lower() for w in long)
    heavy = unusual_value_warnings(SteelMemberParams(**{**MINIMAL, "transverse_load_kn": 800.0}))
    assert any("load" in w.lower() for w in heavy)
    heavy_axial = unusual_value_warnings(SteelMemberParams(**{**MINIMAL, "axial_load_kn": 3000.0}))
    assert any("axial" in w.lower() for w in heavy_axial)
    # Ordinary members raise no flag.
    assert unusual_value_warnings(SteelMemberParams(**MINIMAL)) == []


def test_extraction_schema_covers_every_param_field_and_is_all_optional():
    param_fields = set(SteelMemberParams.model_fields)
    schema_fields = set(SteelMemberExtractionResult.model_fields)
    assert param_fields <= schema_fields
    empty = SteelMemberExtractionResult()
    assert all(getattr(empty, f) is None for f in schema_fields)


def test_clarification_question_exists_for_every_critical_field():
    for field in CRITICAL_FIELDS:
        assert CLARIFICATION_QUESTIONS[field].strip()
