"""RollingStockMemberComponent adapter — registry, protocol, metadata, shared outputs.

The package-`__init__` wiring into `src/components/__init__.py` is a sibling slice, so
these tests import the module DIRECTLY (which self-registers) and drive the component
instance, exactly as the pier_abutment tests do for their own slice.
"""

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
from components.rolling_stock_member.module import RollingStockMemberComponent
from components.rolling_stock_member.params import (
    RollingStockMemberGeometry,
    RollingStockMemberParams,
)

TYPE_ID = "rolling_stock_member"
CANONICAL = {"member_length_m": 6.0}


@pytest.fixture
def member():
    return RollingStockMemberComponent()


def test_registered_and_available_graduated_from_the_stub():
    # Importing the module self-registered the available component over the
    # coming_soon placeholder of the same type_id.
    assert registry.has(TYPE_ID) and registry.is_available(TYPE_ID)
    ids = {c["type_id"]: c["status"] for c in registry.list_components()}
    assert ids[TYPE_ID] == "available"


def test_satisfies_the_component_module_protocol(member):
    assert isinstance(member, ComponentModule)


def test_declares_full_metadata(member):
    assert member.type_id == TYPE_ID
    assert member.display_name == "Rolling-Stock Member"
    assert member.domain == "mechanical"
    assert member.status == "available"
    assert member.param_model is RollingStockMemberParams
    assert member.geometry_model is RollingStockMemberGeometry
    assert set(member.codes) == {"RDSO Specifications", "IS 800"}
    assert member.critical_fields == ["member_length_m"]
    assert any("rdso" in ex.lower() or "underframe" in ex.lower() for ex in member.scope_examples)
    # member_labels + analysis_model exposed via the interface.
    assert "member" in member.member_labels
    assert member.analysis_model.__name__ == "RollingStockMemberAnalysis"


def test_intake_helpers(member):
    schema = member.extraction_schema()
    assert "member_length_m" in schema.model_fields
    assert member.clarify_question("member_length_m")
    assert member.unusual_value_warnings({**CANONICAL, "member_length_m": 13.0})


def test_size_analyse_run_checks_return_shared_result_types(member):
    sizing = member.size(CANONICAL)
    assert isinstance(sizing, SizingOutput) and isinstance(sizing.geometry, RollingStockMemberGeometry)
    analysis = member.analyse(CANONICAL, sizing.geometry)
    assert isinstance(analysis, AnalysisOutput)
    checks = member.run_checks(CANONICAL, sizing.geometry, analysis.analysis)
    assert isinstance(checks, CheckOutput)
    assert all(c.status == "PASS" for c in checks.checks)
    # Accepts the typed model identically to the dict form.
    typed = member.size(RollingStockMemberParams(**CANONICAL))
    assert typed.geometry.model_dump() == sizing.geometry.model_dump()


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
    assert len(proof.checklist) == 9
    assert proof.verdict == "recommended_for_approval"
    # ONLY whitelisted artefact kinds — no new kinds introduced.
    assert {kind for kind, _ in proof.artefacts} == {"bmd_svg", "compliance"}
    assert proof.validate_narration("moment 987654 kNm")  # invented -> rejected
    assert "RECOMMENDED FOR APPROVAL" in proof.render_memo(None)

    summary = member.type_summary(
        params=CANONICAL, geometry=g, analysis=analysis.analysis,
        checks=[c.model_dump() for c in checks.checks], proof=proof,
    )
    # Exact key set is the pinned strength_summary shape.
    assert set(summary) == {
        "kind", "max_bending_stress_mpa", "permissible_bending_stress_mpa", "bending_ok",
        "max_shear_stress_mpa", "permissible_shear_stress_mpa", "shear_ok",
        "governing_load_case", "verdict",
    }
    assert summary["kind"] == "strength_summary"
    assert summary["bending_ok"] is True
    assert summary["shear_ok"] is True
    assert summary["verdict"] == "recommended_for_approval"
    assert isinstance(summary["governing_load_case"], str) and summary["governing_load_case"]
    assert all(isinstance(summary[k], float) for k in (
        "max_bending_stress_mpa", "permissible_bending_stress_mpa",
        "max_shear_stress_mpa", "permissible_shear_stress_mpa",
    ))


def test_memo_prompt_is_the_rolling_stock_member_system_prompt(member):
    prompt = member.memo_prompt()
    assert prompt and ("rolling-stock" in prompt.lower() or "rolling stock" in prompt.lower())
