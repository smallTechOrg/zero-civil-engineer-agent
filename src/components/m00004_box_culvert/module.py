"""M00004BoxCulvertComponent — the ninth registered component.

The RDSO/M-00004 STANDARD single box culvert: a params-direct (form-only),
standard-driven component that reproduces a published standard config on the
entered opening. Distinct from the load-engineered `box_culvert`; it never
imports that engine. Declares `params_direct_only = True` — the intake LLM nodes
are bypassed (see spec/capabilities/m00004-box-culvert.md).

A first-class `ComponentModule` (structurally satisfying `components.base`)
delegating to this package's catalogue, sizing, checks, drawing (GA + PDF sheet),
3D and proof-check modules. `register(M00004BoxCulvertComponent())` runs at
import (see `__init__.py`).
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
from components.m00004_box_culvert.analysis import M00004Analysis
from components.m00004_box_culvert.params import (
    CRITICAL_FIELDS,
    M00004Geometry,
    M00004Params,
    unusual_value_warnings,
)
from components.registry import register

_MEMO_PROMPT = Path(__file__).resolve().parent / "m00004_memo.md"


class M00004BoxCulvertComponent:
    """RDSO/M-00004 standard single box culvert — standard-driven, params-direct."""

    # ---- declarative metadata ----
    type_id = "m00004_box_culvert"
    display_name = "M-00004 Standard Box Culvert (RDSO)"
    domain = "civil"
    summary = (
        "Reproduces the published RDSO/M-00004 standard single box culvert from a typed "
        "parameter form: a deterministic catalogue lookup picks the enclosing/nearest "
        "standard config and emits the full standard package — GA (DXF/SVG), 3D solid "
        "(STEP/GLB) and an M-00004-styled PDF sheet with the a1..h bars drawn in position. "
        "Standard-driven (not load-engineered); every catalogue value is PROVISIONAL."
    )
    status = "available"
    codes = ["RDSO/M-00004", "IRS Concrete Bridge Code"]
    scope_examples: list[str] = []
    critical_fields = list(CRITICAL_FIELDS)
    param_model = M00004Params
    geometry_model = M00004Geometry
    # Extra (not in the minimal Protocol): the analysis rehydration model.
    analysis_model = M00004Analysis
    # This component is reachable ONLY via the picker -> parameter form: the API
    # rejects it when submitted without a `params` object (422 PARAMS_REQUIRED).
    params_direct_only = True

    # ---- intake (UNREACHABLE on this params-direct component) ----
    def extraction_schema(self) -> type:
        return M00004Params

    def clarify_question(self, missing_field: str) -> str:
        return (
            f"Please provide {missing_field.replace('_', ' ')} on the M-00004 standard "
            "box-culvert form (the form enforces span, height and fill)."
        )

    def unusual_value_warnings(self, params) -> list[str]:
        return unusual_value_warnings(coerce(M00004Params, params))

    # ---- deterministic engineering pipeline ----
    def size(self, params) -> SizingOutput:
        from components.m00004_box_culvert.sizing import size_output

        return size_output(coerce(M00004Params, params))

    def analyse(self, params, geometry) -> AnalysisOutput:
        from components.m00004_box_culvert.analysis import analyse

        return analyse(coerce(M00004Params, params), coerce(M00004Geometry, geometry))

    def run_checks(self, params, geometry, analysis) -> CheckOutput:
        from components.m00004_box_culvert.checks import run_checks

        output = run_checks(
            coerce(M00004Params, params),
            coerce(M00004Geometry, geometry),
            coerce(M00004Analysis, analysis),
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
        from components.m00004_box_culvert.calcsheet import compose_calc_sheet

        segments = [[coerce(CalcStep, step) for step in segment] for segment in trail_segments]
        return compose_calc_sheet(
            trail=segments,
            checks=[coerce(CheckResult, c) for c in checks],
            assumptions=[coerce(Assumption, a) for a in assumptions],
            warnings=list(warnings),
            params=coerce(M00004Params, params),
            geometry=coerce(M00004Geometry, geometry),
            out_dir=out_dir,
        )

    def draw(self, params, geometry, out_dir: Path, run_id: str) -> dict[str, Path]:
        from components.m00004_box_culvert.drawing import draw

        return draw(
            coerce(M00004Params, params),
            coerce(M00004Geometry, geometry),
            out_dir,
            run_id=run_id,
        )

    def model3d(self, geometry, out_dir: Path) -> dict[str, Path]:
        from components.m00004_box_culvert.model3d import model3d

        return model3d(coerce(M00004Geometry, geometry), out_dir)

    # ---- review-stage composed GA sheet + zip bundle (M-00004-only hook) ----
    def compose(self, params, geometry, out_dir: Path, run_id: str) -> dict[str, Path]:
        """Compose the RDSO GA sheet PDF + the zip bundle from on-disk outputs.

        Invoked (guarded, non-fatal) in the graph `review` node after `draw`
        (2D — always on disk) and `model3d` (STEP — possibly absent) complete.
        Delegates to `compose.compose`, which reads the per-diagram DXFs + STEP
        files from `out_dir` and degrades gracefully if any input is missing.
        Returns `{"m00004_ga_sheet": Path, "m00004_bundle": Path}`.
        """
        from components.m00004_box_culvert import compose as _compose

        return _compose.compose(
            coerce(M00004Params, params),
            coerce(M00004Geometry, geometry),
            out_dir,
            run_id=run_id,
        )

    # ---- IR-protocol review spine ----
    def proof_check(
        self, *, params, geometry, analysis, checks, ga_dxf_path: Path, out_dir: Path
    ) -> ProofCheckOutput:
        from components.m00004_box_culvert.proofcheck import (
            PROOF_MEMO_FILENAME,
            COMPLIANCE_FILENAME,
            memo_facts,
            render_memo,
            run_proof_check,
            validate_narration,
        )

        params = coerce(M00004Params, params)
        geometry = coerce(M00004Geometry, geometry)
        check_rows = [coerce(CheckResult, c) for c in checks]

        result = run_proof_check(
            params=params,
            geometry=geometry,
            checks=check_rows,
            ga_dxf_path=ga_dxf_path,
            out_dir=out_dir,
        )

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
            fe_comparison=None,
            checklist=[item.model_dump() for item in result.items],
            verdict=result.verdict,
            fe_agreement_pct=100.0,
            memo_facts=facts,
            validate_narration=_validate,
            render_memo=_render,
            artefacts=[("compliance", COMPLIANCE_FILENAME)],
            memo_kind="proof_memo",
            memo_filename=PROOF_MEMO_FILENAME,
        )

    def memo_prompt(self) -> str:
        return _MEMO_PROMPT.read_text(encoding="utf-8").strip()

    # ---- type-specific outputs ----
    def type_summary(self, *, params, geometry, analysis, checks, proof) -> dict:
        from components.m00004_box_culvert.summary import type_summary

        return type_summary(geometry=coerce(M00004Geometry, geometry), verdict=proof.verdict)


register(M00004BoxCulvertComponent())
