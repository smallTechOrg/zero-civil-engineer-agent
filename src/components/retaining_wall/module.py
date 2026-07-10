"""RetainingWallComponent — component #2, the RCC cantilever retaining wall.

A first-class `ComponentModule` (structurally satisfying `components.base`)
delegating to this package's engine (`sizing`/`analysis`/`checks`), drawing, 3D
and proof-check modules. Mirrors the culvert adapter exactly: declarative
metadata, lazy heavy imports inside methods, `coerce(...)` at method tops, and a
`proof_check` returning a `ProofCheckOutput` with pre-bound
`validate_narration`/`render_memo` closures + an `artefacts` list.

`register(RetainingWallComponent())` runs at import (see `__init__.py`).
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
from components.retaining_wall.analysis import RetainingWallAnalysis, analyse_wall
from components.retaining_wall.params import (
    CLARIFICATION_QUESTIONS,
    CRITICAL_FIELDS,
    RetainingWallGeometry,
    RetainingWallParams,
    RWExtractionResult,
    unusual_value_warnings,
)

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


class RetainingWallComponent:
    """RCC cantilever retaining wall — IRS Concrete Bridge Code / IS 456 / IR Bridge Rules."""

    # ---- declarative metadata ----
    type_id = "rcc_cantilever_retaining_wall"
    display_name = "RCC Cantilever Retaining Wall"
    domain = "civil"
    summary = (
        "RCC cantilever retaining wall for a railway cutting or embankment — earth-pressure "
        "and stability analysis, RCC section design of stem/heel/toe, a dimensioned GA "
        "drawing + 3D model, and the same IR-protocol proof-check to IRS/IS-456 codes."
    )
    status = "available"
    codes = ["IRS Concrete Bridge Code", "IS 456", "IR Bridge Rules"]
    scope_examples = [
        "design a 5 m high RCC cantilever retaining wall, SBC 200 kN/m2, BG single-line track "
        "surcharge, backfill phi 30 degrees",
        "retaining wall for a railway cutting, 6 m retained height, safe bearing capacity 250",
        "RCC cantilever retaining wall for a railway embankment",
        "design a retaining wall to retain 4 m of earth with a shear key",
    ]
    critical_fields = list(CRITICAL_FIELDS)  # retained_height -> SBC -> backfill phi
    param_model = RetainingWallParams
    geometry_model = RetainingWallGeometry
    # Extra (not in the minimal Protocol): the analysis rehydration model.
    analysis_model = RetainingWallAnalysis

    @property
    def member_labels(self) -> dict[str, str]:
        """Human-readable member names, exposed via the interface so the shared
        `check` node narrates failing members through dispatch, not a direct
        component-engine import (component-registry SC#6)."""
        from components.retaining_wall.checks import MEMBER_LABELS

        return MEMBER_LABELS

    # ---- intake ----
    def extraction_schema(self) -> type:
        return RWExtractionResult

    def clarify_question(self, missing_field: str) -> str:
        return CLARIFICATION_QUESTIONS[missing_field]

    def unusual_value_warnings(self, params) -> list[str]:
        return unusual_value_warnings(coerce(RetainingWallParams, params))

    # ---- deterministic engineering pipeline ----
    def size(self, params) -> SizingOutput:
        from components.retaining_wall.sizing import size_wall

        result = size_wall(coerce(RetainingWallParams, params))
        return SizingOutput(
            geometry=result.geometry,
            assumptions=list(result.assumptions),
            trail=list(result.trail),
            warnings=list(result.warnings),
        )

    def analyse(self, params, geometry) -> AnalysisOutput:
        result = analyse_wall(
            coerce(RetainingWallParams, params), coerce(RetainingWallGeometry, geometry)
        )
        return AnalysisOutput(
            analysis=result,
            assumptions=list(result.assumptions),
            trail=list(result.trail),
        )

    def run_checks(self, params, geometry, analysis) -> CheckOutput:
        from components.retaining_wall.checks import run_wall_checks

        output = run_wall_checks(
            coerce(RetainingWallAnalysis, analysis),
            coerce(RetainingWallGeometry, geometry),
            coerce(RetainingWallParams, params),
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
        from components.retaining_wall.calcsheet import compose_calc_sheet

        segments = [[coerce(CalcStep, step) for step in segment] for segment in trail_segments]
        return compose_calc_sheet(
            trail=segments,
            checks=[coerce(CheckResult, c) for c in checks],
            assumptions=[coerce(Assumption, a) for a in assumptions],
            warnings=list(warnings),
            params=coerce(RetainingWallParams, params),
            geometry=coerce(RetainingWallGeometry, geometry),
            out_dir=out_dir,
        )

    def draw(self, params, geometry, out_dir: Path, run_id: str) -> dict[str, Path]:
        from components.retaining_wall.drawing import generate_ga

        return generate_ga(
            coerce(RetainingWallParams, params),
            coerce(RetainingWallGeometry, geometry),
            out_dir,
            run_id=run_id,
        )

    def model3d(self, geometry, out_dir: Path) -> dict[str, Path]:
        from components.retaining_wall.model3d import generate_solid

        return generate_solid(coerce(RetainingWallGeometry, geometry), out_dir)

    # ---- IR-protocol review spine ----
    def proof_check(
        self, *, params, geometry, analysis, checks, ga_dxf_path: Path, out_dir: Path
    ) -> ProofCheckOutput:
        from components.retaining_wall.proofcheck import (
            BMD_FILENAME,
            memo_facts,
            render_memo,
            run_proof_check,
            validate_narration,
        )
        from proofcheck.checklist import COMPLIANCE_FILENAME
        from proofcheck.memo import PROOF_MEMO_FILENAME

        params = coerce(RetainingWallParams, params)
        geometry = coerce(RetainingWallGeometry, geometry)
        analysis = coerce(RetainingWallAnalysis, analysis)
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
        return (_PROMPT_DIR / "rw_memo.md").read_text(encoding="utf-8").strip()

    # ---- type-specific outputs ----
    def type_summary(self, *, params, geometry, analysis, checks, proof) -> dict:
        from components.retaining_wall.summary import type_summary

        return type_summary(
            params=coerce(RetainingWallParams, params),
            analysis=coerce(RetainingWallAnalysis, analysis),
            verdict=proof.verdict,
        )


register(RetainingWallComponent())
