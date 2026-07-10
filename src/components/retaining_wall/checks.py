"""Stability + RCC section-design checks for the cantilever retaining wall.

Two families of clause-cited `CheckResult` rows:

* **Stability** (from the analysis) — factor of safety against overturning
  (>= 2.0), sliding (>= 1.5) and base bearing (max toe pressure <= SBC, heel
  pressure >= 0, no tension).
* **RCC section design** (IS 456 working stress + IRS CBC) — the stem, heel and
  toe checked as cantilevers for flexure, shear, minimum steel and cover. A stem
  thinner than the flexure-required depth flows through to a FAIL row (the
  under-design demo case), graded major by the proof-check.

Reuses the shared `CheckResult` row shape (`components.base`) so the graph's
check node and calc-sheet composer treat every component alike.
"""

from __future__ import annotations

import math

from pydantic import BaseModel

from components.base import Assumption, CheckResult, coerce
from components.retaining_wall._engine_common import (
    ASSUMED_BAR_DIA_MM,
    CITATION_COVER,
    CITATION_FLEXURE,
    CITATION_MIN_STEEL,
    CITATION_SHEAR,
    CITATION_STABILITY,
    CITATION_STEEL,
    MIN_CLEAR_COVER_MM,
    MIN_STEEL_PCT_GROSS,
    Trail,
    working_stress_constants,
)
from components.retaining_wall.analysis import RetainingWallAnalysis, slab_design_moments
from components.retaining_wall.params import RetainingWallGeometry, RetainingWallParams
from components.retaining_wall.sizing import FOS_OVERTURNING_MIN, FOS_SLIDING_MIN

MEMBER_LABELS = {
    "stability": "Stability",
    "stem": "Stem",
    "heel": "Heel slab",
    "toe": "Toe slab",
    "all": "All members",
}


class WallChecksOutput(BaseModel):
    """Everything `run_wall_checks` returns — rows plus their provenance."""

    checks: list[CheckResult]
    trail: list = []
    assumptions: list[Assumption] = []


def _severity(status: str) -> str:
    return "critical" if status == "FAIL" else "info"


def _fos_row(
    *,
    kind: str,
    label: str,
    value: float,
    limit: float,
    trail_ref: str,
    higher_is_safe: bool = True,
) -> CheckResult:
    status = "PASS" if (value >= limit if higher_is_safe else value <= limit) else "FAIL"
    comparator = ">=" if higher_is_safe else "<="
    return CheckResult(
        clause=CITATION_STABILITY,
        requirement=f"{label}: factor of safety {comparator} {limit:g}",
        computed=f"FoS = {value:.2f}",
        limit=f"{comparator} {limit:g}",
        status=status,
        member="stability",
        kind=kind,
        trail_ref=trail_ref,
        severity_hint=_severity(status),
    )


