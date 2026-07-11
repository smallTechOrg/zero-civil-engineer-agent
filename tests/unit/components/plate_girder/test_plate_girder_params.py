"""PlateGirderParams / geometry / intake schema — validation and defaults."""

import pytest
from pydantic import ValidationError

from components.plate_girder.params import (
    CLARIFICATION_QUESTIONS,
    CRITICAL_FIELDS,
    PlateGirderExtractionResult,
    PlateGirderParams,
    unusual_value_warnings,
)

MINIMAL = dict(span_m=24.0, steel_grade="E250")


def test_critical_fields_are_span_and_steel_grade_in_order():
    assert CRITICAL_FIELDS == ("span_m", "steel_grade")


def test_defaults_are_applied_for_non_critical_fields():
    params = PlateGirderParams(**MINIMAL)
    assert params.loading_standard.value == "25t-2008"
    assert params.gauge.value == "BG"
    assert params.deck_type == "deck"
    assert params.number_of_girders == 2
    # Section overrides default to None (auto-size).
    assert params.web_depth_mm is None
    assert params.flange_thickness_mm is None


def test_span_is_required():
    with pytest.raises(ValidationError):
        PlateGirderParams(steel_grade="E250")


def test_steel_grade_is_required():
    with pytest.raises(ValidationError):
        PlateGirderParams(span_m=24.0)


@pytest.mark.parametrize(
    "field,value",
    [
        ("span_m", 4.0),   # below 6.0 hard min
        ("span_m", 70.0),  # above 60.0 hard max
        ("number_of_girders", 1),   # below 2
        ("number_of_girders", 7),   # above 6
        ("steel_grade", "E450"),    # not a permitted grade
        ("deck_type", "sideways"),  # not a permitted deck type
    ],
)
def test_out_of_range_values_are_rejected(field, value):
    with pytest.raises(ValidationError):
        PlateGirderParams(**{**MINIMAL, field: value})


def test_negative_override_rejected():
    with pytest.raises(ValidationError):
        PlateGirderParams(**{**MINIMAL, "flange_thickness_mm": -20.0})


def test_extra_field_forbidden():
    with pytest.raises(ValidationError):
        PlateGirderParams(**{**MINIMAL, "unexpected": 1.0})


def test_unusual_value_warnings_flag_long_span():
    long = unusual_value_warnings(PlateGirderParams(**{**MINIMAL, "span_m": 50.0}))
    assert any("span" in w.lower() for w in long)
    # Ordinary spans raise no flag.
    assert unusual_value_warnings(PlateGirderParams(**MINIMAL)) == []


def test_extraction_schema_covers_every_param_field_and_is_all_optional():
    param_fields = set(PlateGirderParams.model_fields)
    schema_fields = set(PlateGirderExtractionResult.model_fields)
    assert param_fields <= schema_fields
    empty = PlateGirderExtractionResult()
    assert all(getattr(empty, f) is None for f in schema_fields)


def test_clarification_question_exists_for_the_critical_field():
    for field in CRITICAL_FIELDS:
        assert CLARIFICATION_QUESTIONS[field].strip()


def test_clarification_question_ordering_asks_span_before_steel_grade():
    assert CRITICAL_FIELDS[0] == "span_m"
    assert CRITICAL_FIELDS[1] == "steel_grade"
    assert "E250" in CLARIFICATION_QUESTIONS["steel_grade"]
    assert "E350" in CLARIFICATION_QUESTIONS["steel_grade"]
