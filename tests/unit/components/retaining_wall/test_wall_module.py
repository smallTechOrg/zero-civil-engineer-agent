"""RetainingWallComponent adapter — registry, protocol, metadata, shared outputs."""

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
from components.retaining_wall.params import RetainingWallGeometry, RetainingWallParams

TYPE_ID = "rcc_cantilever_retaining_wall"
CANONICAL = {"retained_height_m": 5.0, "safe_bearing_capacity_kn_m2": 200.0, "backfill_friction_angle_deg": 30.0}


@pytest.fixture
def wall():
    return registry.get(TYPE_ID)


def test_registered_and_available_alongside_the_culvert():
    ids = {c["type_id"]: c["status"] for c in registry.list_components()}
    assert ids["box_culvert"] == "available"
    assert ids[TYPE_ID] == "available"
    assert registry.has(TYPE_ID) and registry.is_available(TYPE_ID)


def test_satisfies_the_component_module_protocol(wall):
    assert isinstance(wall, ComponentModule)


def test_declares_full_metadata(wall):
    assert wall.type_id == TYPE_ID
    assert wall.display_name == "RCC Cantilever Retaining Wall"
    assert wall.domain == "civil"
    assert wall.status == "available"
    assert wall.param_model is RetainingWallParams
    assert wall.geometry_model is RetainingWallGeometry
    assert set(wall.codes) == {
        "IRS Concrete Bridge Code", "IS 456", "IR Bridge Rules",
        "IRS Bridge Substructure & Foundation Code",
    }
    assert wall.critical_fields == [
        "retained_height_m", "safe_bearing_capacity_kn_m2", "backfill_friction_angle_deg",
    ]
    # Scope examples must strongly cue auto-detect for retaining-wall requests.
    assert any("retaining wall" in ex.lower() for ex in wall.scope_examples)


def test_classify_metadata_lists_the_wall_with_scope_examples():
    meta = {m["type_id"]: m for m in registry.classify_metadata()}
    assert meta[TYPE_ID]["status"] == "available"
    assert meta[TYPE_ID]["scope_examples"]


def test_intake_helpers(wall):
    schema = wall.extraction_schema()
    assert "retained_height_m" in schema.model_fields
    assert wall.clarify_question("retained_height_m")
    assert wall.unusual_value_warnings({**CANONICAL, "retained_height_m": 7.5})


def test_size_analyse_run_checks_return_shared_result_types(wall):
    sizing = wall.size(CANONICAL)
    assert isinstance(sizing, SizingOutput) and isinstance(sizing.geometry, RetainingWallGeometry)
    analysis = wall.analyse(CANONICAL, sizing.geometry)
    assert isinstance(analysis, AnalysisOutput)
    checks = wall.run_checks(CANONICAL, sizing.geometry, analysis.analysis)
    assert isinstance(checks, CheckOutput)
    assert all(c.status == "PASS" for c in checks.checks)
    # Accepts the typed model identically to the dict form.
    typed = wall.size(RetainingWallParams(**CANONICAL))
    assert typed.geometry.model_dump() == sizing.geometry.model_dump()


def test_calc_sheet_draw_model3d_and_proof_write_the_shared_artefacts(wall, tmp_path: Path):
    sizing = wall.size(CANONICAL)
    g = sizing.geometry
    analysis = wall.analyse(CANONICAL, g)
    checks = wall.run_checks(CANONICAL, g, analysis.analysis)

    sheet = wall.compose_calc_sheet(
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

    draw = wall.draw(CANONICAL, g, tmp_path, run_id="mod")
    assert set(draw) == {"ga_dxf", "ga_svg"} and draw["ga_dxf"].is_file()
    m3d = wall.model3d(g, tmp_path)
    assert set(m3d) == {"model_glb", "model_step"} and m3d["model_glb"].is_file()

    proof = wall.proof_check(
        params=CANONICAL, geometry=g, analysis=analysis.analysis,
        checks=[c.model_dump() for c in checks.checks], ga_dxf_path=tmp_path / "ga.dxf",
        out_dir=tmp_path,
    )
    assert isinstance(proof, ProofCheckOutput)
    assert len(proof.checklist) == 12
    assert proof.verdict == "recommended_for_approval"
    # ONLY whitelisted artefact kinds — no new kinds introduced.
    assert {kind for kind, _ in proof.artefacts} == {"bmd_svg", "compliance"}
    assert proof.validate_narration("moment 987654 kNm")  # invented → rejected
    assert "RECOMMENDED FOR APPROVAL" in proof.render_memo(None)

    summary = wall.type_summary(
        params=CANONICAL, geometry=g, analysis=analysis.analysis,
        checks=[c.model_dump() for c in checks.checks], proof=proof,
    )
    assert summary["kind"] == "stability"
    assert summary["verdict"] == "recommended_for_approval"


def test_memo_prompt_is_the_retaining_wall_system_prompt(wall):
    prompt = wall.memo_prompt()
    assert prompt and "retaining" in prompt.lower()