def run_wall_checks(
    analysis: RetainingWallAnalysis,
    geometry: RetainingWallGeometry,
    params: RetainingWallParams,
) -> WallChecksOutput:
    """All stability + RCC section-design checks with a CalcStep trail."""
    analysis = coerce(RetainingWallAnalysis, analysis)
    geometry = coerce(RetainingWallGeometry, geometry)
    params = coerce(RetainingWallParams, params)
    trail = Trail("K")
    wsc = working_stress_constants(params.concrete_grade, params.steel_grade)

    checks: list[CheckResult] = []

    # --- stability ---
    trail.record(
        description="Overturning stability", formula="FoS_ot = Mr / Mo",
        inputs={"Mr_knm": analysis.resisting_moment_knm, "Mo_knm": analysis.overturning_moment_knm},
        value=analysis.fos_overturning, unit="-", citation=CITATION_STABILITY,
    )
    checks.append(_fos_row(kind="overturning", label="Overturning",
                           value=analysis.fos_overturning, limit=FOS_OVERTURNING_MIN, trail_ref=trail.last_id()))

    trail.record(
        description="Sliding stability", formula="FoS_sl = (mu*W + Pp) / H",
        inputs={"resistance_kn": analysis.sliding_resistance_kn, "horizontal_kn": analysis.total_horizontal_kn},
        value=analysis.fos_sliding, unit="-", citation=CITATION_STABILITY,
    )
    checks.append(_fos_row(kind="sliding", label="Sliding",
                           value=analysis.fos_sliding, limit=FOS_SLIDING_MIN, trail_ref=trail.last_id()))

    trail.record(
        description="Maximum base pressure (toe)", formula="p_max = W/B * (1 + 6e/B)",
        inputs={"total_vertical_kn": analysis.total_vertical_kn, "eccentricity_m": analysis.eccentricity_m},
        value=analysis.max_base_pressure_kn_m2, unit="kN/m^2", citation=CITATION_STABILITY,
    )
    bp_id = trail.last_id()
    bearing_status = "PASS" if analysis.max_base_pressure_kn_m2 <= params.safe_bearing_capacity_kn_m2 else "FAIL"
    checks.append(CheckResult(
        clause=CITATION_STABILITY,
        requirement="Bearing: maximum toe pressure within the safe bearing capacity",
        computed=f"p_max = {analysis.max_base_pressure_kn_m2:.1f} kN/m^2",
        limit=f"SBC = {params.safe_bearing_capacity_kn_m2:g} kN/m^2",
        status=bearing_status, member="stability", kind="bearing",
        trail_ref=bp_id, severity_hint=_severity(bearing_status),
    ))

    trail.record(
        description="Minimum base pressure (heel)", formula="p_min = W/B * (1 - 6e/B)",
        inputs={"total_vertical_kn": analysis.total_vertical_kn, "eccentricity_m": analysis.eccentricity_m},
        value=analysis.min_base_pressure_kn_m2, unit="kN/m^2", citation=CITATION_STABILITY,
    )
    tn_id = trail.last_id()
    tension_status = "PASS" if analysis.min_base_pressure_kn_m2 >= -1e-6 else "FAIL"
    checks.append(CheckResult(
        clause=CITATION_STABILITY,
        requirement="Bearing: heel pressure non-negative (no tension under the base)",
        computed=f"p_min = {analysis.min_base_pressure_kn_m2:.1f} kN/m^2 (e = {analysis.eccentricity_m:.3f} m)",
        limit=">= 0 kN/m^2",
        status=tension_status, member="stability", kind="bearing_tension",
        trail_ref=tn_id, severity_hint=_severity(tension_status),
    ))

    # --- section design ---
    checks.extend(_stem_checks(analysis, geometry, params, wsc, trail))
    checks.extend(_slab_cantilever_checks(analysis, geometry, params, wsc, trail))
    checks.append(_cover_check(params, trail))

    return WallChecksOutput(checks=checks, trail=trail.steps, assumptions=_check_assumptions())


def _effective_depth(thickness_mm: float, params: RetainingWallParams, label: str) -> float:
    d = thickness_mm - params.clear_cover_mm - ASSUMED_BAR_DIA_MM / 2.0
    if d <= 0:
        raise ValueError(
            f"{label} effective depth is non-positive ({d:g} mm) — thickness "
            f"{thickness_mm:g} mm cannot accommodate cover {params.clear_cover_mm:g} mm"
        )
    return d


def _flexure_and_steel_rows(
    *,
    member: str,
    label: str,
    thickness_mm: float,
    moment_knm: float,
    params: RetainingWallParams,
    wsc,
    trail: Trail,
) -> list[CheckResult]:
    d = _effective_depth(thickness_mm, params, label)
    d_req = math.sqrt(moment_knm * 1e6 / (wsc.q_n_mm2 * 1000.0)) if moment_knm > 0 else 0.0
    trail.record(
        description=f"{member}: required vs provided effective depth (flexure)",
        formula="d_req = sqrt(M / (Q*b)); d = t - cover - bar/2",
        inputs={"M_knm": round(moment_knm, 2), "Q_n_mm2": round(wsc.q_n_mm2, 4), "thickness_mm": thickness_mm},
        value=round(d_req, 1), unit="mm", citation=CITATION_FLEXURE,
    )
    d_id = trail.last_id()
    flexure_status = "PASS" if d_req <= d else "FAIL"
    flexure = CheckResult(
        clause=CITATION_FLEXURE,
        requirement=f"Flexure (working stress): required effective depth within provided ({label})",
        computed=f"d_req = {d_req:.0f} mm for M = {moment_knm:.1f} kN*m/m",
        limit=f"d = {d:.0f} mm provided (t = {thickness_mm:g} mm)",
        status=flexure_status, member=member, kind="flexure",
        trail_ref=d_id, severity_hint=_severity(flexure_status),
    )
    as_req = moment_knm * 1e6 / (wsc.sigma_st * wsc.j * d) if moment_knm > 0 else 0.0
    as_min = MIN_STEEL_PCT_GROSS / 100.0 * 1000.0 * thickness_mm
    trail.record(
        description=f"{member}: required tensile steel (working stress)",
        formula="As = M / (sigma_st * j * d)",
        inputs={"M_knm": round(moment_knm, 2), "sigma_st": wsc.sigma_st, "j": round(wsc.j, 4), "d_mm": round(d, 1)},
        value=round(as_req, 1), unit="mm^2/m", citation=CITATION_STEEL,
    )
    as_id = trail.last_id()
    governs = as_min if as_min > as_req else as_req
    min_steel = CheckResult(
        clause=CITATION_MIN_STEEL,
        requirement=f"Reinforcement: required steel vs code minimum ({label})",
        computed=f"As_req = {as_req:.0f} mm^2/m; governing As = {governs:.0f} mm^2/m",
        limit=f"As_min = {as_min:.0f} mm^2/m ({MIN_STEEL_PCT_GROSS:g}% gross)",
        status="PASS", member=member, kind="min_steel",
        trail_ref=as_id, severity_hint="info",
    )
    return [flexure, min_steel]


