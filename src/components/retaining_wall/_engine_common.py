"""Shared engineering constants, permissible-stress tables, earth-pressure
coefficients and the calc-trail recorder for the RCC cantilever retaining wall.

Every constant names its source. The permissible-stress values follow IS 456
working-stress practice (Tables 21/22/23) and the earth-pressure formulae follow
Rankine (level backfill) / Coulomb (sloped backfill). The track-surcharge
equivalent height follows IR Bridge Rules practice for BG single-line loading.

TRANSCRIPTION-HONESTY DISCIPLINE (same as the culvert engine): the permissible
constants carry `needs_verification=True` — they are transcribed for the POC and
must be checked digit-for-digit against the source codes before demo day (IR
engineer pre-review required per spec).
"""

from __future__ import annotations

import math
from typing import NamedTuple

from domain.culvert import CalcStep, ConcreteGrade, SteelGrade

# --------------------------------------------------------------------------- units
CONCRETE_UNIT_WEIGHT_KN_M3 = 25.0  # RCC self-weight, IS 456 / IS 875
ASSUMED_BAR_DIA_MM = 20.0  # effective-depth allowance: d = t - cover - dia/2
MIN_CLEAR_COVER_MM = 40.0  # IS 456 cl. 26.4 — moderate exposure minimum
MIN_STEEL_PCT_GROSS = 0.12  # IS 456 cl. 26.5.2.1 — HYSD minimum, % of gross area

# IR Bridge Rules — live-load (track) surcharge on the retaining backfill taken
# as an equivalent height of earth fill. BG single-line practice: ~1.2 m of fill.
TRACK_SURCHARGE_EQUIVALENT_HEIGHT_M = 1.2

# --------------------------------------------------------------------------- citations
VERIFY_BANNER = (
    "TRANSCRIPTION FOR DEMO — verify each value against the cited source before "
    "demo day (IR engineer pre-review required per spec)"
)
IS456_DOCUMENT = (
    "IS 456:2000 — Plain and Reinforced Concrete Code of Practice, Bureau of "
    "Indian Standards"
)
IRS_CBC_DOCUMENT = (
    "IRS Concrete Bridge Code — Code of Practice for Plain, Reinforced and "
    "Prestressed Concrete for General Bridge Construction, Ministry of Railways"
)
IR_BRIDGE_RULES_DOCUMENT = (
    "IRS Bridge Rules — Rules specifying the loads for design of super and "
    "sub-structures of bridges, Ministry of Railways"
)


def _clause(head: str, document: str) -> str:
    return f"{head} — {document} [clause/table pending verification]. {VERIFY_BANNER}."


CITATION_USER_INPUT = (
    "User design requirement — validated against the RCC cantilever retaining-wall range"
)
CITATION_PROPORTIONING = _clause(
    "Cantilever retaining-wall proportioning rules (base ~0.5-0.7H, base slab "
    "~H/12, stem flexure-governed)",
    "IS 456 working-stress design of cantilever retaining walls",
)
CITATION_RANKINE = _clause(
    "Rankine active/passive earth-pressure theory (level backfill)",
    "IRS Bridge Substructure & Foundation Code / IS 456 retaining-wall practice",
)
CITATION_COULOMB = _clause(
    "Coulomb active earth-pressure theory (sloped backfill, vertical virtual back)",
    "IRS Bridge Substructure & Foundation Code / IS 456 retaining-wall practice",
)
CITATION_SURCHARGE = _clause(
    "Live-load (track) surcharge as an equivalent height of fill, BG single line",
    IR_BRIDGE_RULES_DOCUMENT,
)
CITATION_STABILITY = _clause(
    "Overturning (FoS >= 2.0), sliding (FoS >= 1.5) and base-pressure (<= SBC, no "
    "tension) stability of a gravity/cantilever retaining wall",
    "IRS Bridge Substructure & Foundation Code",
)
CITATION_FLEXURE = _clause(
    "Working-stress flexure: balanced moment-of-resistance constant Q = "
    "0.5*sigma_cbc*k*j, modular ratio m = 280/(3*sigma_cbc)",
    IS456_DOCUMENT,
)
CITATION_STEEL = _clause(
    "Permissible tensile stress in reinforcement sigma_st (working-stress basis)",
    IS456_DOCUMENT,
)
CITATION_SHEAR = _clause(
    "Permissible shear stress in concrete without shear reinforcement (working-stress)",
    IS456_DOCUMENT,
)
CITATION_MIN_STEEL = _clause(
    f"Minimum reinforcement {MIN_STEEL_PCT_GROSS:g}% of the gross section (HYSD)",
    IS456_DOCUMENT,
)
CITATION_COVER = _clause(
    f"Minimum clear cover {MIN_CLEAR_COVER_MM:g} mm for moderate exposure",
    IS456_DOCUMENT,
)

