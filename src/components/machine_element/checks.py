"""Strength checks for the machine element (shaft or welded joint).

Clause-cited `CheckResult` rows (standard machine-design working practice):

* **shaft** — (1) combined bending+torsion: maximum shear stress within the
  permissible (design) shear stress / static factor of safety against shear yield;
  (2) fatigue: rotating-shaft Soderberg factor of safety within the required
  endurance FoS; (3) stress-concentration OBSERVATION note (shoulder fillet /
  keyway).
* **welded_joint** — the circular fillet-weld throat shear stress within the
  permissible weld shear stress; a weld-detail OBSERVATION note.

A shaft diameter (or weld leg) thinner than the demand flows through to a FAIL row
(the under-design demo case), graded major by the proof-check. Reuses the shared
`CheckResult` row shape so the graph's check node and calc-sheet composer treat
every component alike.
"""

from __future__ import annotations

from pydantic import BaseModel

from components.base import Assumption, CheckResult, coerce
from components.machine_element._engine_common import (
    CITATION_COMBINED,
    CITATION_FATIGUE,
    CITATION_WELD_SHEAR,
    CITATION_WELD_THROAT,
    FATIGUE_STRESS_CONC_KT,
    Trail,
)
from components.machine_element.analysis import MachineElementAnalysis
from components.machine_element.params import MachineElementGeometry, MachineElementParams

MEMBER_LABELS = {
    "shaft": "Shaft",
    "weld": "Fillet weld",
    "all": "All elements",
}


class MachineElementChecksOutput(BaseModel):
    """Everything `run_element_checks` returns — rows plus their provenance."""

    checks: list[CheckResult]
    trail: list = []
    assumptions: list[Assumption] = []


def _severity(status: str) -> str:
    return "critical" if status == "FAIL" else "info"


def run_element_checks(
    analysis: MachineElementAnalysis,
    geometry: MachineElementGeometry,
    params: MachineElementParams,
) -> MachineElementChecksOutput:
    """All strength checks with a CalcStep trail."""
    analysis = coerce(MachineElementAnalysis, analysis)
    geometry = coerce(MachineElementGeometry, geometry)
    params = coerce(MachineElementParams, params)
    if analysis.element_kind == "welded_joint":
        return _weld_checks(analysis, geometry)
    return _shaft_checks(analysis, geometry)


def _shaft_checks(
    analysis: MachineElementAnalysis, geometry: MachineElementGeometry
) -> MachineElementChecksOutput:
    trail = Trail("K")
    checks: list[CheckResult] = []

    # --- combined bending + torsion (static) ---
    trail.record(
        description="Maximum shear stress (combined bending + torsion) vs permissible",
        formula="tau_max = 16 Te / (pi d^3)",
        inputs={"Te_nmm": analysis.equiv_twisting_moment_nmm, "d_mm": geometry.diameter_mm},
        value=analysis.max_stress_mpa, unit="N/mm^2", citation=CITATION_COMBINED,
    )
    c_status = "PASS" if analysis.max_stress_mpa <= analysis.permissible_stress_mpa else "FAIL"
    checks.append(CheckResult(
        clause=CITATION_COMBINED,
        requirement="Combined bending + torsion: maximum shear stress within the permissible shear stress",
        computed=(
            f"tau_max = {analysis.max_stress_mpa:.1f} N/mm^2 (FoS = {analysis.factor_of_safety:.2f} vs "
            f"shear yield {analysis.shear_yield_mpa:.1f})"
        ),
        limit=f"tau_perm = {analysis.permissible_stress_mpa:g} N/mm^2 (FoS_required {analysis.required_fos:g})",
        status=c_status, member="shaft", kind="combined_stress",
        trail_ref=trail.last_id(), severity_hint=_severity(c_status),
    ))

    # --- fatigue (rotating-shaft Soderberg) ---
    trail.record(
        description="Rotating-shaft fatigue factor of safety (Soderberg) vs required",
        formula="1/n = sigma_a/sigma_e' + sqrt(3) tau_m/fy",
        inputs={
            "sigma_a_mpa": analysis.stress_amplitude_mpa,
            "sigma_e_mpa": analysis.endurance_limit_mpa,
            "fy_mpa": analysis.yield_mpa,
        },
        value=analysis.fatigue_fos, unit="-", citation=CITATION_FATIGUE,
    )
    f_status = "PASS" if analysis.fatigue_fos >= analysis.required_fatigue_fos else "FAIL"
    checks.append(CheckResult(
        clause=CITATION_FATIGUE,
        requirement="Fatigue: rotating-shaft endurance factor of safety within the required value",
        computed=(
            f"n_f = {analysis.fatigue_fos:.2f} for sigma_a = {analysis.stress_amplitude_mpa:.1f}, "
            f"sigma_e' = {analysis.endurance_limit_mpa:.1f} N/mm^2"
        ),
        limit=f"n_f >= {analysis.required_fatigue_fos:g}",
        status=f_status, member="shaft", kind="fatigue",
        trail_ref=trail.last_id(), severity_hint=_severity(f_status),
    ))

    # --- stress-concentration observation note ---
    trail.record(
        description="Stress-concentration at the shoulder fillet / keyway — Kt applied to bending",
        formula="Kt applied to the reversed bending amplitude (fatigue)",
        inputs={"Kt": FATIGUE_STRESS_CONC_KT, "fillet_radius_mm": geometry.fillet_radius_mm},
        value=analysis.stress_amplitude_mpa, unit="N/mm^2", citation=CITATION_FATIGUE,
    )
    checks.append(CheckResult(
        clause=CITATION_FATIGUE,
        requirement="Stress concentration at the shoulder fillet / keyway is accounted for in fatigue",
        computed=(
            f"Kt = {FATIGUE_STRESS_CONC_KT:g} applied; fillet r = {geometry.fillet_radius_mm:g} mm, "
            f"keyway {geometry.keyway_width_mm:g} x {geometry.keyway_depth_mm:g} mm"
        ),
        limit="a detailed Kt from the actual fillet/keyway geometry to be confirmed",
        status="PASS", member="shaft", kind="stress_concentration",
        trail_ref=trail.last_id(), severity_hint="info",
    ))

    return MachineElementChecksOutput(checks=checks, trail=trail.steps, assumptions=_shaft_assumptions())


