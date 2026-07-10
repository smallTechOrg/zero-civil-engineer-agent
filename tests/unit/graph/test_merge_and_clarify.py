"""Extraction merge rules + the deterministic clarify question (spec/agent.md extract/clarify)."""

import pytest
from pydantic import ValidationError

from domain.culvert import CulvertParams
from graph.extraction import (
    CRITICAL_FIELDS,
    ExtractionResult,
    merge_params,
    select_clarification,
    validation_error_message,
)

CANONICAL_PRIOR = {
    "clear_span_m": 4.0,
    "clear_height_m": 3.0,
    "cushion_m": 2.5,
    "gauge": "BG",
    "tracks": 1,
    "loading_standard": "25t-2008",
    "concrete_grade": "M30",
}


def test_this_turn_overrides_prior_which_overrides_preset():
    outcome = merge_params(
        extracted={"cushion_m": 4.0},
        prior_params={**CANONICAL_PRIOR, "concrete_grade": "M25"},
        preset_values={"concrete_grade": "M35", "clear_cover_mm": 50},
    )
    assert outcome.merged["cushion_m"] == 4.0          # this turn wins
    assert outcome.merged["clear_span_m"] == 4.0       # carried from prior
    assert outcome.merged["concrete_grade"] == "M25"   # prior beats preset
    assert outcome.merged["clear_cover_mm"] == 50      # preset fills the gap
    assert outcome.missing_critical == []


def test_preset_never_supplies_critical_fields():
    outcome = merge_params(
        extracted={"clear_height_m": 3.0, "cushion_m": 2.0},
        prior_params=None,
        preset_values={"clear_span_m": 4.0, "concrete_grade": "M30"},
    )
    assert "clear_span_m" not in outcome.merged
    assert outcome.missing_critical == ["clear_span_m"]


def test_missing_criticals_listed_in_priority_order_span_height_cushion():
    outcome = merge_params(extracted={}, prior_params=None, preset_values={})
    assert outcome.missing_critical == list(CRITICAL_FIELDS)
    assert outcome.missing_critical == ["clear_span_m", "clear_height_m", "cushion_m"]


def test_prior_params_satisfy_criticals_for_a_refinement_turn():
    outcome = merge_params(
        extracted={"cushion_m": 4.0}, prior_params=CANONICAL_PRIOR, preset_values={}
    )
    assert outcome.missing_critical == []
    assert outcome.merged["clear_height_m"] == 3.0


def test_preset_sourced_fields_are_tagged_for_assumptions():
    outcome = merge_params(
        extracted={"clear_span_m": 4.0, "clear_height_m": 3.0, "cushion_m": 2.5},
        prior_params=None,
        preset_values={"concrete_grade": "M35", "clear_cover_mm": 45},
    )
    assert sorted(outcome.preset_fields) == ["clear_cover_mm", "concrete_grade"]


def test_preset_fields_overridden_by_turn_or_prior_are_not_tagged():
    outcome = merge_params(
        extracted={"clear_span_m": 4.0, "clear_height_m": 3.0, "cushion_m": 2.5,
                   "concrete_grade": "M25"},
        prior_params={"clear_cover_mm": 60},
        preset_values={"concrete_grade": "M35", "clear_cover_mm": 45},
    )
    assert outcome.preset_fields == []


def test_unknown_fields_are_dropped_not_merged():
    outcome = merge_params(
        extracted={"clear_span_m": 4.0, "clear_height_m": 3.0, "cushion_m": 2.5},
        prior_params={"not_a_param": 1},
        preset_values={"also_not_a_param": 2},
    )
    assert "not_a_param" not in outcome.merged
    assert "also_not_a_param" not in outcome.merged


def test_extraction_result_defaults_every_field_to_none():
    result = ExtractionResult()
    assert all(v is None for v in result.model_dump().values())


def test_extraction_result_covers_every_culvert_param_field():
    assert set(ExtractionResult.model_fields) == set(CulvertParams.model_fields)


def test_clarify_asks_span_first_then_height_then_cushion():
    field, question = select_clarification(["clear_span_m", "clear_height_m", "cushion_m"])
    assert field == "clear_span_m"
    assert "span" in question.lower()

    field, question = select_clarification(["cushion_m", "clear_height_m"])
    assert field == "clear_height_m"
    assert "height" in question.lower()

    field, question = select_clarification(["cushion_m"])
    assert field == "cushion_m"
    assert "cushion" in question.lower()


def test_clarify_question_names_a_typical_range():
    _, question = select_clarification(["clear_span_m"])
    assert "1 m" in question and "6 m" in question


def test_validation_error_message_names_field_and_limit():
    with pytest.raises(ValidationError) as excinfo:
        CulvertParams(clear_span_m=12.0, clear_height_m=3.0, cushion_m=2.5)
    message = validation_error_message(excinfo.value)
    assert "clear_span_m" in message
    assert "8" in message  # the hard upper bound is named
