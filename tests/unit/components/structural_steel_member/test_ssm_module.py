"""StructuralSteelMemberComponent adapter — registry, protocol, metadata, shared outputs."""

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

# Import the module directly so it self-registers (the package is not yet wired
# into components/__init__.py — that is a sibling slice), exactly like the
# pier_abutment tests import directly.
from components.structural_steel_member.module import StructuralSteelMemberComponent
from components.structural_steel_member.params import SteelMemberGeometry, SteelMemberParams

TYPE_ID = "structural_steel_member"
CANONICAL = {"cantilever_length_m": 6.0, "transverse_load_kn": 20.0}


@pytest.fixture
def member():
    return registry.get(TYPE_ID)


def test_registered_and_available_replacing_the_coming_soon_stub():
    ids = {c["type_id"]: c["status"] for c in registry.list_components()}
    assert ids[TYPE_ID] == "available"
    assert registry.has(TYPE_ID) and registry.is_available(TYPE_ID)


def test_satisfies_the_component_module_protocol(member):
    assert isinstance(member, ComponentModule)


def test_declares_full_metadata(member):
    assert member.type_id == TYPE_ID
    assert member.display_name == "Structural Steel / Fabrication Member"
    assert member.domain == "mechanical"
    assert member.status == "available"
    assert member.param_model is SteelMemberParams
    assert member.geometry_model is SteelMemberGeometry
    assert set(member.codes) == {"IS 800", "IS 816"}
    assert member.critical_fields == ["cantilever_length_m", "transverse_load_kn"]
    assert any("bracket" in ex.lower() or "steel" in ex.lower() for ex in member.scope_examples)


def test_classify_metadata_lists_the_member_with_scope_examples():
    meta = {m["type_id"]: m for m in registry.classify_metadata()}
    assert meta[TYPE_ID]["status"] == "available"
    assert meta[TYPE_ID]["scope_examples"]


def test_intake_helpers(member):
    schema = member.extraction_schema()
    assert "cantilever_length_m" in schema.model_fields
    assert "transverse_load_kn" in schema.model_fields
    assert member.clarify_question("cantilever_length_m")
    assert member.clarify_question("transverse_load_kn")
    assert member.unusual_value_warnings({**CANONICAL, "cantilever_length_m": 11.0})


def test_size_analyse_run_checks_return_shared_result_types(member):
    sizing = member.size(CANONICAL)
    assert isinstance(sizing, SizingOutput) and isinstance(sizing.geometry, SteelMemberGeometry)
    analysis = member.analyse(CANONICAL, sizing.geometry)
    assert isinstance(analysis, AnalysisOutput)
    checks = member.run_checks(CANONICAL, sizing.geometry, analysis.analysis)
    assert isinstance(checks, CheckOutput)
    assert all(c.status == "PASS" for c in checks.checks)
    # Accepts the typed model identically to the dict form.
    typed = member.size(SteelMemberParams(**CANONICAL))
    assert typed.geometry.model_dump() == sizing.geometry.model_dump()


def test_member_labels_exposed(member):
    assert "weld" in member.member_labels
    assert member.analysis_model.__name__ == "SteelMemberAnalysis"


def test_calc_sheet_draw_model3d_and_proof_write_the_shared_artefacts(member, tmp_path: Path):
    sizing = member.size(CANONICAL)
    g = sizing.geometry
    analysis = member.analyse(CANONICAL, g)
    checks = member.run_checks(CANONICAL, g, analysis.analysis)

    sheet = member.compose_calc_sheet(
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

    draw = member.draw(CANONICAL, g, tmp_path, run_id="mod")
    assert set(draw) == {"ga_dxf", "ga_svg"} and draw["ga_dxf"].is_file()
    m3d = member.model3d(g, tmp_path)
    assert set(m3d) == {"model_glb", "model_step"} and m3d["model_glb"].is_file()

    proof = member.proof_check(
        params=CANONICAL, geometry=g, analysis=analysis.analysis,
        checks=[c.model_dump() for c in checks.checks], ga_dxf_path=tmp_path / "ga.dxf",
        out_dir=tmp_path,
    )
    assert isinstance(proof, ProofCheckOutput)
    assert proof.verdict == "recommended_for_approval"
    # ONLY whitelisted artefact kinds — no new kinds introduced.
    assert {kind for kind, _ in proof.artefacts} == {"bmd_svg", "compliance"}
    assert proof.validate_narration("moment 987654 kNm")  # invented -> rejected
    assert "RECOMMENDED FOR APPROVAL" in proof.render_memo(None)

    summary = member.type_summary(
        params=CANONICAL, geometry=g, analysis=analysis.analysis,
        checks=[c.model_dump() for c in checks.checks], proof=proof,
    )
    # Exact key set is the PINNED utilisation_summary shape.
    assert set(summary) == {
        "kind",
        "max_bending_stress_mpa", "permissible_bending_stress_mpa", "bending_ok",
        "max_shear_stress_mpa", "permissible_shear_stress_mpa", "shear_ok",
        "max_axial_stress_mpa", "permissible_axial_stress_mpa", "axial_ok",
        "weld_stress_mpa", "permissible_weld_stress_mpa", "weld_ok",
        "verdict",
    }
    assert summary["kind"] == "utilisation_summary"
    assert summary["verdict"] == "recommended_for_approval"
    assert summary["bending_ok"] and summary["shear_ok"] and summary["axial_ok"] and summary["weld_ok"]
    assert all(isinstance(summary[k], float) for k in (
        "max_bending_stress_mpa", "permissible_bending_stress_mpa",
        "max_shear_stress_mpa", "permissible_shear_stress_mpa",
        "max_axial_stress_mpa", "permissible_axial_stress_mpa",
        "weld_stress_mpa", "permissible_weld_stress_mpa",
    ))


def test_memo_prompt_is_the_steel_member_system_prompt(member):
    prompt = member.memo_prompt()
    assert prompt and ("steel" in prompt.lower() and ("weld" in prompt.lower()))
