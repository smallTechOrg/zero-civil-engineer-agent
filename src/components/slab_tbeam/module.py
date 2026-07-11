"""SlabTbeamComponent — component #3, the RCC slab / T-beam superstructure deck.

A first-class `ComponentModule` (structurally satisfying `components.base`)
delegating to this package's engine (`sizing`/`analysis`/`checks`), drawing, 3D
and proof-check modules. Mirrors the retaining-wall adapter exactly: declarative
metadata, lazy heavy imports inside methods, `coerce(...)` at method tops, and a
`proof_check` returning a `ProofCheckOutput` with pre-bound
`validate_narration`/`render_memo` closures + an `artefacts` list.

`register(SlabTbeamComponent())` runs at import (see `__init__.py`).
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
from components.slab_tbeam.analysis import SlabTbeamAnalysis, analyse_deck
from components.slab_tbeam.params import (
    CLARIFICATION_QUESTIONS,
    CRITICAL_FIELDS,
    SlabTbeamExtractionResult,
    SlabTbeamGeometry,
    SlabTbeamParams,
    unusual_value_warnings,
)

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


class SlabTbeamComponent:
    """RCC slab / T-beam deck — IRS Concrete Bridge Code / IS 456 / IR Bridge Rules (25t)."""

    # ---- declarative metadata ----
    type_id = "slab_tbeam"
    display_name = "RCC Slab / T-Beam Deck"
    domain = "civil"
    summary = (
        "RCC slab or T-beam superstructure deck spanning a railway track — dead + 25t "
        "live-load (EUDL x CDA) analysis with lateral distribution, RCC working-stress "
        "section design of the slab/girder, a dimensioned GA drawing + 3D model, and the "
        "same IR-protocol proof-check to IRS/IS-456 codes."
    )
    status = "available"
    codes = ["IRS Concrete Bridge Code", "IS 456", "IR Bridge Rules"]
    scope_examples = [
        "design a 12 m simply-supported RCC T-beam deck, BG single line, 25t loading",
        "solid RCC slab deck 6 m span for a railway bridge, 5 m carriageway",
        "RCC slab and girder superstructure deck spanning 15 m with 4 girders",
        "design an RCC deck slab to span a 8 m railway opening",
    ]
    critical_fields = list(CRITICAL_FIELDS)  # span_m
    param_model = SlabTbeamParams
    geometry_model = SlabTbeamGeometry
    # Extra (not in the minimal Protocol): the analysis rehydration model.
    analysis_model = SlabTbeamAnalysis

    @property
    def member_labels(self) -> dict[str, str]:
        """Human-readable member names, exposed via the interface so the shared
        `check` node narrates failing members through dispatch, not a direct
        component-engine import (component-registry SC#6)."""
        from components.slab_tbeam.checks import MEMBER_LABELS

        return MEMBER_LABELS

    # ---- intake ----
    def extraction_schema(self) -> type:
        return SlabTbeamExtractionResult

    def clarify_question(self, missing_field: str) -> str:
        return CLARIFICATION_QUESTIONS[missing_field]

    def unusual_value_warnings(self, params) -> list[str]:
        return unusual_value_warnings(coerce(SlabTbeamParams, params))

    # ---- deterministic engineering pipeline ----
    def size(self, params) -> SizingOutput:
        from components.slab_tbeam.sizing import size_deck

        result = size_deck(coerce(SlabTbeamParams, params))
        return SizingOutput(
            geometry=result.geometry,
            assumptions=list(result.assumptions),
            trail=list(result.trail),
            warnings=list(result.warnings),
        )

    def analyse(self, params, geometry) -> AnalysisOutput:
        result = analyse_deck(
            coerce(SlabTbeamParams, params), coerce(SlabTbeamGeometry, geometry)
        )
        return AnalysisOutput(
            analysis=result,
            assumptions=list(result.assumptions),
            trail=list(result.trail),
        )

    def run_checks(self, params, geometry, analysis) -> CheckOutput:
        from components.slab_tbeam.checks import run_deck_checks

        output = run_deck_checks(
            coerce(SlabTbeamAnalysis, analysis),
            coerce(SlabTbeamGeometry, geometry),
            coerce(SlabTbeamParams, params),
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
        from components.slab_tbeam.calcsheet import compose_calc_sheet

        segments = [[coerce(CalcStep, step) for step in segment] for segment in trail_segments]
        return compose_calc_sheet(
            trail=segments,
            checks=[coerce(CheckResult, c) for c in checks],
            assumptions=[coerce(Assumption, a) for a in assumptions],
            warnings=list(warnings),
            params=coerce(SlabTbeamParams, params),
            geometry=coerce(SlabTbeamGeometry, geometry),
            out_dir=out_dir,
        )

    def draw(self, params, geometry, out_dir: Path, run_id: str) -> dict[str, Path]:
        from components.slab_tbeam.drawing import generate_ga

        return generate_ga(
            coerce(SlabTbeamParams, params),
            coerce(SlabTbeamGeometry, geometry),
            out_dir,
            run_id=run_id,
        )

    def model3d(self, geometry, out_dir: Path) -> dict[str, Path]:
        from components.slab_tbeam.model3d import generate_solid

        return generate_solid(coerce(SlabTbeamGeometry, geometry), out_dir)

    # ---- IR-protocol review spine ----
    def proof_check(
        self, *, params, geometry, analysis, checks, ga_dxf_path: Path, out_dir: Path
    ) -> ProofCheckOutput:
        from components.slab_tbeam.proofcheck import (
            BMD_FILENAME,
            memo_facts,
            render_memo,
            run_proof_check,
            validate_narration,
        )
        from proofcheck.checklist import COMPLIANCE_FILENAME
        from proofcheck.memo import PROOF_MEMO_FILENAME

        params = coerce(SlabTbeamParams, params)
        geometry = coerce(SlabTbeamGeometry, geometry)
        analysis = coerce(SlabTbeamAnalysis, analysis)
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
        return (_PROMPT_DIR / "slab_tbeam_memo.md").read_text(encoding="utf-8").strip()

    # ---- type-specific outputs ----
    def type_summary(self, *, params, geometry, analysis, checks, proof) -> dict:
        from components.slab_tbeam.summary import type_summary

        return type_summary(
            params=coerce(SlabTbeamParams, params),
            geometry=coerce(SlabTbeamGeometry, geometry),
            analysis=coerce(SlabTbeamAnalysis, analysis),
            checks=[coerce(CheckResult, c) for c in checks],
            verdict=proof.verdict,
        )


register(SlabTbeamComponent())
