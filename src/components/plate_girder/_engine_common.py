"""Shared engineering constants, permissible-stress tables, section-property
helpers and the calc-trail recorder for the welded steel plate-girder component.

Every constant names its source. The permissible-stress values follow IRS Steel
Bridge Code / IS 800 working-stress (allowable-stress) practice; each is
transcribed for the POC and carries `needs_verification=True` — it must be
checked digit-for-digit against the source codes before demo day (IR engineer
pre-review required per spec).

This module is deliberately SELF-CONTAINED (it does not import from any other
component package) so the plate-girder slice stays independent. It may reuse
shared platform pieces (`domain.culvert` enums, `components.base`, `engine.loading`).
"""

from __future__ import annotations

import math
from typing import NamedTuple

from domain.culvert import CalcStep

# --------------------------------------------------------------------------- units / materials
STEEL_UNIT_WEIGHT_KN_M3 = 78.5  # structural steel self-weight, IS 800 / IS 875
E_STEEL_MPA = 2.0e5  # Young's modulus of structural steel, N/mm^2 (IS 800)

# Superimposed dead load (deck slab / trough, ballast, track, services) taken as a
# uniform allowance per track — transcribed for the POC, pending verification.
DECK_DEAD_LOAD_KN_PER_M = 30.0

# Live-load deflection limit — span / 600 (IRS live-load deflection limit for
# steel railway girder spans).
DEFLECTION_LIMIT_RATIO = 600.0

# Web slenderness (depth / thickness) ceiling for a web with intermediate
# transverse stiffeners — working-stress practice; clause pending verification.
WEB_SLENDERNESS_LIMIT = 200.0

# --------------------------------------------------------------------------- citations
VERIFY_BANNER = (
    "TRANSCRIPTION FOR DEMO — verify each value against the cited source before "
    "demo day (IR engineer pre-review required per spec)"
)
IRS_STEEL_BRIDGE_CODE_DOCUMENT = (
    "IRS Steel Bridge Code — Code of Practice for the Design of Steel or Wrought "
    "Iron Bridges Carrying Rail, Road or Pedestrian Traffic, Ministry of Railways"
)
IS800_DOCUMENT = (
    "IS 800:2007 — General Construction in Steel, Code of Practice, Bureau of "
    "Indian Standards (working/allowable-stress design provisions)"
)
IR_BRIDGE_RULES_DOCUMENT = (
    "IRS Bridge Rules — Rules specifying the loads for design of super and "
    "sub-structures of bridges, Ministry of Railways"
)


def _clause(head: str, document: str) -> str:
    return f"{head} — {document} [clause/table pending verification]. {VERIFY_BANNER}."


CITATION_USER_INPUT = (
    "User design requirement — validated against the steel plate-girder range"
)
CITATION_PROPORTIONING = _clause(
    "Welded plate-girder proportioning (web depth ~ span/10-span/12, web "
    "thickness shear/slenderness-governed, flanges from the required section modulus)",
    IRS_STEEL_BRIDGE_CODE_DOCUMENT,
)
CITATION_DEAD_LOAD = _clause(
    "Dead load = girder self-weight (steel at 78.5 kN/m^3) + superimposed deck/track "
    "allowance",
    IS800_DOCUMENT,
)
CITATION_LIVE_LOAD = _clause(
    "Live load = 25t Loading-2008 EUDL for BM / shear at loaded length ~ span, "
    "augmented by the coefficient of dynamic augment (CDA), shared equally per girder",
    IR_BRIDGE_RULES_DOCUMENT,
)
CITATION_BENDING = _clause(
    "Permissible bending stress in the extreme fibre, working-stress basis "
    "(sigma_bt = 0.66 fy)",
    IRS_STEEL_BRIDGE_CODE_DOCUMENT,
)
CITATION_SHEAR = _clause(
    "Permissible average shear stress in the web, working-stress basis "
    "(tau_va = 0.40 fy)",
    IRS_STEEL_BRIDGE_CODE_DOCUMENT,
)
CITATION_DEFLECTION = _clause(
    "Live-load deflection limit span/600 for a simply-supported steel railway girder",
    IRS_STEEL_BRIDGE_CODE_DOCUMENT,
)
CITATION_SLENDERNESS = _clause(
    f"Web slenderness d/t <= {WEB_SLENDERNESS_LIMIT:g} with intermediate transverse "
    "stiffeners; stiffener spacing ~ web depth",
    IS800_DOCUMENT,
)
CITATION_FATIGUE = _clause(
    "Fatigue assessment of welded details (stress range vs the S-N detail category) — "
    "flagged for a full fatigue check outside this POC scope",
    IRS_STEEL_BRIDGE_CODE_DOCUMENT,
)
CITATION_SECTION = _clause(
    "Elastic section properties of a doubly-symmetric welded I-section "
    "(I = t_w*d^3/12 + 2*[b_f*t_f^3/12 + b_f*t_f*((d+t_f)/2)^2]); Z = I/(D/2))",
    IS800_DOCUMENT,
)

CODES = ["IRS Steel Bridge Code", "IS 800", "IR Bridge Rules"]


# --------------------------------------------------------------------------- permissible table
class SteelPermissible(NamedTuple):
    """Working-stress permissible stresses for one structural-steel grade, N/mm^2."""

    grade: str
    fy_n_mm2: float  # yield stress
    sigma_bending_n_mm2: float  # permissible bending stress, extreme fibre (~0.66 fy)
    sigma_shear_n_mm2: float  # permissible average web shear stress (~0.40 fy)
    needs_verification: bool


STEEL_PERMISSIBLE: dict[str, SteelPermissible] = {
    "E250": SteelPermissible("E250", 250.0, 165.0, 100.0, True),
    "E350": SteelPermissible("E350", 350.0, 231.0, 140.0, True),
}


def permissible(steel_grade: str) -> SteelPermissible:
    """Permissible-stress row for a steel grade — raises KeyError if untranscribed."""
    return STEEL_PERMISSIBLE[steel_grade]


# --------------------------------------------------------------------------- section properties
class SectionProperties(NamedTuple):
    """Elastic properties of the welded I-section (mm-based)."""

    area_mm2: float
    inertia_mm4: float  # second moment of area about the strong (horizontal) axis
    section_modulus_mm3: float  # Z = I / (D/2)
    overall_depth_mm: float


def section_properties(
    *,
    web_depth_mm: float,
    web_thickness_mm: float,
    flange_width_mm: float,
    flange_thickness_mm: float,
) -> SectionProperties:
    """Exact elastic properties of a doubly-symmetric welded I-section."""
    d = web_depth_mm
    tw = web_thickness_mm
    bf = flange_width_mm
    tf = flange_thickness_mm
    overall = d + 2.0 * tf
    area = tw * d + 2.0 * bf * tf
    lever = (d + tf) / 2.0
    inertia = tw * d**3 / 12.0 + 2.0 * (bf * tf**3 / 12.0 + bf * tf * lever**2)
    modulus = inertia / (overall / 2.0)
    return SectionProperties(
        area_mm2=area,
        inertia_mm4=inertia,
        section_modulus_mm3=modulus,
        overall_depth_mm=overall,
    )


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
