"""BoxCulvertComponent adapter — the module delegates to the unchanged engine.

Deterministic end-to-end through the ComponentModule interface (no LLM): sizing,
analysis, checks, calc sheet, GA drawing, proof-check and type summary — proving
the adapter reproduces the culvert pipeline and returns the shared result types
the graph nodes (and the retaining-wall slices) build against.
"""

from pathlib import Path

import pytest

from components import registry
from components.base import (
    AnalysisOutput,
    CheckOutput,
    ProofCheckOutput,
    SizingOutput,
)
from domain.culvert import BoxGeometry, CulvertParams

CANONICAL = {"clear_span_m": 4.0, "clear_height_m": 3.0, "cushion_m": 2.5}


@pytest.fixture
def culvert():
    return registry.get("box_culvert")


def test_metadata_and_schemas(culvert):
    assert culvert.param_model is CulvertParams
    assert culvert.geometry_model is BoxGeometry
    schema = culvert.extraction_schema()
    assert "clear_span_m" in schema.model_fields
    assert culvert.clarify_question("clear_span_m")  # non-empty pointed question


def test_size_returns_sizing_output_over_the_engine(culvert):
    out = culvert.size(CANONICAL)  # accepts a dict (state form)
    assert isinstance(out, SizingOutput)
    assert isinstance(out.geometry, BoxGeometry)
    assert out.geometry.external_width_m > CANONICAL["clear_span_m"]
    assert out.trail  # provenance CalcSteps
    # Same result when passed the typed model.
    typed = culvert.size(CulvertParams(**CANONICAL))
    assert typed.geometry.model_dump() == out.geometry.model_dump()


def test_analyse_and_run_checks(culvert):
    sizing = culvert.size(CANONICAL)
    analysis = culvert.analyse(CANONICAL, sizing.geometry)
    assert isinstance(analysis, AnalysisOutput)
    assert analysis.analysis.load_cases and analysis.analysis.combinations

    checks = culvert.run_checks(CANONICAL, sizing.geometry, analysis.analysis)
    assert isinstance(checks, CheckOutput)
    # 4 checks per member x 3 members + cover = 13 rows, all PASS for the canonical box.
    assert len(checks.checks) == 13
    assert all(c.status == "PASS" for c in checks.checks)


def test_unusual_value_warnings_flags_high_cushion(culvert):
    warnings = culvert.unusual_value_warnings({**CANONICAL, "cushion_m": 9.0})
    assert any("cushion" in w.lower() for w in warnings)


def test_compose_calc_sheet_and_draw_write_the_shared_artefacts(culvert, tmp_path: Path):
    sizing = culvert.size(CANONICAL)
    analysis = culvert.analyse(CANONICAL, sizing.geometry)
    checks = culvert.run_checks(CANONICAL, sizing.geometry, analysis.analysis)

    sheet = culvert.compose_calc_sheet(
        params=CANONICAL,
        geometry=sizing.geometry,
        analysis=analysis.analysis,
        checks=[c.model_dump() for c in checks.checks],
        assumptions=[a.model_dump() for a in sizing.assumptions],
        warnings=[],
        trail_segments=[
            [s.model_dump() for s in sizing.trail],
            [s.model_dump() for s in analysis.trail],
            [s.model_dump() for s in checks.trail],
        ],
        out_dir=tmp_path,
    )
    assert sheet.name == "calc_sheet.json" and sheet.is_file()

    paths = culvert.draw(CANONICAL, sizing.geometry, tmp_path, run_id="unit-run")
    assert set(paths) == {"ga_dxf", "ga_svg"}
    assert paths["ga_dxf"].is_file() and paths["ga_svg"].is_file()


def test_proof_check_and_type_summary(culvert, tmp_path: Path):
    sizing = culvert.size(CANONICAL)
    analysis = culvert.analyse(CANONICAL, sizing.geometry)
    checks = culvert.run_checks(CANONICAL, sizing.geometry, analysis.analysis)
    culvert.draw(CANONICAL, sizing.geometry, tmp_path, run_id="unit-run")  # proof reads ga.dxf

    proof = culvert.proof_check(
        params=CANONICAL,
        geometry=sizing.geometry,
        analysis=analysis.analysis,
        checks=[c.model_dump() for c in checks.checks],
        ga_dxf_path=tmp_path / "ga.dxf",
        out_dir=tmp_path,
    )
    assert isinstance(proof, ProofCheckOutput)
    assert len(proof.checklist) == 12
    assert proof.verdict == "recommended_for_approval"
    # proof_check already wrote its diagram/compliance artefacts.
    assert {kind for kind, _ in proof.artefacts} == {"bmd_svg", "sfd_svg", "compliance"}
    assert (tmp_path / "compliance.json").is_file()

    # Grounding callables behave: an invented number is rejected; a rendered
    # deterministic memo never embeds it.
    assert proof.validate_narration("moment of 999999 kN·m")  # rejected → problems
    assert proof.validate_narration(None) == ["narration is empty"]
    memo = proof.render_memo(None)
    assert "RECOMMENDED FOR APPROVAL" in memo

    summary = culvert.type_summary(
        params=CANONICAL,
        geometry=sizing.geometry,
        analysis=analysis.analysis,
        checks=[c.model_dump() for c in checks.checks],
        proof=proof,
    )
    assert summary["kind"] == "member_check"
    assert summary["checks_total"] == 13
    assert summary["checks_passed"] == 13
    assert summary["verdict"] == "recommended_for_approval"


def test_memo_prompt_is_the_culvert_system_prompt(culvert):
    prompt = culvert.memo_prompt()
    assert prompt and isinstance(prompt, str)
