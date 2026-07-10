"""Dead + live-load analysis of the simply-supported welded plate girder.

Given `PlateGirderParams` and a proportioned `PlateGirderGeometry`, computes the
per-girder design bending moment and shear force from:

* **Dead load** — girder self-weight (steel at 78.5 kN/m^3 over the exact section
  area) plus a superimposed deck/track allowance, as a UDL over the span.
* **Live load** — 25t Loading-2008 EUDL for bending moment and for shear at a
  loaded length equal to the span, augmented by the coefficient of dynamic augment
  (CDA at zero cushion — an open deck), and shared equally across the girders.

From the design actions and the exact elastic section properties it derives the
extreme-fibre bending stress, the average web shear stress and the live-load
deflection, each against its working-stress permissible value / limit.

`compute_forces` is the pure numeric core (reused by the sizing loop);
`analyse_girder` wraps it with the CalcStep trail and Assumptions and returns the
`PlateGirderAnalysis` model the calc sheet, checks and proof-check consume.
"""

from __future__ import annotations

from typing import NamedTuple

from pydantic import BaseModel, Field

from components.base import Assumption, coerce
from components.plate_girder._engine_common import (
    CITATION_BENDING,
    CITATION_DEAD_LOAD,
    CITATION_DEFLECTION,
    CITATION_LIVE_LOAD,
    CITATION_SECTION,
    CITATION_SHEAR,
    CITATION_SLENDERNESS,
    DECK_DEAD_LOAD_KN_PER_M,
    DEFLECTION_LIMIT_RATIO,
    E_STEEL_MPA,
    STEEL_UNIT_WEIGHT_KN_M3,
    WEB_SLENDERNESS_LIMIT,
    Trail,
    permissible,
    section_properties,
)
from components.plate_girder.params import PlateGirderGeometry, PlateGirderParams
from engine.loading import get_loading_standard


class PlateGirderAnalysis(BaseModel):
    """Dead + live-load analysis of one plate girder — the rehydratable model.

    Field names are normative (calc sheet, checks, proof-check and summary read them).
    """

    loaded_length_m: float = Field(description="Loaded length for the live-load lookup, m")
    live_load_extrapolated: bool = Field(
        default=False, description="True when the EUDL was extrapolated beyond the tabulated range"
    )
    number_of_girders: int = Field(description="Girders sharing the track load")

    # --- dead load (per girder) ---
    self_weight_kn_m: float = Field(description="Girder self-weight UDL, kN/m")
    deck_load_kn_m: float = Field(description="Deck/track superimposed dead load per girder, kN/m")
    dead_load_kn_m: float = Field(description="Total dead-load UDL per girder, kN/m")
    dead_moment_knm: float = Field(description="Dead-load mid-span bending moment per girder, kN*m")
    dead_shear_kn: float = Field(description="Dead-load end shear per girder, kN")

    # --- live load ---
    eudl_bm_kn: float = Field(description="25t EUDL for bending moment (per track), kN")
    eudl_shear_kn: float = Field(description="25t EUDL for shear (per track), kN")
    cda: float = Field(description="Coefficient of dynamic augment applied to the live load")
    live_moment_knm: float = Field(description="Live-load + impact mid-span moment per girder, kN*m")
    live_shear_kn: float = Field(description="Live-load + impact end shear per girder, kN")

    # --- design actions (per girder) ---
    design_moment_knm: float = Field(description="Design bending moment per girder, kN*m")
    design_shear_kn: float = Field(description="Design shear force per girder, kN")

    # --- section properties ---
    section_area_mm2: float = Field(description="Cross-sectional area of one girder, mm^2")
    inertia_mm4: float = Field(description="Second moment of area, mm^4")
    section_modulus_cm3: float = Field(description="Elastic section modulus Z, cm^3")
    overall_depth_mm: float = Field(description="Overall girder depth, mm")

    # --- stresses & serviceability ---
    max_bending_stress_mpa: float = Field(description="Extreme-fibre bending stress, N/mm^2")
    permissible_bending_stress_mpa: float = Field(description="Permissible bending stress, N/mm^2")
    max_shear_stress_mpa: float = Field(description="Average web shear stress, N/mm^2")
    permissible_shear_stress_mpa: float = Field(description="Permissible average shear stress, N/mm^2")
    max_deflection_mm: float = Field(description="Live-load mid-span deflection, mm")
    deflection_limit_mm: float = Field(description="Deflection limit span/600, mm")
    web_slenderness: float = Field(description="Web depth / thickness ratio")
    web_slenderness_limit: float = Field(description="Permissible web slenderness")

    assumptions: list[Assumption] = Field(default_factory=list)
    trail: list = Field(default_factory=list, description="CalcStep trail")


