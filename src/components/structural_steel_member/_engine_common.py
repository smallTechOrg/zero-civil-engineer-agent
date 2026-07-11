"""Shared engineering constants, permissible-stress tables, section-property and
weld-group helpers, and the calc-trail recorder for the fabricated structural-steel
member component (IS 800 working-stress / IS 816 fillet welds).

Every constant names its source. The permissible stresses follow IS 800
working-stress (allowable-stress) practice and the IS 816 fillet-weld permissible
stress; each transcribed value carries `needs_verification=True` — it must be
checked digit-for-digit against the source codes before demo day (IR engineer
pre-review required per spec).

DESIGN METHOD (declared, consistent everywhere): **working-stress / allowable-
stress design** to IS 800. Section actions are elastic; member adequacy is a
permissible-stress comparison (axial, bending, shear) plus the IS 800 combined
axial+bending interaction and the IS 816 fillet-weld-group check.

The permissible axial compressive stress `sigma_ac` is COMPUTED from the
documented Merchant-Rankine formula (the same formula IS 800 used to generate its
`sigma_ac` table) and independently CROSS-CHECKED against a transcribed
`sigma_ac` table row for fy = 250 N/mm^2.

This module is deliberately SELF-CONTAINED (it imports from no other component
package) so the slice stays independent. It may reuse shared platform pieces
(`domain.culvert.CalcStep`).
"""

from __future__ import annotations

import math
from typing import NamedTuple

from domain.culvert import CalcStep

# --------------------------------------------------------------------------- units / materials
STEEL_UNIT_WEIGHT_KN_M3 = 78.5  # structural steel self-weight, IS 800
E_STEEL_MPA = 2.0e5  # Young's modulus of structural steel, N/mm^2 (IS 800)

# Merchant-Rankine constant used by IS 800 to generate the permissible axial
# compressive stress table (transcribed for the POC, pending verification).
MERCHANT_RANKINE_N = 1.4

# Effective-length factor for a fixed-free cantilever member (IS 800 Table for
# effective length of compression members).
CANTILEVER_EFFECTIVE_LENGTH_FACTOR = 2.0

# Compression-member slenderness ceiling KL/r (IS 800 — a member carrying loads
# resulting from dead + imposed loads).
SLENDERNESS_LIMIT = 180.0

# Fillet-weld throat = 0.707 x leg size (IS 816 — 45-degree fillet throat).
FILLET_THROAT_FACTOR = 0.707

# Permissible stress on the throat of a shop fillet weld, working-stress basis
# (IS 816). Transcribed for the POC, pending verification.
PERMISSIBLE_WELD_STRESS_MPA = 108.0

# --------------------------------------------------------------------------- citations
VERIFY_BANNER = (
    "TRANSCRIPTION FOR DEMO — verify each value against the cited source before "
    "demo day (IR engineer pre-review required per spec)"
)
IS800_DOCUMENT = (
    "IS 800 — General Construction in Steel, Code of Practice, Bureau of Indian "
    "Standards (working-stress / allowable-stress design method)"
)
IS816_DOCUMENT = (
    "IS 816 — Code of Practice for Use of Metal Arc Welding for General "
    "Construction in Mild Steel, Bureau of Indian Standards (working-stress "
    "fillet-weld permissible stress)"
)


def _clause(head: str, document: str) -> str:
    return f"{head} — {document} [clause/table pending verification]. {VERIFY_BANNER}."


CITATION_USER_INPUT = (
    "User design requirement — validated against the fabricated steel-member range"
)
CITATION_PROPORTIONING = _clause(
    "Fabricated steel-member proportioning (cantilever depth from the moment and "
    "length, web thickness shear/slenderness-governed, flanges from the required "
    "section modulus, flange width from the compression-slenderness limit)",
    IS800_DOCUMENT,
)
CITATION_DEAD_LOAD = _clause(
    "Member self-weight (steel at 78.5 kN/m^3) as a distributed action along the "
    "cantilever",
    IS800_DOCUMENT,
)
CITATION_ACTIONS = _clause(
    "Cantilever design actions in member-local axes: bending M = P*L + self-weight, "
    "shear V, and the co-existent axial force N",
    IS800_DOCUMENT,
)
CITATION_SECTION = _clause(
    "Elastic section properties of a doubly-symmetric welded I-section "
    "(I_xx, Z = I_xx/(D/2), I_yy, r_min = sqrt(I_yy/A))",
    IS800_DOCUMENT,
)
CITATION_AXIAL = _clause(
    "Permissible axial compressive stress sigma_ac from the Merchant-Rankine formula "
    "(fcc = pi^2 E/lambda^2, n = 1.4), working-stress basis, cross-checked against the "
    "transcribed sigma_ac table",
    IS800_DOCUMENT,
)
CITATION_BENDING = _clause(
    "Permissible bending compressive stress, working-stress basis "
    "(sigma_bc = 0.66 fy, laterally restrained)",
    IS800_DOCUMENT,
)
CITATION_SHEAR = _clause(
    "Permissible average shear stress in the web, working-stress basis "
    "(tau_va = 0.40 fy)",
    IS800_DOCUMENT,
)
CITATION_COMBINED = _clause(
    "Combined axial + bending interaction "
    "(sigma_ac,cal/sigma_ac + sigma_bc,cal/sigma_bc <= 1.0)",
    IS800_DOCUMENT,
)
CITATION_SLENDERNESS = _clause(
    f"Compression-member slenderness KL/r <= {SLENDERNESS_LIMIT:g} "
    "(cantilever effective length K = 2.0)",
    IS800_DOCUMENT,
)
CITATION_WELD = _clause(
    "Fillet-weld group check: throat stress from the combined normal (axial + "
    "bending) and shear actions vs the permissible fillet-weld stress",
    IS816_DOCUMENT,
)
CITATION_WELD_SIZE = _clause(
    "Fillet-weld leg not exceeding the thickness of the thinner part joined; "
    "minimum weld size vs the thicker part",
    IS816_DOCUMENT,
)

