"""BoxCulvertComponent — component #1, a thin adapter over the existing engine.

Every method delegates to the UNCHANGED `src/engine`, `src/drawing`,
`src/model3d`, `src/proofcheck` functions; the refactor only moves the pipeline
dispatch decision into `registry.get(component_type)`. Culvert behaviour is
byte-for-byte the same as the pre-registry pipeline. Heavy engineering imports
(FE, CAD, drawing) load lazily inside methods so registering the component at
process start stays cheap.

`register(BoxCulvertComponent())` runs at import (see `components/__init__.py`).
"""

from __future__ import annotations

from pathlib import Path

from components.base import (
    AnalysisOutput,
    Assumption,
    CalcStep,
    CheckOutput,
    CheckResult,
    ProofCheckOutput,
    SizingOutput,
    coerce,
)
from components.registry import register
from domain.culvert import (
    AnalysisResult,
    BoxGeometry,
    CulvertParams,
    unusual_value_warnings,
)
from graph.extraction import CLARIFICATION_QUESTIONS, CRITICAL_FIELDS, ExtractionResult

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


class BoxCulvertComponent:
    """Single-cell RCC box culvert — IRS Concrete Bridge Code (25t Loading-2008)."""

    # ---- declarative metadata ----
    type_id = "box_culvert"
    display_name = "Box Culvert"
    domain = "civil"
    summary = "Single-cell RCC box culvert under a railway embankment — sized, analysed, drawn and proof-checked to IRS codes."
    status = "available"
    codes = ["IRS Concrete Bridge Code", "IRS Bridge Rules", "25t Loading-2008"]
    scope_examples = [
        "single box culvert, 4 m clear span, 3 m height, 2.5 m cushion, BG single line, 25t loading",
        "RCC box culvert under a railway embankment",
        "design a 3 m x 3 m box culvert with 2 m fill",
        "single-cell box culvert for a level crossing replacement",
    ]
    critical_fields = list(CRITICAL_FIELDS)  # clear_span_m → clear_height_m → cushion_m
    param_model = CulvertParams
    geometry_model = BoxGeometry
    # Extra (not in the minimal Protocol): the analysis rehydration model.
    analysis_model = AnalysisResult

    @property
    def member_labels(self) -> dict[str, str]:
        """Human-readable member names, exposed via the interface so the shared
        `check` node narrates failing members WITHOUT importing `engine.checks`
        directly (component-registry SC#6)."""
        from engine.checks import MEMBER_LABELS

        return MEMBER_LABELS

    # ---- intake ----
    def extraction_schema(self) -> type:
        return ExtractionResult

    def clarify_question(self, missing_field: str) -> str:
        return CLARIFICATION_QUESTIONS[missing_field]

    def unusual_value_warnings(self, params) -> list[str]:
        return unusual_value_warnings(coerce(CulvertParams, params))

    # ---- deterministic engineering pipeline ----
    def size(self, params) -> SizingOutput:
        from engine import size_culvert

        result = size_culvert(coerce(CulvertParams, params))
        return SizingOutput(
            geometry=result.geometry,
            assumptions=list(result.assumptions),
            trail=list(result.trail),
            warnings=list(result.warnings),
        )

    def analyse(self, params, geometry) -> AnalysisOutput:
        from engine.analysis import analyse_frame

        result = analyse_frame(coerce(CulvertParams, params), coerce(BoxGeometry, geometry))
        return AnalysisOutput(
            analysis=result,
            assumptions=list(result.assumptions),
            trail=list(result.trail),
        )

    def run_checks(self, params, geometry, analysis) -> CheckOutput:
        from engine.checks import run_member_checks

        output = run_member_checks(
            coerce(AnalysisResult, analysis),
            coerce(BoxGeometry, geometry),
            coerce(CulvertParams, params),
        )
        return CheckOutput(
            checks=list(output.checks),
            assumptions=list(output.assumptions),
            trail=list(output.trail),
        )

    def compose_calc_sheet(
        self,
        *,
        params,
        geometry,
        analysis,
        checks,
        assumptions,
        warnings,
        trail_segments,
        out_dir: Path,
    ) -> Path:
        from engine.calcsheet import compose_calc_sheet

        # State carries trail steps as dicts; the engine composer needs CalcStep
        # objects. Coerce each step in each engine-ordered segment.
        segments = [[coerce(CalcStep, step) for step in segment] for segment in trail_segments]
        return compose_calc_sheet(
            trail=segments,
            checks=[coerce(CheckResult, c) for c in checks],
            assumptions=[coerce(Assumption, a) for a in assumptions],
            warnings=list(warnings),
            params=coerce(CulvertParams, params),
            geometry=coerce(BoxGeometry, geometry),
            out_dir=out_dir,
        )

    def draw(self, params, geometry, out_dir: Path, run_id: str) -> dict[str, Path]:
        from drawing.ga import generate_ga

        return generate_ga(
            coerce(BoxGeometry, geometry),
            coerce(CulvertParams, params),
            out_dir,
            run_id=run_id,
        )

    def model3d(self, geometry, out_dir: Path) -> dict[str, Path]:
        from model3d import generate_solid

        return generate_solid(coerce(BoxGeometry, geometry), out_dir)

    # ---- IR-protocol review spine ----
    def proof_check(
        self, *, params, geometry, analysis, checks, ga_dxf_path: Path, out_dir: Path
    ) -> ProofCheckOutput:
        from engine.fe_check import BMD_FILENAME, SFD_FILENAME, cross_check
        from proofcheck import (
            COMPLIANCE_FILENAME,
            PROOF_MEMO_FILENAME,
            memo_facts,
            render_memo,
            run_checklist,
            validate_narration,
        )

        params = coerce(CulvertParams, params)
        geometry = coerce(BoxGeometry, geometry)
        analysis = coerce(AnalysisResult, analysis)
        check_rows = [coerce(CheckResult, c) for c in checks]

        fe = cross_check(params, geometry, analysis, out_dir)
        result = run_checklist(
            params=params,
            geometry=geometry,
            analysis=analysis,
            checks=check_rows,
            fe=fe,
            ga_dxf_path=ga_dxf_path,
            out_dir=out_dir,
        )

        # Reconstruct the run's warnings deterministically so the memo body is
        # byte-identical to the pre-registry pipeline (param unusual-value flags
        # then sizing thinner-override flags). Assumptions are not shown in the
        # memo body; omitting them only tightens narration grounding (safe).
        warnings = unusual_value_warnings(params) + list(self.size(params).warnings)
        facts = memo_facts(result, params=params, geometry=geometry, warnings=warnings)

        def _validate(narration: str | None) -> list[str]:
            if not narration or not narration.strip():
                return ["narration is empty"]
            return validate_narration(narration, result, extra_facts=facts)

        def _render(narration: str | None) -> str:
            return render_memo(
                result, narration, params=params, geometry=geometry, warnings=warnings
            )

        return ProofCheckOutput(
            fe_comparison=fe,
            checklist=[item.model_dump() for item in result.items],
            verdict=result.verdict,
            fe_agreement_pct=result.fe_agreement_pct,
            memo_facts=facts,
            validate_narration=_validate,
            render_memo=_render,
            artefacts=[
                ("bmd_svg", BMD_FILENAME),
                ("sfd_svg", SFD_FILENAME),
                ("compliance", COMPLIANCE_FILENAME),
            ],
            memo_kind="proof_memo",
            memo_filename=PROOF_MEMO_FILENAME,
        )

    def memo_prompt(self) -> str:
        return (_PROMPT_DIR / "memo.md").read_text(encoding="utf-8").strip()

    # ---- type-specific outputs ----
    def type_summary(self, *, params, geometry, analysis, checks, proof) -> dict:
        """Member-check summary — pass/fail counts and the governing member."""
        from engine.checks import MEMBER_LABELS

        rows = [coerce(CheckResult, c) for c in checks]
        failing = [r for r in rows if r.status != "PASS"]
        members = sorted({MEMBER_LABELS.get(r.member, r.member) for r in failing})
        return {
            "kind": "member_check",
            "checks_total": len(rows),
            "checks_passed": sum(1 for r in rows if r.status == "PASS"),
            "checks_failed": len(failing),
            "failing_members": members,
            "verdict": proof.verdict,
            "fe_agreement_pct": proof.fe_agreement_pct,
        }


register(BoxCulvertComponent())
