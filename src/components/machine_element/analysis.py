"""Strength analysis of the machine element (shaft or welded joint).

Given `MachineElementParams` and a proportioned `MachineElementGeometry`,
computes the governing stress and the factor of safety:

* **shaft** — torque from the transmitted power, the overhung bending moment from
  the mounted gear/pulley, the equivalent twisting moment (combined bending +
  torsion by the maximum-shear-stress theory), the maximum shear stress, the
  static factor of safety against shear yield, AND the rotating-shaft fatigue
  (Soderberg) factor of safety with a corrected endurance limit.
* **welded_joint** — the same torque carried by a circular fillet weld group in
  torsion; the throat shear stress and its factor of safety.

`compute_core` is the pure numeric core (reused by the sizing loop);
`analyse_element` wraps it with the CalcStep trail and Assumptions and returns the
`MachineElementAnalysis` model the calc sheet, checks and proof-check consume.
"""

from __future__ import annotations

import math
from typing import NamedTuple

from pydantic import BaseModel, Field

from components.base import Assumption, coerce
from components.machine_element._engine_common import (
    CITATION_BENDING,
    CITATION_COMBINED,
    CITATION_FATIGUE,
    CITATION_MATERIAL,
    CITATION_PERMISSIBLE,
    CITATION_TORQUE,
    CITATION_WELD_SHEAR,
    CITATION_WELD_THROAT,
    FATIGUE_STRESS_CONC_KT,
    REQUIRED_FATIGUE_FOS,
    TRANSVERSE_LOAD_FACTOR,
    bending_stress_mpa,
    circular_weld_shear_mpa,
    corrected_endurance_mpa,
    equivalent_twisting_moment_nmm,
    fatigue_factor_of_safety,
    material,
    permissible_shear_mpa,
    shaft_shear_stress_mpa,
    shear_yield_mpa,
    tangential_force_n,
    torque_nmm,
    weld_throat_mm,
)
from components.machine_element.params import MachineElementGeometry, MachineElementParams


class MachineElementAnalysis(BaseModel):
    """Strength analysis of one machine element — the rehydratable model.

    Field names are normative (calc sheet, checks, proof-check and summary read them).
    """

    element_kind: str = Field(description="'shaft' | 'welded_joint'")

    # --- material ---
    yield_mpa: float = Field(description="Tensile yield strength, N/mm^2")
    ultimate_mpa: float = Field(description="Ultimate tensile strength, N/mm^2")
    shear_yield_mpa: float = Field(description="Shear yield stress 0.5 fy, N/mm^2")
    required_fos: float = Field(description="Design factor of safety against shear yield")

    # --- driving actions ---
    torque_nmm: float = Field(description="Transmitted torque, N.mm")
    tangential_force_n: float = Field(description="Tangential force at the pitch radius, N (shaft)")
    transverse_load_n: float = Field(description="Net transverse (bending) load on the overhang, N (shaft)")
    bending_moment_nmm: float = Field(description="Overhung bending moment, N.mm (shaft)")
    equiv_twisting_moment_nmm: float = Field(description="Equivalent twisting moment Te, N.mm (shaft)")

    # --- governing static strength (pinned summary source) ---
    max_stress_mpa: float = Field(description="Governing (shear) stress, N/mm^2")
    permissible_stress_mpa: float = Field(description="Permissible (design) shear stress = tau_y/FoS, N/mm^2")
    factor_of_safety: float = Field(description="Actual factor of safety = shear yield / max stress")

    # --- fatigue (shaft only) ---
    fatigue_applicable: bool = Field(default=False, description="True for a rotating shaft")
    stress_amplitude_mpa: float = Field(default=0.0, description="Reversed-bending stress amplitude Kt*sigma_a, N/mm^2")
    endurance_limit_mpa: float = Field(default=0.0, description="Corrected endurance limit sigma_e', N/mm^2")
    fatigue_fos: float = Field(default=0.0, description="Soderberg fatigue factor of safety")
    required_fatigue_fos: float = Field(default=REQUIRED_FATIGUE_FOS, description="Required fatigue FoS")

    # --- geometry echo (for checks / drawing consistency) ---
    diameter_mm: float = Field(default=0.0, description="Governing shaft diameter, mm (shaft)")
    hub_diameter_mm: float = Field(default=0.0, description="Welded hub diameter, mm (weld)")
    weld_size_mm: float = Field(default=0.0, description="Fillet-weld leg size, mm (weld)")
    weld_throat_mm: float = Field(default=0.0, description="Fillet-weld throat, mm (weld)")

    assumptions: list[Assumption] = Field(default_factory=list)
    trail: list = Field(default_factory=list, description="CalcStep trail")


