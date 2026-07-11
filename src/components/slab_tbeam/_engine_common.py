"""Shared engineering constants, permissible-stress tables and the calc-trail
recorder for the RCC slab / T-beam superstructure deck.

The RCC working-stress machinery (`working_stress_constants`,
`CONCRETE_PERMISSIBLE`, `STEEL_PERMISSIBLE`, the `Trail` recorder) is a
deliberate COPY of the retaining-wall engine's — the slab/T-beam slice keeps its
own copy so the two components stay independent (no cross-import). The deck-
specific constants (deck depth proportioning, the track SIDL allowance, the
lateral live-load distribution width, the span/effective-depth deflection limit)
are added here.

TRANSCRIPTION-HONESTY DISCIPLINE (same as the culvert / retaining-wall engines):
the permissible constants and the deck loading allowances carry
`needs_verification=True` — they are transcribed / assumed for the POC and must
be checked digit-for-digit against the source codes before demo day (IR engineer
pre-review required per spec).
"""

from __future__ import annotations

from typing import NamedTuple

from domain.culvert import CalcStep, ConcreteGrade, SteelGrade

# --------------------------------------------------------------------------- units / allowances
CONCRETE_UNIT_WEIGHT_KN_M3 = 25.0  # RCC self-weight, IS 456 / IS 875
ASSUMED_BAR_DIA_MM = 20.0  # effective-depth allowance: d = t - cover - dia/2
MIN_CLEAR_COVER_MM = 40.0  # IS 456 cl. 26.4 — moderate exposure minimum
MIN_STEEL_PCT_GROSS = 0.12  # IS 456 cl. 26.5.1 — HYSD minimum, % of gross area

# Superimposed dead load of the permanent way carried by a ballasted railway deck
# (ballast cushion + sleepers + rails + guard rails + services), taken as a
# uniform pressure over the deck. Transcribed/assumed for the POC.
TRACK_SIDL_KN_M2 = 12.0

# Lateral distribution width of one BG track's live load across the deck — the
# sleeper length plus a nominal dispersal. The full-track EUDL is shared over
# this width (capped at the actual deck width). Assumed for the POC.
TRACK_LATERAL_DISTRIBUTION_WIDTH_M = 3.0

# Deck-depth proportioning ratios (span / overall-depth). Solid slabs run about
# span/12 to span/15; a T-beam rib runs about span/10.
SOLID_SLAB_SPAN_DEPTH_RATIO = 12.0
TBEAM_RIB_SPAN_DEPTH_RATIO = 10.0
DECK_SLAB_MIN_THICKNESS_MM = 200.0  # minimum deck-slab (flange) thickness
RIB_MIN_WIDTH_MM = 300.0  # minimum rib (web) width

# IS 456 cl. 23.2.1 — basic span/effective-depth ratio for a simply supported
# member (deflection control, deemed-to-satisfy). No modification factor is
# applied at this level of design (conservative).
SPAN_DEPTH_DEFLECTION_LIMIT = 20.0

# The POC railway loading standard (IR Bridge Rules 25t Loading-2008).
LIVE_LOAD_STANDARD_NAME = "25t-2008"

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
    "User design requirement — validated against the RCC slab / T-beam deck range"
)
CITATION_PROPORTIONING = _clause(
    "Deck-depth proportioning (solid slab ~span/12-span/15; T-beam rib ~span/10; "
    "flexure/shear demand governs the final depth)",
    "IRS Concrete Bridge Code / IS 456 working-stress deck design",
)
CITATION_FLANGE = _clause(
    "Effective flange width of a T-beam bf = span/6 + bw + 6*Df, not exceeding the "
    "girder spacing",
    "IS 456 cl. 23.1.2",
)
CITATION_DEAD_LOAD = _clause(
    "Dead load = RCC self-weight (25 kN/m^3) + permanent-way superimposed dead load",
    IS456_DOCUMENT,
)
CITATION_LIVE_LOAD = _clause(
    "Live load — 25t Loading-2008 EUDL for bending moment / shear at the loaded "
    "length, amplified by the coefficient of dynamic augment (CDA)",
    IR_BRIDGE_RULES_DOCUMENT,
)
CITATION_DISTRIBUTION = _clause(
    "Lateral distribution of the track live load across the deck / to the T-beam "
    "ribs over an effective distribution width",
    "IRS Concrete Bridge Code deck-design practice",
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
CITATION_SHEAR_MAX = _clause(
    "Maximum permissible shear stress in concrete with shear reinforcement tau_c,max "
    "(working-stress); stirrups carry shear beyond tau_c",
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
CITATION_DEFLECTION = _clause(
    f"Span / effective-depth ratio <= {SPAN_DEPTH_DEFLECTION_LIMIT:g} (simply "
    "supported, deemed-to-satisfy deflection control)",
    "IS 456 cl. 23.2.1",
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

# IS 456 working-stress maximum shear stress in concrete WITH shear reinforcement
# (Table 23 "tau_c,max", N/mm^2). A section whose nominal shear stress exceeds this
# is inadequate even with stirrups. Girders (T-beams) carry shear via designed
# stirrups up to this cap; a solid slab is designed to need no shear steel (tau_c).
CONCRETE_TAU_C_MAX: dict[ConcreteGrade, float] = {
    ConcreteGrade.M25: 1.6,
    ConcreteGrade.M30: 1.8,
    ConcreteGrade.M35: 1.9,
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


def permissible_shear_stress(concrete: ConcreteGrade, deck_type: str) -> tuple[float, bool]:
    """(tau_permissible N/mm^2, has_shear_reinforcement) for the member.

    A solid slab is designed to carry shear on the concrete alone (tau_c, no
    stirrups). A T-beam girder carries shear on designed stirrups up to the
    maximum permissible shear stress tau_c,max.
    """
    if deck_type == "t_beam":
        return CONCRETE_TAU_C_MAX[concrete], True
    return CONCRETE_PERMISSIBLE[concrete].tau_c_n_mm2, False


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
