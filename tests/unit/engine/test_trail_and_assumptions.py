"""Traceability — every geometry number has a cited CalcStep; every engine default an Assumption."""

from domain.culvert import Assumption, CalcStep, CulvertParams
from engine import size_culvert

CANONICAL = {"clear_span_m": 4.0, "clear_height_m": 3.0, "cushion_m": 2.5}

BANNED_CITATION_TOKENS = ["IS 456", "IS456", "IS 800", "IS800", "IRC"]


def _canonical_result():
    return size_culvert(CulvertParams(**CANONICAL))


def test_every_geometry_number_has_a_calc_step_with_matching_value_and_unit():
    result = _canonical_result()
    steps = result.trail

    for field, value in result.geometry.model_dump().items():
        unit = "mm" if field.endswith("_mm") else "m"
        matches = [s for s in steps if s.value == value and s.unit == unit]
        assert matches, f"geometry field {field}={value} {unit} has no CalcStep"


def test_every_calc_step_is_fully_populated():
    for step in _canonical_result().trail:
        assert isinstance(step, CalcStep)
        assert step.step_id
        assert step.description
        assert step.formula
        assert isinstance(step.inputs, dict) and step.inputs
        assert step.unit
        assert step.citation


def test_calc_step_ids_are_unique_and_ordered():
    steps = _canonical_result().trail

    ids = [s.step_id for s in steps]
    assert len(ids) == len(set(ids))
    assert ids == sorted(ids)


def test_auto_sized_thickness_steps_carry_substituted_inputs():
    steps = _canonical_result().trail

    top_slab_steps = [s for s in steps if s.description.startswith("Top slab thickness")]
    assert len(top_slab_steps) == 1
    assert top_slab_steps[0].inputs.get("clear_span_m") == 4.0
    assert top_slab_steps[0].value == 400.0


def test_barrel_length_step_records_the_formula_inputs():
    steps = _canonical_result().trail

    barrel_steps = [s for s in steps if "barrel" in s.description.lower()]
    assert len(barrel_steps) == 1
    inputs = barrel_steps[0].inputs
    assert inputs.get("formation_width_m") == 6.85
    assert inputs.get("side_slope_h_per_v") == 2.0


def test_every_engine_defaulted_field_has_an_assumption_with_a_note():
    result = _canonical_result()

    assumed_fields = {a.field for a in result.assumptions}
    assert assumed_fields == {
        "top_slab_thickness_mm",
        "bottom_slab_thickness_mm",
        "wall_thickness_mm",
        "barrel_length_m",
    }
    for assumption in result.assumptions:
        assert isinstance(assumption, Assumption)
        assert assumption.source == "engine_default"
        assert assumption.note and len(assumption.note) > 10
        assert assumption.value is not None


def test_no_is_456_or_irc_citation_anywhere():
    result = _canonical_result()

    texts = [s.citation for s in result.trail]
    texts += [s.formula for s in result.trail]
    texts += [s.description for s in result.trail]
    texts += [a.note for a in result.assumptions]
    texts += result.warnings

    for text in texts:
        for banned in BANNED_CITATION_TOKENS:
            assert banned not in text, f"banned citation token {banned!r} in {text!r}"


def test_citations_reference_irs_or_rdso_sources():
    result = _canonical_result()

    for step in result.trail:
        cited = step.citation
        assert any(token in cited for token in ("RDSO", "IRS", "Indian Railways")), (
            f"step {step.step_id} citation lacks an IRS/RDSO source: {cited!r}"
        )


def test_sizing_result_serialises_to_json_for_graph_state():
    result = _canonical_result()

    dumped = result.model_dump(mode="json")

    assert set(dumped) == {"geometry", "assumptions", "trail", "warnings"}
    assert dumped["geometry"]["barrel_length_m"] == 32.05