class ForceCore(NamedTuple):
    """The pure numeric analysis result (no trail) — shared by sizing + analyse."""

    element_kind: str
    yield_mpa: float
    ultimate_mpa: float
    shear_yield_mpa: float
    required_fos: float
    torque_nmm: float
    tangential_force_n: float
    transverse_load_n: float
    bending_moment_nmm: float
    equiv_twisting_moment_nmm: float
    max_stress_mpa: float
    permissible_stress_mpa: float
    factor_of_safety: float
    fatigue_applicable: bool
    stress_amplitude_mpa: float
    endurance_limit_mpa: float
    fatigue_fos: float
    required_fatigue_fos: float
    diameter_mm: float
    hub_diameter_mm: float
    weld_size_mm: float
    weld_throat_mm: float


def compute_core(params: MachineElementParams, geometry: MachineElementGeometry) -> ForceCore:
    """Deterministic torque, stresses and factor(s) of safety for the element."""
    mat = material(params.material_grade)
    tau_y = shear_yield_mpa(mat.yield_mpa)
    perm = permissible_shear_mpa(mat.yield_mpa, params.required_factor_of_safety)
    torque = torque_nmm(params.power_kw, params.speed_rpm)

    if geometry.element_kind == "welded_joint":
        d_hub = geometry.hub_diameter_mm
        size = geometry.weld_size_mm
        tau_weld = circular_weld_shear_mpa(torque, d_hub, size)
        fos = tau_y / tau_weld if tau_weld > 0 else float("inf")
        return ForceCore(
            element_kind="welded_joint",
            yield_mpa=mat.yield_mpa, ultimate_mpa=mat.ultimate_mpa, shear_yield_mpa=tau_y,
            required_fos=params.required_factor_of_safety,
            torque_nmm=torque, tangential_force_n=0.0, transverse_load_n=0.0,
            bending_moment_nmm=0.0, equiv_twisting_moment_nmm=torque,
            max_stress_mpa=tau_weld, permissible_stress_mpa=perm, factor_of_safety=fos,
            fatigue_applicable=False, stress_amplitude_mpa=0.0, endurance_limit_mpa=0.0,
            fatigue_fos=0.0, required_fatigue_fos=REQUIRED_FATIGUE_FOS,
            diameter_mm=0.0, hub_diameter_mm=d_hub, weld_size_mm=size,
            weld_throat_mm=weld_throat_mm(size),
        )

    # --- shaft ---
    d = geometry.diameter_mm
    f_t = tangential_force_n(torque, params.mounting_pcd_mm)
    w = TRANSVERSE_LOAD_FACTOR * f_t
    moment = w * params.overhang_mm
    te = equivalent_twisting_moment_nmm(
        params.bending_shock_factor, moment, params.torsion_shock_factor, torque
    )
    tau_max = shaft_shear_stress_mpa(te, d)
    fos = tau_y / tau_max if tau_max > 0 else float("inf")

    endurance = corrected_endurance_mpa(mat.ultimate_mpa)
    sigma_a = FATIGUE_STRESS_CONC_KT * bending_stress_mpa(moment, d)
    n_f = fatigue_factor_of_safety(
        moment_nmm=moment, torque_value_nmm=torque, diameter_mm=d,
        endurance_mpa=endurance, yield_mpa=mat.yield_mpa,
    )
    return ForceCore(
        element_kind="shaft",
        yield_mpa=mat.yield_mpa, ultimate_mpa=mat.ultimate_mpa, shear_yield_mpa=tau_y,
        required_fos=params.required_factor_of_safety,
        torque_nmm=torque, tangential_force_n=f_t, transverse_load_n=w,
        bending_moment_nmm=moment, equiv_twisting_moment_nmm=te,
        max_stress_mpa=tau_max, permissible_stress_mpa=perm, factor_of_safety=fos,
        fatigue_applicable=True, stress_amplitude_mpa=sigma_a, endurance_limit_mpa=endurance,
        fatigue_fos=n_f, required_fatigue_fos=REQUIRED_FATIGUE_FOS,
        diameter_mm=d, hub_diameter_mm=0.0, weld_size_mm=0.0, weld_throat_mm=0.0,
    )


