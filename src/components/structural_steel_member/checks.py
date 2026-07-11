"""Strength + connection checks for the fabricated welded-I cantilever member.

Clause-cited `CheckResult` rows (IS 800 working stress / IS 816 fillet welds):

* **Axial** — direct axial stress within the permissible axial compressive stress
  (slenderness-dependent, Merchant-Rankine).
* **Bending** — extreme-fibre stress within the permissible bending stress.
* **Shear** — average web shear stress within the permissible shear stress.
* **Combined** — the axial+bending interaction ratio within 1.0.
* **Weld** — the base fillet-weld-group throat stress within the IS 816 permissible.
* **Slenderness** — KL/r within the compression-member limit (detailing; minor on fail).

A section/weld thinner than the demand flows through to a FAIL row (the under-design
demo case), graded major by the proof-check. Reuses the shared `CheckResult` row
shape so the graph's check node and calc-sheet composer treat every component alike.
"""

from __future__ import annotations

from pydantic import BaseModel

from components.base import Assumption, CheckResult, coerce
from components.structural_steel_member._engine_common import (
    CITATION_AXIAL,
    CITATION_BENDING,
    CITATION_COMBINED,
    CITATION_SHEAR,
    CITATION_SLENDERNESS,
    CITATION_WELD,
    Trail,
)
from components.structural_steel_member.analysis import SteelMemberAnalysis
from components.structural_steel_member.params import (
    SteelMemberGeometry,
    SteelMemberParams,
)

MEMBER_LABELS = {
    "member": "Fabricated member",
    "web": "Web",
    "weld": "Base weld group",
    "all": "All members",
}


class MemberChecksOutput(BaseModel):
    """Everything `run_member_checks` returns — rows plus their provenance."""

    checks: list[CheckResult]
    trail: list = []
    assumptions: list[Assumption] = []


def _severity(status: str) -> str:
    return "critical" if status == "FAIL" else "info"


