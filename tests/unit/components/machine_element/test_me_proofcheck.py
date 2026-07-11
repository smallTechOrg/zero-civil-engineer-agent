"""Proof-check spine — verdict rule, cross-check, narration grounding, artefacts."""

import json
from pathlib import Path

import pytest

from components.machine_element.analysis import analyse_element
from components.machine_element.checks import run_element_checks
from components.machine_element.drawing import generate_ga
from components.machine_element.params import MachineElementParams
from components.machine_element.proofcheck import (
    render_memo,
    run_proof_check,
    validate_narration,
)
from components.machine_element.sizing import size_element


def _run(params: MachineElementParams, out_dir: Path):
    g = size_element(params).geometry
    analysis = analyse_element(params, g)
    checks = run_element_checks(analysis, g, params)
    generate_ga(params, g, out_dir, run_id="pc")  # proof reads ga.dxf
    result = run_proof_check(
        params=params, geometry=g, analysis=analysis,
        checks=list(checks.checks), ga_dxf_path=out_dir / "ga.dxf", out_dir=out_dir,
    )
    return result, g, analysis


SOUND = MachineElementParams(power_kw=20.0, speed_rpm=1000.0)
UNDER = MachineElementParams(power_kw=20.0, speed_rpm=1000.0, diameter_mm=25.0)
WELD_UNDER = MachineElementParams(
    power_kw=100.0, speed_rpm=100.0, element_kind="welded_joint",
    hub_diameter_mm=120.0, weld_size_mm=3.0,
)


def test_sound_shaft_is_recommended_for_approval(tmp_path: Path):
    result, _g, _a = _run(SOUND, tmp_path)
    assert result.verdict == "recommended_for_approval"
    assert result.cross_check.within_tolerance
    assert result.agreement_pct >= 99.0
    assert (tmp_path / "compliance.json").is_file()
    assert (tmp_path / "bmd.svg").is_file()
    payload = json.loads((tmp_path / "compliance.json").read_text())
    assert payload["verdict"] == "recommended_for_approval"
    items = payload["items"]
    assert [i["item"] for i in items] == list(range(1, len(items) + 1))
    # The design-basis / material-transcription honesty item is graded OBSERVATION.
    assert items[0]["severity"] == "OBSERVATION"
    dxf_item = next(i for i in result.items if "drawing" in i.title.lower())
    assert dxf_item.severity == "PASS"


def test_under_design_shaft_returns_for_revision_naming_the_member(tmp_path: Path):
    result, geometry, analysis = _run(UNDER, tmp_path)
    assert result.verdict == "return_for_revision"
    majors = [i for i in result.items if i.severity == "NON_CONFORMITY_MAJOR"]
    assert any("Combined-stress" in i.title for i in majors)
    memo = render_memo(result, None, params=UNDER, geometry=geometry, analysis=analysis,
                       warnings=["Shaft diameter override 25 mm is smaller than sized"])
    assert "RETURN FOR REVISION" in memo
    assert "shaft" in memo.lower()


def test_under_design_weld_returns_for_revision(tmp_path: Path):
    result, _g, _a = _run(WELD_UNDER, tmp_path)
    assert result.verdict == "return_for_revision"
    majors = [i for i in result.items if i.severity == "NON_CONFORMITY_MAJOR"]
    assert any("Weld shear" in i.title for i in majors)


def test_narration_grounding_rejects_ungrounded_number_and_forbidden_citation(tmp_path: Path):
    result, _g, _a = _run(SOUND, tmp_path)
    # An invented number that appears nowhere in the deterministic results.
    assert validate_narration("the torque is 987654321 N.mm", result)
    # Forbidden out-of-domain (concrete) citation — machine element cites machine-design basis.
    assert validate_narration("checked as per IS 456 provisions", result)
    # Forbidden road-congress citation.
    assert validate_narration("as per IRC:24 clauses", result)
    # Forbidden bridge citation.
    assert validate_narration("verified to the IRS Concrete Bridge Code", result)
    # Empty narration is rejected.
    assert validate_narration("", result) == ["narration is empty"]
    # A narration that states the OPPOSITE verdict is rejected (SOUND -> approval).
    assert validate_narration("this design is a return for revision", result)


def test_deterministic_memo_is_self_grounded(tmp_path: Path):
    result, geometry, analysis = _run(SOUND, tmp_path)
    memo = render_memo(result, None, params=SOUND, geometry=geometry, analysis=analysis)
    assert validate_narration(memo, result) == []
    assert "RECOMMENDED FOR APPROVAL" in memo


def test_independent_cross_check_recomputes_the_stress(tmp_path: Path):
    result, _g, analysis = _run(SOUND, tmp_path)
    cross = result.cross_check
    assert cross.max_stress_mpa == pytest.approx(analysis.max_stress_mpa, rel=1e-4)
    assert cross.factor_of_safety == pytest.approx(analysis.factor_of_safety, rel=1e-4)
    assert cross.within_tolerance and cross.agreement_pct >= 99.0


def test_dxf_readback_item_fails_when_drawing_is_missing(tmp_path: Path):
    g = size_element(SOUND).geometry
    analysis = analyse_element(SOUND, g)
    checks = run_element_checks(analysis, g, SOUND)
    result = run_proof_check(
        params=SOUND, geometry=g, analysis=analysis, checks=list(checks.checks),
        ga_dxf_path=tmp_path / "does_not_exist.dxf", out_dir=tmp_path,
    )
    dxf_item = next(i for i in result.items if "drawing" in i.title.lower())
    assert dxf_item.severity == "NON_CONFORMITY_MAJOR"
    assert result.verdict == "return_for_revision"
