"""Proof-check spine — verdict rule, cross-check, narration grounding, artefacts."""

import json
from pathlib import Path

import pytest

from components.rolling_stock_member.analysis import analyse_member
from components.rolling_stock_member.checks import run_member_checks
from components.rolling_stock_member.drawing import generate_ga
from components.rolling_stock_member.params import RollingStockMemberParams
from components.rolling_stock_member.proofcheck import (
    render_memo,
    run_proof_check,
    validate_narration,
)
from components.rolling_stock_member.sizing import size_member


def _run(params: RollingStockMemberParams, out_dir: Path):
    g = size_member(params).geometry
    analysis = analyse_member(params, g)
    checks = run_member_checks(analysis, g, params)
    generate_ga(params, g, out_dir, run_id="pc")  # proof reads ga.dxf
    result = run_proof_check(
        params=params, geometry=g, analysis=analysis,
        checks=list(checks.checks), ga_dxf_path=out_dir / "ga.dxf", out_dir=out_dir,
    )
    return result, g, analysis


SOUND = RollingStockMemberParams(member_length_m=6.0)
UNDER = RollingStockMemberParams(
    member_length_m=3.0, flange_thickness_mm=8.0, flange_width_mm=100.0,
    design_buffing_load_kn=1500.0,
)


def test_sound_member_is_recommended_for_approval(tmp_path: Path):
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
    assert len(items) == 9
    # The design-basis honesty item is graded OBSERVATION, never silently passed.
    assert items[0]["severity"] == "OBSERVATION"
    # DXF read-back item passed.
    dxf_item = next(i for i in result.items if "drawing" in i.title.lower())
    assert dxf_item.severity == "PASS"


def test_under_design_returns_for_revision_naming_the_member(tmp_path: Path):
    result, geometry, analysis = _run(UNDER, tmp_path)
    assert result.verdict == "return_for_revision"
    majors = [i for i in result.items if i.severity == "NON_CONFORMITY_MAJOR"]
    assert any("Bending" in i.title for i in majors)
    memo = render_memo(result, None, params=UNDER, geometry=geometry, analysis=analysis,
                       warnings=["Flange thickness override 8 mm is thinner than sized"])
    assert "RETURN FOR REVISION" in memo
    assert "member" in memo.lower()


def test_narration_grounding_rejects_ungrounded_number_and_forbidden_citation(tmp_path: Path):
    result, _g, _a = _run(SOUND, tmp_path)
    # An invented number that appears nowhere in the deterministic results.
    assert validate_narration("the design moment is 987654 kNm", result)
    # A forbidden (concrete) citation — the member cites RDSO / IS 800 only.
    assert validate_narration("checked as per IS 456 provisions", result)
    # A forbidden road-congress citation.
    assert validate_narration("as per IRC:24 clauses", result)
    # Empty narration is rejected.
    assert validate_narration("", result) == ["narration is empty"]
    # A narration that states the OPPOSITE verdict is rejected (SOUND -> approval).
    assert validate_narration("this design is a return for revision", result)


def test_deterministic_memo_is_self_grounded(tmp_path: Path):
    result, geometry, analysis = _run(SOUND, tmp_path)
    memo = render_memo(result, None, params=SOUND, geometry=geometry, analysis=analysis)
    # The fully deterministic memo passes its own grounding validator.
    assert validate_narration(memo, result) == []
    assert "RECOMMENDED FOR APPROVAL" in memo


def test_independent_cross_check_recomputes_the_section(tmp_path: Path):
    result, _g, analysis = _run(SOUND, tmp_path)
    cross = result.cross_check
    # The cross-check re-derives the section modulus and stresses from scratch and
    # agrees with the recorded analysis (rounded to its own display precision).
    assert cross.section_modulus_cm3 == pytest.approx(analysis.section_modulus_cm3, rel=1e-4)
    assert cross.max_bending_stress_mpa == pytest.approx(analysis.max_bending_stress_mpa, rel=1e-4)
    assert cross.max_axial_stress_mpa == pytest.approx(analysis.max_axial_stress_mpa, rel=1e-4)
    assert cross.within_tolerance and cross.agreement_pct >= 99.0


def test_dxf_readback_item_fails_when_drawing_is_missing(tmp_path: Path):
    g = size_member(SOUND).geometry
    analysis = analyse_member(SOUND, g)
    checks = run_member_checks(analysis, g, SOUND)
    result = run_proof_check(
        params=SOUND, geometry=g, analysis=analysis, checks=list(checks.checks),
        ga_dxf_path=tmp_path / "does_not_exist.dxf", out_dir=tmp_path,
    )
    dxf_item = next(i for i in result.items if "drawing" in i.title.lower())
    assert dxf_item.severity == "NON_CONFORMITY_MAJOR"
    assert result.verdict == "return_for_revision"