def _lookup_eudl(standard, kind: str, length_m: float) -> tuple[float, bool]:
    """(EUDL kN, extrapolated?) — interpolate within the transcribed table, or
    honestly extrapolate beyond its last row using the tail slope (flagged so the
    caller records a `needs_verification` assumption for long spans)."""
    table = standard.eudl_bm_table() if kind == "bm" else standard.eudl_shear_table()
    lookup = standard.eudl_bm_kn if kind == "bm" else standard.eudl_shear_kn
    last_length = table[-1].loaded_length_m
    if length_m <= last_length:
        return lookup(length_m), False
    lower, upper = table[-2], table[-1]
    slope = (upper.eudl_kn - lower.eudl_kn) / (upper.loaded_length_m - lower.loaded_length_m)
    return upper.eudl_kn + slope * (length_m - last_length), True


class ForceCore(NamedTuple):
    """The pure numeric analysis result (no trail) — shared by sizing + analyse."""

    loaded_length_m: float
    live_load_extrapolated: bool
    number_of_girders: int
    self_weight_kn_m: float
    deck_load_kn_m: float
    dead_load_kn_m: float
    dead_moment_knm: float
    dead_shear_kn: float
    eudl_bm_kn: float
    eudl_shear_kn: float
    cda: float
    live_moment_knm: float
    live_shear_kn: float
    design_moment_knm: float
    design_shear_kn: float
    section_area_mm2: float
    inertia_mm4: float
    section_modulus_mm3: float
    overall_depth_mm: float
    max_bending_stress_mpa: float
    permissible_bending_stress_mpa: float
    max_shear_stress_mpa: float
    permissible_shear_stress_mpa: float
    max_deflection_mm: float
    deflection_limit_mm: float
    web_slenderness: float


