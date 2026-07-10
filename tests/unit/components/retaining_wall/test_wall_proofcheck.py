"""Proof-check spine — verdict rule, narration grounding, artefacts."""

import json
from pathlib import Path

import pytest

from components.retaining_wall.analysis import analyse_wall
from components.retaining_wall.checks import run_wall_checks
from components.retaining_wall.drawing import generate_ga
from components.retaining_wall.params import RetainingWallParams
from components.retaining_wall.proofcheck import (
    render_memo,
    run_proof_check,
    validate_narration,
)
from components.retaining_wall.sizing import size_wall


def _run(params: RetainingWallParams, out_dir: Path):
    g = size_wall(params).geometry
    analysis = analyse_wall(params, g)
    checks = run_wall_checks(analysis, g, params)
    generate_ga(params, g, out_dir, run_id="pc")  # proof reads ga.dxf
    result = run_proof_check(
        params=params, geometry=g, analysis=analysis,
        checks=list(checks.checks), ga_dxf_path=out_dir / "ga.dxf", out_dir=out_dir,
    )
    return result, g, analysis


SOUND = RetainingWallParams(
    retained_height_m=5.0, safe_bearing_capacity_kn_m2=200.0, backfill_friction_angle_deg=30.0
)
UNDER = RetainingWallParams(
    retained_height_m=5.0, safe_bearing_capacity_kn_m2=200.0, backfill_friction_angle_deg=30.0,
    stem_base_thickness_mm=250.0,
)


def test_sound_wall_is_recommended_for_approval(tmp_path: Path):
    result, geometry, analysis = _run(SOUND, tmp_path)
    assert result.verdict == "recommended_for_approval"
    assert len(result.items) == 12
    assert result.cross_check.within_tolerance
    assert result.agreement_pct >= 95.0
    assert (tmp_path / "compliance.json").is_file()
    assert (tmp_path / "bmd.svg").is_file()
    payload = json.loads((tmp_path / "compliance.json").read_text())
    assert payload["verdict"] == "recommended_for_approval"
    assert [i["item"] for i in payload["items"]] == list(range(1, 13))
    # DXF read-back item passed.
    dxf_item = next(i for i in result.items if i.item == 12)
    assert dxf_item.severity == "PASS"


def test_under_design_returns_for_revision_naming_the_stem(tmp_path: Path):
    result, geometry, analysis = _run(UNDER, tmp_path)
    assert result.verdict == "return_for_revision"
    majors = [i for i in result.items if i.severity == "NON_CONFORMITY_MAJOR"]
    assert any("Stem flexure" == i.title for i in majors)
    memo = render_memo(result, None, params=UNDER, geometry=geometry, analysis=analysis,
                       warnings=["Stem base thickness override 250 mm is thinner than sized"])
    assert "RETURN FOR REVISION" in memo
    assert "stem" in memo.lower()


def test_narration_grounding_rejects_ungrounded_number_and_forbidden_citation(tmp_path: Path):
    result, _g, _a = _run(SOUND, tmp_path)
    # An invented number that appears nowhere in the deterministic results.
    assert validate_narration("the driving thrust is 987654 kN", result)
    # A forbidden (road-congress) citation.
    assert validate_narration("checked as per IRC:78 provisions", result)
    # Empty narration is rejected.
    assert validate_narration("", result) == ["narration is empty"]
    # A narration that states the OPPOSITE verdict is rejected (SOUND -> approval).
    assert validate_narration("this design is a return for revision", result)


def test_deterministic_memo_is_self_grounded(tmp_path: Path):
    result, geometry, analysis = _run(SOUND, tmp_path)
    memo = render_memo(result, None, params=SOUND, geometry=geometry, analysis=analysis)
    # The fully deterministic memo passes its own grounding validator (no number
    # in the memo is absent from the deterministic results).
    assert validate_narration(memo, result) == []


def test_dxf_readback_item_fails_when_drawing_is_missing(tmp_path: Path):
    g = size_wall(SOUND).geometry
    analysis = analyse_wall(SOUND, g)
    checks = run_wall_checks(analysis, g, SOUND)
    result = run_proof_check(
        params=SOUND, geometry=g, analysis=analysis, checks=list(checks.checks),
        ga_dxf_path=tmp_path / "does_not_exist.dxf", out_dir=tmp_path,
    )
    dxf_item = next(i for i in result.items if i.item == 12)
    assert dxf_item.severity == "NON_CONFORMITY_MAJOR"
    assert result.verdict == "return_for_revision"
