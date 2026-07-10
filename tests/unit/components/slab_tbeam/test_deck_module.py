"""SlabTbeamComponent adapter — registry, protocol, metadata, shared outputs."""

from pathlib import Path

import pytest

from components import registry
from components.base import (
    AnalysisOutput,
    CheckOutput,
    ComponentModule,
    ProofCheckOutput,
    SizingOutput,
)
from components.slab_tbeam.params import SlabTbeamGeometry, SlabTbeamParams

TYPE_ID = "slab_tbeam"
CANONICAL = {"span_m": 12.0, "deck_type": "t_beam"}


@pytest.fixture
def deck():
    return registry.get(TYPE_ID)


def test_registered_and_available_alongside_the_other_components():
    ids = {c["type_id"]: c["status"] for c in registry.list_components()}
    assert ids["box_culvert"] == "available"
    assert ids["rcc_cantilever_retaining_wall"] == "available"
    assert ids[TYPE_ID] == "available"
    assert registry.has(TYPE_ID) and registry.is_available(TYPE_ID)


def test_satisfies_the_component_module_protocol(deck):
    assert isinstance(deck, ComponentModule)


def test_declares_full_metadata(deck):
    assert deck.type_id == TYPE_ID
    assert deck.display_name == "RCC Slab / T-Beam Deck"
    assert deck.domain == "civil"
    assert deck.status == "available"
    assert deck.param_model is SlabTbeamParams
    assert deck.geometry_model is SlabTbeamGeometry
    assert set(deck.codes) == {"IRS Concrete Bridge Code", "IS 456", "IR Bridge Rules"}
    assert deck.critical_fields == ["span_m"]
    assert any("t-beam" in ex.lower() or "slab" in ex.lower() for ex in deck.scope_examples)


def test_classify_metadata_lists_the_deck_with_scope_examples():
    meta = {m["type_id"]: m for m in registry.classify_metadata()}
    assert meta[TYPE_ID]["status"] == "available"
    assert meta[TYPE_ID]["scope_examples"]


def test_intake_helpers(deck):
    schema = deck.extraction_schema()
    assert "span_m" in schema.model_fields
    assert deck.clarify_question("span_m")
    assert deck.unusual_value_warnings({**CANONICAL, "span_m": 22.0})


def test_size_analyse_run_checks_return_shared_result_types(deck):
    sizing = deck.size(CANONICAL)
    assert isinstance(sizing, SizingOutput) and isinstance(sizing.geometry, SlabTbeamGeometry)
    analysis = deck.analyse(CANONICAL, sizing.geometry)
    assert isinstance(analysis, AnalysisOutput)
    checks = deck.run_checks(CANONICAL, sizing.geometry, analysis.analysis)
    assert isinstance(checks, CheckOutput)
    assert all(c.status == "PASS" for c in checks.checks)
    # Accepts the typed model identically to the dict form.
    typed = deck.size(SlabTbeamParams(**CANONICAL))
    assert typed.geometry.model_dump() == sizing.geometry.model_dump()


def test_calc_sheet_draw_model3d_and_proof_write_the_shared_artefacts(deck, tmp_path: Path):
    sizing = deck.size(CANONICAL)
    g = sizing.geometry
    analysis = deck.analyse(CANONICAL, g)
    checks = deck.run_checks(CANONICAL, g, analysis.analysis)

    sheet = deck.compose_calc_sheet(
        params=CANONICAL, geometry=g, analysis=analysis.analysis,
        checks=[c.model_dump() for c in checks.checks],
        assumptions=[a.model_dump() for a in sizing.assumptions], warnings=[],
        trail_segments=[
            [s.model_dump() for s in sizing.trail],
            [s.model_dump() for s in analysis.trail],
            [s.model_dump() for s in checks.trail],
        ],
        out_dir=tmp_path,
    )
    assert sheet.name == "calc_sheet.json" and sheet.is_file()

    draw = deck.draw(CANONICAL, g, tmp_path, run_id="mod")
    assert set(draw) == {"ga_dxf", "ga_svg"} and draw["ga_dxf"].is_file()
    m3d = deck.model3d(g, tmp_path)
    assert set(m3d) == {"model_glb", "model_step"} and m3d["model_glb"].is_file()

    proof = deck.proof_check(
        params=CANONICAL, geometry=g, analysis=analysis.analysis,
        checks=[c.model_dump() for c in checks.checks], ga_dxf_path=tmp_path / "ga.dxf",
        out_dir=tmp_path,
    )
    assert isinstance(proof, ProofCheckOutput)
    assert len(proof.checklist) == 9
    assert proof.verdict == "recommended_for_approval"
    # ONLY whitelisted artefact kinds — no new kinds introduced.
    assert {kind for kind, _ in proof.artefacts} == {"bmd_svg", "compliance"}
    assert proof.validate_narration("moment 987654 kNm")  # invented -> rejected
    assert "RECOMMENDED FOR APPROVAL" in proof.render_memo(None)

    summary = deck.type_summary(
        params=CANONICAL, geometry=g, analysis=analysis.analysis,
        checks=[c.model_dump() for c in checks.checks], proof=proof,
    )
    assert summary["kind"] == "flexure_summary"
    assert summary["verdict"] == "recommended_for_approval"
    assert set(summary) == {
        "kind", "design_moment_knm", "required_depth_mm", "provided_depth_mm",
        "flexure_ok", "design_shear_kn", "shear_stress_mpa", "permissible_shear_mpa",
        "shear_ok", "steel_area_mm2", "min_steel_mm2", "verdict",
    }


def test_member_labels_and_analysis_model_are_exposed(deck):
    assert "girder" in deck.member_labels or "deck" in deck.member_labels
    from components.slab_tbeam.analysis import SlabTbeamAnalysis

    assert deck.analysis_model is SlabTbeamAnalysis


def test_memo_prompt_is_the_deck_system_prompt(deck):
    prompt = deck.memo_prompt()
    assert prompt and ("t-beam" in prompt.lower() or "deck" in prompt.lower())
