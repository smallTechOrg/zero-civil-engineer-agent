"""StructuralSteelMemberComponent — the fabricated structural-steel member (mechanical domain).

A first-class `ComponentModule` (structurally satisfying `components.base`)
delegating to this package's engine (`sizing`/`analysis`/`checks`), drawing, 3D
and proof-check modules. Mirrors the civil components exactly: declarative
metadata, lazy heavy imports inside methods, `coerce(...)` at method tops, and a
`proof_check` returning a `ProofCheckOutput` with pre-bound
`validate_narration`/`render_memo` closures + an `artefacts` list.

This is a breadth-first NEW component on the SAME `ComponentModule` interface and
IR-protocol review spine as the civil components — it replaces the mechanical-domain
`structural_steel_member` coming_soon stub with a real, available module.

`register(StructuralSteelMemberComponent())` runs at import (see `__init__.py`).
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
from components.structural_steel_member.analysis import SteelMemberAnalysis, analyse_member
from components.structural_steel_member.params import (
    CLARIFICATION_QUESTIONS,
    CRITICAL_FIELDS,
    SteelMemberExtractionResult,
    SteelMemberGeometry,
    SteelMemberParams,
    unusual_value_warnings,
)

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


class StructuralSteelMemberComponent:
    """Fabricated structural-steel member (bracket / gantry post / OHE mast) — IS 800 / IS 816."""

    # ---- declarative metadata ----
    type_id = "structural_steel_member"
    display_name = "Structural Steel / Fabrication Member"
    domain = "mechanical"
    summary = (
        "Fabricated welded-I structural-steel member (bracket, gantry post or OHE mast) — "
        "working-stress design of the section (axial, bending, shear, combined interaction) "
        "and the base fillet-weld connection to IS 800 / IS 816, a fabrication drawing with "
        "weld symbols + a 3D model, and the same IR-protocol proof-check."
    )
    status = "available"
    codes = ["IS 800", "IS 816"]
    scope_examples = [
        "design a welded steel bracket to IS 800 with a fillet-weld base connection",
        "fabricated steel gantry post, 6 m, 20 kN tip load, IS 800 + IS 816 weld check",
        "OHE mast fabricated member, working-stress design to IS 800",
        "welded I-section cantilever member with a checked fillet-weld group",
    ]
    critical_fields = list(CRITICAL_FIELDS)  # cantilever_length_m, transverse_load_kn
    param_model = SteelMemberParams
    geometry_model = SteelMemberGeometry
    # Extra (not in the minimal Protocol): the analysis rehydration model.
    analysis_model = SteelMemberAnalysis

    @property
    def member_labels(self) -> dict[str, str]:
        """Human-readable member names, exposed via the interface so the shared
        `check` node narrates failing members through dispatch, not a direct
        component-engine import."""
        from components.structural_steel_member.checks import MEMBER_LABELS

        return MEMBER_LABELS

    # ---- intake ----
    def extraction_schema(self) -> type:
        return SteelMemberExtractionResult

    def clarify_question(self, missing_field: str) -> str:
        return CLARIFICATION_QUESTIONS[missing_field]

    def unusual_value_warnings(self, params) -> list[str]:
        return unusual_value_warnings(coerce(SteelMemberParams, params))

    # ---- deterministic engineering pipeline ----
    def size(self, params) -> SizingOutput:
        from components.structural_steel_member.sizing import size_member

        result = size_member(coerce(SteelMemberParams, params))
        return SizingOutput(
            geometry=result.geometry,
            assumptions=list(result.assumptions),
            trail=list(result.trail),
            warnings=list(result.warnings),
        )

    def analyse(self, params, geometry) -> AnalysisOutput:
        result = analyse_member(
            coerce(SteelMemberParams, params), coerce(SteelMemberGeometry, geometry)
        )
        return AnalysisOutput(
            analysis=result,
            assumptions=list(result.assumptions),
            trail=list(result.trail),
        )

    def run_checks(self, params, geometry, analysis) -> CheckOutput:
        from components.structural_steel_member.checks import run_member_checks

        output = run_member_checks(
            coerce(SteelMemberAnalysis, analysis),
            coerce(SteelMemberGeometry, geometry),
            coerce(SteelMemberParams, params),
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
        from components.structural_steel_member.calcsheet import compose_calc_sheet

        segments = [[coerce(CalcStep, step) for step in segment] for segment in trail_segments]
        return compose_calc_sheet(
            trail=segments,
            checks=[coerce(CheckResult, c) for c in checks],
            assumptions=[coerce(Assumption, a) for a in assumptions],
            warnings=list(warnings),
            params=coerce(SteelMemberParams, params),
            geometry=coerce(SteelMemberGeometry, geometry),
            out_dir=out_dir,
        )

    def draw(self, params, geometry, out_dir: Path, run_id: str) -> dict[str, Path]:
        from components.structural_steel_member.drawing import generate_ga

        return generate_ga(
            coerce(SteelMemberParams, params),
            coerce(SteelMemberGeometry, geometry),
            out_dir,
            run_id=run_id,
        )

    def model3d(self, geometry, out_dir: Path) -> dict[str, Path]:
        from components.structural_steel_member.model3d import generate_solid

        return generate_solid(coerce(SteelMemberGeometry, geometry), out_dir)

    # ---- IR-protocol review spine ----
    def proof_check(
        self, *, params, geometry, analysis, checks, ga_dxf_path: Path, out_dir: Path
    ) -> ProofCheckOutput:
        from components.structural_steel_member.proofcheck import (
            BMD_FILENAME,
            memo_facts,
            render_memo,
            run_proof_check,
            validate_narration,
        )
        from proofcheck.checklist import COMPLIANCE_FILENAME
        from proofcheck.memo import PROOF_MEMO_FILENAME

        params = coerce(SteelMemberParams, params)
        geometry = coerce(SteelMemberGeometry, geometry)
        analysis = coerce(SteelMemberAnalysis, analysis)
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
        return (_PROMPT_DIR / "structural_steel_member_memo.md").read_text(encoding="utf-8").strip()

    # ---- type-specific outputs ----
    def type_summary(self, *, params, geometry, analysis, checks, proof) -> dict:
        from components.structural_steel_member.summary import type_summary

        return type_summary(
            analysis=coerce(SteelMemberAnalysis, analysis),
            verdict=proof.verdict,
        )


register(StructuralSteelMemberComponent())
