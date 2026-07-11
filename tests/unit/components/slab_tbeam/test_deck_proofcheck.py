"""Proof-check spine — verdict rule, narration grounding, artefacts."""

import json
from pathlib import Path

from components.slab_tbeam.analysis import analyse_deck
from components.slab_tbeam.checks import run_deck_checks
from components.slab_tbeam.drawing import generate_ga
from components.slab_tbeam.params import SlabTbeamParams
from components.slab_tbeam.proofcheck import (
    render_memo,
    run_proof_check,
    validate_narration,
)
from components.slab_tbeam.sizing import size_deck


def _run(params: SlabTbeamParams, out_dir: Path):
    g = size_deck(params).geometry
    analysis = analyse_deck(params, g)
    checks = run_deck_checks(analysis, g, params)
    generate_ga(params, g, out_dir, run_id="pc")  # proof reads ga.dxf
    result = run_proof_check(
        params=params, geometry=g, analysis=analysis,
        checks=list(checks.checks), ga_dxf_path=out_dir / "ga.dxf", out_dir=out_dir,
    )
    return result, g, analysis


SOUND = SlabTbeamParams(span_m=12.0, deck_type="t_beam")
UNDER = SlabTbeamParams(span_m=12.0, deck_type="solid_slab", slab_depth_mm=300.0)


def test_sound_deck_is_recommended_for_approval(tmp_path: Path):
    result, geometry, analysis = _run(SOUND, tmp_path)
    assert result.verdict == "recommended_for_approval"
    assert len(result.items) == 9
    assert result.cross_check.within_tolerance
    assert result.agreement_pct >= 95.0
    assert (tmp_path / "compliance.json").is_file()
    assert (tmp_path / "bmd.svg").is_file()
    payload = json.loads((tmp_path / "compliance.json").read_text())
    assert payload["verdict"] == "recommended_for_approval"
    assert [i["item"] for i in payload["items"]] == list(range(1, 10))
    dxf_item = next(i for i in result.items if i.item == 9)
    assert dxf_item.severity == "PASS"


def test_under_design_returns_for_revision_on_a_flexure_major(tmp_path: Path):
    result, geometry, analysis = _run(UNDER, tmp_path)
    assert result.verdict == "return_for_revision"
    majors = [i for i in result.items if i.severity == "NON_CONFORMITY_MAJOR"]
    assert any(i.title == "Flexure adequacy" for i in majors)
    memo = render_memo(result, None, params=UNDER, geometry=geometry, analysis=analysis,
                       warnings=["Overall slab depth override 300 mm is thinner than sized"])
    assert "RETURN FOR REVISION" in memo


def test_live_load_re_derivation_item_conforms_for_a_sound_deck(tmp_path: Path):
    result, _g, _a = _run(SOUND, tmp_path)
    ll_item = next(i for i in result.items if i.item == 2)
    assert ll_item.severity == "PASS"
    assert "EUDL" in ll_item.title


def test_narration_grounding_rejects_ungrounded_number_and_forbidden_citation(tmp_path: Path):
    result, _g, _a = _run(SOUND, tmp_path)
    assert validate_narration("the design moment is 987654 kN*m", result)
    assert validate_narration("checked as per IS 800 provisions", result)  # steel code forbidden
    assert validate_narration("designed per IRC:21 clauses", result)  # road-congress forbidden
    assert validate_narration("", result) == ["narration is empty"]
    # A narration stating the OPPOSITE verdict is rejected (SOUND -> approval).
    assert validate_narration("this deck is a return for revision", result)


def test_deterministic_memo_is_self_grounded(tmp_path: Path):
    result, geometry, analysis = _run(SOUND, tmp_path)
    memo = render_memo(result, None, params=SOUND, geometry=geometry, analysis=analysis)
    assert validate_narration(memo, result) == []


def test_dxf_readback_item_fails_when_drawing_is_missing(tmp_path: Path):
    g = size_deck(SOUND).geometry
    analysis = analyse_deck(SOUND, g)
    checks = run_deck_checks(analysis, g, SOUND)
    result = run_proof_check(
        params=SOUND, geometry=g, analysis=analysis, checks=list(checks.checks),
        ga_dxf_path=tmp_path / "does_not_exist.dxf", out_dir=tmp_path,
    )
    dxf_item = next(i for i in result.items if i.item == 9)
    assert dxf_item.severity == "NON_CONFORMITY_MAJOR"
    assert result.verdict == "return_for_revision"
