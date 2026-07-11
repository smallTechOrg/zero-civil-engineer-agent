"""PlateGirderComponent adapter — registry, protocol, metadata, shared outputs."""

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
from components.plate_girder.params import PlateGirderGeometry, PlateGirderParams

TYPE_ID = "plate_girder"
CANONICAL = {"span_m": 24.0, "steel_grade": "E250"}


@pytest.fixture
def girder():
    return registry.get(TYPE_ID)


def test_registered_and_available_alongside_the_other_components():
    ids = {c["type_id"]: c["status"] for c in registry.list_components()}
    assert ids[TYPE_ID] == "available"
    assert registry.has(TYPE_ID) and registry.is_available(TYPE_ID)


def test_satisfies_the_component_module_protocol(girder):
    assert isinstance(girder, ComponentModule)


def test_declares_full_metadata(girder):
    assert girder.type_id == TYPE_ID
    assert girder.display_name == "Welded Steel Plate Girder"
    assert girder.domain == "civil"
    assert girder.status == "available"
    assert girder.param_model is PlateGirderParams
    assert girder.geometry_model is PlateGirderGeometry
    assert set(girder.codes) == {"IRS Steel Bridge Code", "IS 800", "IR Bridge Rules"}
    assert girder.critical_fields == ["span_m", "steel_grade"]
    assert any("plate girder" in ex.lower() for ex in girder.scope_examples)


def test_classify_metadata_lists_the_girder_with_scope_examples():
    meta = {m["type_id"]: m for m in registry.classify_metadata()}
    assert meta[TYPE_ID]["status"] == "available"
    assert meta[TYPE_ID]["scope_examples"]


def test_intake_helpers(girder):
    schema = girder.extraction_schema()
    assert "span_m" in schema.model_fields
    assert girder.clarify_question("span_m")
    assert girder.unusual_value_warnings({**CANONICAL, "span_m": 50.0})


def test_size_analyse_run_checks_return_shared_result_types(girder):
    sizing = girder.size(CANONICAL)
    assert isinstance(sizing, SizingOutput) and isinstance(sizing.geometry, PlateGirderGeometry)
    analysis = girder.analyse(CANONICAL, sizing.geometry)
    assert isinstance(analysis, AnalysisOutput)
    checks = girder.run_checks(CANONICAL, sizing.geometry, analysis.analysis)
    assert isinstance(checks, CheckOutput)
    assert all(c.status == "PASS" for c in checks.checks)
    # Accepts the typed model identically to the dict form.
    typed = girder.size(PlateGirderParams(**CANONICAL))
    assert typed.geometry.model_dump() == sizing.geometry.model_dump()


def test_member_labels_exposed(girder):
    assert "girder" in girder.member_labels
    assert girder.analysis_model.__name__ == "PlateGirderAnalysis"


def test_calc_sheet_draw_model3d_and_proof_write_the_shared_artefacts(girder, tmp_path: Path):
    sizing = girder.size(CANONICAL)
    g = sizing.geometry
    analysis = girder.analyse(CANONICAL, g)
    checks = girder.run_checks(CANONICAL, g, analysis.analysis)

    sheet = girder.compose_calc_sheet(
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

    draw = girder.draw(CANONICAL, g, tmp_path, run_id="mod")
    assert set(draw) == {"ga_dxf", "ga_svg"} and draw["ga_dxf"].is_file()
    m3d = girder.model3d(g, tmp_path)
    assert set(m3d) == {"model_glb", "model_step"} and m3d["model_glb"].is_file()

    proof = girder.proof_check(
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

    summary = girder.type_summary(
        params=CANONICAL, geometry=g, analysis=analysis.analysis,
        checks=[c.model_dump() for c in checks.checks], proof=proof,
    )
    assert summary == {
        "kind": "stress_summary",
        "max_bending_stress_mpa": summary["max_bending_stress_mpa"],
        "permissible_bending_stress_mpa": summary["permissible_bending_stress_mpa"],
        "bending_ok": True,
        "max_shear_stress_mpa": summary["max_shear_stress_mpa"],
        "permissible_shear_stress_mpa": summary["permissible_shear_stress_mpa"],
        "shear_ok": True,
        "max_deflection_mm": summary["max_deflection_mm"],
        "deflection_limit_mm": summary["deflection_limit_mm"],
        "deflection_ok": True,
        "verdict": "recommended_for_approval",
    }
    # Exact key set is the pinned stress_summary shape.
    assert set(summary) == {
        "kind", "max_bending_stress_mpa", "permissible_bending_stress_mpa", "bending_ok",
        "max_shear_stress_mpa", "permissible_shear_stress_mpa", "shear_ok",
        "max_deflection_mm", "deflection_limit_mm", "deflection_ok", "verdict",
    }
    assert all(isinstance(summary[k], float) for k in (
        "max_bending_stress_mpa", "permissible_bending_stress_mpa",
        "max_shear_stress_mpa", "permissible_shear_stress_mpa",
        "max_deflection_mm", "deflection_limit_mm",
    ))


def test_memo_prompt_is_the_plate_girder_system_prompt(girder):
    prompt = girder.memo_prompt()
    assert prompt and ("plate girder" in prompt.lower() or "plate-girder" in prompt.lower())
