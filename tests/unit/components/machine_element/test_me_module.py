"""MachineElementComponent adapter — registry, protocol, metadata, shared outputs."""

from pathlib import Path

import pytest

import components.machine_element.module  # noqa: F401  (self-registers, overriding the coming_soon stub)
from components import registry
from components.base import (
    AnalysisOutput,
    CheckOutput,
    ComponentModule,
    ProofCheckOutput,
    SizingOutput,
)
from components.machine_element.params import MachineElementGeometry, MachineElementParams

TYPE_ID = "machine_element"
CANONICAL = {"power_kw": 20.0, "speed_rpm": 1000.0}


@pytest.fixture
def element():
    return registry.get(TYPE_ID)


def test_registered_and_available_alongside_the_other_components():
    ids = {c["type_id"]: c["status"] for c in registry.list_components()}
    assert ids[TYPE_ID] == "available"
    assert registry.has(TYPE_ID) and registry.is_available(TYPE_ID)


def test_satisfies_the_component_module_protocol(element):
    assert isinstance(element, ComponentModule)


def test_declares_full_metadata(element):
    assert element.type_id == TYPE_ID
    assert element.display_name == "Machine Element"
    assert element.domain == "mechanical"
    assert element.status == "available"
    assert element.param_model is MachineElementParams
    assert element.geometry_model is MachineElementGeometry
    assert set(element.codes) == {"Machine Design Code (Shigley / PSG / Design Data Book)", "IS 816"}
    assert element.critical_fields == ["power_kw"]
    assert any("shaft" in ex.lower() for ex in element.scope_examples)


def test_declared_codes_are_mechanical_not_civil(element):
    joined = " | ".join(element.codes)
    # Machine-design basis only — NO bridge/road/concrete codes.
    assert "IRC" not in joined
    assert "IS 456" not in joined
    assert "IRS Concrete Bridge Code" not in joined


def test_classify_metadata_lists_the_element_with_scope_examples():
    meta = {m["type_id"]: m for m in registry.classify_metadata()}
    assert meta[TYPE_ID]["status"] == "available"
    assert meta[TYPE_ID]["scope_examples"]


def test_intake_helpers(element):
    schema = element.extraction_schema()
    assert "power_kw" in schema.model_fields
    assert element.clarify_question("power_kw")
    assert element.unusual_value_warnings({**CANONICAL, "power_kw": 1500.0})


def test_size_analyse_run_checks_return_shared_result_types(element):
    sizing = element.size(CANONICAL)
    assert isinstance(sizing, SizingOutput) and isinstance(sizing.geometry, MachineElementGeometry)
    analysis = element.analyse(CANONICAL, sizing.geometry)
    assert isinstance(analysis, AnalysisOutput)
    checks = element.run_checks(CANONICAL, sizing.geometry, analysis.analysis)
    assert isinstance(checks, CheckOutput)
    assert all(c.status == "PASS" for c in checks.checks)
    # Accepts the typed model identically to the dict form.
    typed = element.size(MachineElementParams(**CANONICAL))
    assert typed.geometry.model_dump() == sizing.geometry.model_dump()


def test_member_labels_exposed(element):
    assert "shaft" in element.member_labels
    assert element.analysis_model.__name__ == "MachineElementAnalysis"


def test_calc_sheet_draw_model3d_and_proof_write_the_shared_artefacts(element, tmp_path: Path):
    sizing = element.size(CANONICAL)
    g = sizing.geometry
    analysis = element.analyse(CANONICAL, g)
    checks = element.run_checks(CANONICAL, g, analysis.analysis)

    sheet = element.compose_calc_sheet(
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

    draw = element.draw(CANONICAL, g, tmp_path, run_id="mod")
    assert set(draw) == {"ga_dxf", "ga_svg"} and draw["ga_dxf"].is_file()
    m3d = element.model3d(g, tmp_path)
    assert set(m3d) == {"model_glb", "model_step"} and m3d["model_glb"].is_file()

    proof = element.proof_check(
        params=CANONICAL, geometry=g, analysis=analysis.analysis,
        checks=[c.model_dump() for c in checks.checks], ga_dxf_path=tmp_path / "ga.dxf",
        out_dir=tmp_path,
    )
    assert isinstance(proof, ProofCheckOutput)
    assert proof.verdict == "recommended_for_approval"
    # ONLY whitelisted artefact kinds — no new kinds introduced.
    assert {kind for kind, _ in proof.artefacts} == {"bmd_svg", "compliance"}
    assert proof.validate_narration("torque 987654321 N.mm")  # invented -> rejected
    assert "RECOMMENDED FOR APPROVAL" in proof.render_memo(None)

    summary = element.type_summary(
        params=CANONICAL, geometry=g, analysis=analysis.analysis,
        checks=[c.model_dump() for c in checks.checks], proof=proof,
    )
    # Exact key set is the pinned fos_summary shape.
    assert set(summary) == {
        "kind", "max_stress_mpa", "permissible_stress_mpa", "stress_ok",
        "factor_of_safety", "required_fos", "fos_ok", "verdict",
    }
    assert summary["kind"] == "fos_summary"
    assert summary["stress_ok"] is True
    assert summary["fos_ok"] is True
    assert summary["fos_ok"] == (summary["factor_of_safety"] >= summary["required_fos"])
    assert summary["verdict"] == "recommended_for_approval"
    assert all(isinstance(summary[k], float) for k in (
        "max_stress_mpa", "permissible_stress_mpa", "factor_of_safety", "required_fos",
    ))


def test_memo_prompt_is_the_machine_element_system_prompt(element):
    prompt = element.memo_prompt()
    assert prompt and ("machine element" in prompt.lower() or "machine-element" in prompt.lower())
