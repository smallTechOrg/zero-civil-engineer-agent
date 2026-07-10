"""Calc-sheet composer — sections, merged trail, every check.trail_ref resolves."""

import json
from pathlib import Path

import pytest

from components.pier_abutment.analysis import analyse_substructure
from components.pier_abutment.calcsheet import compose_calc_sheet
from components.pier_abutment.checks import run_substructure_checks
from components.pier_abutment.params import PierAbutmentParams
from components.pier_abutment.sizing import size_substructure

PARAMS = PierAbutmentParams(
    pier_height_m=9.0, superstructure_reaction_kn=5000.0,
    safe_bearing_capacity_kn_m2=300.0, component_kind="abutment",
)


@pytest.fixture
def artefacts(tmp_path: Path):
    sizing = size_substructure(PARAMS)
    g = sizing.geometry
    analysis = analyse_substructure(PARAMS, g)
    checks = run_substructure_checks(analysis, g, PARAMS)
    path = compose_calc_sheet(
        trail=[
            [s.model_dump() for s in sizing.trail],
            [s.model_dump() for s in analysis.trail],
            [s.model_dump() for s in checks.trail],
        ],
        checks=[c.model_dump() for c in checks.checks],
        assumptions=[a.model_dump() for a in sizing.assumptions],
        warnings=list(sizing.warnings),
        params=PARAMS,
        geometry=g,
        out_dir=tmp_path,
    )
    return path, checks


def test_calc_sheet_written_with_the_four_sections(artefacts):
    path, _checks = artefacts
    assert path.name == "calc_sheet.json" and path.is_file()
    doc = json.loads(path.read_text())
    section_ids = [s["id"] for s in doc["sections"]]
    assert section_ids == ["design_basis", "loading", "stability", "section_checks"]
    assert doc["trail"], "the merged drill-down trail is present"


def test_every_check_trail_ref_resolves_to_a_recorded_step(artefacts):
    path, checks = artefacts
    doc = json.loads(path.read_text())
    step_ids = {s["step_id"] for s in doc["trail"]}
    for check in checks.checks:
        assert check.trail_ref in step_ids
    # The section_checks lines carry a status and a resolvable trail_ref.
    section = next(s for s in doc["sections"] if s["id"] == "section_checks")
    assert section["lines"]
    for line in section["lines"]:
        assert line["status"] in {"PASS", "FAIL"}
        assert line["trail_ref"] in step_ids


def test_a_dangling_trail_ref_is_rejected(tmp_path: Path):
    g = size_substructure(PARAMS).geometry
    analysis = analyse_substructure(PARAMS, g)
    checks = run_substructure_checks(analysis, g, PARAMS)
    # Drop the checks trail so the check rows reference missing steps.
    with pytest.raises(ValueError):
        compose_calc_sheet(
            trail=[[s.model_dump() for s in analysis.trail]],
            checks=[c.model_dump() for c in checks.checks],
            assumptions=[], warnings=[], params=PARAMS, geometry=g, out_dir=tmp_path,
        )
