"""Stability + section checks for the pier / abutment substructure.

Clause-cited `CheckResult` rows (IRS Bridge Substructure & Foundation Code):

* **Stability** — factor of safety against overturning (>= 2.0) and sliding
  (>= 1.5), maximum base bearing (p_max <= SBC) and no tension (p_min >= 0).
* **Pier section** — direct compressive stress in the pier/stem within the
  permissible working-stress value; plus a clear-cover check.

An under-designed footing (weak soil or a deliberately small override) flows
through to a FAIL row, graded major by the proof-check. Reuses the shared
`CheckResult` row shape so the graph's check node and calc-sheet composer treat
every component alike.
"""

from __future__ import annotations

from pydantic import BaseModel

from components.base import Assumption, CheckResult, coerce
from components.pier_abutment._engine_common import (
    CITATION_COVER,
    CITATION_DIRECT_STRESS,
    CITATION_STABILITY,
    MIN_CLEAR_COVER_MM,
    Trail,
)
from components.pier_abutment.analysis import PierAbutmentAnalysis
from components.pier_abutment.params import PierAbutmentGeometry, PierAbutmentParams
from components.pier_abutment.sizing import FOS_OVERTURNING_MIN, FOS_SLIDING_MIN

MEMBER_LABELS = {
    "stability": "Stability",
    "pier": "Pier / stem",
    "footing": "Footing",
    "all": "All members",
}


class PierAbutmentChecksOutput(BaseModel):
    """Everything `run_substructure_checks` returns — rows plus their provenance."""

    checks: list[CheckResult]
    trail: list = []
    assumptions: list[Assumption] = []


def _severity(status: str) -> str:
    return "critical" if status == "FAIL" else "info"


def _fos_row(*, kind: str, label: str, value: float, limit: float, trail_ref: str) -> CheckResult:
    status = "PASS" if value >= limit else "FAIL"
    return CheckResult(
        clause=CITATION_STABILITY,
        requirement=f"{label}: factor of safety >= {limit:g}",
        computed=f"FoS = {value:.2f}",
        limit=f">= {limit:g}",
        status=status,
        member="stability",
        kind=kind,
        trail_ref=trail_ref,
        severity_hint=_severity(status),
    )


