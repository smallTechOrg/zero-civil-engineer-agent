"""Strength + serviceability checks for the welded steel plate girder.

Clause-cited `CheckResult` rows (IRS Steel Bridge Code / IS 800 working stress):

* **Bending** — extreme-fibre stress within the permissible bending stress.
* **Shear** — average web shear stress within the permissible shear stress.
* **Deflection** — live-load deflection within span/600.
* **Web slenderness** — web depth/thickness within the stiffened-web limit.
* **Fatigue** — an OBSERVATION note: a full welded-detail fatigue check is flagged
  as beyond this POC scope.

A flange/web thinner than the demand flows through to a FAIL row (the under-design
demo case), graded major by the proof-check. Reuses the shared `CheckResult` row
shape so the graph's check node and calc-sheet composer treat every component alike.
"""

from __future__ import annotations

from pydantic import BaseModel

from components.base import Assumption, CheckResult, coerce
from components.plate_girder._engine_common import (
    CITATION_BENDING,
    CITATION_DEFLECTION,
    CITATION_FATIGUE,
    CITATION_SHEAR,
    CITATION_SLENDERNESS,
    Trail,
)
from components.plate_girder.analysis import PlateGirderAnalysis
from components.plate_girder.params import PlateGirderGeometry, PlateGirderParams

MEMBER_LABELS = {
    "girder": "Plate girder",
    "web": "Web",
    "flange": "Flange",
    "all": "All members",
}


class GirderChecksOutput(BaseModel):
    """Everything `run_girder_checks` returns — rows plus their provenance."""

    checks: list[CheckResult]
    trail: list = []
    assumptions: list[Assumption] = []


def _severity(status: str) -> str:
    return "critical" if status == "FAIL" else "info"


def run_girder_checks(
    analysis: PlateGirderAnalysis,
    geometry: PlateGirderGeometry,
    params: PlateGirderParams,
) -> GirderChecksOutput:
    """All strength + serviceability checks with a CalcStep trail."""
    analysis = coerce(PlateGirderAnalysis, analysis)
    geometry = coerce(PlateGirderGeometry, geometry)
    params = coerce(PlateGirderParams, params)
    trail = Trail("K")
    checks: list[CheckResult] = []

    # --- bending ---
    trail.record(
        description="Extreme-fibre bending stress vs permissible",
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
        status=b_status, member="girder", kind="bending",
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

    # --- deflection ---
    trail.record(
        description="Live-load deflection vs span/600 limit",
        formula="delta = 5 w L^4 / (384 E I); limit = L/600",
        inputs={
            "delta_mm": analysis.max_deflection_mm,
            "limit_mm": analysis.deflection_limit_mm,
        },
        value=analysis.max_deflection_mm, unit="mm", citation=CITATION_DEFLECTION,
    )
    d_status = "PASS" if analysis.max_deflection_mm <= analysis.deflection_limit_mm else "FAIL"
    checks.append(CheckResult(
        clause=CITATION_DEFLECTION,
        requirement="Deflection: live-load deflection within span/600",
        computed=f"delta = {analysis.max_deflection_mm:.2f} mm",
        limit=f"span/600 = {analysis.deflection_limit_mm:.2f} mm",
        status=d_status, member="girder", kind="deflection",
        trail_ref=trail.last_id(), severity_hint=_severity(d_status),
    ))

    # --- web slenderness ---
    trail.record(
        description="Web slenderness d/t vs stiffened-web limit",
        formula="lambda_w = d_web / t_web",
        inputs={
            "d_web_mm": geometry.web_depth_mm,
            "t_web_mm": geometry.web_thickness_mm,
            "stiffener_spacing_mm": geometry.stiffener_spacing_mm,
        },
        value=analysis.web_slenderness, unit="-", citation=CITATION_SLENDERNESS,
    )
    sl_status = "PASS" if analysis.web_slenderness <= analysis.web_slenderness_limit else "FAIL"
    checks.append(CheckResult(
        clause=CITATION_SLENDERNESS,
        requirement="Web slenderness: depth/thickness within the stiffened-web limit",
        computed=f"d/t = {analysis.web_slenderness:.1f} (stiffeners at {geometry.stiffener_spacing_mm:g} mm)",
        limit=f"d/t <= {analysis.web_slenderness_limit:g}",
        status=sl_status, member="web", kind="web_slenderness",
        trail_ref=trail.last_id(), severity_hint=_severity(sl_status),
    ))

    # --- fatigue (observation note) ---
    trail.record(
        description="Fatigue of welded details — flagged for a full assessment",
        formula="stress range vs S-N detail category (not evaluated at this level)",
        inputs={"design_moment_knm": analysis.design_moment_knm},
        value=analysis.max_bending_stress_mpa, unit="N/mm^2", citation=CITATION_FATIGUE,
    )
    checks.append(CheckResult(
        clause=CITATION_FATIGUE,
        requirement="Fatigue: welded flange/web and stiffener details require an S-N check",
        computed="fatigue not evaluated — flagged for a full welded-detail assessment",
        limit="stress range within the detail-category endurance",
        status="PASS", member="girder", kind="fatigue",
        trail_ref=trail.last_id(), severity_hint="info",
    ))

    return GirderChecksOutput(checks=checks, trail=trail.steps, assumptions=_check_assumptions())


def _check_assumptions() -> list[Assumption]:
    return [
        Assumption(
            field="section_class",
            value="doubly-symmetric welded I",
            source="engine_default",
            note=(
                "Girder treated as a doubly-symmetric welded I-section; elastic "
                "(working-stress) section modulus used for bending; average web shear."
            ),
        ),
        Assumption(
            field="fatigue_scope",
            value="flagged",
            source="engine_default",
            note=(
                "A full fatigue assessment of the welded flange/web and stiffener "
                "details (stress range vs S-N detail category) is beyond this POC scope "
                "and is graded an observation."
            ),
        ),
    ]