def compute_forces(
    params: PlateGirderParams, geometry: PlateGirderGeometry
) -> ForceCore:
    """Deterministic dead + live-load actions, stresses and deflection for a girder."""
    span_m = geometry.span_mm / 1000.0
    span_mm = geometry.span_mm
    n = geometry.number_of_girders
    perm = permissible(params.steel_grade)

    section = section_properties(
        web_depth_mm=geometry.web_depth_mm,
        web_thickness_mm=geometry.web_thickness_mm,
        flange_width_mm=geometry.flange_width_mm,
        flange_thickness_mm=geometry.flange_thickness_mm,
    )

    # --- dead load (per girder) ---
    self_weight = section.area_mm2 * 1e-6 * STEEL_UNIT_WEIGHT_KN_M3  # kN/m
    deck_load = DECK_DEAD_LOAD_KN_PER_M / n  # kN/m per girder
    dead_udl = self_weight + deck_load
    dead_moment = dead_udl * span_m**2 / 8.0
    dead_shear = dead_udl * span_m / 2.0

    # --- live load: 25t EUDL at loaded length = span, with CDA, shared per girder ---
    loaded_length_m = span_m
    standard = get_loading_standard(params.loading_standard.value)
    eudl_bm, extrap_bm = _lookup_eudl(standard, "bm", loaded_length_m)
    eudl_shear, extrap_shear = _lookup_eudl(standard, "shear", loaded_length_m)
    live_load_extrapolated = extrap_bm or extrap_shear
    cda = standard.cda(loaded_length_m, 0.0)  # open deck — no cushion reduction

    # EUDL is the total equivalent load W: M_max = W*L/8, V_max = W/2 (end shear).
    live_moment = eudl_bm * (1.0 + cda) * span_m / 8.0 / n
    live_shear = eudl_shear * (1.0 + cda) / 2.0 / n

    # --- design actions ---
    design_moment = dead_moment + live_moment
    design_shear = dead_shear + live_shear

    # --- stresses ---
    bending_stress = design_moment * 1e6 / section.section_modulus_mm3  # N/mm^2
    web_area = geometry.web_depth_mm * geometry.web_thickness_mm  # mm^2
    shear_stress = design_shear * 1e3 / web_area  # N/mm^2

    # --- live-load deflection (UDL-equivalent of the live EUDL over the span) ---
    live_udl_per_girder_n_mm = eudl_bm * (1.0 + cda) / n * 1e3 / span_mm  # N/mm
    deflection = (
        5.0 * live_udl_per_girder_n_mm * span_mm**4
        / (384.0 * E_STEEL_MPA * section.inertia_mm4)
    )
    deflection_limit = span_mm / DEFLECTION_LIMIT_RATIO

    web_slenderness = geometry.web_depth_mm / geometry.web_thickness_mm

    return ForceCore(
        loaded_length_m=loaded_length_m,
        live_load_extrapolated=live_load_extrapolated,
        number_of_girders=n,
        self_weight_kn_m=self_weight,
        deck_load_kn_m=deck_load,
        dead_load_kn_m=dead_udl,
        dead_moment_knm=dead_moment,
        dead_shear_kn=dead_shear,
        eudl_bm_kn=eudl_bm,
        eudl_shear_kn=eudl_shear,
        cda=cda,
        live_moment_knm=live_moment,
        live_shear_kn=live_shear,
        design_moment_knm=design_moment,
        design_shear_kn=design_shear,
        section_area_mm2=section.area_mm2,
        inertia_mm4=section.inertia_mm4,
        section_modulus_mm3=section.section_modulus_mm3,
        overall_depth_mm=section.overall_depth_mm,
        max_bending_stress_mpa=bending_stress,
        permissible_bending_stress_mpa=perm.sigma_bending_n_mm2,
        max_shear_stress_mpa=shear_stress,
        permissible_shear_stress_mpa=perm.sigma_shear_n_mm2,
        max_deflection_mm=deflection,
        deflection_limit_mm=deflection_limit,
        web_slenderness=web_slenderness,
    )