def run_substructure_checks(
    analysis: PierAbutmentAnalysis,
    geometry: PierAbutmentGeometry,
    params: PierAbutmentParams,
) -> PierAbutmentChecksOutput:
    """All stability + section checks with a CalcStep trail."""
    analysis = coerce(PierAbutmentAnalysis, analysis)
    geometry = coerce(PierAbutmentGeometry, geometry)
    params = coerce(PierAbutmentParams, params)
    trail = Trail("K")
    member = "pier"
    checks: list[CheckResult] = []

    # --- overturning ---
    trail.record(
        description="Overturning stability", formula="FoS_ot = Mr / Mo",
        inputs={"Mr_knm": analysis.resisting_moment_knm, "Mo_knm": analysis.overturning_moment_knm},
        value=analysis.fos_overturning, unit="-", citation=CITATION_STABILITY,
    )
    checks.append(_fos_row(kind="overturning", label="Overturning",
                           value=analysis.fos_overturning, limit=FOS_OVERTURNING_MIN,
                           trail_ref=trail.last_id()))

    # --- sliding ---
    trail.record(
        description="Sliding stability", formula="FoS_sl = (mu*W + Pp) / H",
        inputs={"resistance_kn": analysis.sliding_resistance_kn, "horizontal_kn": analysis.total_horizontal_kn},
        value=analysis.fos_sliding, unit="-", citation=CITATION_STABILITY,
    )
    checks.append(_fos_row(kind="sliding", label="Sliding",
                           value=analysis.fos_sliding, limit=FOS_SLIDING_MIN,
                           trail_ref=trail.last_id()))

    # --- bearing (max pressure) ---
    trail.record(
        description="Maximum base pressure (toe)", formula="p_max = W/A * (1 + 6e/B)",
        inputs={"total_vertical_kn": analysis.total_vertical_kn, "eccentricity_m": analysis.eccentricity_m},
        value=analysis.max_base_pressure_kn_m2, unit="kN/m^2", citation=CITATION_STABILITY,
    )
    bearing_status = "PASS" if analysis.max_base_pressure_kn_m2 <= params.safe_bearing_capacity_kn_m2 else "FAIL"
    checks.append(CheckResult(
        clause=CITATION_STABILITY,
        requirement="Bearing: maximum toe pressure within the safe bearing capacity",
        computed=f"p_max = {analysis.max_base_pressure_kn_m2:.1f} kN/m^2",
        limit=f"SBC = {params.safe_bearing_capacity_kn_m2:g} kN/m^2",
        status=bearing_status, member="stability", kind="bearing",
        trail_ref=trail.last_id(), severity_hint=_severity(bearing_status),
    ))

    # --- no tension (min pressure) ---
    trail.record(
        description="Minimum base pressure (heel)", formula="p_min = W/A * (1 - 6e/B)",
        inputs={"total_vertical_kn": analysis.total_vertical_kn, "eccentricity_m": analysis.eccentricity_m},
        value=analysis.min_base_pressure_kn_m2, unit="kN/m^2", citation=CITATION_STABILITY,
    )
    tension_status = "PASS" if analysis.min_base_pressure_kn_m2 >= -1e-6 else "FAIL"
    checks.append(CheckResult(
        clause=CITATION_STABILITY,
        requirement="Bearing: heel pressure non-negative (no tension under the footing)",
        computed=f"p_min = {analysis.min_base_pressure_kn_m2:.1f} kN/m^2 (e = {analysis.eccentricity_m:.3f} m)",
        limit=">= 0 kN/m^2",
        status=tension_status, member="stability", kind="bearing_tension",
        trail_ref=trail.last_id(), severity_hint=_severity(tension_status),
    ))

    # --- pier direct compressive stress ---
    trail.record(
        description="pier: direct compressive stress", formula="sigma_cc = axial / A_pier",
        inputs={"axial_kn": analysis.pier_axial_kn, "pier_area_m2": analysis.pier_area_m2},
        value=round(analysis.pier_direct_stress_n_mm2, 4), unit="N/mm^2", citation=CITATION_DIRECT_STRESS,
    )
    stress_status = (
        "PASS" if analysis.pier_direct_stress_n_mm2 <= analysis.permissible_direct_stress_n_mm2 else "FAIL"
    )
    checks.append(CheckResult(
        clause=CITATION_DIRECT_STRESS,
        requirement="Direct stress: pier axial compressive stress within the permissible value",
        computed=f"sigma_cc = {analysis.pier_direct_stress_n_mm2:.3f} N/mm^2 for axial "
                 f"{analysis.pier_axial_kn:.0f} kN",
        limit=f"sigma_cc,perm = {analysis.permissible_direct_stress_n_mm2:.2f} N/mm^2 "
              f"({params.concrete_grade.value})",
        status=stress_status, member=member, kind="direct_stress",
        trail_ref=trail.last_id(), severity_hint=_severity(stress_status),
    ))

    # --- clear cover ---
    trail.record(
        description="Clear cover to reinforcement, provided", formula="cover = clear_cover_mm (user/preset)",
        inputs={"clear_cover_mm": params.clear_cover_mm}, value=params.clear_cover_mm,
        unit="mm", citation=CITATION_COVER,
    )
    cover_status = "PASS" if params.clear_cover_mm >= MIN_CLEAR_COVER_MM else "FAIL"
    checks.append(CheckResult(
        clause=CITATION_COVER,
        requirement="Clear cover: provided cover at least the code minimum (all members)",
        computed=f"cover = {params.clear_cover_mm:g} mm provided",
        limit=f"cover_min = {MIN_CLEAR_COVER_MM:g} mm (moderate exposure)",
        status=cover_status, member="all", kind="cover",
        trail_ref=trail.last_id(), severity_hint=_severity(cover_status),
    ))

    return PierAbutmentChecksOutput(checks=checks, trail=trail.steps, assumptions=_check_assumptions())


def _check_assumptions() -> list[Assumption]:
    return [
        Assumption(
            field="pier_section_check",
            value="direct compression",
            source="engine_default",
            note=(
                "The pier/stem is checked for direct (axial) compressive stress at the top "
                "of the footing; slenderness and biaxial bending detailing are beyond this "
                "breadth-first level and are noted, not verified."
            ),
        ),
        Assumption(
            field="exposure_condition",
            value="moderate",
            source="engine_default",
            note=(
                f"Moderate exposure assumed for the cover check — minimum clear cover "
                f"{MIN_CLEAR_COVER_MM:g} mm (IS 456 cl. 26.4)."
            ),
        ),
    ]
