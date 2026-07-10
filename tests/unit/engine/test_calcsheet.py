"""Calc-sheet composer (Phase 2, spec/capabilities/calc-sheet.md).

The pinned calc_sheet.json shape (the Phase-2 frontend renders EXACTLY this),
machine-verified trail closure (every trail_ref resolves, every {ref} input
resolves, no cycles), per-load-case loading lines with ACS-level citations,
per-member check lines, and the failing-design hard case (the sheet composes
completely with FAIL rows). Deterministic — no LLM, no network.
"""

import json

import pytest

from domain.culvert import CalcStep, CulvertParams
from engine import size_culvert
from engine.analysis import analyse_frame
from engine.calcsheet import compose_calc_sheet
from engine.checks import run_member_checks

CANONICAL = {"clear_span_m": 4.0, "clear_height_m": 3.0, "cushion_m": 2.5}
PINNED_SECTION_IDS = ["design_basis", "loading", "analysis", "member_checks"]
PINNED_LINE_KEYS = {"description", "value", "unit", "citation", "trail_ref", "status"}
PINNED_TRAIL_KEYS = {"step_id", "description", "formula", "inputs", "value", "unit", "citation"}
MEMBERS = ("top_slab", "bottom_slab", "wall")
# Load-case names whose trail steps use a shorter description prefix.
CASE_PREFIX_ALIASES = {"LL+CDA": "LL"}


def _run(**overrides):
    params = CulvertParams(**{**CANONICAL, **overrides})
    sizing = size_culvert(params)
    analysis = analyse_frame(params, sizing.geometry)
    output = run_member_checks(analysis, sizing.geometry, params)
    return params, sizing, analysis, output


def _compose(run, out_dir):
    params, sizing, analysis, output = run
    return compose_calc_sheet(
        trail=[sizing.trail, analysis.trail, output.trail],
        checks=output.checks,
        assumptions=[*sizing.assumptions, *analysis.assumptions, *output.assumptions],
        warnings=sizing.warnings,
        params=params,
        geometry=sizing.geometry,
        out_dir=out_dir,
    )


@pytest.fixture(scope="module")
def canonical_run():
    return _run()


@pytest.fixture(scope="module")
def sheet(canonical_run, tmp_path_factory):
    path = _compose(canonical_run, tmp_path_factory.mktemp("canonical"))
    return json.loads(path.read_text()), path


# --- artefact + pinned shape ----------------------------------------------------


def test_compose_writes_calc_sheet_json_and_returns_its_path(canonical_run, tmp_path):
    path = _compose(canonical_run, tmp_path)

    assert path == tmp_path / "calc_sheet.json"
    assert path.is_file()
    json.loads(path.read_text())  # valid JSON


def test_sheet_has_exactly_the_four_pinned_sections_in_order(sheet):
    doc, _ = sheet

    assert set(doc.keys()) == {"sections", "assumptions", "warnings", "trail"}
    assert [s["id"] for s in doc["sections"]] == PINNED_SECTION_IDS
    for section in doc["sections"]:
        assert section["title"].strip()
        assert isinstance(section["lines"], list)


def test_every_line_carries_the_pinned_keys(sheet):
    doc, _ = sheet

    for section in doc["sections"]:
        assert section["lines"], f"section {section['id']} is empty"
        for line in section["lines"]:
            assert set(line.keys()) == PINNED_LINE_KEYS, line
            assert line["description"].strip()
            assert isinstance(line["value"], (int, float, str))
            assert line["citation"].strip()


def test_status_is_null_outside_member_checks_and_pass_fail_inside(sheet):
    doc, _ = sheet

    for section in doc["sections"]:
        for line in section["lines"]:
            if section["id"] == "member_checks":
                assert line["status"] in ("PASS", "FAIL")
            else:
                assert line["status"] is None


def test_every_trail_entry_carries_the_pinned_keys(sheet):
    doc, _ = sheet

    assert doc["trail"]
    for step in doc["trail"]:
        assert set(step.keys()) == PINNED_TRAIL_KEYS, step["step_id"]
        assert isinstance(step["value"], (int, float))


# --- machine-verified trail closure (calc-sheet.md success criterion) -----------


def test_trail_closure_every_ref_resolves_and_no_cycles(sheet):
    doc, _ = sheet
    steps = doc["trail"]
    ids = [s["step_id"] for s in steps]
    assert len(ids) == len(set(ids)), "duplicate step ids after merge"
    position = {step_id: i for i, step_id in enumerate(ids)}

    # every line trail_ref resolves
    for section in doc["sections"]:
        for line in section["lines"]:
            if line["trail_ref"] is not None:
                assert line["trail_ref"] in position, (section["id"], line["description"])

    # every {ref} input resolves, and only to an EARLIER step (hence acyclic)
    ref_count = 0
    for i, step in enumerate(steps):
        for key, value in step["inputs"].items():
            if isinstance(value, dict):
                assert set(value.keys()) == {"ref", "value"}, (step["step_id"], key)
                assert value["ref"] in position, (step["step_id"], key)
                assert position[value["ref"]] < i, f"forward/self ref at {step['step_id']}.{key}"
                referenced = steps[position[value["ref"]]]
                assert value["value"] == pytest.approx(referenced["value"])
                ref_count += 1
    assert ref_count > 0, "no recursive drill-down refs were emitted at all"


def test_check_steps_link_into_the_analysis_envelope_steps(sheet):
    doc, _ = sheet
    steps = doc["trail"]
    by_id = {s["step_id"]: s for s in steps}

    linked = [
        by_id[value["ref"]]
        for step in steps
        if "design bending moment" in step["description"] or "design shear" in step["description"]
        for value in step["inputs"].values()
        if isinstance(value, dict)
    ]
    assert any(target["description"].startswith("Envelope:") for target in linked)


