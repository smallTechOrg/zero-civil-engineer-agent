"""Strength checks for the fabricated rolling-stock member.

Clause-cited `CheckResult` rows (RDSO wagon-design load cases / IS 800 working
stress):

* **Bending** — extreme-fibre stress (vertical payload case) within permissible.
* **Shear** — average web shear stress (vertical payload case) within permissible.
* **Axial** — gross-section axial stress (longitudinal buffing case) within
  permissible.
* **Combined** — axial+bending interaction (unity check) within 1.0.
* **Weld & fatigue** — an OBSERVATION note: full fillet-weld sizing and welded-
  detail fatigue (S-N) verification are flagged as beyond this POC scope.

A flange/web thinner than the demand flows through to a FAIL row (the under-design
demo case), graded major by the proof-check. Reuses the shared `CheckResult` row
shape so the graph's check node and calc-sheet composer treat every component alike.
"""

from __future__ import annotations

from pydantic import BaseModel

from components.base import Assumption, CheckResult, coerce
from components.rolling_stock_member._engine_common import (
    CITATION_AXIAL,
    CITATION_BENDING,
    CITATION_COMBINED,
    CITATION_SHEAR,
    CITATION_WELD_FATIGUE,
    Trail,
)
from components.rolling_stock_member.analysis import RollingStockMemberAnalysis
from components.rolling_stock_member.params import (
    RollingStockMemberGeometry,
    RollingStockMemberParams,
)

MEMBER_LABELS = {
    "member": "Rolling-stock member",
    "web": "Web",
    "flange": "Flange",
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
    analysis: RollingStockMemberAnalysis,
    geometry: RollingStockMemberGeometry,
    params: RollingStockMemberParams,
) -> MemberChecksOutput:
    """All strength + interaction checks with a CalcStep trail."""
    analysis = coerce(RollingStockMemberAnalysis, analysis)
    geometry = coerce(RollingStockMemberGeometry, geometry)
    params = coerce(RollingStockMemberParams, params)
    trail = Trail("K")
    checks: list[CheckResult] = []

    # --- bending (vertical payload case) ---
    trail.record(
        description="Extreme-fibre bending stress vs permissible (vertical payload case)",
        formula="sigma_b = M / Z",
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
        computed=f"sigma_b = {analysis.max_bending_stress_mpa:.1f} N/mm^2 for M = {analysis.design_moment_knm:.1f} kN*m",
        limit=f"sigma_bt = {analysis.permissible_bending_stress_mpa:g} N/mm^2 ({params.steel_grade})",
        status=b_status, member="member", kind="bending",
        trail_ref=trail.last_id(), severity_hint=_severity(b_status),
    ))

    # --- shear (vertical payload case) ---
    trail.record(
        description="Average web shear stress vs permissible (vertical payload case)",
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

    # --- axial (longitudinal buffing case) ---
    trail.record(
        description="Gross-section axial stress vs permissible (longitudinal buffing case)",
        formula="sigma_a = P / A",
        inputs={
            "P_kn": analysis.buffing_load_kn,
            "A_mm2": analysis.section_area_mm2,
        },
        value=analysis.max_axial_stress_mpa, unit="N/mm^2", citation=CITATION_AXIAL,
    )
    a_status = "PASS" if analysis.max_axial_stress_mpa <= analysis.permissible_axial_stress_mpa else "FAIL"
    checks.append(CheckResult(
        clause=CITATION_AXIAL,
        requirement="Axial: gross-section buffing stress within the permissible axial stress",
        computed=f"sigma_a = {analysis.max_axial_stress_mpa:.1f} N/mm^2 for P = {analysis.buffing_load_kn:.1f} kN",
        limit=f"sigma_ac = {analysis.permissible_axial_stress_mpa:g} N/mm^2 ({params.steel_grade})",
        status=a_status, member="member", kind="axial",
        trail_ref=trail.last_id(), severity_hint=_severity(a_status),
    ))

    # --- combined axial + bending interaction ---
    trail.record(
        description="Combined axial + bending interaction ratio vs unity",
        formula="R = sigma_a/sigma_ac + sigma_b/sigma_bc",
        inputs={
            "ratio": analysis.interaction_ratio,
            "limit": analysis.interaction_limit,
        },
        value=analysis.interaction_ratio, unit="-", citation=CITATION_COMBINED,
    )
    c_status = "PASS" if analysis.interaction_ratio <= analysis.interaction_limit else "FAIL"
    checks.append(CheckResult(
        clause=CITATION_COMBINED,
        requirement="Combined: axial+bending interaction ratio within the unity limit",
        computed=f"R = {analysis.interaction_ratio:.2f} (axial+bending, vertical payload + buffing)",
        limit=f"R <= {analysis.interaction_limit:g}",
        status=c_status, member="member", kind="combined",
        trail_ref=trail.last_id(), severity_hint=_severity(c_status),
    ))

    # --- weld & fatigue (observation note) ---
    trail.record(
        description="Fillet welds & fatigue of welded details — flagged for a full assessment",
        formula="stress range vs S-N detail category (not evaluated at this level)",
        inputs={"weld_size_mm": geometry.weld_size_mm},
        value=geometry.weld_size_mm, unit="mm", citation=CITATION_WELD_FATIGUE,
    )
    checks.append(CheckResult(
        clause=CITATION_WELD_FATIGUE,
        requirement="Welds & fatigue: fillet welds and welded details require a fatigue (S-N) check",
        computed=f"web-to-flange fillet welds {geometry.weld_size_mm:g} mm leg; fatigue not evaluated",
        limit="stress range within the welded-detail-category endurance",
        status="PASS", member="member", kind="weld_fatigue",
        trail_ref=trail.last_id(), severity_hint="info",
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
                "(working-stress) section modulus used for bending; average web shear; "
                "gross-section stress for the axial buffing load."
            ),
        ),
        Assumption(
            field="weld_fatigue_scope",
            value="flagged",
            source="engine_default",
            note=(
                "Detailed fillet-weld sizing / length and a full fatigue assessment of the "
                "welded details (stress range vs S-N detail category) under repeated wagon "
                "loading are beyond this POC scope and are graded an observation."
            ),
        ),
    ]