CODES = ["IS 800", "IS 816"]


# --------------------------------------------------------------------------- permissible table
class SteelPermissible(NamedTuple):
    """Working-stress permissible stresses for one structural-steel grade, N/mm^2."""

    grade: str
    fy_n_mm2: float  # yield stress
    sigma_bending_n_mm2: float  # permissible bending compressive stress (~0.66 fy)
    sigma_shear_n_mm2: float  # permissible average web shear stress (~0.40 fy)
    needs_verification: bool


STEEL_PERMISSIBLE: dict[str, SteelPermissible] = {
    "E250": SteelPermissible("E250", 250.0, 165.0, 100.0, True),
    "E350": SteelPermissible("E350", 350.0, 231.0, 140.0, True),
}


def permissible(steel_grade: str) -> SteelPermissible:
    """Permissible-stress row for a steel grade — raises KeyError if untranscribed."""
    return STEEL_PERMISSIBLE[steel_grade]


# Transcribed IS 800 permissible axial compressive stress sigma_ac (N/mm^2) vs
# slenderness lambda = KL/r, for fy = 250 N/mm^2. Used ONLY as an independent
# cross-check of the Merchant-Rankine computation (and flagged needs_verification).
SIGMA_AC_TABLE_FY250: dict[int, float] = {
    0: 150.0, 10: 150.0, 20: 148.0, 30: 145.0, 40: 139.0, 50: 132.0,
    60: 122.0, 70: 112.0, 80: 101.0, 90: 90.0, 100: 80.0, 110: 72.0,
    120: 64.0, 130: 57.0, 140: 51.0, 150: 45.0, 160: 41.0, 170: 37.0, 180: 33.0,
}
SIGMA_AC_TABLE_NEEDS_VERIFICATION = True


def permissible_axial_stress(fy_n_mm2: float, slenderness: float) -> float:
    """Permissible axial compressive stress (N/mm^2) via the Merchant-Rankine
    formula IS 800 uses to tabulate sigma_ac: 0.6 * fcc*fy / (fcc^n + fy^n)^(1/n),
    with fcc = pi^2 E / lambda^2 the elastic critical (Euler) stress and n = 1.4."""
    if slenderness <= 1e-9:
        return 0.6 * fy_n_mm2
    fcc = math.pi**2 * E_STEEL_MPA / slenderness**2
    n = MERCHANT_RANKINE_N
    return 0.6 * (fcc * fy_n_mm2) / ((fcc**n + fy_n_mm2**n) ** (1.0 / n))


def sigma_ac_table_value(slenderness: float) -> float:
    """Linear interpolation of the transcribed fy=250 sigma_ac table at lambda."""
    lam = max(0.0, slenderness)
    keys = sorted(SIGMA_AC_TABLE_FY250)
    if lam >= keys[-1]:
        return SIGMA_AC_TABLE_FY250[keys[-1]]
    for lower, upper in zip(keys, keys[1:]):
        if lower <= lam <= upper:
            frac = (lam - lower) / (upper - lower) if upper != lower else 0.0
            return SIGMA_AC_TABLE_FY250[lower] + frac * (
                SIGMA_AC_TABLE_FY250[upper] - SIGMA_AC_TABLE_FY250[lower]
            )
    return SIGMA_AC_TABLE_FY250[keys[0]]


# Minimum fillet-weld size (mm) vs the thickness of the THICKER part joined —
# transcribed from IS 816 Table 1 (pending verification).
_MIN_WELD_SIZE_BANDS: tuple[tuple[float, float], ...] = (
    (10.0, 3.0),  # thicker part <= 10 mm
    (20.0, 5.0),  # 10 < t <= 20 mm
    (32.0, 6.0),  # 20 < t <= 32 mm
    (50.0, 8.0),  # 32 < t <= 50 mm
)
MIN_WELD_SIZE_NEEDS_VERIFICATION = True