def test_member_check_lines_reference_check_trail_steps(sheet):
    doc, _ = sheet
    ids = {s["step_id"] for s in doc["trail"]}
    member_checks = next(s for s in doc["sections"] if s["id"] == "member_checks")

    for line in member_checks["lines"]:
        assert line["trail_ref"] in ids


# --- section content criteria ----------------------------------------------------


def test_loading_section_has_at_least_one_line_per_load_case(sheet, canonical_run):
    doc, _ = sheet
    _, _, analysis, _ = canonical_run
    loading = next(s for s in doc["sections"] if s["id"] == "loading")
    descriptions = [line["description"] for line in loading["lines"]]

    for case in analysis.load_cases:
        prefix = CASE_PREFIX_ALIASES.get(case.name, case.name) + ":"
        assert any(d.startswith(prefix) for d in descriptions), f"no loading line for {case.name}"


def test_every_loading_line_citation_carries_the_acs_level(sheet):
    doc, _ = sheet
    loading = next(s for s in doc["sections"] if s["id"] == "loading")

    for line in loading["lines"]:
        assert "ACS" in line["citation"], line["description"]


def test_member_checks_section_has_at_least_one_line_per_member(sheet):
    doc, _ = sheet
    member_checks = next(s for s in doc["sections"] if s["id"] == "member_checks")

    for member in MEMBERS:
        assert any(line["description"].startswith(member) for line in member_checks["lines"])


def test_design_basis_names_the_grades_and_the_loading_standard(sheet):
    doc, _ = sheet
    design_basis = next(s for s in doc["sections"] if s["id"] == "design_basis")
    values = {str(line["value"]) for line in design_basis["lines"]}

    assert "M30" in values
    assert "Fe500" in values
    assert "25t-2008" in values


def test_every_numeric_line_carries_a_trail_ref(sheet):
    doc, _ = sheet

    for section in doc["sections"]:
        for line in section["lines"]:
            if isinstance(line["value"], (int, float)):
                assert line["trail_ref"] is not None, (section["id"], line["description"])


def test_assumptions_are_carried_with_field_value_source_note(sheet):
    doc, _ = sheet

    assert doc["assumptions"]
    for assumption in doc["assumptions"]:
        assert set(assumption.keys()) == {"field", "value", "source", "note"}
        assert assumption["source"] in ("user", "preset", "engine_default")
        assert assumption["note"].strip()


def test_empty_warnings_compose_cleanly(sheet):
    doc, _ = sheet

    assert doc["warnings"] == []  # canonical run has no warnings — and the key still exists


# --- merge behaviour ---------------------------------------------------------------


def test_colliding_step_ids_across_segments_are_rekeyed_not_dropped(sheet, canonical_run):
    doc, _ = sheet
    _, sizing, analysis, output = canonical_run
    expected_steps = len(sizing.trail) + len(analysis.trail) + len(output.trail)
    sizing_ids = {s.step_id for s in sizing.trail}
    analysis_ids = {s.step_id for s in analysis.trail}
    assert sizing_ids & analysis_ids, "precondition: the landed trails do collide"

    assert len(doc["trail"]) == expected_steps


def test_dangling_explicit_ref_is_a_loud_error(canonical_run, tmp_path):
    params, sizing, analysis, output = canonical_run
    poison = CalcStep(
        step_id="K999",
        description="poison: references a step that does not exist",
        formula="x = ref",
        inputs={"x": "ref:ZZ99"},
        value=1.0,
        unit="-",
        citation="test",
    )

    with pytest.raises(ValueError, match="ZZ99"):
        compose_calc_sheet(
            trail=[sizing.trail, analysis.trail, [*output.trail, poison]],
            checks=output.checks,
            assumptions=output.assumptions,
            warnings=[],
            params=params,
            geometry=sizing.geometry,
            out_dir=tmp_path,
        )


def test_sheet_composition_is_deterministic_byte_identical(canonical_run, tmp_path):
    first = _compose(canonical_run, tmp_path / "a")
    second = _compose(canonical_run, tmp_path / "b")

    assert first.read_text() == second.read_text()


# --- hard case: the failing design still composes completely -----------------------


def test_under_designed_run_composes_completely_with_visible_fail_rows(tmp_path):
    run = _run(top_slab_thickness_mm=200)
    params, sizing, analysis, output = run

    path = _compose(run, tmp_path)
    doc = json.loads(path.read_text())

    assert [s["id"] for s in doc["sections"]] == PINNED_SECTION_IDS
    member_checks = next(s for s in doc["sections"] if s["id"] == "member_checks")
    statuses = [line["status"] for line in member_checks["lines"]]
    assert "FAIL" in statuses
    assert "PASS" in statuses  # the sheet is complete, not truncated at the failure
    assert any("thinner than the auto-sized" in w for w in doc["warnings"])


def test_no_checks_yet_composes_an_empty_member_checks_section(canonical_run, tmp_path):
    params, sizing, analysis, _ = canonical_run

    path = compose_calc_sheet(
        trail=[sizing.trail, analysis.trail],
        checks=[],
        assumptions=sizing.assumptions,
        warnings=sizing.warnings,
        params=params,
        geometry=sizing.geometry,
        out_dir=tmp_path,
    )
    doc = json.loads(path.read_text())

    assert [s["id"] for s in doc["sections"]] == PINNED_SECTION_IDS
    member_checks = next(s for s in doc["sections"] if s["id"] == "member_checks")
    assert member_checks["lines"] == []