def _stem_checks(analysis, geometry, params, wsc, trail) -> list[CheckResult]:
    rows = _flexure_and_steel_rows(
        member="stem", label="Stem", thickness_mm=geometry.stem_base_thickness_mm,
        moment_knm=analysis.stem_moment_knm, params=params, wsc=wsc, trail=trail,
    )
    d = _effective_depth(geometry.stem_base_thickness_mm, params, "Stem")
    tau = analysis.stem_shear_kn * 1e3 / (1000.0 * d)  # kN/m over mm -> N/mm^2
    trail.record(
        description="stem: applied shear stress at the base",
        formula="tau = V / (b * d)",
        inputs={"V_kn": analysis.stem_shear_kn, "d_mm": round(d, 1)},
        value=round(tau, 4), unit="N/mm^2", citation=CITATION_SHEAR,
    )
    sh_id = trail.last_id()
    shear_status = "PASS" if tau <= wsc.tau_c else "FAIL"
    rows.append(CheckResult(
        clause=CITATION_SHEAR,
        requirement="Shear: applied stress within permissible, no shear reinforcement (Stem)",
        computed=f"tau = {tau:.3f} N/mm^2 for V = {analysis.stem_shear_kn:.1f} kN/m",
        limit=f"tau_c = {wsc.tau_c:.2f} N/mm^2 ({params.concrete_grade.value})",
        status=shear_status, member="stem", kind="shear",
        trail_ref=sh_id, severity_hint=_severity(shear_status),
    ))
    return rows


def _slab_cantilever_checks(analysis, geometry, params, wsc, trail) -> list[CheckResult]:
    """Heel and toe cantilever flexure from the net (load - base pressure) trapezoid."""
    m_heel, m_toe = slab_design_moments(params, geometry)

    rows = _flexure_and_steel_rows(
        member="heel", label="Heel slab", thickness_mm=geometry.base_thickness_mm,
        moment_knm=m_heel, params=params, wsc=wsc, trail=trail,
    )
    rows += _flexure_and_steel_rows(
        member="toe", label="Toe slab", thickness_mm=geometry.base_thickness_mm,
        moment_knm=m_toe, params=params, wsc=wsc, trail=trail,
    )
    return rows


def _cover_check(params: RetainingWallParams, trail: Trail) -> CheckResult:
    trail.record(
        description="Clear cover to reinforcement, provided",
        formula="cover = clear_cover_mm (user/preset)",
        inputs={"clear_cover_mm": params.clear_cover_mm},
        value=params.clear_cover_mm, unit="mm", citation=CITATION_COVER,
    )
    cover_id = trail.last_id()
    status = "PASS" if params.clear_cover_mm >= MIN_CLEAR_COVER_MM else "FAIL"
    return CheckResult(
        clause=CITATION_COVER,
        requirement="Clear cover: provided cover at least the code minimum (all members)",
        computed=f"cover = {params.clear_cover_mm:g} mm provided",
        limit=f"cover_min = {MIN_CLEAR_COVER_MM:g} mm (moderate exposure)",
        status=status, member="all", kind="cover",
        trail_ref=cover_id, severity_hint=_severity(status),
    )


def _check_assumptions() -> list[Assumption]:
    return [
        Assumption(
            field="effective_depth_bar_allowance",
            value=f"{ASSUMED_BAR_DIA_MM:g} mm bar diameter",
            source="engine_default",
            note=(
                f"Effective depth d = t - clear cover - {ASSUMED_BAR_DIA_MM:g}/2 mm "
                "(assumed main-bar diameter; no rebar detailing at this level)."
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
        Assumption(
            field="cantilever_critical_sections",
            value="stem base / stem-face of heel and toe",
            source="engine_default",
            note=(
                "Stem checked at its base; heel and toe checked as cantilevers at the "
                "faces of the stem, from the net (load - base pressure) distribution."
            ),
        ),
    ]
