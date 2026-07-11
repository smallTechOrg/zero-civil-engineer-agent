"""RollingStockMemberComponent — the fabricated rolling-stock structural member.

A first-class `ComponentModule` (structurally satisfying `components.base`)
delegating to this package's engine (`sizing`/`analysis`/`checks`), drawing, 3D
and proof-check modules. Mirrors the civil components exactly: declarative
metadata, lazy heavy imports inside methods, `coerce(...)` at method tops, and a
`proof_check` returning a `ProofCheckOutput` with pre-bound
`validate_narration`/`render_memo` closures + an `artefacts` list.

This is the first MECHANICAL-domain component — a breadth-first plug-in on the
SAME interface + IR-protocol review spine as the civil components. It replaces the
`rolling_stock_member` coming-soon stub of the same `type_id`.

`register(RollingStockMemberComponent())` runs at import (see `__init__.py`).
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
from components.rolling_stock_member.analysis import (
    RollingStockMemberAnalysis,
    analyse_member,
)
from components.rolling_stock_member.params import (
    CLARIFICATION_QUESTIONS,
    CRITICAL_FIELDS,
    RollingStockMemberExtractionResult,
    RollingStockMemberGeometry,
    RollingStockMemberParams,
    unusual_value_warnings,
)

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


class RollingStockMemberComponent:
    """Fabricated rolling-stock underframe member — RDSO Specifications / IS 800."""

    # ---- declarative metadata ----
    type_id = "rolling_stock_member"
    display_name = "Rolling-Stock Member"
    domain = "mechanical"
    summary = (
        "Fabricated rolling-stock structural member (wagon underframe member — sole bar, "
        "headstock or cross member) — RDSO wagon-design load-case analysis (vertical payload "
        "with dynamic augment + longitudinal buffing/draft load), IS 800 working-stress section "
        "checks (bending, shear, axial and combined interaction), a fabrication drawing with weld "
        "symbols + a 3D model, and the same IR-protocol proof-check to RDSO Specifications / IS 800."
    )
    status = "available"
    codes = ["RDSO Specifications", "IS 800"]
    scope_examples = [
        "design a wagon underframe sole-bar member, 10 m, to RDSO specs",
        "rolling-stock headstock member carrying the draft-gear buffing load",
        "underframe cross member, 2.4 m, checked to RDSO loading and IS 800",
        "design a fabricated freight-stock underframe member for buffing + payload",
    ]
    critical_fields = list(CRITICAL_FIELDS)  # member_length_m
    param_model = RollingStockMemberParams
    geometry_model = RollingStockMemberGeometry
    # Extra (not in the minimal Protocol): the analysis rehydration model.
    analysis_model = RollingStockMemberAnalysis

    @property
    def member_labels(self) -> dict[str, str]:
        """Human-readable member names, exposed via the interface so the shared
        `check` node narrates failing members through dispatch, not a direct
        component-engine import."""
        from components.rolling_stock_member.checks import MEMBER_LABELS

        return MEMBER_LABELS

    # ---- intake ----
    def extraction_schema(self) -> type:
        return RollingStockMemberExtractionResult

    def clarify_question(self, missing_field: str) -> str:
        return CLARIFICATION_QUESTIONS[missing_field]

    def unusual_value_warnings(self, params) -> list[str]:
        return unusual_value_warnings(coerce(RollingStockMemberParams, params))

    # ---- deterministic engineering pipeline ----
    def size(self, params) -> SizingOutput:
        from components.rolling_stock_member.sizing import size_member

        result = size_member(coerce(RollingStockMemberParams, params))
        return SizingOutput(
            geometry=result.geometry,
            assumptions=list(result.assumptions),
            trail=list(result.trail),
            warnings=list(result.warnings),
        )

    def analyse(self, params, geometry) -> AnalysisOutput:
        result = analyse_member(
            coerce(RollingStockMemberParams, params),
            coerce(RollingStockMemberGeometry, geometry),
        )
        return AnalysisOutput(
            analysis=result,
            assumptions=list(result.assumptions),
            trail=list(result.trail),
        )

    def run_checks(self, params, geometry, analysis) -> CheckOutput:
        from components.rolling_stock_member.checks import run_member_checks

        output = run_member_checks(
            coerce(RollingStockMemberAnalysis, analysis),
            coerce(RollingStockMemberGeometry, geometry),
            coerce(RollingStockMemberParams, params),
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
        from components.rolling_stock_member.calcsheet import compose_calc_sheet

        segments = [[coerce(CalcStep, step) for step in segment] for segment in trail_segments]
        return compose_calc_sheet(
            trail=segments,
            checks=[coerce(CheckResult, c) for c in checks],
            assumptions=[coerce(Assumption, a) for a in assumptions],
            warnings=list(warnings),
            params=coerce(RollingStockMemberParams, params),
            geometry=coerce(RollingStockMemberGeometry, geometry),
            out_dir=out_dir,
        )

    def draw(self, params, geometry, out_dir: Path, run_id: str) -> dict[str, Path]:
        from components.rolling_stock_member.drawing import generate_ga

        return generate_ga(
            coerce(RollingStockMemberParams, params),
            coerce(RollingStockMemberGeometry, geometry),
            out_dir,
            run_id=run_id,
        )

    def model3d(self, geometry, out_dir: Path) -> dict[str, Path]:
        from components.rolling_stock_member.model3d import generate_solid

        return generate_solid(coerce(RollingStockMemberGeometry, geometry), out_dir)

    # ---- IR-protocol review spine ----
    def proof_check(
        self, *, params, geometry, analysis, checks, ga_dxf_path: Path, out_dir: Path
    ) -> ProofCheckOutput:
        from components.rolling_stock_member.proofcheck import (
            BMD_FILENAME,
            memo_facts,
            render_memo,
            run_proof_check,
            validate_narration,
        )
        from proofcheck.checklist import COMPLIANCE_FILENAME
        from proofcheck.memo import PROOF_MEMO_FILENAME

        params = coerce(RollingStockMemberParams, params)
        geometry = coerce(RollingStockMemberGeometry, geometry)
        analysis = coerce(RollingStockMemberAnalysis, analysis)
        check_rows = [coerce(CheckResult, c) for c in checks]

        result = run_proof_check(
            params=params,
            geometry=geometry,
            analysis=analysis,
            checks=check_rows,
            ga_dxf_path=ga_dxf_path,
            out_dir=out_dir,
        )

        warnings = unusual_value_warnings(params) + list(self.size(params).warnings)
        facts = memo_facts(
            result, params=params, geometry=geometry, analysis=analysis, warnings=warnings
        )

        def _validate(narration: str | None) -> list[str]:
            if not narration or not narration.strip():
                return ["narration is empty"]
            return validate_narration(narration, result, extra_facts=facts)

        def _render(narration: str | None) -> str:
            return render_memo(
                result, narration, params=params, geometry=geometry,
                analysis=analysis, warnings=warnings,
            )

        return ProofCheckOutput(
            fe_comparison=result.cross_check,
            checklist=[item.model_dump() for item in result.items],
            verdict=result.verdict,
            fe_agreement_pct=result.agreement_pct,
            memo_facts=facts,
            validate_narration=_validate,
            render_memo=_render,
            artefacts=[
                ("bmd_svg", BMD_FILENAME),
                ("compliance", COMPLIANCE_FILENAME),
            ],
            memo_kind="proof_memo",
            memo_filename=PROOF_MEMO_FILENAME,
        )

    def memo_prompt(self) -> str:
        return (_PROMPT_DIR / "rolling_stock_member_memo.md").read_text(encoding="utf-8").strip()

    # ---- type-specific outputs ----
    def type_summary(self, *, params, geometry, analysis, checks, proof) -> dict:
        from components.rolling_stock_member.summary import type_summary

        return type_summary(
            analysis=coerce(RollingStockMemberAnalysis, analysis),
            verdict=proof.verdict,
        )


register(RollingStockMemberComponent())