def min_weld_size(thicker_part_mm: float) -> float:
    """IS 816 minimum fillet-weld leg for the thicker part joined (transcribed)."""
    for upper, size in _MIN_WELD_SIZE_BANDS:
        if thicker_part_mm <= upper:
            return size
    return 10.0


# --------------------------------------------------------------------------- section properties
class SectionProperties(NamedTuple):
    """Elastic properties of the doubly-symmetric welded I-section (mm-based)."""

    area_mm2: float
    inertia_xx_mm4: float  # strong-axis second moment (bending)
    section_modulus_mm3: float  # Z = I_xx / (D/2)
    inertia_yy_mm4: float  # weak-axis second moment (axial buckling)
    radius_of_gyration_min_mm: float  # r_min = sqrt(I_yy / A)
    overall_depth_mm: float


def section_properties(
    *,
    web_depth_mm: float,
    web_thickness_mm: float,
    flange_width_mm: float,
    flange_thickness_mm: float,
) -> SectionProperties:
    """Exact elastic properties of a doubly-symmetric welded I-section.

    `web_depth_mm` is the CLEAR web depth between flanges; the overall depth is
    `web_depth + 2 x flange_thickness`.
    """
    dw = web_depth_mm
    tw = web_thickness_mm
    bf = flange_width_mm
    tf = flange_thickness_mm
    overall = dw + 2.0 * tf
    area = tw * dw + 2.0 * bf * tf
    lever = (dw + tf) / 2.0
    inertia_xx = tw * dw**3 / 12.0 + 2.0 * (bf * tf**3 / 12.0 + bf * tf * lever**2)
    inertia_yy = dw * tw**3 / 12.0 + 2.0 * (tf * bf**3 / 12.0)
    modulus = inertia_xx / (overall / 2.0)
    r_min = math.sqrt(inertia_yy / area) if area > 0 else 0.0
    return SectionProperties(
        area_mm2=area,
        inertia_xx_mm4=inertia_xx,
        section_modulus_mm3=modulus,
        inertia_yy_mm4=inertia_yy,
        radius_of_gyration_min_mm=r_min,
        overall_depth_mm=overall,
    )


# --------------------------------------------------------------------------- weld group (lines)
class WeldGroupLineProperties(NamedTuple):
    """Unit-throat "weld treated as a line" properties of the base weld group.

    The member is fillet-welded to its base along both flanges (lines of length
    b_f at y = +/- D/2) and both web faces (lines of length d_w at the centroid).
    Multiply by the actual throat thickness to get area / inertia / modulus.
    """

    length_mm: float  # total weld line length
    inertia_line_mm3: float  # unit-throat I about the horizontal (bending) axis
    modulus_line_mm2: float  # unit-throat section modulus about that axis


def weld_group_line_props(
    *, overall_depth_mm: float, web_depth_mm: float, flange_width_mm: float
) -> WeldGroupLineProperties:
    """Unit-throat line properties of the base fillet-weld group."""
    d = overall_depth_mm
    dw = web_depth_mm
    bf = flange_width_mm
    length = 2.0 * bf + 2.0 * dw
    inertia_line = 2.0 * (bf * (d / 2.0) ** 2) + 2.0 * (dw**3 / 12.0)
    modulus_line = inertia_line / (d / 2.0)
    return WeldGroupLineProperties(
        length_mm=length, inertia_line_mm3=inertia_line, modulus_line_mm2=modulus_line
    )


class WeldStresses(NamedTuple):
    """Resolved fillet-weld throat stresses for the base weld group, N/mm^2."""

    throat_mm: float
    throat_area_mm2: float
    weld_modulus_mm3: float
    normal_stress_mpa: float  # from axial + bending (perpendicular to the throat)
    shear_stress_mpa: float  # from the transverse shear
    resultant_stress_mpa: float


def weld_stresses(
    *,
    weld_size_mm: float,
    overall_depth_mm: float,
    web_depth_mm: float,
    flange_width_mm: float,
    moment_knm: float,
    shear_kn: float,
    axial_kn: float,
) -> WeldStresses:
    """Combined fillet-weld-throat stresses for the base weld group.

    Normal component = axial/A_w + bending M/Z_w; shear component = V/A_w; the
    resultant is their vector sum (IS 816 combined-stress rule for fillet welds).
    """
    lines = weld_group_line_props(
        overall_depth_mm=overall_depth_mm,
        web_depth_mm=web_depth_mm,
        flange_width_mm=flange_width_mm,
    )
    throat = FILLET_THROAT_FACTOR * weld_size_mm
    area = throat * lines.length_mm
    modulus = throat * lines.modulus_line_mm2
    normal = (axial_kn * 1e3) / area + (moment_knm * 1e6) / modulus
    shear = (shear_kn * 1e3) / area
    resultant = math.hypot(normal, shear)
    return WeldStresses(
        throat_mm=throat,
        throat_area_mm2=area,
        weld_modulus_mm3=modulus,
        normal_stress_mpa=normal,
        shear_stress_mpa=shear,
        resultant_stress_mpa=resultant,
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
