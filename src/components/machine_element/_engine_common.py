"""Shared machine-element constants, material tables, strength helpers, the
citation strings and the calc-trail recorder for the machine-element component.

The engineering basis is STANDARD DESIGN OF MACHINE ELEMENTS — the closed-form
methods reproduced across the standard texts (Shigley "Mechanical Engineering
Design"; PSG / the "Design Data Book"; Bhandari "Design of Machine Elements").
Every transcribed material strength / correction factor names its source and
carries `needs_verification=True`; it must be checked against the source Design
Data Book before demo day (engineer pre-review required per spec).

This module is deliberately SELF-CONTAINED (it does not import from any other
component package) so the machine-element slice stays independent. It reuses only
shared platform pieces (`domain.culvert.CalcStep`, `components.base`).

NOTE ON DOMAIN: a machine element is a MECHANICAL component — the strength basis
is machine-design practice, NOT any civil/bridge code. Bridge/road/concrete codes
(IRC, IS 456, IRS Concrete Bridge Code) are out-of-domain and forbidden here.
"""

from __future__ import annotations

import math
from typing import NamedTuple

from domain.culvert import CalcStep

# --------------------------------------------------------------------------- kinematics / units
# Torque from transmitted power: P = 2*pi*N*T/60. With P in kW and N in rev/min,
# T[N.mm] = (60e6 / (2*pi)) * P / N.  (T[N.m] = 9550 * P[kW] / N[rpm].)
TORQUE_CONSTANT_NMM = 60.0e6 / (2.0 * math.pi)

# Maximum-shear-stress (Guest/Tresca) theory: shear yield = 0.5 * tensile yield.
SHEAR_YIELD_RATIO = 0.5

# Overhung transverse (bending) load on the shaft from a belt/gear mounted at the
# pitch radius: net transverse pull ~ factor * tangential force (a belt drive with
# a ~3:1 tension ratio gives a resultant ~ 2 * F_tangential). Transcribed.
TRANSVERSE_LOAD_FACTOR = 2.0

# Rotating-shaft fatigue — endurance limit and Marin-type correction factors.
ENDURANCE_RATIO = 0.5     # sigma_e' ~ 0.5 * sigma_ult for wrought steel (unnotched)
SURFACE_FACTOR = 0.75     # k_a — machined / cold-drawn surface
SIZE_FACTOR = 0.85        # k_b — size factor for a typical (30-60 mm) shaft
FATIGUE_STRESS_CONC_KT = 1.5  # K_t at the shoulder fillet / keyway (transcribed)
REQUIRED_FATIGUE_FOS = 1.5    # design factor of safety on endurance (rotating shaft)

# Fillet weld — effective throat = 0.707 * leg size (a standard weld convention).
WELD_THROAT_FACTOR = 0.707
MIN_WELD_SIZE_MM = 3.0    # smallest practical fillet leg
MAX_WELD_SIZE_MM = 25.0

# Shaft sizing helpers — round diameters up to a preferred R-series-ish step.
DIAMETER_STEP_MM = 5.0
MIN_SHAFT_DIAMETER_MM = 10.0

# --------------------------------------------------------------------------- citations
VERIFY_BANNER = (
    "TRANSCRIPTION FOR DEMO — verify each value against the cited Design Data Book "
    "before demo day (engineer pre-review required per spec)"
)
# The single declared code string (the machine-design basis); it is embedded
# verbatim in every machine-design citation so the code-set guard recognises it.
MACHINE_DESIGN_CODE = "Machine Design Code (Shigley / PSG / Design Data Book)"
MACHINE_DESIGN_DOCUMENT = (
    "Standard Design of Machine Elements — Shigley 'Mechanical Engineering Design', "
    "PSG / 'Design Data Book', Bhandari 'Design of Machine Elements' (closed-form "
    "strength, combined-stress, fatigue and welded-joint methods)"
)
IS816_DOCUMENT = (
    "IS 816 — Code of Practice for use of Metal Arc Welding for General Construction "
    "(fillet-weld effective throat = 0.707 x size, weld-group strength provisions)"
)

# The declared code set (mirrors ComponentModule.codes and the spec). Honest and
# minimal: the standard machine-design methods, plus IS 816 for the fillet weld.
CODES = [MACHINE_DESIGN_CODE, "IS 816"]


def _clause(head: str, document: str) -> str:
    return f"{head} — {document} [table/clause pending verification]. {VERIFY_BANNER}."