CODES = ["IRS Concrete Bridge Code", "IS 456", "IR Bridge Rules"]


# --------------------------------------------------------------------------- permissible tables
class ConcretePermissible(NamedTuple):
    """IS 456 working-stress permissible stresses for one concrete grade, N/mm^2."""

    grade: str
    sigma_cbc_n_mm2: float  # permissible flexural compressive stress (Table 21)
    tau_c_n_mm2: float  # permissible shear stress, nominal pt, no shear steel (Table 23)
    needs_verification: bool


class SteelPermissible(NamedTuple):
    """IS 456 working-stress permissible tensile stress for one steel grade, N/mm^2."""

    grade: str
    sigma_st_n_mm2: float  # Table 22, working-stress basis
    needs_verification: bool


CONCRETE_PERMISSIBLE: dict[ConcreteGrade, ConcretePermissible] = {
    ConcreteGrade.M25: ConcretePermissible("M25", 8.5, 0.36, True),
    ConcreteGrade.M30: ConcretePermissible("M30", 10.0, 0.40, True),
    ConcreteGrade.M35: ConcretePermissible("M35", 11.5, 0.44, True),
}
STEEL_PERMISSIBLE: dict[SteelGrade, SteelPermissible] = {
    SteelGrade.FE415: SteelPermissible("Fe415", 230.0, True),
    SteelGrade.FE500: SteelPermissible("Fe500", 275.0, True),
}


class WorkingStressConstants(NamedTuple):
    sigma_cbc: float
    sigma_st: float
    m: float
    k: float
    j: float
    q_n_mm2: float
    tau_c: float


def working_stress_constants(
    concrete: ConcreteGrade, steel: SteelGrade
) -> WorkingStressConstants:
    """Balanced working-stress section constants (m, k, j, Q) for the grade pair."""
    c = CONCRETE_PERMISSIBLE[concrete]
    s = STEEL_PERMISSIBLE[steel]
    m = 280.0 / (3.0 * c.sigma_cbc_n_mm2)
    k = m * c.sigma_cbc_n_mm2 / (m * c.sigma_cbc_n_mm2 + s.sigma_st_n_mm2)
    j = 1.0 - k / 3.0
    q = 0.5 * c.sigma_cbc_n_mm2 * k * j
    return WorkingStressConstants(
        sigma_cbc=c.sigma_cbc_n_mm2,
        sigma_st=s.sigma_st_n_mm2,
        m=m,
        k=k,
        j=j,
        q_n_mm2=q,
        tau_c=c.tau_c_n_mm2,
    )


# --------------------------------------------------------------------------- earth pressure
def rankine_ka(phi_deg: float) -> float:
    """Rankine active coefficient for a level backfill (beta = 0)."""
    phi = math.radians(phi_deg)
    return (1.0 - math.sin(phi)) / (1.0 + math.sin(phi))


def rankine_kp(phi_deg: float) -> float:
    """Rankine passive coefficient for a level surface."""
    phi = math.radians(phi_deg)
    return (1.0 + math.sin(phi)) / (1.0 - math.sin(phi))


def coulomb_ka(phi_deg: float, beta_deg: float, delta_deg: float, theta_deg: float = 0.0) -> float:
    """Coulomb active coefficient (theta = back-face angle from vertical,
    delta = wall friction, beta = backfill slope) — for the sloped-backfill case."""
    phi = math.radians(phi_deg)
    beta = math.radians(beta_deg)
    delta = math.radians(delta_deg)
    theta = math.radians(theta_deg)
    num = math.cos(phi - theta) ** 2
    root = math.sqrt(
        max(
            0.0,
            math.sin(phi + delta)
            * math.sin(phi - beta)
            / (math.cos(delta + theta) * math.cos(theta - beta)),
        )
    )
    den = (
        math.cos(theta) ** 2
        * math.cos(delta + theta)
        * (1.0 + root) ** 2
    )
    return num / den


def active_coefficient(phi_deg: float, beta_deg: float) -> tuple[float, str, str]:
    """(Ka, method, citation). Rankine when level; Coulomb (vertical virtual back,
    wall friction delta = beta) for a sloped backfill."""
    if beta_deg <= 0.0:
        return rankine_ka(phi_deg), "Rankine (level backfill)", CITATION_RANKINE
    return (
        coulomb_ka(phi_deg, beta_deg, delta_deg=beta_deg, theta_deg=0.0),
        "Coulomb (sloped backfill, vertical virtual back)",
        CITATION_COULOMB,
    )


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
