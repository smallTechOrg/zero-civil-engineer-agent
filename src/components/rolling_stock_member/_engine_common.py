"""Shared engineering constants, permissible-stress tables, section-property
helpers and the calc-trail recorder for the rolling-stock structural-member
component (wagon underframe member / sole bar / headstock).

Every constant names its source. The member is a fabricated (welded) steel
I-section designed to RDSO wagon-design load cases with IS 800 working-stress
section checks; each transcribed value (RDSO design loads / dynamic augment /
permissible stresses) is transcribed for the POC and carries
`needs_verification=True` — it must be checked digit-for-digit against the
source RDSO specification and IS 800 before demo day (IR engineer pre-review
required per spec).

This module is deliberately SELF-CONTAINED (it does not import from any other
component package) so the rolling-stock-member slice stays independent. It may
reuse shared platform pieces (`domain.culvert` enums / `components.base`).
"""

from __future__ import annotations

import math
from typing import NamedTuple

from domain.culvert import CalcStep

# --------------------------------------------------------------------------- units / materials
STEEL_UNIT_WEIGHT_KN_M3 = 78.5  # structural steel self-weight, IS 800 / IS 875
E_STEEL_MPA = 2.0e5  # Young's modulus of structural steel, N/mm^2 (IS 800)

# RDSO wagon-design dynamic augment applied to the vertical payload for
# underframe members — transcribed for the POC, pending verification.
VERTICAL_IMPACT_FACTOR = 1.30

# RDSO / UIC design proof buffing (longitudinal compressive) load for the
# COMPLETE wagon underframe — a transcribed reference value (needs verification).
# The per-member share is a design parameter (`design_buffing_load_kn`).
RDSO_PROOF_BUFFING_LOAD_KN = 2000.0

# Web slenderness (depth / thickness) ceiling for a fabricated member web —
# working-stress practice; clause pending verification.
WEB_SLENDERNESS_LIMIT = 180.0

# Combined axial + bending interaction ceiling (unity check).
INTERACTION_LIMIT = 1.0

# --------------------------------------------------------------------------- citations
VERIFY_BANNER = (
    "TRANSCRIPTION FOR DEMO — verify each value against the cited source before "
    "demo day (IR engineer pre-review required per spec)"
)
RDSO_DOCUMENT = (
    "RDSO Specifications — Research Designs & Standards Organisation wagon-design "
    "criteria (vertical payload with dynamic augment and longitudinal buffing / "
    "draft-gear load cases for freight-stock underframes), Ministry of Railways"
)
IS800_DOCUMENT = (
    "IS 800:2007 — General Construction in Steel, Code of Practice, Bureau of "
    "Indian Standards (working/allowable-stress design provisions)"
)


def _clause(head: str, document: str) -> str:
    return f"{head} — {document} [clause/table pending verification]. {VERIFY_BANNER}."


CITATION_USER_INPUT = (
    "User design requirement — validated against the rolling-stock member range"
)
CITATION_PROPORTIONING = _clause(
    "Fabricated rolling-stock member proportioning (welded I-section: web depth "
    "from the member length, web thickness shear/slenderness-governed, flanges "
    "from the required section modulus and axial area)",
    IS800_DOCUMENT,
)
CITATION_SELF_WEIGHT = _clause(
    "Member self-weight (fabricated steel section at 78.5 kN/m^3)",
    IS800_DOCUMENT,
)
CITATION_VERTICAL_LOAD = _clause(
    "Vertical load case = design payload / tare vertical load over the member, "
    "augmented by the RDSO wagon-design dynamic augment (impact factor)",
    RDSO_DOCUMENT,
)
CITATION_BUFFING_LOAD = _clause(
    "Longitudinal load case = the member's share of the RDSO draft-gear buffing "
    "(compressive) / draft (tensile) load along the centre sill / sole bar",
    RDSO_DOCUMENT,
)
CITATION_BENDING = _clause(
    "Permissible bending stress in the extreme fibre, working-stress basis "
    "(sigma_bt = 0.66 fy)",
    IS800_DOCUMENT,
)
CITATION_SHEAR = _clause(
    "Permissible average shear stress in the web, working-stress basis "
    "(tau_va = 0.40 fy)",
    IS800_DOCUMENT,
)
CITATION_AXIAL = _clause(
    "Permissible axial stress on the gross section for a stocky (low-slenderness) "
    "member, working-stress basis (sigma_ac = 0.60 fy)",
    IS800_DOCUMENT,
)
CITATION_COMBINED = _clause(
    "Combined axial + bending interaction (unity check): "
    "sigma_ac,cal/sigma_ac + sigma_bc,cal/sigma_bc <= 1.0",
    IS800_DOCUMENT,
)
CITATION_WELD_FATIGUE = _clause(
    "Fabrication welds (fillet welds joining web to flanges) and fatigue of the "
    "welded details under repeated wagon loading — flagged for a full weld / S-N "
    "fatigue assessment outside this POC scope",
    RDSO_DOCUMENT,
)
CITATION_SECTION = _clause(
    "Elastic section properties of a doubly-symmetric welded I-section "
    "(I = t_w*d^3/12 + 2*[b_f*t_f^3/12 + b_f*t_f*((d+t_f)/2)^2]); Z = I/(D/2))",
    IS800_DOCUMENT,
)

CODES = ["RDSO Specifications", "IS 800"]


# --------------------------------------------------------------------------- permissible table
class SteelPermissible(NamedTuple):
    """Working-stress permissible stresses for one structural-steel grade, N/mm^2."""

    grade: str
    fy_n_mm2: float  # yield stress
    sigma_bending_n_mm2: float  # permissible bending stress, extreme fibre (~0.66 fy)
    sigma_shear_n_mm2: float  # permissible average web shear stress (~0.40 fy)
    sigma_axial_n_mm2: float  # permissible axial stress, stocky member (~0.60 fy)
    needs_verification: bool


STEEL_PERMISSIBLE: dict[str, SteelPermissible] = {
    "E250": SteelPermissible("E250", 250.0, 165.0, 100.0, 150.0, True),
    "E350": SteelPermissible("E350", 350.0, 231.0, 140.0, 210.0, True),
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


def fillet_weld_size_mm(web_thickness_mm: float, flange_thickness_mm: float) -> float:
    """Fillet-weld leg joining the web to the flanges — ~0.7 x the thinner plate,
    floored at a 6 mm minimum leg (fabrication-practice minimum)."""
    leg = 0.7 * min(web_thickness_mm, flange_thickness_mm)
    return max(6.0, round_up(leg, 1.0))


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
