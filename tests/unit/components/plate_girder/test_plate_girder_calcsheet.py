"""Calc-sheet composition — sections, trail merge, every check trail_ref resolves."""

import json
from pathlib import Path

from components.plate_girder.analysis import analyse_girder
from components.plate_girder.calcsheet import compose_calc_sheet
from components.plate_girder.checks import run_girder_checks
from components.plate_girder.params import PlateGirderParams
from components.plate_girder.sizing import size_girder

PARAMS = PlateGirderParams(span_m=24.0, steel_grade="E250")


def _compose(tmp_path: Path):
    sizing = size_girder(PARAMS)
    g = sizing.geometry
    analysis = analyse_girder(PARAMS, g)
    checks = run_girder_checks(analysis, g, PARAMS)
    path = compose_calc_sheet(
        trail=[sizing.trail, analysis.trail, checks.trail],
        checks=checks.checks,
        assumptions=sizing.assumptions + analysis.assumptions,
        warnings=sizing.warnings,
        params=PARAMS,
        geometry=g,
        out_dir=tmp_path,
    )
    return path, checks


def test_calc_sheet_is_written_with_the_expected_sections(tmp_path: Path):
    path, _ = _compose(tmp_path)
    assert path.name == "calc_sheet.json" and path.is_file()
    doc = json.loads(path.read_text())
    section_ids = [s["id"] for s in doc["sections"]]
    assert section_ids == ["design_basis", "loading", "section_analysis", "section_checks"]
    assert doc["trail"] and doc["assumptions"]


def test_every_check_line_references_a_real_trail_step(tmp_path: Path):
    path, checks = _compose(tmp_path)
    doc = json.loads(path.read_text())
    trail_ids = {s["step_id"] for s in doc["trail"]}
    section_checks = next(s for s in doc["sections"] if s["id"] == "section_checks")
    assert len(section_checks["lines"]) == len(checks.checks)
    for line in section_checks["lines"]:
        assert line["trail_ref"] in trail_ids
        assert line["status"] in ("PASS", "FAIL")


def test_composition_rejects_a_dangling_check_trail_ref(tmp_path: Path):
    """A check that references a missing trail step must raise (audit integrity)."""
    import pytest

    sizing = size_girder(PARAMS)
    g = sizing.geometry
    analysis = analyse_girder(PARAMS, g)
    checks = run_girder_checks(analysis, g, PARAMS)
    broken = checks.checks[0].model_copy(update={"trail_ref": "K99"})
    with pytest.raises(ValueError):
        compose_calc_sheet(
            trail=[sizing.trail, analysis.trail, checks.trail],
            checks=[broken, *checks.checks[1:]],
            assumptions=sizing.assumptions,
            warnings=[],
            params=PARAMS,
            geometry=g,
            out_dir=tmp_path,
        )
