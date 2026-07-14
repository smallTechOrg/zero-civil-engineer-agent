"""Standard-conformance checks for the M-00004 standard box culvert.

Because this is a STANDARD-DRIVEN component (not load-engineered), the checks are
NOT independent strength verifications. Each row records that a value has been
reproduced from the M-00004 standard config and is therefore PASS-by-reproduction,
carrying an explicit PROVISIONAL note that it has NOT been independently verified.
The proof-check memo makes the same honesty statement at the design-basis level.
"""

from __future__ import annotations

from pydantic import BaseModel

from components.base import Assumption, CalcStep, CheckOutput, CheckResult, coerce
from components.m00004_box_culvert.analysis import M00004Analysis
from components.m00004_box_culvert.params import M00004Geometry, M00004Params
from components.m00004_box_culvert.sizing import VERIFY_TAG

MEMBER_LABELS = {
    "all": "All members",
    "top_slab": "Top slab",
    "bottom_slab": "Bottom slab",
    "wall": "Side walls",
}

_CLAUSE = "RDSO/M-00004 standard single box culvert (reproduced detailing)"


class M00004ChecksOutput(BaseModel):
    checks: list[CheckResult]
    trail: list[CalcStep] = []
    assumptions: list[Assumption] = []


def _row(*, requirement, computed, limit, member, kind, trail_ref) -> CheckResult:
    return CheckResult(
        clause=_CLAUSE,
        requirement=requirement,
        computed=computed,
        limit=limit,
        status="PASS",
        member=member,
        kind=kind,
        trail_ref=trail_ref,
        severity_hint="info",
    )


def run_checks(
    params: M00004Params, geometry: M00004Geometry, analysis: M00004Analysis
) -> M00004ChecksOutput:
    """Emit standard-conformance rows (each PASS with a PROVISIONAL note)."""
    params = coerce(M00004Params, params)
    geometry = coerce(M00004Geometry, geometry)

    steps = [
        CalcStep(
            step_id="K01",
            description="Standard config conformance",
            formula="config = " + geometry.config_id,
            inputs={"config_id": geometry.config_id},
            value=geometry.thickness_mm,
            unit="mm",
            citation=_CLAUSE + f" - {VERIFY_TAG}",
        ),
        CalcStep(
            step_id="K02",
            description="Reproduced detailing (thickness/haunch)",
            formula="t, B taken from standard config",
            inputs={"thickness_mm": geometry.thickness_mm, "haunch_mm": geometry.haunch_mm},
            value=geometry.haunch_mm,
            unit="mm",
            citation=_CLAUSE + f" - {VERIFY_TAG}",
        ),
        CalcStep(
            step_id="K03",
            description="Reproduced reinforcement schedule (a1..h)",
            formula="bar schedule taken from standard config",
            inputs={"marks": ", ".join(sorted(geometry.bar_schedule))},
            value=float(len(geometry.bar_schedule)),
            unit="marks",
            citation=_CLAUSE + f" - {VERIFY_TAG}",
        ),
        CalcStep(
            step_id="K04",
            description="Derived barrel length",
            formula="L = formation_width + 2 x side_slope x (cushion + outer_height)",
            inputs={"outer_height_mm": geometry.outer_height_mm},
            value=geometry.barrel_length_mm,
            unit="mm",
            citation="Standard single-cell box geometry",
        ),
    ]

    checks = [
        _row(
            requirement=(
                "Slab/wall thickness must be reproduced from the selected M-00004 standard "
                "config (standard-driven, not independently sized)."
            ),
            computed=f"config {geometry.config_id}, thickness {geometry.thickness_mm:g} mm",
            limit=f"reproduced from the standard config ({VERIFY_TAG})",
            member="all",
            kind="standard_config",
            trail_ref="K01",
        ),
        _row(
            requirement=(
                "Haunch detailing must be reproduced from the selected standard config."
            ),
            computed=f"haunch {geometry.haunch_mm:g} mm from config {geometry.config_id}",
            limit=f"reproduced from the standard config ({VERIFY_TAG})",
            member="all",
            kind="standard_detailing",
            trail_ref="K02",
        ),
        _row(
            requirement=(
                "The a1..h reinforcement schedule must be reproduced from the standard config "
                "(PROVISIONAL demonstration set - not independently designed)."
            ),
            computed=f"{len(geometry.bar_schedule)} marks reproduced from config {geometry.config_id}",
            limit=f"reproduced from the standard config ({VERIFY_TAG})",
            member="all",
            kind="standard_reinforcement",
            trail_ref="K03",
        ),
        _row(
            requirement=(
                "The barrel length must follow the standard embankment cross-section formula."
            ),
            computed=f"barrel length {geometry.barrel_length_mm:g} mm",
            limit="formation_width + 2 x side_slope x (cushion + outer_height)",
            member="all",
            kind="geometry",
            trail_ref="K04",
        ),
    ]

    assumptions = [
        Assumption(
            field="check_basis",
            value="standard-conformance",
            source="engine_default",
            note=(
                "Checks record reproduction of the M-00004 standard, NOT independent strength "
                f"verification. Every value is PROVISIONAL - {VERIFY_TAG}."
            ),
        )
    ]
    return M00004ChecksOutput(checks=checks, trail=steps, assumptions=assumptions)
