"""Proof-check spine — verdict rule, cross-check, narration grounding, artefacts."""

import json
from pathlib import Path

from components.pier_abutment.analysis import analyse_substructure
from components.pier_abutment.checks import run_substructure_checks
from components.pier_abutment.drawing import generate_ga
from components.pier_abutment.params import PierAbutmentParams
from components.pier_abutment.proofcheck import (
    render_memo,
    run_proof_check,
    validate_narration,
)
from components.pier_abutment.sizing import size_substructure


def _run(params: PierAbutmentParams, out_dir: Path):
    g = size_substructure(params).geometry
    analysis = analyse_substructure(params, g)
    checks = run_substructure_checks(analysis, g, params)
    generate_ga(params, g, out_dir, run_id="pc")  # proof reads ga.dxf
    result = run_proof_check(
        params=params, geometry=g, analysis=analysis,
        checks=list(checks.checks), ga_dxf_path=out_dir / "ga.dxf", out_dir=out_dir,
    )
    return result, g, analysis


SOUND = PierAbutmentParams(
    pier_height_m=9.0, superstructure_reaction_kn=5000.0,
    safe_bearing_capacity_kn_m2=300.0, component_kind="abutment",
)
UNDER = PierAbutmentParams(
    pier_height_m=9.0, superstructure_reaction_kn=8000.0,
    safe_bearing_capacity_kn_m2=200.0, footing_length_mm=2600.0, footing_width_mm=2600.0,
)


def test_sound_substructure_is_recommended_for_approval(tmp_path: Path):
    result, _g, _a = _run(SOUND, tmp_path)
    assert result.verdict == "recommended_for_approval"
    assert len(result.items) == 10
    assert result.cross_check.within_tolerance
    assert result.agreement_pct >= 95.0
    assert (tmp_path / "compliance.json").is_file()
    assert (tmp_path / "bmd.svg").is_file()
    payload = json.loads((tmp_path / "compliance.json").read_text())
    assert payload["verdict"] == "recommended_for_approval"
    assert [i["item"] for i in payload["items"]] == list(range(1, 11))
    # Design-basis honesty is graded OBSERVATION, never silently PASS.
    assert next(i for i in result.items if i.item == 1).severity == "OBSERVATION"
    # DXF read-back item passed.
    assert next(i for i in result.items if i.item == 10).severity == "PASS"


def test_under_design_returns_for_revision_naming_the_footing(tmp_path: Path):
    result, geometry, analysis = _run(UNDER, tmp_path)
    assert result.verdict == "return_for_revision"
    majors = [i for i in result.items if i.severity == "NON_CONFORMITY_MAJOR"]
    titles = {i.title for i in majors}
    assert "Overturning stability" in titles
    assert "Bearing pressure" in titles
    memo = render_memo(result, None, params=UNDER, geometry=geometry, analysis=analysis)
    assert "RETURN FOR REVISION" in memo


def test_narration_grounding_rejects_ungrounded_number_and_forbidden_citation(tmp_path: Path):
    result, _g, _a = _run(SOUND, tmp_path)
    # An invented number that appears nowhere in the deterministic results.
    assert validate_narration("the driving thrust is 987654 kN", result)
    # A forbidden steel-code citation (IS 800) and a road-congress citation (IRC).
    assert validate_narration("checked as per IS 800 provisions", result)
    assert validate_narration("designed per IRC:78 clauses", result)
    # Empty narration is rejected.
    assert validate_narration("", result) == ["narration is empty"]
    # A narration that states the OPPOSITE verdict is rejected (SOUND -> approval).
    assert validate_narration("this design is a return for revision", result)


def test_deterministic_memo_is_self_grounded(tmp_path: Path):
    result, geometry, analysis = _run(SOUND, tmp_path)
    memo = render_memo(result, None, params=SOUND, geometry=geometry, analysis=analysis)
    # Every number the deterministic memo prints comes from the results.
    assert validate_narration(memo, result) == []


def test_dxf_readback_item_fails_when_drawing_is_missing(tmp_path: Path):
    g = size_substructure(SOUND).geometry
    analysis = analyse_substructure(SOUND, g)
    checks = run_substructure_checks(analysis, g, SOUND)
    result = run_proof_check(
        params=SOUND, geometry=g, analysis=analysis, checks=list(checks.checks),
        ga_dxf_path=tmp_path / "does_not_exist.dxf", out_dir=tmp_path,
    )
    dxf_item = next(i for i in result.items if i.item == 10)
    assert dxf_item.severity == "NON_CONFORMITY_MAJOR"
    assert result.verdict == "return_for_revision"
