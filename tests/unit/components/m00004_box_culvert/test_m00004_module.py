"""The component satisfies the ComponentModule protocol and wires the pipeline."""

from pathlib import Path

import pytest

# Slice (b) has not yet wired this into components/__init__.py, so import the
# module explicitly to run its register() call.
import components.m00004_box_culvert.module  # noqa: F401  (self-registers)
from components import registry
from components.base import (
    AnalysisOutput,
    CheckOutput,
    ComponentModule,
    ProofCheckOutput,
    SizingOutput,
)
from components.m00004_box_culvert.params import M00004Params

TYPE_ID = "m00004_box_culvert"


@pytest.fixture
def module():
    return registry.get(TYPE_ID)


@pytest.fixture
def params():
    return M00004Params(clear_span_m=4.0, clear_height_m=4.0, cushion_m=2.0)


def test_registered(module):
    assert registry.has(TYPE_ID) and registry.is_available(TYPE_ID)


def test_satisfies_protocol(module):
    assert isinstance(module, ComponentModule)


def test_declares_full_metadata(module):
    assert module.type_id == TYPE_ID
    assert module.display_name == "M-00004 Standard Box Culvert (RDSO)"
    assert module.domain == "civil"
    assert module.status == "available"
    assert module.codes == ["RDSO/M-00004", "IRS Concrete Bridge Code"]
    assert module.scope_examples == []
    assert module.critical_fields == ["clear_span_m", "clear_height_m", "cushion_m"]
    assert module.param_model is M00004Params
    # params-direct-only marker (bypasses the LLM intake nodes)
    assert getattr(module, "params_direct_only") is True


def test_full_pipeline_and_type_summary_shape(module, params, tmp_path):
    sizing = module.size(params)
    assert isinstance(sizing, SizingOutput)
    geometry = sizing.geometry

    analysis_out = module.analyse(params, geometry)
    assert isinstance(analysis_out, AnalysisOutput)

    checks_out = module.run_checks(params, geometry, analysis_out.analysis)
    assert isinstance(checks_out, CheckOutput)
    assert checks_out.checks and all(c.status == "PASS" for c in checks_out.checks)

    paths = module.draw(params, geometry, tmp_path, run_id="t-0001")
    assert paths["ga_dxf"].exists() and paths["m00004_sheet"].exists()

    proof = module.proof_check(
        params=params, geometry=geometry, analysis=analysis_out.analysis,
        checks=checks_out.checks, ga_dxf_path=paths["ga_dxf"], out_dir=tmp_path,
    )
    assert isinstance(proof, ProofCheckOutput)
    assert proof.verdict == "provisional_standard_reproduction"
    assert (tmp_path / "compliance.json").exists()

    summary = module.type_summary(
        params=params, geometry=geometry, analysis=analysis_out.analysis,
        checks=checks_out.checks, proof=proof,
    )
    assert summary["kind"] == "m00004_standard"
    assert summary["config_id"] == "F2_4x4"
    assert summary["thickness_mm"] == 500
    assert summary["haunch_mm"] == 450
    assert "barrel_length_mm" in summary
    assert summary["provisional_flags"] == []
    assert summary["verdict"] == "provisional_standard_reproduction"


def test_memo_prompt_is_self_contained_and_provisional(module):
    prompt = module.memo_prompt()
    assert "PROVISIONAL" in prompt
    assert "M-00004" in prompt


def test_calc_sheet_composes(module, params, tmp_path):
    sizing = module.size(params)
    analysis_out = module.analyse(params, sizing.geometry)
    checks_out = module.run_checks(params, sizing.geometry, analysis_out.analysis)
    path = module.compose_calc_sheet(
        params=params, geometry=sizing.geometry, analysis=analysis_out.analysis,
        checks=checks_out.checks, assumptions=sizing.assumptions,
        warnings=sizing.warnings,
        trail_segments=[sizing.trail, analysis_out.trail, checks_out.trail],
        out_dir=tmp_path,
    )
    assert Path(path).exists()
    import json
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    assert {s["id"] for s in doc["sections"]} >= {
        "standard_basis", "config_selection", "reinforcement", "conformance"
    }
