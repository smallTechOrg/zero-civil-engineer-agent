"""PierAbutmentComponent adapter — registry, protocol, metadata, shared outputs."""

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
from components.pier_abutment.params import PierAbutmentGeometry, PierAbutmentParams

TYPE_ID = "pier_abutment"
CANONICAL = {
    "pier_height_m": 9.0,
    "superstructure_reaction_kn": 5000.0,
    "safe_bearing_capacity_kn_m2": 300.0,
}


@pytest.fixture
def pa():
    return registry.get(TYPE_ID)


def test_registered_and_available_graduated_from_the_stub():
    # The self-registering module wins over the coming_soon placeholder.
    assert registry.has(TYPE_ID) and registry.is_available(TYPE_ID)
    ids = {c["type_id"]: c["status"] for c in registry.list_components()}
    assert ids[TYPE_ID] == "available"


def test_satisfies_the_component_module_protocol(pa):
    assert isinstance(pa, ComponentModule)


def test_declares_full_metadata(pa):
    assert pa.type_id == TYPE_ID
    assert pa.display_name == "Pier & Abutment Substructure"
    assert pa.domain == "civil"
    assert pa.status == "available"
    assert pa.param_model is PierAbutmentParams
    assert pa.geometry_model is PierAbutmentGeometry
    # The RCC section design honestly cites the concrete codes, so they are declared
    # alongside the substructure/loads codes (IRC / IS 800 remain out-of-domain).
    assert set(pa.codes) == {
        "IRS Bridge Substructure & Foundation Code",
        "IRS Bridge Rules",
        "IRS Concrete Bridge Code",
        "IS 456",
    }
    assert pa.critical_fields == [
        "pier_height_m", "superstructure_reaction_kn", "safe_bearing_capacity_kn_m2",
    ]
    assert any("pier" in ex.lower() or "abutment" in ex.lower() for ex in pa.scope_examples)
    # member_labels + analysis_model exposed via the interface.
    assert "pier" in pa.member_labels
    assert pa.analysis_model is not None


def test_intake_helpers(pa):
    schema = pa.extraction_schema()
    assert "pier_height_m" in schema.model_fields
    assert pa.clarify_question("pier_height_m")
    assert pa.unusual_value_warnings({**CANONICAL, "safe_bearing_capacity_kn_m2": 60.0})


def test_size_analyse_run_checks_return_shared_result_types(pa):
    sizing = pa.size(CANONICAL)
    assert isinstance(sizing, SizingOutput) and isinstance(sizing.geometry, PierAbutmentGeometry)
    analysis = pa.analyse(CANONICAL, sizing.geometry)
    assert isinstance(analysis, AnalysisOutput)
    checks = pa.run_checks(CANONICAL, sizing.geometry, analysis.analysis)
    assert isinstance(checks, CheckOutput)
    assert all(c.status == "PASS" for c in checks.checks)
    # Accepts the typed model identically to the dict form.
    typed = pa.size(PierAbutmentParams(**CANONICAL))
    assert typed.geometry.model_dump() == sizing.geometry.model_dump()


def test_calc_sheet_draw_model3d_and_proof_write_the_shared_artefacts(pa, tmp_path: Path):
    sizing = pa.size(CANONICAL)
    g = sizing.geometry
    analysis = pa.analyse(CANONICAL, g)
    checks = pa.run_checks(CANONICAL, g, analysis.analysis)

    sheet = pa.compose_calc_sheet(
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

    draw = pa.draw(CANONICAL, g, tmp_path, run_id="mod")
    assert set(draw) == {"ga_dxf", "ga_svg"} and draw["ga_dxf"].is_file()
    m3d = pa.model3d(g, tmp_path)
    assert set(m3d) == {"model_glb", "model_step"} and m3d["model_glb"].is_file()

    proof = pa.proof_check(
        params=CANONICAL, geometry=g, analysis=analysis.analysis,
        checks=[c.model_dump() for c in checks.checks], ga_dxf_path=tmp_path / "ga.dxf",
        out_dir=tmp_path,
    )
    assert isinstance(proof, ProofCheckOutput)
    assert len(proof.checklist) == 10
    assert proof.verdict == "recommended_for_approval"
    # ONLY whitelisted artefact kinds — no new kinds introduced.
    assert {kind for kind, _ in proof.artefacts} == {"bmd_svg", "compliance"}
    assert proof.validate_narration("moment 987654 kNm")  # invented → rejected
    assert "RECOMMENDED FOR APPROVAL" in proof.render_memo(None)

    summary = pa.type_summary(
        params=CANONICAL, geometry=g, analysis=analysis.analysis,
        checks=[c.model_dump() for c in checks.checks], proof=proof,
    )
    # EXACT reused-stability-panel shape.
    assert set(summary) == {
        "kind", "fos_overturning", "fos_sliding", "max_bearing_pressure_kn_m2",
        "sbc_kn_m2", "bearing_ok", "verdict",
    }
    assert summary["kind"] == "stability"
    assert summary["verdict"] == "recommended_for_approval"
    assert summary["bearing_ok"] is True


def test_memo_prompt_is_the_substructure_system_prompt(pa):
    prompt = pa.memo_prompt()
    assert prompt and ("pier" in prompt.lower() or "abutment" in prompt.lower())