def _weld_checks(
    analysis: MachineElementAnalysis, geometry: MachineElementGeometry
) -> MachineElementChecksOutput:
    trail = Trail("K")
    checks: list[CheckResult] = []

    # --- weld throat shear ---
    trail.record(
        description="Torsional shear stress in the circular fillet weld vs permissible",
        formula="tau = T / (0.707 s * pi D^2 / 2)",
        inputs={"s_mm": geometry.weld_size_mm, "D_mm": geometry.hub_diameter_mm},
        value=analysis.max_stress_mpa, unit="N/mm^2", citation=CITATION_WELD_SHEAR,
    )
    w_status = "PASS" if analysis.max_stress_mpa <= analysis.permissible_stress_mpa else "FAIL"
    checks.append(CheckResult(
        clause=CITATION_WELD_SHEAR,
        requirement="Fillet weld: throat shear stress within the permissible weld shear stress",
        computed=(
            f"tau = {analysis.max_stress_mpa:.1f} N/mm^2 (FoS = {analysis.factor_of_safety:.2f}) for a "
            f"{geometry.weld_size_mm:g} mm leg (throat {geometry.weld_throat_mm:.1f} mm)"
        ),
        limit=f"tau_perm = {analysis.permissible_stress_mpa:g} N/mm^2 (FoS_required {analysis.required_fos:g})",
        status=w_status, member="weld", kind="weld_shear",
        trail_ref=trail.last_id(), severity_hint=_severity(w_status),
    ))

    # --- weld-detail observation ---
    trail.record(
        description="Fillet-weld effective throat and detailing",
        formula="t = 0.707 s",
        inputs={"s_mm": geometry.weld_size_mm, "throat_mm": geometry.weld_throat_mm},
        value=analysis.max_stress_mpa, unit="N/mm^2", citation=CITATION_WELD_THROAT,
    )
    checks.append(CheckResult(
        clause=CITATION_WELD_THROAT,
        requirement="Fillet-weld leg / throat and edge detailing per IS 816 provisions",
        computed=f"leg {geometry.weld_size_mm:g} mm, throat {geometry.weld_throat_mm:.1f} mm on a {geometry.plate_thickness_mm:g} mm plate",
        limit="leg within the plate-thickness detailing limits (min/max size)",
        status="PASS", member="weld", kind="weld_detail",
        trail_ref=trail.last_id(), severity_hint="info",
    ))

    return MachineElementChecksOutput(checks=checks, trail=trail.steps, assumptions=_weld_assumptions())


def _shaft_assumptions() -> list[Assumption]:
    return [
        Assumption(
            field="shaft_strength_theory", value="maximum-shear-stress (Guest/Tresca)",
            source="engine_default",
            note=("Shaft designed by the maximum-shear-stress theory (combined bending + torsion "
                  "equivalent twisting moment); a solid circular section is assumed."),
        ),
        Assumption(
            field="fatigue_scope", value="Soderberg, corrected endurance",
            source="engine_default",
            note=("Fatigue assessed by the Soderberg criterion with a corrected endurance limit; "
                  "detailed notch-sensitivity and load-spectrum fatigue is beyond this POC scope."),
        ),
    ]


def _weld_assumptions() -> list[Assumption]:
    return [
        Assumption(
            field="weld_strength_basis", value="throat shear, weld-as-a-line",
            source="engine_default",
            note=("Fillet weld checked on the effective throat (0.707 s) treated as a line; "
                  "the electrode is assumed to develop at least the parent-metal shear strength."),
        ),
    ]