CITATION_USER_INPUT = (
    "User design requirement — validated against the machine-element input range"
)
CITATION_PROPORTIONING = _clause(
    f"{MACHINE_DESIGN_CODE}: element proportioning (shaft diameter from the "
    "permissible shear stress, fillet-weld leg from the weld-group strength)",
    MACHINE_DESIGN_DOCUMENT,
)
CITATION_TORQUE = _clause(
    f"{MACHINE_DESIGN_CODE}: torque from transmitted power, T = 9550 * P[kW] / N[rpm]",
    MACHINE_DESIGN_DOCUMENT,
)
CITATION_BENDING = _clause(
    f"{MACHINE_DESIGN_CODE}: overhung transverse (bending) load from a belt/gear at "
    "the pitch radius, M = W * overhang",
    MACHINE_DESIGN_DOCUMENT,
)
CITATION_COMBINED = _clause(
    f"{MACHINE_DESIGN_CODE}: combined bending + torsion by the maximum-shear-stress "
    "theory, equivalent twisting moment Te = sqrt((Cm*M)^2 + (Ct*T)^2), tau = 16 Te/(pi d^3)",
    MACHINE_DESIGN_DOCUMENT,
)
CITATION_PERMISSIBLE = _clause(
    f"{MACHINE_DESIGN_CODE}: permissible (design) shear stress = shear yield / FoS, "
    "shear yield = 0.5 * tensile yield (maximum-shear-stress theory)",
    MACHINE_DESIGN_DOCUMENT,
)
CITATION_FATIGUE = _clause(
    f"{MACHINE_DESIGN_CODE}: rotating-shaft fatigue — corrected endurance limit "
    "sigma_e' = k_a k_b (0.5 sigma_ult) and the Soderberg criterion for reversed "
    "bending + steady torsion",
    MACHINE_DESIGN_DOCUMENT,
)
CITATION_MATERIAL = _clause(
    f"{MACHINE_DESIGN_CODE}: material yield / ultimate strengths from the Design Data "
    "Book steel tables",
    MACHINE_DESIGN_DOCUMENT,
)
CITATION_WELD_THROAT = _clause(
    "IS 816: fillet-weld effective throat = 0.707 x leg size; the circular weld group "
    "is treated as a line (polar modulus Zp = pi D^2 / 2 per unit throat)",
    IS816_DOCUMENT,
)
CITATION_WELD_SHEAR = _clause(
    f"IS 816 / {MACHINE_DESIGN_CODE}: torsional shear stress in the fillet weld throat, "
    "tau = T / (0.707 s * pi D^2 / 2), within the permissible weld shear stress",
    IS816_DOCUMENT,
)


# --------------------------------------------------------------------------- material table
class MachineMaterial(NamedTuple):
    """Yield / ultimate tensile strength for one shaft/weld steel, N/mm^2."""

    grade: str
    yield_mpa: float
    ultimate_mpa: float
    needs_verification: bool


# Transcribed from the Design Data Book steel tables (representative values).
MACHINE_MATERIALS: dict[str, MachineMaterial] = {
    "40C8": MachineMaterial("40C8", 330.0, 600.0, True),   # plain carbon steel (~C40)
    "EN24": MachineMaterial("EN24", 680.0, 900.0, True),   # heat-treated alloy steel
}


def material(grade: str) -> MachineMaterial:
    """Material row for a grade — raises KeyError if untranscribed."""
    return MACHINE_MATERIALS[grade]


# --------------------------------------------------------------------------- strength helpers
def torque_nmm(power_kw: float, speed_rpm: float) -> float:
    """Transmitted torque, N.mm (T[N.m] = 9550 P/N)."""
    return TORQUE_CONSTANT_NMM * power_kw / speed_rpm


def shear_yield_mpa(yield_mpa: float) -> float:
    """Shear yield stress by the maximum-shear-stress theory (0.5 * tensile yield)."""
    return SHEAR_YIELD_RATIO * yield_mpa


def permissible_shear_mpa(yield_mpa: float, required_fos: float) -> float:
    """Design permissible shear stress = shear yield / required factor of safety."""
    return shear_yield_mpa(yield_mpa) / required_fos


def tangential_force_n(torque_value_nmm: float, pcd_mm: float) -> float:
    """Tangential force at the pitch radius, F_t = T / (PCD/2), N."""
    return torque_value_nmm / (pcd_mm / 2.0)


def equivalent_twisting_moment_nmm(cm: float, moment_nmm: float, ct: float, torque_value_nmm: float) -> float:
    """Te = sqrt((Cm*M)^2 + (Ct*T)^2) — combined bending + torsion (max-shear theory)."""
    return math.hypot(cm * moment_nmm, ct * torque_value_nmm)


def shaft_shear_stress_mpa(equiv_torque_nmm: float, diameter_mm: float) -> float:
    """Maximum shear stress in a solid shaft, tau = 16 Te / (pi d^3), N/mm^2."""
    return 16.0 * equiv_torque_nmm / (math.pi * diameter_mm**3)


def bending_stress_mpa(moment_nmm: float, diameter_mm: float) -> float:
    """Extreme-fibre bending stress in a solid shaft, sigma = 32 M / (pi d^3), N/mm^2."""
    return 32.0 * moment_nmm / (math.pi * diameter_mm**3)


