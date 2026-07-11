"""PierAbutmentComponent — the pier & abutment substructure (Expansion Phase 2).

A first-class `ComponentModule` (structurally satisfying `components.base`)
delegating to this package's engine (`sizing`/`analysis`/`checks`), drawing, 3D
and proof-check modules. Mirrors the retaining-wall adapter exactly: declarative
metadata, lazy heavy imports inside methods, `coerce(...)` at method tops, and a
`proof_check` returning a `ProofCheckOutput` with pre-bound
`validate_narration`/`render_memo` closures + an `artefacts` list.

`register(PierAbutmentComponent())` runs at import (see `__init__.py`). It
graduates the `pier_abutment` roadmap stub to an available component: the
self-registering module wins over the coming_soon placeholder of the same
`type_id`.
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
from components.pier_abutment.analysis import PierAbutmentAnalysis, analyse_substructure
from components.pier_abutment.params import (
    CLARIFICATION_QUESTIONS,
    CRITICAL_FIELDS,
    PierAbutmentExtractionResult,
    PierAbutmentGeometry,
    PierAbutmentParams,
    unusual_value_warnings,
)
from components.registry import register

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


class PierAbutmentComponent:
    """Bridge pier / abutment substructure — IRS Bridge Substructure & Foundation Code / IRS Bridge Rules."""

    # ---- declarative metadata ----
    type_id = "pier_abutment"
    display_name = "Pier & Abutment Substructure"
    domain = "civil"
    summary = (
        "Bridge pier and abutment substructure — carries the superstructure reaction through "
        "an RCC pier/stem and spread footing to the founding soil. Stability (overturning / "
        "sliding / base bearing) and pier-section checks, a dimensioned GA drawing + 3D model, "
        "and the same IR-protocol proof-check to the IRS Bridge Substructure & Foundation Code."
    )
    status = "available"
    codes = [
        "IRS Bridge Substructure & Foundation Code",
        "IRS Bridge Rules",
        "IRS Concrete Bridge Code",
        "IS 456",
    ]
    scope_examples = [
        "design a bridge pier for a 20 m railway span, SBC 300 kN/m2, reaction 4000 kN",
        "RCC abutment for a single-span railway bridge, 8 m high, backfill phi 30",
        "design a pier 9 m high carrying 6000 kN, safe bearing capacity 350",
        "bridge abutment substructure on a spread footing with track surcharge",
    ]
    critical_fields = list(CRITICAL_FIELDS)  # pier_height -> reaction -> SBC
    param_model = PierAbutmentParams
    geometry_model = PierAbutmentGeometry
    # Extra (not in the minimal Protocol): the analysis rehydration model.
    analysis_model = PierAbutmentAnalysis

    @property
    def member_labels(self) -> dict[str, str]:
        """Human-readable member names, exposed via the interface so the shared
        `check` node narrates failing members through dispatch (component-registry SC#6)."""
        from components.pier_abutment.checks import MEMBER_LABELS

        return MEMBER_LABELS

    # ---- intake ----
    def extraction_schema(self) -> type:
        return PierAbutmentExtractionResult

    def clarify_question(self, missing_field: str) -> str:
        return CLARIFICATION_QUESTIONS[missing_field]

    def unusual_value_warnings(self, params) -> list[str]:
        return unusual_value_warnings(coerce(PierAbutmentParams, params))

    # ---- deterministic engineering pipeline ----
    def size(self, params) -> SizingOutput:
        from components.pier_abutment.sizing import size_substructure

        result = size_substructure(coerce(PierAbutmentParams, params))
        return SizingOutput(
            geometry=result.geometry,
            assumptions=list(result.assumptions),
            trail=list(result.trail),
            warnings=list(result.warnings),
        )

    def analyse(self, params, geometry) -> AnalysisOutput:
        result = analyse_substructure(
            coerce(PierAbutmentParams, params), coerce(PierAbutmentGeometry, geometry)
        )
        return AnalysisOutput(
            analysis=result,
            assumptions=list(result.assumptions),
            trail=list(result.trail),
        )

    def run_checks(self, params, geometry, analysis) -> CheckOutput:
        from components.pier_abutment.checks import run_substructure_checks

        output = run_substructure_checks(
            coerce(PierAbutmentAnalysis, analysis),
            coerce(PierAbutmentGeometry, geometry),
            coerce(PierAbutmentParams, params),
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
        from components.pier_abutment.calcsheet import compose_calc_sheet

        segments = [[coerce(CalcStep, step) for step in segment] for segment in trail_segments]
        return compose_calc_sheet(
            trail=segments,
            checks=[coerce(CheckResult, c) for c in checks],
            assumptions=[coerce(Assumption, a) for a in assumptions],
            warnings=list(warnings),
            params=coerce(PierAbutmentParams, params),
            geometry=coerce(PierAbutmentGeometry, geometry),
            out_dir=out_dir,
        )

    def draw(self, params, geometry, out_dir: Path, run_id: str) -> dict[str, Path]:
        from components.pier_abutment.drawing import generate_ga

        return generate_ga(
            coerce(PierAbutmentParams, params),
            coerce(PierAbutmentGeometry, geometry),
            out_dir,
            run_id=run_id,
        )

    def model3d(self, geometry, out_dir: Path) -> dict[str, Path]:
        from components.pier_abutment.model3d import generate_solid

        return generate_solid(coerce(PierAbutmentGeometry, geometry), out_dir)

    # ---- IR-protocol review spine ----
    def proof_check(
        self, *, params, geometry, analysis, checks, ga_dxf_path: Path, out_dir: Path
    ) -> ProofCheckOutput:
        from components.pier_abutment.proofcheck import (
            BMD_FILENAME,
            memo_facts,
            render_memo,
            run_proof_check,
            validate_narration,
        )
        from proofcheck.checklist import COMPLIANCE_FILENAME
        from proofcheck.memo import PROOF_MEMO_FILENAME

        params = coerce(PierAbutmentParams, params)
        geometry = coerce(PierAbutmentGeometry, geometry)
        analysis = coerce(PierAbutmentAnalysis, analysis)
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
        return (_PROMPT_DIR / "pier_abutment_memo.md").read_text(encoding="utf-8").strip()

    # ---- type-specific outputs ----
    def type_summary(self, *, params, geometry, analysis, checks, proof) -> dict:
        from components.pier_abutment.summary import type_summary

        return type_summary(
            params=coerce(PierAbutmentParams, params),
            analysis=coerce(PierAbutmentAnalysis, analysis),
            verdict=proof.verdict,
        )


register(PierAbutmentComponent())