def analyse_girder(
    params: PlateGirderParams, geometry: PlateGirderGeometry
) -> PlateGirderAnalysis:
    """Full analysis with the CalcStep trail + modelling assumptions."""
    params = coerce(PlateGirderParams, params)
    geometry = coerce(PlateGirderGeometry, geometry)
    core = compute_forces(params, geometry)
    trail = Trail("A")

    span_m = geometry.span_mm / 1000.0

    trail.record(
        description="Girder self-weight UDL (steel section)",
        formula="w_sw = A_section * gamma_steel",
        inputs={
            "A_section_mm2": round(core.section_area_mm2, 1),
            "gamma_steel_kn_m3": STEEL_UNIT_WEIGHT_KN_M3,
        },
        value=round(core.self_weight_kn_m, 4),
        unit="kN/m",
        citation=CITATION_DEAD_LOAD,
    )
    trail.record(
        description="Superimposed deck/track dead load per girder",
        formula="w_deck = deck_allowance / number_of_girders",
        inputs={
            "deck_allowance_kn_m": DECK_DEAD_LOAD_KN_PER_M,
            "number_of_girders": core.number_of_girders,
        },
        value=round(core.deck_load_kn_m, 4),
        unit="kN/m",
        citation=CITATION_DEAD_LOAD,
    )
    trail.record(
        description="Dead-load bending moment per girder",
        formula="M_dl = w_dl * L^2 / 8",
        inputs={"w_dl_kn_m": round(core.dead_load_kn_m, 4), "L_m": round(span_m, 3)},
        value=round(core.dead_moment_knm, 3),
        unit="kN*m",
        citation=CITATION_DEAD_LOAD,
    )
    trail.record(
        description="Live load: EUDL for bending moment (per track)",
        formula="EUDL(BM) at loaded length L from the 25t-2008 table",
        inputs={"loaded_length_m": round(core.loaded_length_m, 3)},
        value=round(core.eudl_bm_kn, 3),
        unit="kN",
        citation=CITATION_LIVE_LOAD,
    )
    trail.record(
        description="Live load: EUDL for shear (per track)",
        formula="EUDL(shear) at loaded length L from the 25t-2008 table",
        inputs={"loaded_length_m": round(core.loaded_length_m, 3)},
        value=round(core.eudl_shear_kn, 3),
        unit="kN",
        citation=CITATION_LIVE_LOAD,
    )
    trail.record(
        description="Live load: coefficient of dynamic augment",
        formula="CDA = 0.15 + 8/(6+L), open deck (no cushion reduction)",
        inputs={"loaded_length_m": round(core.loaded_length_m, 3), "cushion_m": 0.0},
        value=round(core.cda, 4),
        unit="-",
        citation=CITATION_LIVE_LOAD,
    )
    trail.record(
        description="Live-load bending moment per girder (with impact)",
        formula="M_ll = EUDL(BM) * (1 + CDA) * L / 8 / n",
        inputs={
            "eudl_bm_kn": round(core.eudl_bm_kn, 3),
            "cda": round(core.cda, 4),
            "L_m": round(span_m, 3),
            "n": core.number_of_girders,
        },
        value=round(core.live_moment_knm, 3),
        unit="kN*m",
        citation=CITATION_LIVE_LOAD,
    )
    trail.record(
        description="Design bending moment per girder",
        formula="M = M_dl + M_ll",
        inputs={
            "M_dl_knm": round(core.dead_moment_knm, 3),
            "M_ll_knm": round(core.live_moment_knm, 3),
        },
        value=round(core.design_moment_knm, 3),
        unit="kN*m",
        citation=CITATION_LIVE_LOAD,
    )
    trail.record(
        description="Design shear force per girder",
        formula="V = w_dl*L/2 + EUDL(shear)*(1+CDA)/2/n",
        inputs={
            "V_dl_kn": round(core.dead_shear_kn, 3),
            "V_ll_kn": round(core.live_shear_kn, 3),
        },
        value=round(core.design_shear_kn, 3),
        unit="kN",
        citation=CITATION_LIVE_LOAD,
    )
    trail.record(
        description="Elastic section modulus of the welded I-section",
        formula="Z = I / (D/2)",
        inputs={
            "I_mm4": round(core.inertia_mm4, 0),
            "overall_depth_mm": round(core.overall_depth_mm, 1),
        },
        value=round(core.section_modulus_mm3 / 1000.0, 1),
        unit="cm^3",
        citation=CITATION_SECTION,
    )
    trail.record(
        description="Extreme-fibre bending stress",
        formula="sigma_b = M / Z",
        inputs={
            "M_knm": round(core.design_moment_knm, 3),
            "Z_cm3": round(core.section_modulus_mm3 / 1000.0, 1),
        },
        value=round(core.max_bending_stress_mpa, 3),
        unit="N/mm^2",
        citation=CITATION_BENDING,
    )
    trail.record(
        description="Average web shear stress",
        formula="tau = V / (d_web * t_web)",
        inputs={
            "V_kn": round(core.design_shear_kn, 3),
            "d_web_mm": geometry.web_depth_mm,
            "t_web_mm": geometry.web_thickness_mm,
        },
        value=round(core.max_shear_stress_mpa, 3),
        unit="N/mm^2",
        citation=CITATION_SHEAR,
    )
    trail.record(
        description="Live-load mid-span deflection",
        formula="delta = 5 * w_ll * L^4 / (384 * E * I)",
        inputs={
            "E_n_mm2": E_STEEL_MPA,
            "I_mm4": round(core.inertia_mm4, 0),
            "L_m": round(span_m, 3),
        },
        value=round(core.max_deflection_mm, 3),
        unit="mm",
        citation=CITATION_DEFLECTION,
    )
    trail.record(
        description="Web slenderness ratio",
        formula="lambda_w = d_web / t_web",
        inputs={"d_web_mm": geometry.web_depth_mm, "t_web_mm": geometry.web_thickness_mm},
        value=round(core.web_slenderness, 2),
        unit="-",
        citation=CITATION_SLENDERNESS,
    )

    assumptions = [
        Assumption(
            field="steel_unit_weight_kn_m3",
            value=STEEL_UNIT_WEIGHT_KN_M3,
            source="engine_default",
            note=f"Structural steel self-weight taken as {STEEL_UNIT_WEIGHT_KN_M3:g} kN/m^3 (IS 800 / IS 875).",
        ),
        Assumption(
            field="deck_dead_load_kn_m",
            value=DECK_DEAD_LOAD_KN_PER_M,
            source="engine_default",
            note=(
                f"Superimposed deck/track dead load taken as {DECK_DEAD_LOAD_KN_PER_M:g} kN/m per "
                "track (deck slab/trough, ballast, track, services) — a transcribed allowance "
                "pending verification against the deck detail."
            ),
        ),
        Assumption(
            field="live_load_distribution",
            value=f"1/{core.number_of_girders} per girder",
            source="engine_default",
            note=(
                "The single-track 25t live load (with CDA) is shared equally across the "
                f"{core.number_of_girders} main girders — a simplified even distribution; a "
                "grillage/eccentricity analysis is beyond this POC scope."
            ),
        ),
    ]
    if core.live_load_extrapolated:
        assumptions.append(Assumption(
            field="eudl_extrapolated_needs_verification",
            value=f"L = {core.loaded_length_m:g} m",
            source="engine_default",
            note=(
                f"The loaded length {core.loaded_length_m:g} m exceeds the transcribed 25t-2008 "
                "EUDL table (max 30 m); the EUDL was extrapolated using the tail slope of the "
                "table — an ASSUMED value that NEEDS VERIFICATION against a proper long-span "
                "live-load derivation before demo day (IRS Bridge Rules 25t Loading-2008)."
            ),
        ))

    return PlateGirderAnalysis(
        loaded_length_m=round(core.loaded_length_m, 4),
        live_load_extrapolated=core.live_load_extrapolated,
        number_of_girders=core.number_of_girders,
        self_weight_kn_m=round(core.self_weight_kn_m, 4),
        deck_load_kn_m=round(core.deck_load_kn_m, 4),
        dead_load_kn_m=round(core.dead_load_kn_m, 4),
        dead_moment_knm=round(core.dead_moment_knm, 4),
        dead_shear_kn=round(core.dead_shear_kn, 4),
        eudl_bm_kn=round(core.eudl_bm_kn, 4),
        eudl_shear_kn=round(core.eudl_shear_kn, 4),
        cda=round(core.cda, 6),
        live_moment_knm=round(core.live_moment_knm, 4),
        live_shear_kn=round(core.live_shear_kn, 4),
        design_moment_knm=round(core.design_moment_knm, 4),
        design_shear_kn=round(core.design_shear_kn, 4),
        section_area_mm2=round(core.section_area_mm2, 2),
        inertia_mm4=round(core.inertia_mm4, 2),
        section_modulus_cm3=round(core.section_modulus_mm3 / 1000.0, 3),
        overall_depth_mm=round(core.overall_depth_mm, 3),
        max_bending_stress_mpa=round(core.max_bending_stress_mpa, 4),
        permissible_bending_stress_mpa=round(core.permissible_bending_stress_mpa, 4),
        max_shear_stress_mpa=round(core.max_shear_stress_mpa, 4),
        permissible_shear_stress_mpa=round(core.permissible_shear_stress_mpa, 4),
        max_deflection_mm=round(core.max_deflection_mm, 4),
        deflection_limit_mm=round(core.deflection_limit_mm, 4),
        web_slenderness=round(core.web_slenderness, 4),
        web_slenderness_limit=WEB_SLENDERNESS_LIMIT,
        assumptions=assumptions,
        trail=trail.steps,
    )
