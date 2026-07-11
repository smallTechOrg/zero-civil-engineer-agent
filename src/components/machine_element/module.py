"""MachineElementComponent — the mechanical-domain machine element.

A first-class `ComponentModule` (structurally satisfying `components.base`)
delegating to this package's engine (`sizing`/`analysis`/`checks`), drawing, 3D
and proof-check modules. Mirrors the civil components exactly: declarative
metadata, lazy heavy imports inside methods, `coerce(...)` at method tops, and a
`proof_check` returning a `ProofCheckOutput` with pre-bound
`validate_narration`/`render_memo` closures + an `artefacts` list.

This is a breadth-first NEW component on the SAME `ComponentModule` interface and
IR-protocol review spine as the civil components — it replaces the `machine_element`
coming_soon stub. Two element kinds are supported: a transmission `shaft` (combined
bending + torsion, static + fatigue factors of safety) and a `welded_joint` (a
circular fillet-welded hub in torsion). The engineering basis is STANDARD MACHINE
DESIGN, not any civil/bridge code.

`register(MachineElementComponent())` runs at import (see `__init__.py`).
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
from components.machine_element._engine_common import CODES
from components.machine_element.analysis import MachineElementAnalysis, analyse_element
from components.machine_element.params import (
    CLARIFICATION_QUESTIONS,
    CRITICAL_FIELDS,
    MachineElementExtractionResult,
    MachineElementGeometry,
    MachineElementParams,
    unusual_value_warnings,
)
from components.registry import register

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


class MachineElementComponent:
    """Machine element — standard design of machine elements (Shigley / PSG / IS 816)."""

    # ---- declarative metadata ----
    type_id = "machine_element"
    display_name = "Machine Element"
    domain = "mechanical"
    summary = (
        "Machine element (transmission shaft or welded coupling hub) — torque from the "
        "transmitted power, combined bending + torsion by the maximum-shear-stress theory, "
        "a static factor of safety against yield and a rotating-shaft fatigue check (or the "
        "torsional shear in a circular fillet weld), a dimensioned detail drawing with GD&T "
        "and weld symbols + a 3D model, and the same IR-protocol proof-check against standard "
        "machine-design practice."
    )
    status = "available"
    codes = list(CODES)
    scope_examples = [
        "design a power-transmission shaft for 20 kW at 1000 rpm",
        "size a transmission shaft transmitting 15 kW at 1450 rpm with an overhung pulley",
        "design a welded coupling hub transmitting 100 kW at 100 rpm",
        "check a fillet-welded hub for a 50 kW drive at 300 rpm",
    ]
    critical_fields = list(CRITICAL_FIELDS)  # power_kw
    param_model = MachineElementParams
    geometry_model = MachineElementGeometry
    # Extra (not in the minimal Protocol): the analysis rehydration model.
    analysis_model = MachineElementAnalysis

    @property
    def member_labels(self) -> dict[str, str]:
        """Human-readable member names, exposed via the interface so the shared
        `check` node narrates failing members through dispatch, not a direct
        component-engine import."""
        from components.machine_element.checks import MEMBER_LABELS

        return MEMBER_LABELS

    # ---- intake ----
    def extraction_schema(self) -> type:
        return MachineElementExtractionResult

    def clarify_question(self, missing_field: str) -> str:
        return CLARIFICATION_QUESTIONS[missing_field]

    def unusual_value_warnings(self, params) -> list[str]:
        return unusual_value_warnings(coerce(MachineElementParams, params))

    # ---- deterministic engineering pipeline ----
    def size(self, params) -> SizingOutput:
        from components.machine_element.sizing import size_element

        result = size_element(coerce(MachineElementParams, params))
        return SizingOutput(
            geometry=result.geometry,
            assumptions=list(result.assumptions),
            trail=list(result.trail),
            warnings=list(result.warnings),
        )

    def analyse(self, params, geometry) -> AnalysisOutput:
        result = analyse_element(
            coerce(MachineElementParams, params), coerce(MachineElementGeometry, geometry)
        )
        return AnalysisOutput(
            analysis=result,
            assumptions=list(result.assumptions),
            trail=list(result.trail),
        )

    def run_checks(self, params, geometry, analysis) -> CheckOutput:
        from components.machine_element.checks import run_element_checks

        output = run_element_checks(
            coerce(MachineElementAnalysis, analysis),
            coerce(MachineElementGeometry, geometry),
            coerce(MachineElementParams, params),
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
        from components.machine_element.calcsheet import compose_calc_sheet

        segments = [[coerce(CalcStep, step) for step in segment] for segment in trail_segments]
        return compose_calc_sheet(
            trail=segments,
            checks=[coerce(CheckResult, c) for c in checks],
            assumptions=[coerce(Assumption, a) for a in assumptions],
            warnings=list(warnings),
            params=coerce(MachineElementParams, params),
            geometry=coerce(MachineElementGeometry, geometry),
            out_dir=out_dir,
        )

    def draw(self, params, geometry, out_dir: Path, run_id: str) -> dict[str, Path]:
        from components.machine_element.drawing import generate_ga

        return generate_ga(
            coerce(MachineElementParams, params),
            coerce(MachineElementGeometry, geometry),
            out_dir,
            run_id=run_id,
        )

    def model3d(self, geometry, out_dir: Path) -> dict[str, Path]:
        from components.machine_element.model3d import generate_solid

        return generate_solid(coerce(MachineElementGeometry, geometry), out_dir)

    # ---- IR-protocol review spine ----
    def proof_check(
        self, *, params, geometry, analysis, checks, ga_dxf_path: Path, out_dir: Path
    ) -> ProofCheckOutput:
        from components.machine_element.proofcheck import (
            BMD_FILENAME,
            memo_facts,
            render_memo,
            run_proof_check,
            validate_narration,
        )
        from proofcheck.checklist import COMPLIANCE_FILENAME
        from proofcheck.memo import PROOF_MEMO_FILENAME

        params = coerce(MachineElementParams, params)
        geometry = coerce(MachineElementGeometry, geometry)
        analysis = coerce(MachineElementAnalysis, analysis)
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
        return (_PROMPT_DIR / "machine_element_memo.md").read_text(encoding="utf-8").strip()

    # ---- type-specific outputs ----
    def type_summary(self, *, params, geometry, analysis, checks, proof) -> dict:
        from components.machine_element.summary import type_summary

        return type_summary(
            analysis=coerce(MachineElementAnalysis, analysis),
            verdict=proof.verdict,
        )


register(MachineElementComponent())
