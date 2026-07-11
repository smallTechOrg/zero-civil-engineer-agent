"""Shared engineering constants, permissible-stress tables, earth-pressure
coefficients and the calc-trail recorder for the pier & abutment substructure.

Every constant names its source. The permissible-stress values follow IS 456 /
IRS Concrete Bridge Code working-stress practice (direct compression), the
earth-pressure formulae follow Rankine (level backfill), and the longitudinal
(braking / tractive) force and track surcharge follow IRS Bridge Rules practice.

TRANSCRIPTION-HONESTY DISCIPLINE (same as the retaining-wall engine): the
permissible constants and the braking / surcharge factors carry
`needs_verification=True` — they are transcribed for the POC and must be checked
digit-for-digit against the source codes before demo day (IR engineer pre-review
required per spec).

This module is a SELF-CONTAINED copy of the machinery pattern the retaining wall
uses (stability + earth pressure + trail recorder); the pier/abutment slice never
imports from `components.retaining_wall` so the two slices stay independent.
"""

from __future__ import annotations

import math
from typing import NamedTuple

from domain.culvert import CalcStep, ConcreteGrade, SteelGrade

# --------------------------------------------------------------------------- units / factors
CONCRETE_UNIT_WEIGHT_KN_M3 = 25.0  # RCC self-weight, IS 456
MIN_CLEAR_COVER_MM = 40.0  # IS 456 cl. 26.4 — moderate exposure minimum
GRAVITY_M_S2 = 9.81

# IRS Bridge Rules — longitudinal (tractive effort / braking) force taken, for
# this breadth-first POC, as a fraction of the vertical superstructure reaction
# delivered to the substructure. A transcribed estimate pending verification.
LONGITUDINAL_FORCE_FRACTION = 0.15

# IR Bridge Rules — live-load (track) surcharge behind an abutment taken as an
# equivalent height of earth fill. BG single-line practice: ~1.2 m of fill.
TRACK_SURCHARGE_EQUIVALENT_HEIGHT_M = 1.2

# --------------------------------------------------------------------------- citations
VERIFY_BANNER = (
    "TRANSCRIPTION FOR DEMO — verify each value against the cited source before "
    "demo day (IR engineer pre-review required per spec)"
)
IRS_SUBSTRUCTURE_DOCUMENT = (
    "IRS Bridge Substructure & Foundation Code — Code of Practice for the Design "
    "of Sub-structures and Foundations of Bridges, Ministry of Railways"
)
IRS_BRIDGE_RULES_DOCUMENT = (
    "IRS Bridge Rules — Rules specifying the loads for design of super and "
    "sub-structures of bridges, Ministry of Railways"
)
IRS_CBC_DOCUMENT = (
    "IRS Concrete Bridge Code — Code of Practice for Plain, Reinforced and "
    "Prestressed Concrete for General Bridge Construction, Ministry of Railways"
)


def _clause(head: str, document: str) -> str:
    return f"{head} — {document} [clause/table pending verification]. {VERIFY_BANNER}."


CITATION_USER_INPUT = (
    "User design requirement — validated against the pier/abutment substructure range"
)
CITATION_PROPORTIONING = _clause(
    "Substructure proportioning (pier section from axial demand, spread footing "
    "sized so max base pressure <= SBC with no tension)",
    IRS_SUBSTRUCTURE_DOCUMENT,
)
CITATION_RANKINE = _clause(
    "Rankine active/passive earth-pressure theory (level backfill behind the abutment)",
    IRS_SUBSTRUCTURE_DOCUMENT,
)
CITATION_LONGITUDINAL = _clause(
    "Longitudinal (tractive effort / braking) force as a fraction of the "
    "superstructure reaction, applied at bearing level",
    IRS_BRIDGE_RULES_DOCUMENT,
)
CITATION_SURCHARGE = _clause(
    "Live-load (track) surcharge behind the abutment as an equivalent height of "
    "fill, BG single line",
    IRS_BRIDGE_RULES_DOCUMENT,
)
CITATION_STABILITY = _clause(
    "Overturning (FoS >= 2.0), sliding (FoS >= 1.5) and base-pressure (<= SBC, no "
    "tension) stability of the substructure on its spread footing",
    IRS_SUBSTRUCTURE_DOCUMENT,
)
CITATION_DIRECT_STRESS = _clause(
    "Permissible direct (axial) compressive stress in concrete sigma_cc "
    "(working-stress basis)",
    IRS_CBC_DOCUMENT,
)
CITATION_COVER = _clause(
    f"Minimum clear cover {MIN_CLEAR_COVER_MM:g} mm for moderate exposure",
    IRS_CBC_DOCUMENT,
)

CODES = [
    "IRS Bridge Substructure & Foundation Code",
    "IRS Bridge Rules",
    "IRS Concrete Bridge Code",
    "IS 456",
]


# --------------------------------------------------------------------------- permissible tables
class ConcretePermissible(NamedTuple):
    """IRS/IS-456 working-stress permissible stresses for one concrete grade, N/mm^2."""

    grade: str
    sigma_cc_n_mm2: float  # permissible direct (axial) compressive stress (Table 21)
    needs_verification: bool


CONCRETE_PERMISSIBLE: dict[ConcreteGrade, ConcretePermissible] = {
    ConcreteGrade.M25: ConcretePermissible("M25", 6.0, True),
    ConcreteGrade.M30: ConcretePermissible("M30", 8.0, True),
    ConcreteGrade.M35: ConcretePermissible("M35", 9.0, True),
}

# Steel grade is carried for the audit record / cover context; the breadth-first
# check set is stability + direct compression, so no steel-stress table is needed.
_STEEL_GRADES = {SteelGrade.FE415: "Fe415", SteelGrade.FE500: "Fe500"}


def permissible_direct_stress(concrete: ConcreteGrade) -> float:
    """Permissible direct compressive stress sigma_cc for the grade, N/mm^2."""
    return CONCRETE_PERMISSIBLE[concrete].sigma_cc_n_mm2


# --------------------------------------------------------------------------- earth pressure
def rankine_ka(phi_deg: float) -> float:
    """Rankine active coefficient for a level backfill (beta = 0)."""
    phi = math.radians(phi_deg)
    return (1.0 - math.sin(phi)) / (1.0 + math.sin(phi))


def rankine_kp(phi_deg: float) -> float:
    """Rankine passive coefficient for a level surface."""
    phi = math.radians(phi_deg)
    return (1.0 + math.sin(phi)) / (1.0 - math.sin(phi))


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
