"""RCC section-design checks for the slab / T-beam deck (IS 456 working stress).

A family of clause-cited `CheckResult` rows on the governing member (the slab
strip per metre for a solid slab, the critical girder for a T-beam): flexure
(required vs provided effective depth), reinforcement (required vs minimum
steel), shear (applied vs permissible stress), deflection (span/effective-depth
ratio) and clear cover. A member thinner than the flexure-required depth flows
through to a FAIL row (the under-design demo case), graded major by the
proof-check.

Reuses the shared `CheckResult` row shape (`components.base`) so the graph's
check node and calc-sheet composer treat every component alike.
"""

from __future__ import annotations

import math

from pydantic import BaseModel

from components.base import Assumption, CheckResult, coerce
from components.slab_tbeam._engine_common import (
    ASSUMED_BAR_DIA_MM,
    CITATION_COVER,
    CITATION_DEFLECTION,
    CITATION_FLEXURE,
    CITATION_MIN_STEEL,
    CITATION_SHEAR,
    CITATION_SHEAR_MAX,
    CITATION_STEEL,
    MIN_CLEAR_COVER_MM,
    MIN_STEEL_PCT_GROSS,
    SPAN_DEPTH_DEFLECTION_LIMIT,
    Trail,
    permissible_shear_stress,
    working_stress_constants,
)
from components.slab_tbeam.analysis import SlabTbeamAnalysis
from components.slab_tbeam.params import SlabTbeamGeometry, SlabTbeamParams

MEMBER_LABELS = {
    "deck": "Deck slab",
    "girder": "Longitudinal girder",
    "all": "All members",
}


class DeckChecksOutput(BaseModel):
    """Everything `run_deck_checks` returns — rows plus their provenance."""

    checks: list[CheckResult]
    trail: list = []
    assumptions: list[Assumption] = []


def _severity(status: str) -> str:
    return "critical" if status == "FAIL" else "info"


def _member_id(deck_type: str) -> str:
    return "deck" if deck_type == "solid_slab" else "girder"


def _effective_depth(geometry: SlabTbeamGeometry, params: SlabTbeamParams) -> float:
    d = geometry.overall_depth_mm - params.clear_cover_mm - ASSUMED_BAR_DIA_MM / 2.0
    if d <= 0:
        raise ValueError(
            f"deck effective depth is non-positive ({d:g} mm) — overall depth "
            f"{geometry.overall_depth_mm:g} mm cannot accommodate cover "
            f"{params.clear_cover_mm:g} mm"
        )
    return d


