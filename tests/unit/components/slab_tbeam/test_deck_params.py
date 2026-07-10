"""Slab / T-beam parameter + geometry models and intake schema."""

import pytest
from pydantic import ValidationError

from components.slab_tbeam.params import (
    CLARIFICATION_QUESTIONS,
    CRITICAL_FIELDS,
    SlabTbeamExtractionResult,
    SlabTbeamParams,
    unusual_value_warnings,
)


def test_span_is_the_single_critical_field_with_no_default():
    assert CRITICAL_FIELDS == ("span_m",)
    with pytest.raises(ValidationError):
        SlabTbeamParams()  # span_m has no default


def test_defaults_are_the_normative_values():
    p = SlabTbeamParams(span_m=10.0)
    assert p.deck_type == "solid_slab"
    assert p.carriageway_width_m == 5.0
    assert p.number_of_girders == 3
    assert p.concrete_grade.value == "M30"
    assert p.steel_grade.value == "Fe500"
    assert p.clear_cover_mm == 40.0
    assert p.loading_standard.value == "25t-2008"
    assert p.gauge.value == "BG"
    # geometry overrides default to None (auto-size).
    assert p.slab_depth_mm is None and p.rib_depth_mm is None


def test_hard_ranges_rejected():
    with pytest.raises(ValidationError):
        SlabTbeamParams(span_m=2.0)  # below 3.0
    with pytest.raises(ValidationError):
        SlabTbeamParams(span_m=30.0)  # above 25.0
    with pytest.raises(ValidationError):
        SlabTbeamParams(span_m=10.0, number_of_girders=1)  # below 2
    with pytest.raises(ValidationError):
        SlabTbeamParams(span_m=10.0, clear_cover_mm=20.0)  # below 30


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        SlabTbeamParams(span_m=10.0, bogus_field=1)


def test_negative_override_rejected():
    with pytest.raises(ValidationError):
        SlabTbeamParams(span_m=10.0, rib_depth_mm=-100.0)


def test_extraction_schema_makes_every_field_optional():
    result = SlabTbeamExtractionResult()  # all None — never invents
    assert result.span_m is None
    assert "span_m" in SlabTbeamExtractionResult.model_fields
    assert "deck_type" in SlabTbeamExtractionResult.model_fields


def test_clarify_question_for_the_critical_field():
    assert "span_m" in CLARIFICATION_QUESTIONS
    assert CLARIFICATION_QUESTIONS["span_m"]


def test_unusual_value_warnings_flag_long_and_uneconomic_spans():
    assert unusual_value_warnings(SlabTbeamParams(span_m=8.0)) == []
    long_span = unusual_value_warnings(SlabTbeamParams(span_m=22.0))
    assert any("exceeds" in w for w in long_span)
    uneconomic_slab = unusual_value_warnings(
        SlabTbeamParams(span_m=14.0, deck_type="solid_slab")
    )
    assert any("solid slab" in w.lower() for w in uneconomic_slab)