def analyse_element(
    params: MachineElementParams, geometry: MachineElementGeometry
) -> MachineElementAnalysis:
    """Full analysis with the CalcStep trail + modelling assumptions."""
    from components.machine_element._engine_common import Trail

    params = coerce(MachineElementParams, params)
    geometry = coerce(MachineElementGeometry, geometry)
    core = compute_core(params, geometry)
    trail = Trail("A")

    trail.record(
        description="Transmitted torque from power and speed",
        formula="T = 9550 * P[kW] / N[rpm]  (N.mm)",
        inputs={"power_kw": params.power_kw, "speed_rpm": params.speed_rpm},
        value=round(core.torque_nmm, 1), unit="N.mm", citation=CITATION_TORQUE,
    )
    trail.record(
        description="Material strengths (yield / ultimate / shear yield)",
        formula="tau_y = 0.5 * fy (maximum-shear-stress theory)",
        inputs={"grade": params.material_grade, "fy_mpa": core.yield_mpa, "fu_mpa": core.ultimate_mpa},
        value=round(core.shear_yield_mpa, 2), unit="N/mm^2", citation=CITATION_MATERIAL,
    )
    trail.record(
        description="Permissible (design) shear stress",
        formula="tau_perm = tau_y / FoS_required",
        inputs={"tau_y_mpa": round(core.shear_yield_mpa, 2), "FoS_required": core.required_fos},
        value=round(core.permissible_stress_mpa, 2), unit="N/mm^2", citation=CITATION_PERMISSIBLE,
    )

    if core.element_kind == "shaft":
        _record_shaft(trail, params, core)
    else:
        _record_weld(trail, geometry, core)

    assumptions = _assumptions(params, core)
    return MachineElementAnalysis(
        element_kind=core.element_kind,
        yield_mpa=round(core.yield_mpa, 3),
        ultimate_mpa=round(core.ultimate_mpa, 3),
        shear_yield_mpa=round(core.shear_yield_mpa, 4),
        required_fos=round(core.required_fos, 4),
        torque_nmm=round(core.torque_nmm, 4),
        tangential_force_n=round(core.tangential_force_n, 4),
        transverse_load_n=round(core.transverse_load_n, 4),
        bending_moment_nmm=round(core.bending_moment_nmm, 4),
        equiv_twisting_moment_nmm=round(core.equiv_twisting_moment_nmm, 4),
        max_stress_mpa=round(core.max_stress_mpa, 4),
        permissible_stress_mpa=round(core.permissible_stress_mpa, 4),
        factor_of_safety=round(core.factor_of_safety, 4),
        fatigue_applicable=core.fatigue_applicable,
        stress_amplitude_mpa=round(core.stress_amplitude_mpa, 4),
        endurance_limit_mpa=round(core.endurance_limit_mpa, 4),
        fatigue_fos=round(core.fatigue_fos, 4),
        required_fatigue_fos=round(core.required_fatigue_fos, 4),
        diameter_mm=round(core.diameter_mm, 4),
        hub_diameter_mm=round(core.hub_diameter_mm, 4),
        weld_size_mm=round(core.weld_size_mm, 4),
        weld_throat_mm=round(core.weld_throat_mm, 4),
        assumptions=assumptions,
        trail=trail.steps,
    )


def _record_shaft(trail, params: MachineElementParams, core: ForceCore) -> None:
    trail.record(
        description="Tangential force at the mounted pitch radius",
        formula="F_t = T / (PCD/2)",
        inputs={"T_nmm": round(core.torque_nmm, 1), "PCD_mm": params.mounting_pcd_mm},
        value=round(core.tangential_force_n, 2), unit="N", citation=CITATION_BENDING,
    )
    trail.record(
        description="Net transverse (bending) load on the overhang",
        formula="W = k_belt * F_t",
        inputs={"F_t_n": round(core.tangential_force_n, 2), "k_belt": TRANSVERSE_LOAD_FACTOR},
        value=round(core.transverse_load_n, 2), unit="N", citation=CITATION_BENDING,
    )
    trail.record(
        description="Overhung bending moment",
        formula="M = W * overhang",
        inputs={"W_n": round(core.transverse_load_n, 2), "overhang_mm": params.overhang_mm},
        value=round(core.bending_moment_nmm, 1), unit="N.mm", citation=CITATION_BENDING,
    )
    trail.record(
        description="Equivalent twisting moment (combined bending + torsion)",
        formula="Te = sqrt((Cm*M)^2 + (Ct*T)^2)",
        inputs={
            "Cm": params.bending_shock_factor, "M_nmm": round(core.bending_moment_nmm, 1),
            "Ct": params.torsion_shock_factor, "T_nmm": round(core.torque_nmm, 1),
        },
        value=round(core.equiv_twisting_moment_nmm, 1), unit="N.mm", citation=CITATION_COMBINED,
    )
    trail.record(
        description="Maximum shear stress in the shaft",
        formula="tau_max = 16 Te / (pi d^3)",
        inputs={"Te_nmm": round(core.equiv_twisting_moment_nmm, 1), "d_mm": core.diameter_mm},
        value=round(core.max_stress_mpa, 3), unit="N/mm^2", citation=CITATION_COMBINED,
    )
    trail.record(
        description="Static factor of safety against shear yield",
        formula="FoS = tau_y / tau_max",
        inputs={"tau_y_mpa": round(core.shear_yield_mpa, 2), "tau_max_mpa": round(core.max_stress_mpa, 3)},
        value=round(core.factor_of_safety, 3), unit="-", citation=CITATION_COMBINED,
    )
    trail.record(
        description="Corrected endurance limit (rotating-shaft fatigue)",
        formula="sigma_e' = k_a * k_b * 0.5 * fu",
        inputs={"fu_mpa": core.ultimate_mpa},
        value=round(core.endurance_limit_mpa, 2), unit="N/mm^2", citation=CITATION_FATIGUE,
    )
    trail.record(
        description="Reversed-bending stress amplitude (with stress concentration)",
        formula="sigma_a = Kt * 32 M / (pi d^3)",
        inputs={"Kt": FATIGUE_STRESS_CONC_KT, "M_nmm": round(core.bending_moment_nmm, 1), "d_mm": core.diameter_mm},
        value=round(core.stress_amplitude_mpa, 3), unit="N/mm^2", citation=CITATION_FATIGUE,
    )
    trail.record(
        description="Fatigue factor of safety (Soderberg — reversed bending + steady torsion)",
        formula="1/n = sigma_a/sigma_e' + sqrt(3) tau_m/fy",
        inputs={
            "sigma_a_mpa": round(core.stress_amplitude_mpa, 3),
            "sigma_e_mpa": round(core.endurance_limit_mpa, 2),
            "fy_mpa": core.yield_mpa,
        },
        value=round(core.fatigue_fos, 3), unit="-", citation=CITATION_FATIGUE,
    )


