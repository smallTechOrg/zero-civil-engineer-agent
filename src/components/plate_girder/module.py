"""PlateGirderComponent — component #3, the welded steel plate girder.

A first-class `ComponentModule` (structurally satisfying `components.base`)
delegating to this package's engine (`sizing`/`analysis`/`checks`), drawing, 3D
and proof-check modules. Mirrors the other components exactly: declarative
metadata, lazy heavy imports inside methods, `coerce(...)` at method tops, and a
`proof_check` returning a `ProofCheckOutput` with pre-bound
`validate_narration`/`render_memo` closures + an `artefacts` list.

`register(PlateGirderComponent())` runs at import (see `__init__.py`).
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
from components.plate_girder.analysis import PlateGirderAnalysis, analyse_girder
from components.plate_girder.params import (
    CLARIFICATION_QUESTIONS,
    CRITICAL_FIELDS,
    PlateGirderExtractionResult,
    PlateGirderGeometry,
    PlateGirderParams,
    unusual_value_warnings,
)
from components.registry import register

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


class PlateGirderComponent:
    """Welded steel plate girder — IRS Steel Bridge Code / IS 800 / IR Bridge Rules."""

    # ---- declarative metadata ----
    type_id = "plate_girder"
    display_name = "Welded Steel Plate Girder"
    domain = "civil"
    summary = (
        "Welded steel plate-girder superstructure for a railway span — dead + 25t live-load "
        "(EUDL + CDA) analysis, working-stress design of the web and flanges (bending, shear, "
        "deflection, web slenderness), a dimensioned GA drawing + 3D model, and the same "
        "IR-protocol proof-check to IRS Steel Bridge Code / IS 800."
    )
    status = "available"
    codes = ["IRS Steel Bridge Code", "IS 800", "IR Bridge Rules"]
    scope_examples = [
        "design a 24 m welded steel plate girder for a BG single line, 25t loading",
        "steel plate girder deck span of 18 m, two girders, E350 steel",
        "through-type plate girder bridge for a 30 m railway span",
        "design a welded plate girder superstructure to span 40 m",
    ]
    critical_fields = list(CRITICAL_FIELDS)  # span_m
    param_model = PlateGirderParams
    geometry_model = PlateGirderGeometry
    # Extra (not in the minimal Protocol): the analysis rehydration model.
    analysis_model = PlateGirderAnalysis

    @property
    def member_labels(self) -> dict[str, str]:
        """Human-readable member names, exposed via the interface so the shared
        `check` node narrates failing members through dispatch, not a direct
        component-engine import."""
        from components.plate_girder.checks import MEMBER_LABELS

        return MEMBER_LABELS

    # ---- intake ----
    def extraction_schema(self) -> type:
        return PlateGirderExtractionResult

    def clarify_question(self, missing_field: str) -> str:
        return CLARIFICATION_QUESTIONS[missing_field]

    def unusual_value_warnings(self, params) -> list[str]:
        return unusual_value_warnings(coerce(PlateGirderParams, params))

    # ---- deterministic engineering pipeline ----
    def size(self, params) -> SizingOutput:
        from components.plate_girder.sizing import size_girder

        result = size_girder(coerce(PlateGirderParams, params))
        return SizingOutput(
            geometry=result.geometry,
            assumptions=list(result.assumptions),
            trail=list(result.trail),
            warnings=list(result.warnings),
        )

    def analyse(self, params, geometry) -> AnalysisOutput:
        result = analyse_girder(
            coerce(PlateGirderParams, params), coerce(PlateGirderGeometry, geometry)
        )
        return AnalysisOutput(
            analysis=result,
            assumptions=list(result.assumptions),
            trail=list(result.trail),
        )

    def run_checks(self, params, geometry, analysis) -> CheckOutput:
        from components.plate_girder.checks import run_girder_checks

        output = run_girder_checks(
            coerce(PlateGirderAnalysis, analysis),
            coerce(PlateGirderGeometry, geometry),
            coerce(PlateGirderParams, params),
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
        from components.plate_girder.calcsheet import compose_calc_sheet

        segments = [[coerce(CalcStep, step) for step in segment] for segment in trail_segments]
        return compose_calc_sheet(
            trail=segments,
            checks=[coerce(CheckResult, c) for c in checks],
            assumptions=[coerce(Assumption, a) for a in assumptions],
            warnings=list(warnings),
            params=coerce(PlateGirderParams, params),
            geometry=coerce(PlateGirderGeometry, geometry),
            out_dir=out_dir,
        )

    def draw(self, params, geometry, out_dir: Path, run_id: str) -> dict[str, Path]:
        from components.plate_girder.drawing import generate_ga

        return generate_ga(
            coerce(PlateGirderParams, params),
            coerce(PlateGirderGeometry, geometry),
            out_dir,
            run_id=run_id,
        )

    def model3d(self, geometry, out_dir: Path) -> dict[str, Path]:
        from components.plate_girder.model3d import generate_solid

        return generate_solid(coerce(PlateGirderGeometry, geometry), out_dir)

    # ---- IR-protocol review spine ----
    def proof_check(
        self, *, params, geometry, analysis, checks, ga_dxf_path: Path, out_dir: Path
    ) -> ProofCheckOutput:
        from components.plate_girder.proofcheck import (
            BMD_FILENAME,
            memo_facts,
            render_memo,
            run_proof_check,
            validate_narration,
        )
        from proofcheck.checklist import COMPLIANCE_FILENAME
        from proofcheck.memo import PROOF_MEMO_FILENAME

        params = coerce(PlateGirderParams, params)
        geometry = coerce(PlateGirderGeometry, geometry)
        analysis = coerce(PlateGirderAnalysis, analysis)
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
        return (_PROMPT_DIR / "plate_girder_memo.md").read_text(encoding="utf-8").strip()

    # ---- type-specific outputs ----
    def type_summary(self, *, params, geometry, analysis, checks, proof) -> dict:
        from components.plate_girder.summary import type_summary

        return type_summary(
            analysis=coerce(PlateGirderAnalysis, analysis),
            verdict=proof.verdict,
        )


register(PlateGirderComponent())