def run_deck_checks(
    analysis: SlabTbeamAnalysis,
    geometry: SlabTbeamGeometry,
    params: SlabTbeamParams,
) -> DeckChecksOutput:
    """All RCC section-design checks with a CalcStep trail."""
    analysis = coerce(SlabTbeamAnalysis, analysis)
    geometry = coerce(SlabTbeamGeometry, geometry)
    params = coerce(SlabTbeamParams, params)
    trail = Trail("K")
    wsc = working_stress_constants(params.concrete_grade, params.steel_grade)

    member = _member_id(geometry.deck_type)
    label = MEMBER_LABELS[member]
    d = _effective_depth(geometry, params)
    b = analysis.design_width_mm
    bw = analysis.web_width_mm
    moment = analysis.design_moment_knm
    shear = analysis.design_shear_kn

    checks: list[CheckResult] = []

    # --- flexure ---
    d_req = math.sqrt(moment * 1e6 / (wsc.q_n_mm2 * b)) if moment > 0 else 0.0
    trail.record(
        description=f"{member}: required vs provided effective depth (flexure)",
        formula="d_req = sqrt(M / (Q*b)); d = t - cover - bar/2",
        inputs={"M_knm": round(moment, 2), "Q_n_mm2": round(wsc.q_n_mm2, 4), "b_mm": round(b, 1)},
        value=round(d_req, 1), unit="mm", citation=CITATION_FLEXURE,
    )
    d_id = trail.last_id()
    flexure_status = "PASS" if d_req <= d else "FAIL"
    checks.append(CheckResult(
        clause=CITATION_FLEXURE,
        requirement=f"Flexure (working stress): required effective depth within provided ({label})",
        computed=f"d_req = {d_req:.0f} mm for M = {moment:.1f} kN*m",
        limit=f"d = {d:.0f} mm provided (D = {geometry.overall_depth_mm:g} mm)",
        status=flexure_status, member=member, kind="flexure",
        trail_ref=d_id, severity_hint=_severity(flexure_status),
    ))

    # --- reinforcement (required vs minimum) ---
    as_req = moment * 1e6 / (wsc.sigma_st * wsc.j * d) if moment > 0 else 0.0
    as_min = MIN_STEEL_PCT_GROSS / 100.0 * bw * geometry.overall_depth_mm
    trail.record(
        description=f"{member}: required tensile steel (working stress)",
        formula="As = M / (sigma_st * j * d)",
        inputs={"M_knm": round(moment, 2), "sigma_st": wsc.sigma_st, "j": round(wsc.j, 4), "d_mm": round(d, 1)},
        value=round(as_req, 1), unit="mm^2", citation=CITATION_STEEL,
    )
    as_id = trail.last_id()
    governs = as_min if as_min > as_req else as_req
    checks.append(CheckResult(
        clause=CITATION_MIN_STEEL,
        requirement=f"Reinforcement: required steel vs code minimum ({label})",
        computed=f"As_req = {as_req:.0f} mm^2; governing As = {governs:.0f} mm^2",
        limit=f"As_min = {as_min:.0f} mm^2 ({MIN_STEEL_PCT_GROSS:g}% gross)",
        status="PASS", member=member, kind="min_steel",
        trail_ref=as_id, severity_hint="info",
    ))

    # --- shear ---
    tau_perm, has_stirrups = permissible_shear_stress(params.concrete_grade, geometry.deck_type)
    shear_clause = CITATION_SHEAR_MAX if has_stirrups else CITATION_SHEAR
    tau = shear * 1e3 / (bw * d)  # kN over mm^2 -> N/mm^2
    trail.record(
        description=f"{member}: applied shear stress at the support",
        formula="tau = V / (b_w * d)",
        inputs={"V_kn": round(shear, 2), "b_w_mm": round(bw, 1), "d_mm": round(d, 1)},
        value=round(tau, 4), unit="N/mm^2", citation=shear_clause,
    )
    sh_id = trail.last_id()
    shear_status = "PASS" if tau <= tau_perm else "FAIL"
    if has_stirrups:
        requirement = (
            f"Shear: nominal stress within the maximum permissible (stirrups carry shear "
            f"beyond tau_c) ({label})"
        )
        limit = f"tau_c,max = {tau_perm:.2f} N/mm^2 ({params.concrete_grade.value})"
    else:
        requirement = f"Shear: applied stress within permissible, no shear reinforcement ({label})"
        limit = f"tau_c = {tau_perm:.2f} N/mm^2 ({params.concrete_grade.value})"
    checks.append(CheckResult(
        clause=shear_clause,
        requirement=requirement,
        computed=f"tau = {tau:.3f} N/mm^2 for V = {shear:.1f} kN",
        limit=limit,
        status=shear_status, member=member, kind="shear",
        trail_ref=sh_id, severity_hint=_severity(shear_status),
    ))

    # --- deflection (span / effective-depth) ---
    span_over_d = geometry.span_mm / d
    trail.record(
        description=f"{member}: span / effective-depth ratio (deflection control)",
        formula="span / d",
        inputs={"span_mm": geometry.span_mm, "d_mm": round(d, 1)},
        value=round(span_over_d, 3), unit="-", citation=CITATION_DEFLECTION,
    )
    df_id = trail.last_id()
    defl_status = "PASS" if span_over_d <= SPAN_DEPTH_DEFLECTION_LIMIT else "FAIL"
    checks.append(CheckResult(
        clause=CITATION_DEFLECTION,
        requirement=f"Deflection: span/effective-depth within the deemed-to-satisfy limit ({label})",
        computed=f"span/d = {span_over_d:.1f}",
        limit=f"<= {SPAN_DEPTH_DEFLECTION_LIMIT:g} (simply supported)",
        status=defl_status, member=member, kind="deflection",
        trail_ref=df_id, severity_hint=_severity(defl_status),
    ))

    # --- clear cover ---
    trail.record(
        description="Clear cover to reinforcement, provided",
        formula="cover = clear_cover_mm (user/preset)",
        inputs={"clear_cover_mm": params.clear_cover_mm},
        value=params.clear_cover_mm, unit="mm", citation=CITATION_COVER,
    )
    cover_id = trail.last_id()
    cover_status = "PASS" if params.clear_cover_mm >= MIN_CLEAR_COVER_MM else "FAIL"
    checks.append(CheckResult(
        clause=CITATION_COVER,
        requirement="Clear cover: provided cover at least the code minimum (all members)",
        computed=f"cover = {params.clear_cover_mm:g} mm provided",
        limit=f"cover_min = {MIN_CLEAR_COVER_MM:g} mm (moderate exposure)",
        status=cover_status, member="all", kind="cover",
        trail_ref=cover_id, severity_hint=_severity(cover_status),
    ))

    return DeckChecksOutput(checks=checks, trail=trail.steps, assumptions=_check_assumptions())


def _check_assumptions() -> list[Assumption]:
    return [
        Assumption(
            field="effective_depth_bar_allowance",
            value=f"{ASSUMED_BAR_DIA_MM:g} mm bar diameter",
            source="engine_default",
            note=(
                f"Effective depth d = D - clear cover - {ASSUMED_BAR_DIA_MM:g}/2 mm "
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
            field="critical_section",
            value="midspan flexure / support shear",
            source="engine_default",
            note=(
                "The simply-supported deck is checked for flexure at midspan and shear "
                "at the support; the T-beam flange acts in compression."
            ),
        ),
    ]