def run_member_checks(
    analysis: SteelMemberAnalysis,
    geometry: SteelMemberGeometry,
    params: SteelMemberParams,
) -> MemberChecksOutput:
    """All strength + connection checks with a CalcStep trail."""
    analysis = coerce(SteelMemberAnalysis, analysis)
    geometry = coerce(SteelMemberGeometry, geometry)
    params = coerce(SteelMemberParams, params)
    trail = Trail("K")
    checks: list[CheckResult] = []

    # --- axial ---
    trail.record(
        description="Direct axial stress vs permissible (slenderness-dependent)",
        formula="sigma_ac,cal = N / A",
        inputs={
            "N_kn": analysis.design_axial_kn,
            "A_mm2": analysis.section_area_mm2,
            "lambda": analysis.slenderness_ratio,
        },
        value=analysis.max_axial_stress_mpa, unit="N/mm^2", citation=CITATION_AXIAL,
    )
    a_status = "PASS" if analysis.max_axial_stress_mpa <= analysis.permissible_axial_stress_mpa else "FAIL"
    checks.append(CheckResult(
        clause=CITATION_AXIAL,
        requirement="Axial: direct compressive stress within the permissible axial stress",
        computed=f"sigma_ac = {analysis.max_axial_stress_mpa:.1f} N/mm^2 for N = {analysis.design_axial_kn:.1f} kN (lambda {analysis.slenderness_ratio:.0f})",
        limit=f"sigma_ac = {analysis.permissible_axial_stress_mpa:.1f} N/mm^2 ({params.steel_grade})",
        status=a_status, member="member", kind="axial",
        trail_ref=trail.last_id(), severity_hint=_severity(a_status),
    ))

    # --- bending ---
    trail.record(
        description="Extreme-fibre bending stress vs permissible",
        formula="sigma_bc,cal = M / Z",
        inputs={
            "M_knm": analysis.design_moment_knm,
            "Z_cm3": analysis.section_modulus_cm3,
        },
        value=analysis.max_bending_stress_mpa, unit="N/mm^2", citation=CITATION_BENDING,
    )
    b_status = "PASS" if analysis.max_bending_stress_mpa <= analysis.permissible_bending_stress_mpa else "FAIL"
    checks.append(CheckResult(
        clause=CITATION_BENDING,
        requirement="Bending: extreme-fibre stress within the permissible bending stress",
        computed=f"sigma_bc = {analysis.max_bending_stress_mpa:.1f} N/mm^2 for M = {analysis.design_moment_knm:.1f} kN*m",
        limit=f"sigma_bc = {analysis.permissible_bending_stress_mpa:g} N/mm^2 ({params.steel_grade})",
        status=b_status, member="member", kind="bending",
        trail_ref=trail.last_id(), severity_hint=_severity(b_status),
    ))

    # --- shear ---
    trail.record(
        description="Average web shear stress vs permissible",
        formula="tau = V / (d_web * t_web)",
        inputs={
            "V_kn": analysis.design_shear_kn,
            "d_web_mm": geometry.web_depth_mm,
            "t_web_mm": geometry.web_thickness_mm,
        },
        value=analysis.max_shear_stress_mpa, unit="N/mm^2", citation=CITATION_SHEAR,
    )
    s_status = "PASS" if analysis.max_shear_stress_mpa <= analysis.permissible_shear_stress_mpa else "FAIL"
    checks.append(CheckResult(
        clause=CITATION_SHEAR,
        requirement="Shear: average web stress within the permissible shear stress",
        computed=f"tau = {analysis.max_shear_stress_mpa:.1f} N/mm^2 for V = {analysis.design_shear_kn:.1f} kN",
        limit=f"tau_va = {analysis.permissible_shear_stress_mpa:g} N/mm^2 ({params.steel_grade})",
        status=s_status, member="web", kind="shear",
        trail_ref=trail.last_id(), severity_hint=_severity(s_status),
    ))

    # --- combined interaction ---
    trail.record(
        description="Combined axial + bending interaction vs 1.0",
        formula="r = sigma_ac,cal/sigma_ac + sigma_bc,cal/sigma_bc",
        inputs={
            "axial_ratio": round(analysis.max_axial_stress_mpa / analysis.permissible_axial_stress_mpa, 4),
            "bending_ratio": round(analysis.max_bending_stress_mpa / analysis.permissible_bending_stress_mpa, 4),
        },
        value=analysis.combined_ratio, unit="-", citation=CITATION_COMBINED,
    )
    c_status = "PASS" if analysis.combined_ratio <= analysis.combined_limit else "FAIL"
    checks.append(CheckResult(
        clause=CITATION_COMBINED,
        requirement="Combined: axial + bending interaction ratio within 1.0",
        computed=f"interaction = {analysis.combined_ratio:.2f}",
        limit=f"<= {analysis.combined_limit:g}",
        status=c_status, member="member", kind="combined",
        trail_ref=trail.last_id(), severity_hint=_severity(c_status),
    ))

    # --- weld ---
    trail.record(
        description="Base fillet-weld throat stress vs permissible",
        formula="f_r = sqrt((N/A_w + M/Z_w)^2 + (V/A_w)^2)",
        inputs={
            "weld_size_mm": geometry.weld_size_mm,
            "throat_mm": analysis.weld_throat_mm,
        },
        value=analysis.weld_stress_mpa, unit="N/mm^2", citation=CITATION_WELD,
    )
    w_status = "PASS" if analysis.weld_stress_mpa <= analysis.permissible_weld_stress_mpa else "FAIL"
    checks.append(CheckResult(
        clause=CITATION_WELD,
        requirement="Weld: base fillet-weld-group throat stress within the permissible weld stress",
        computed=f"f_r = {analysis.weld_stress_mpa:.1f} N/mm^2 for a {geometry.weld_size_mm:g} mm fillet",
        limit=f"q_perm = {analysis.permissible_weld_stress_mpa:g} N/mm^2 (IS 816)",
        status=w_status, member="weld", kind="weld",
        trail_ref=trail.last_id(), severity_hint=_severity(w_status),
    ))

    # --- slenderness (detailing; minor on fail) ---
    trail.record(
        description="Compression-member slenderness vs limit",
        formula="lambda = K * L / r_min",
        inputs={
            "lambda": analysis.slenderness_ratio,
            "limit": analysis.slenderness_limit,
        },
        value=analysis.slenderness_ratio, unit="-", citation=CITATION_SLENDERNESS,
    )
    sl_status = "PASS" if analysis.slenderness_ratio <= analysis.slenderness_limit else "FAIL"
    checks.append(CheckResult(
        clause=CITATION_SLENDERNESS,
        requirement="Slenderness: KL/r within the compression-member limit",
        computed=f"KL/r = {analysis.slenderness_ratio:.1f}",
        limit=f"<= {analysis.slenderness_limit:g}",
        status=sl_status, member="member", kind="slenderness",
        trail_ref=trail.last_id(), severity_hint=_severity(sl_status),
    ))

    return MemberChecksOutput(checks=checks, trail=trail.steps, assumptions=_check_assumptions())


def _check_assumptions() -> list[Assumption]:
    return [
        Assumption(
            field="section_class",
            value="doubly-symmetric welded I",
            source="engine_default",
            note=(
                "Member treated as a doubly-symmetric welded I-section; elastic "
                "(working-stress) section modulus used for bending, average web shear, "
                "and the gross area for direct axial stress."
            ),
        ),
        Assumption(
            field="connection_model",
            value="base fillet-weld group",
            source="engine_default",
            note=(
                "The end connection is idealised as a fillet-weld group along both "
                "flanges and both web faces at the base, carrying the moment as a weld "
                "bending stress plus direct axial and shear — a single-throat line model."
            ),
        ),
    ]