def _record_weld(trail, geometry: MachineElementGeometry, core: ForceCore) -> None:
    trail.record(
        description="Fillet-weld effective throat",
        formula="t = 0.707 * s",
        inputs={"s_mm": core.weld_size_mm},
        value=round(core.weld_throat_mm, 3), unit="mm", citation=CITATION_WELD_THROAT,
    )
    trail.record(
        description="Torsional shear stress in the circular fillet weld",
        formula="tau = T / (0.707 s * pi D^2 / 2)",
        inputs={
            "T_nmm": round(core.torque_nmm, 1), "s_mm": core.weld_size_mm,
            "D_mm": core.hub_diameter_mm,
        },
        value=round(core.max_stress_mpa, 3), unit="N/mm^2", citation=CITATION_WELD_SHEAR,
    )
    trail.record(
        description="Factor of safety against shear yield in the weld",
        formula="FoS = tau_y / tau_weld",
        inputs={"tau_y_mpa": round(core.shear_yield_mpa, 2), "tau_weld_mpa": round(core.max_stress_mpa, 3)},
        value=round(core.factor_of_safety, 3), unit="-", citation=CITATION_WELD_SHEAR,
    )


def _assumptions(params: MachineElementParams, core: ForceCore) -> list[Assumption]:
    assumptions = [
        Assumption(
            field="material_strengths_needs_verification",
            value=f"{params.material_grade}: fy {core.yield_mpa:g}, fu {core.ultimate_mpa:g} N/mm^2",
            source="engine_default",
            note=(
                f"{params.material_grade} yield {core.yield_mpa:g} and ultimate {core.ultimate_mpa:g} "
                "N/mm^2 are transcribed from the Design Data Book steel tables — ASSUMED values "
                "that NEED VERIFICATION against the source before demo day."
            ),
        ),
    ]
    if core.element_kind == "shaft":
        assumptions.append(Assumption(
            field="transverse_load_factor",
            value=TRANSVERSE_LOAD_FACTOR,
            source="engine_default",
            note=(
                f"Net transverse (bending) load taken as {TRANSVERSE_LOAD_FACTOR:g} x the tangential "
                "force (a belt drive with a ~3:1 tension ratio) — a transcribed modelling factor "
                "pending verification against the actual drive."
            ),
        ))
        assumptions.append(Assumption(
            field="fatigue_factors_needs_verification",
            value=f"Kt {FATIGUE_STRESS_CONC_KT:g}, k_a k_b (0.5 fu) endurance",
            source="engine_default",
            note=(
                f"Fatigue stress-concentration factor Kt = {FATIGUE_STRESS_CONC_KT:g} and the "
                "surface/size endurance-correction factors are transcribed approximations — "
                "ASSUMED values that NEED VERIFICATION against the fillet/keyway detail and the "
                "material S-N data before demo day."
            ),
        ))
    else:
        assumptions.append(Assumption(
            field="weld_group_model",
            value="circular fillet weld, weld-as-a-line",
            source="engine_default",
            note=(
                "The circular fillet weld is treated as a line of throat 0.707 s (polar modulus "
                "Zp = pi D^2/2 per unit throat); electrode strength assumed to match the parent "
                "steel — pending verification against the actual electrode and IS 816 provisions."
            ),
        ))
    return assumptions
