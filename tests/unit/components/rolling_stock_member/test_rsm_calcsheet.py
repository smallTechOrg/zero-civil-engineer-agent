"""Calc-sheet composition — sections, trail merge, every check trail_ref resolves."""

import json
from pathlib import Path

from components.rolling_stock_member.analysis import analyse_member
from components.rolling_stock_member.calcsheet import compose_calc_sheet
from components.rolling_stock_member.checks import run_member_checks
from components.rolling_stock_member.params import RollingStockMemberParams
from components.rolling_stock_member.sizing import size_member

PARAMS = RollingStockMemberParams(member_length_m=6.0)


def _compose(tmp_path: Path):
    sizing = size_member(PARAMS)
    g = sizing.geometry
    analysis = analyse_member(PARAMS, g)
    checks = run_member_checks(analysis, g, PARAMS)
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

    sizing = size_member(PARAMS)
    g = sizing.geometry
    analysis = analyse_member(PARAMS, g)
    checks = run_member_checks(analysis, g, PARAMS)
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
