"""RollingStockMemberParams / geometry / intake schema — validation and defaults."""

import pytest
from pydantic import ValidationError

from components.rolling_stock_member.params import (
    CLARIFICATION_QUESTIONS,
    CRITICAL_FIELDS,
    RollingStockMemberExtractionResult,
    RollingStockMemberParams,
    unusual_value_warnings,
)

MINIMAL = dict(member_length_m=6.0)


def test_critical_field_is_member_length_only():
    assert CRITICAL_FIELDS == ("member_length_m",)


def test_defaults_are_applied_for_non_critical_fields():
    params = RollingStockMemberParams(**MINIMAL)
    assert params.member_kind == "sole_bar"
    assert params.design_vertical_load_kn == 120.0
    assert params.design_buffing_load_kn == 400.0
    assert params.steel_grade == "E250"
    # Section overrides default to None (auto-size).
    assert params.web_depth_mm is None
    assert params.flange_thickness_mm is None


def test_member_length_is_required():
    with pytest.raises(ValidationError):
        RollingStockMemberParams()


@pytest.mark.parametrize(
    "field,value",
    [
        ("member_length_m", 0.2),   # below 0.5 hard min
        ("member_length_m", 20.0),  # above 15.0 hard max
        ("design_vertical_load_kn", 5.0),     # below 10
        ("design_vertical_load_kn", 3000.0),  # above 2000
        ("design_buffing_load_kn", -1.0),     # below 0
        ("design_buffing_load_kn", 4000.0),   # above 3000
        ("steel_grade", "E450"),      # not a permitted grade
        ("member_kind", "solebar"),   # not a permitted kind
    ],
)
def test_out_of_range_values_are_rejected(field, value):
    with pytest.raises(ValidationError):
        RollingStockMemberParams(**{**MINIMAL, field: value})


def test_negative_override_rejected():
    with pytest.raises(ValidationError):
        RollingStockMemberParams(**{**MINIMAL, "flange_thickness_mm": -12.0})


def test_extra_field_forbidden():
    with pytest.raises(ValidationError):
        RollingStockMemberParams(**{**MINIMAL, "unexpected": 1.0})


def test_unusual_value_warnings_flag_long_member_and_heavy_loads():
    long = unusual_value_warnings(RollingStockMemberParams(**{**MINIMAL, "member_length_m": 13.0}))
    assert any("length" in w.lower() for w in long)
    heavy = unusual_value_warnings(
        RollingStockMemberParams(member_length_m=6.0, design_buffing_load_kn=2500.0)
    )
    assert any("buffing" in w.lower() for w in heavy)
    # Ordinary members raise no flag.
    assert unusual_value_warnings(RollingStockMemberParams(**MINIMAL)) == []


def test_extraction_schema_covers_every_param_field_and_is_all_optional():
    param_fields = set(RollingStockMemberParams.model_fields)
    schema_fields = set(RollingStockMemberExtractionResult.model_fields)
    assert param_fields <= schema_fields
    empty = RollingStockMemberExtractionResult()
    assert all(getattr(empty, f) is None for f in schema_fields)


def test_clarification_question_exists_for_the_critical_field():
    for field in CRITICAL_FIELDS:
        assert CLARIFICATION_QUESTIONS[field].strip()
