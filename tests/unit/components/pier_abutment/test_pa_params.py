"""Pier/abutment params — critical fields, ranges, extraction schema, intake helpers."""

import pytest
from pydantic import ValidationError

from components.pier_abutment.params import (
    CLARIFICATION_QUESTIONS,
    CRITICAL_FIELDS,
    PierAbutmentExtractionResult,
    PierAbutmentParams,
    unusual_value_warnings,
)

CANONICAL = dict(
    pier_height_m=9.0, superstructure_reaction_kn=5000.0, safe_bearing_capacity_kn_m2=300.0
)


def test_three_critical_fields_have_no_default():
    assert CRITICAL_FIELDS == (
        "pier_height_m",
        "superstructure_reaction_kn",
        "safe_bearing_capacity_kn_m2",
    )
    # Each critical field is required — omitting any one raises.
    for field in CRITICAL_FIELDS:
        payload = {k: v for k, v in CANONICAL.items() if k != field}
        with pytest.raises(ValidationError):
            PierAbutmentParams(**payload)


def test_defaults_and_component_kind():
    p = PierAbutmentParams(**CANONICAL)
    assert p.component_kind == "pier"
    assert p.span_m == 20.0
    assert p.base_friction_coeff == 0.5
    assert p.concrete_grade.value == "M30"
    assert p.steel_grade.value == "Fe500"
    assert p.clear_cover_mm == 50.0
    # Auto-size sentinels default to None.
    assert p.footing_length_mm is None and p.pier_width_mm is None


def test_out_of_range_and_extra_fields_are_rejected():
    # Boundary: height below the minimum.
    with pytest.raises(ValidationError):
        PierAbutmentParams(**{**CANONICAL, "pier_height_m": 1.0})
    # Reaction above the maximum.
    with pytest.raises(ValidationError):
        PierAbutmentParams(**{**CANONICAL, "superstructure_reaction_kn": 50000.0})
    # SBC below the minimum.
    with pytest.raises(ValidationError):
        PierAbutmentParams(**{**CANONICAL, "safe_bearing_capacity_kn_m2": 10.0})
    # extra="forbid": an unknown field is rejected.
    with pytest.raises(ValidationError):
        PierAbutmentParams(**{**CANONICAL, "nonsense_field": 1.0})
    # A non-positive geometry override is rejected.
    with pytest.raises(ValidationError):
        PierAbutmentParams(**{**CANONICAL, "footing_length_mm": -100.0})


def test_extraction_schema_is_all_optional_and_mirrors_params():
    schema = PierAbutmentExtractionResult
    # Every critical field is present but optional (the LLM never invents them).
    for field in CRITICAL_FIELDS:
        assert field in schema.model_fields
    empty = PierAbutmentExtractionResult()
    assert empty.pier_height_m is None
    assert empty.superstructure_reaction_kn is None
    assert empty.safe_bearing_capacity_kn_m2 is None


def test_clarification_questions_cover_the_three_criticals():
    assert set(CLARIFICATION_QUESTIONS) == set(CRITICAL_FIELDS)
    for text in CLARIFICATION_QUESTIONS.values():
        assert text.strip().endswith("?") or "?" in text


def test_unusual_value_warnings_flags_and_proceeds():
    # A weak soil is flagged; the canonical design is not.
    assert unusual_value_warnings(PierAbutmentParams(**CANONICAL)) == []
    weak = PierAbutmentParams(**{**CANONICAL, "safe_bearing_capacity_kn_m2": 60.0})
    assert any("bearing capacity" in w.lower() for w in unusual_value_warnings(weak))
    tall = PierAbutmentParams(**{**CANONICAL, "pier_height_m": 20.0})
    assert any("height" in w.lower() for w in unusual_value_warnings(tall))