def solid_shaft_diameter_mm(equiv_torque_nmm: float, perm_shear_mpa: float) -> float:
    """Solid-shaft diameter from tau = 16 Te/(pi d^3) <= tau_perm."""
    return (16.0 * equiv_torque_nmm / (math.pi * perm_shear_mpa)) ** (1.0 / 3.0)


def corrected_endurance_mpa(ultimate_mpa: float) -> float:
    """Corrected endurance limit sigma_e' = k_a k_b (0.5 sigma_ult), N/mm^2."""
    return SURFACE_FACTOR * SIZE_FACTOR * ENDURANCE_RATIO * ultimate_mpa


def fatigue_factor_of_safety(
    *, moment_nmm: float, torque_value_nmm: float, diameter_mm: float,
    endurance_mpa: float, yield_mpa: float,
) -> float:
    """Soderberg fatigue FoS for reversed bending + steady torsion on a rotating shaft.

    Reversed bending amplitude sigma_a = K_t * 32 M / (pi d^3) (mean 0, rotating);
    steady torsion tau_m = 16 T / (pi d^3), von-Mises mean sigma_m_eq = sqrt(3) tau_m.
    Soderberg: 1/n = sigma_a/sigma_e' + sigma_m_eq/sigma_y.
    """
    sigma_a = FATIGUE_STRESS_CONC_KT * bending_stress_mpa(moment_nmm, diameter_mm)
    tau_m = 16.0 * torque_value_nmm / (math.pi * diameter_mm**3)
    sigma_m_eq = math.sqrt(3.0) * tau_m
    inv = sigma_a / endurance_mpa + sigma_m_eq / yield_mpa
    return 1.0 / inv if inv > 0 else float("inf")


def fatigue_diameter_mm(
    *, moment_nmm: float, torque_value_nmm: float,
    endurance_mpa: float, yield_mpa: float, required_fatigue_fos: float,
) -> float:
    """Smallest diameter meeting the Soderberg fatigue FoS (closed form in d^3)."""
    coefficient = (
        FATIGUE_STRESS_CONC_KT * 32.0 * moment_nmm / endurance_mpa
        + math.sqrt(3.0) * 16.0 * torque_value_nmm / yield_mpa
    )
    d_cubed = required_fatigue_fos * coefficient / math.pi
    return d_cubed ** (1.0 / 3.0)


# --- fillet weld (circular weld group in torsion) ---
def weld_throat_mm(size_mm: float) -> float:
    """Fillet-weld effective throat = 0.707 * leg size, mm."""
    return WELD_THROAT_FACTOR * size_mm


def circular_weld_shear_mpa(torque_value_nmm: float, hub_diameter_mm: float, size_mm: float) -> float:
    """Torsional shear stress in a circular fillet weld of hub diameter D, leg s.

    Weld-as-a-line polar modulus Zp = pi D^2 / 2 (per unit throat);
    tau = T / (Zp * throat) = T / (pi D^2/2 * 0.707 s), N/mm^2.
    """
    polar_modulus = math.pi * hub_diameter_mm**2 / 2.0
    return torque_value_nmm / (polar_modulus * weld_throat_mm(size_mm))


def weld_size_for_torque_mm(torque_value_nmm: float, hub_diameter_mm: float, perm_shear_mpa: float) -> float:
    """Fillet leg size s from tau_weld <= tau_perm (circular weld in torsion)."""
    polar_modulus = math.pi * hub_diameter_mm**2 / 2.0
    return torque_value_nmm / (polar_modulus * WELD_THROAT_FACTOR * perm_shear_mpa)


def round_up(value: float, step: float) -> float:
    """Ceil `value` up to the nearest multiple of `step` (robust to fp noise)."""
    return math.ceil(round(value / step, 6)) * step


# --------------------------------------------------------------------------- trail recorder
class Trail:
    """Ordered CalcStep recorder with a per-segment id namespace so the sizing
    ('S'), analysis ('A') and checks ('K') trails never collide when merged."""

    def __init__(self, prefix: str) -> None:
        self._prefix = prefix
        self._steps: list[CalcStep] = []

    def record(
        self,
        *,
        description: str,
        formula: str,
        inputs: dict[str, float | int | str],
        value: float,
        unit: str,
        citation: str,
    ) -> float:
        step_id = f"{self._prefix}{len(self._steps) + 1:02d}"
        self._steps.append(
            CalcStep(
                step_id=step_id,
                description=description,
                formula=formula,
                inputs=inputs,
                value=value,
                unit=unit,
                citation=citation,
            )
        )
        return value

    def last_id(self) -> str:
        return self._steps[-1].step_id

    @property
    def steps(self) -> list[CalcStep]:
        return list(self._steps)
