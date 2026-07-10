"""Load-case builder for the single-cell box frame (Phase 2, spec/capabilities/irs-engine.md).

Builds the elementary load cases (DL, FILL, SIDL, LL+CDA, earth pressure
at-rest/active, LL surcharge, water inside) and the IRS working-stress service
combinations (box empty / box full) on the 1 m-strip centreline frame model.
Pure deterministic Python — no LLM, no I/O. Live-load EUDL/CDA values come from
the pluggable `engine.loading` LoadingStandard (injected for tests, lazily
imported otherwise).

Sign conventions are normative in `domain.culvert` (LoadCase docstring):
slab UDLs positive toward the box interior, wall pressures positive inward.

TRANSCRIPTION NOTE (same honesty discipline as the loading-table slice): the
SIDL, dispersal, surcharge and unit-weight constants below are encoded from
IRS practice; verify each against the cited source document before demo day.
"""

import math

from pydantic import BaseModel, Field

from domain.culvert import (
    Assumption,
    BoxGeometry,
    CalcStep,
    CulvertParams,
    LoadCase,
    LoadCombination,
)
from engine.trail import TrailRecorder

# --- cited constants ---------------------------------------------------------

# IRS Bridge Rules — table of unit weights (reinforced concrete 2,500 kg/m^3).
GAMMA_CONCRETE_KN_M3 = 25.0
# IRS Bridge Rules unit weights (water 1,000 kg/m^3, adopted 10.0 kN/m^3 per
# IRICEN worked-example practice).
GAMMA_WATER_KN_M3 = 10.0
# Standard BG ballast cushion under the sleeper (IR Permanent Way practice).
BALLAST_DEPTH_M = 0.35
# IRS Bridge Rules unit weights — stone ballast ~1,900 kg/m^3.
GAMMA_BALLAST_KN_M3 = 19.0
# Permanent way (60 kg/m rail + PSC sleepers + fittings) per track — IRICEN value.
TRACK_PWAY_KN_PER_M = 6.5
# BG PSC sleeper length (lateral dispersal origin).
SLEEPER_LENGTH_M = 2.74
# IRS Bridge Rules Cl. 2.3.4.2 — dispersal through ballast/fill at 1/2 H : 1 V.
DISPERSAL_SLOPE_H_PER_V = 0.5
# EUDL tables are tabulated from 1 m loaded length — never interpolate below.
MIN_LOADED_LENGTH_M = 1.0
# IRS Bridge Substructure & Foundation Code — equivalent live-load surcharge for
# BG: 13.7 t per metre length distributed over 3.0 m width at formation level.
LL_SURCHARGE_FORMATION_KN_M2 = 13.7 * 9.80665 / 3.0

CITATION_UNIT_WEIGHTS = (
    "IRS Bridge Rules — table of unit weights of materials (RCC 25.0 kN/m^3, "
    "stone ballast 19.0 kN/m^3, water 10.0 kN/m^3) [verify transcription before demo]"
)
CITATION_SIDL = (
    "IR Permanent Way practice — 350 mm BG ballast cushion; P.Way dead load 6.5 kN/m "
    "per track (60 kg/m rail, PSC sleepers) per IRICEN course material "
    "[verify transcription before demo]"
)
CITATION_DISPERSAL = (
    "IRS Bridge Rules Cl. 2.3.4.2 — sleeper load dispersal through ballast/fill at a "
    "slope of half horizontal to one vertical [verify transcription before demo]"
)
CITATION_EARTH_PRESSURE = (
    "IRS Bridge Substructure & Foundation Code — earth pressure: at-rest K0 = 1 - sin(phi) "
    "(Jaky), active Ka = (1 - sin(phi))/(1 + sin(phi)) (Rankine); fill above the box acts "
    "as surcharge on the pressure diagram"
)
CITATION_LL_SURCHARGE = (
    "IRS Bridge Substructure & Foundation Code — equivalent live-load surcharge for BG "
    "single line: 13.7 t/m over 3.0 m width at formation level "
    "[verify transcription before demo]"
)
CITATION_RIGID_BASE = (
    "IRICEN box-culvert design practice — rigid box on uniform subgrade: base reaction "
    "taken uniform under the bottom slab (classic rigid-base assumption)"
)
CITATION_COMBINATIONS = (
    "IRS working-stress (service) practice — unfactored combinations incl. box empty/full "
    "variants, per IRICEN box-culvert design examples"
)
CITATION_CENTRELINE_MODEL = (
    "Closed-frame analysis convention — members on centreline dimensions, 1 m strip "
    "(IRICEN box-culvert design course)"
)

CASE_DL = "DL"
CASE_FILL = "FILL"
CASE_SIDL = "SIDL"
CASE_LL = "LL+CDA"
CASE_EP_AT_REST = "EP_at_rest"
CASE_EP_ACTIVE = "EP_active"
CASE_LL_SURCHARGE = "LL_surcharge"
CASE_LL_SURCHARGE_ACTIVE = "LL_surcharge_active"
CASE_WATER = "WATER"


class LoadBuild(BaseModel):
    """Everything `build_load_cases` returns — cases, combinations, provenance."""

    cases: list[LoadCase] = Field(description="Elementary load cases, FE-rebuildable")
    combinations: list[LoadCombination] = Field(description="IRS working-stress combinations")
    assumptions: list[Assumption] = Field(description="Modelling assumptions made explicit")
    trail_steps: list[CalcStep] = Field(description="CalcSteps recorded while building the cases")


def frame_centreline_dimensions(geometry: BoxGeometry) -> tuple[float, float]:
    """(span, height) of the frame centrelines: clear opening + half a member each side."""
    span_c = geometry.clear_span_m + geometry.wall_thickness_mm / 1000.0
    height_c = geometry.clear_height_m + (
        geometry.top_slab_thickness_mm + geometry.bottom_slab_thickness_mm
    ) / 2.0 / 1000.0
    return span_c, height_c


def dispersed_loaded_length_m(span_centreline_m: float, cushion_m: float) -> float:
    """EUDL loaded length: frame span + dispersal through (cushion + ballast) both sides.

    Dispersal is additive (slope x depth per side) so it degrades gracefully to the
    span itself at zero cushion — it can never go negative. Floored at the EUDL
    table minimum of 1 m.
    """
    depth_m = cushion_m + BALLAST_DEPTH_M
    return max(
        MIN_LOADED_LENGTH_M, span_centreline_m + 2.0 * DISPERSAL_SLOPE_H_PER_V * depth_m
    )


def lateral_distribution_width_m(cushion_m: float, barrel_length_m: float) -> float:
    """Lateral spread of one track's load: sleeper length + dispersal, capped at the barrel."""
    depth_m = cushion_m + BALLAST_DEPTH_M
    return min(
        SLEEPER_LENGTH_M + 2.0 * DISPERSAL_SLOPE_H_PER_V * depth_m, barrel_length_m
    )


def build_load_cases(
    params: CulvertParams,
    geometry: BoxGeometry,
    *,
    loading_standard=None,
    trail: TrailRecorder | None = None,
) -> LoadBuild:
    """Build all elementary load cases + combinations for the 1 m-strip frame model.

    `loading_standard` follows the pinned `engine.loading` interface; when None it is
    resolved from `params.loading_standard` via `engine.loading.get_loading_standard`.
    Every computed number is recorded on `trail` (shared with the frame analysis when
    the caller passes its own recorder).
    """
    if loading_standard is None:
        from engine.loading import get_loading_standard

        loading_standard = get_loading_standard(params.loading_standard.value)

    trail = trail if trail is not None else TrailRecorder()
    start_index = len(trail.steps)
    assumptions: list[Assumption] = []
    span_c, height_c = frame_centreline_dimensions(geometry)

    trail.record(
        description="Frame span, wall centreline to wall centreline",
        formula="L_c = clear_span + t_wall / 1000",
        inputs={
            "clear_span_m": geometry.clear_span_m,
            "wall_thickness_mm": geometry.wall_thickness_mm,
        },
        value=span_c,
        unit="m",
        citation=CITATION_CENTRELINE_MODEL,
    )
    trail.record(
        description="Frame height, slab centreline to slab centreline",
        formula="H_c = clear_height + (t_top + t_bottom) / 2 / 1000",
        inputs={
            "clear_height_m": geometry.clear_height_m,
            "top_slab_thickness_mm": geometry.top_slab_thickness_mm,
            "bottom_slab_thickness_mm": geometry.bottom_slab_thickness_mm,
        },
        value=height_c,
        unit="m",
        citation=CITATION_CENTRELINE_MODEL,
    )

    cases = [
        _dead_load_case(geometry, span_c, height_c, trail),
        _fill_case(params, trail),
        _sidl_case(params, geometry, trail),
        _live_load_case(params, geometry, span_c, loading_standard, trail),
        *_earth_pressure_cases(params, geometry, height_c, trail),
        *_ll_surcharge_cases(params, trail),
        _water_case(geometry, height_c, trail),
    ]

    combinations = _combinations()

    assumptions.extend(
        [
            Assumption(
                field="base_reaction",
                value="uniform",
                source="engine_default",
                note=f"Uniform base reaction under the bottom slab — {CITATION_RIGID_BASE}.",
            ),
            Assumption(
                field="sidl_ballast",
                value=f"{BALLAST_DEPTH_M:g} m at {GAMMA_BALLAST_KN_M3:g} kN/m^3",
                source="engine_default",
                note=f"SIDL ballast cushion and unit weight — {CITATION_SIDL}.",
            ),
            Assumption(
                field="sidl_track",
                value=f"{TRACK_PWAY_KN_PER_M:g} kN/m per track",
                source="engine_default",
                note=f"Permanent-way dead load — {CITATION_SIDL}.",
            ),
            Assumption(
                field="ll_surcharge",
                value=round(LL_SURCHARGE_FORMATION_KN_M2, 3),
                source="engine_default",
                note=f"Equivalent live-load surcharge at formation — {CITATION_LL_SURCHARGE}.",
            ),
            Assumption(
                field="water_inside",
                value=f"{GAMMA_WATER_KN_M3:g} kN/m^3 to top-slab soffit",
                source="engine_default",
                note=(
                    "Box-full variant: water to the clear height at "
                    f"{GAMMA_WATER_KN_M3:g} kN/m^3 — {CITATION_UNIT_WEIGHTS}."
                ),
            ),
            Assumption(
                field="dispersal_slope",
                value=f"{DISPERSAL_SLOPE_H_PER_V:g}H:1V",
                source="engine_default",
                note=f"Live-load dispersal through ballast and fill — {CITATION_DISPERSAL}.",
            ),
        ]
    )

    return LoadBuild(
        cases=cases,
        combinations=combinations,
        assumptions=assumptions,
        trail_steps=trail.steps[start_index:],
    )


# --- individual cases --------------------------------------------------------


def _close_reaction(
    name: str,
    span_c: float,
    top_udl: float,
    wall_axial: float,
    bottom_applied: float,
    trail: TrailRecorder,
) -> tuple[float, float]:
    """Uniform base reaction closing vertical equilibrium; returns (reaction, net bottom)."""
    reaction = top_udl + 2.0 * wall_axial / span_c + bottom_applied
    trail.record(
        description=f"{name}: uniform base reaction closing vertical equilibrium",
        formula="q_base = w_top + 2 * P_wall / L_c + w_bottom_applied",
        inputs={
            "w_top_kn_m2": top_udl,
            "P_wall_kn_per_m": wall_axial,
            "w_bottom_applied_kn_m2": bottom_applied,
            "span_centreline_m": span_c,
        },
        value=reaction,
        unit="kN/m^2",
        citation=CITATION_RIGID_BASE,
    )
    net = reaction - bottom_applied
    trail.record(
        description=f"{name}: net upward load bending the bottom slab",
        formula="w_bottom_net = q_base - w_bottom_applied",
        inputs={"q_base_kn_m2": reaction, "w_bottom_applied_kn_m2": bottom_applied},
        value=net,
        unit="kN/m^2",
        citation=CITATION_RIGID_BASE,
    )
    return reaction, net


def _dead_load_case(
    geometry: BoxGeometry, span_c: float, height_c: float, trail: TrailRecorder
) -> LoadCase:
    top = trail.record(
        description="DL: top slab self-weight",
        formula="w = gamma_c * t_top / 1000",
        inputs={
            "gamma_c_kn_m3": GAMMA_CONCRETE_KN_M3,
            "top_slab_thickness_mm": geometry.top_slab_thickness_mm,
        },
        value=GAMMA_CONCRETE_KN_M3 * geometry.top_slab_thickness_mm / 1000.0,
        unit="kN/m^2",
        citation=CITATION_UNIT_WEIGHTS,
    )
    bottom = trail.record(
        description="DL: bottom slab self-weight",
        formula="w = gamma_c * t_bottom / 1000",
        inputs={
            "gamma_c_kn_m3": GAMMA_CONCRETE_KN_M3,
            "bottom_slab_thickness_mm": geometry.bottom_slab_thickness_mm,
        },
        value=GAMMA_CONCRETE_KN_M3 * geometry.bottom_slab_thickness_mm / 1000.0,
        unit="kN/m^2",
        citation=CITATION_UNIT_WEIGHTS,
    )
    wall = trail.record(
        description="DL: wall self-weight per wall (axial — no frame bending)",
        formula="P = gamma_c * t_wall / 1000 * H_c",
        inputs={
            "gamma_c_kn_m3": GAMMA_CONCRETE_KN_M3,
            "wall_thickness_mm": geometry.wall_thickness_mm,
            "height_centreline_m": height_c,
        },
        value=GAMMA_CONCRETE_KN_M3 * geometry.wall_thickness_mm / 1000.0 * height_c,
        unit="kN/m",
        citation=CITATION_UNIT_WEIGHTS,
    )
    reaction, net = _close_reaction(CASE_DL, span_c, top, wall, bottom, trail)
    return LoadCase(
        name=CASE_DL,
        description="Dead load — self-weight of the box members on centreline dimensions",
        top_slab_udl_kn_m2=top,
        wall_pressure_top_kn_m2=0.0,
        wall_pressure_bottom_kn_m2=0.0,
        wall_axial_kn_per_m=wall,
        bottom_slab_applied_udl_kn_m2=bottom,
        base_reaction_kn_m2=reaction,
        bottom_slab_net_udl_kn_m2=net,
        citations=[CITATION_UNIT_WEIGHTS, CITATION_RIGID_BASE, CITATION_CENTRELINE_MODEL],
        notes="Member weights on centreline dimensions; small corner overlap accepted.",
    )


def _fill_case(params: CulvertParams, trail: TrailRecorder) -> LoadCase:
    fill = trail.record(
        description="FILL: earth fill (cushion) on the top slab",
        formula="w = gamma_soil * cushion",
        inputs={
            "soil_unit_weight_kn_m3": params.soil_unit_weight_kn_m3,
            "cushion_m": params.cushion_m,
        },
        value=params.soil_unit_weight_kn_m3 * params.cushion_m,
        unit="kN/m^2",
        citation=CITATION_EARTH_PRESSURE,
    )
    return LoadCase(
        name=CASE_FILL,
        description="Earth fill (cushion) above the top slab, top of slab to formation",
        top_slab_udl_kn_m2=fill,
        wall_pressure_top_kn_m2=0.0,
        wall_pressure_bottom_kn_m2=0.0,
        wall_axial_kn_per_m=0.0,
        bottom_slab_applied_udl_kn_m2=0.0,
        base_reaction_kn_m2=fill,
        bottom_slab_net_udl_kn_m2=fill,
        citations=[CITATION_EARTH_PRESSURE, CITATION_RIGID_BASE],
        notes="Zero at zero cushion by construction.",
    )


def _sidl_case(
    params: CulvertParams, geometry: BoxGeometry, trail: TrailRecorder
) -> LoadCase:
    ballast = trail.record(
        description="SIDL: ballast pressure at formation",
        formula="w = d_ballast * gamma_ballast",
        inputs={
            "ballast_depth_m": BALLAST_DEPTH_M,
            "gamma_ballast_kn_m3": GAMMA_BALLAST_KN_M3,
        },
        value=BALLAST_DEPTH_M * GAMMA_BALLAST_KN_M3,
        unit="kN/m^2",
        citation=CITATION_SIDL,
    )
    width = trail.record(
        description="SIDL: lateral distribution width of the track load",
        formula="W = min(sleeper + 2 * slope * (cushion + ballast), barrel_length)",
        inputs={
            "sleeper_length_m": SLEEPER_LENGTH_M,
            "dispersal_slope_h_per_v": DISPERSAL_SLOPE_H_PER_V,
            "cushion_m": params.cushion_m,
            "ballast_depth_m": BALLAST_DEPTH_M,
            "barrel_length_m": geometry.barrel_length_m,
        },
        value=lateral_distribution_width_m(params.cushion_m, geometry.barrel_length_m),
        unit="m",
        citation=CITATION_DISPERSAL,
    )
    track = trail.record(
        description="SIDL: permanent-way (track) pressure dispersed over the lateral width",
        formula="w = P_way / W",
        inputs={"track_kn_per_m": TRACK_PWAY_KN_PER_M, "lateral_width_m": width},
        value=TRACK_PWAY_KN_PER_M / width,
        unit="kN/m^2",
        citation=CITATION_SIDL,
    )
    total = trail.record(
        description="SIDL: total superimposed dead load on the top slab",
        formula="w_SIDL = w_ballast + w_track",
        inputs={"w_ballast_kn_m2": ballast, "w_track_kn_m2": track},
        value=ballast + track,
        unit="kN/m^2",
        citation=CITATION_SIDL,
    )
    return LoadCase(
        name=CASE_SIDL,
        description="Superimposed dead load — ballast and permanent way on the top slab",
        top_slab_udl_kn_m2=total,
        wall_pressure_top_kn_m2=0.0,
        wall_pressure_bottom_kn_m2=0.0,
        wall_axial_kn_per_m=0.0,
        bottom_slab_applied_udl_kn_m2=0.0,
        base_reaction_kn_m2=total,
        bottom_slab_net_udl_kn_m2=total,
        citations=[CITATION_SIDL, CITATION_DISPERSAL, CITATION_RIGID_BASE],
        notes=f"Track load dispersed over {width:g} m lateral width.",
    )


def _live_load_case(
    params: CulvertParams,
    geometry: BoxGeometry,
    span_c: float,
    loading_standard,
    trail: TrailRecorder,
) -> LoadCase:
    loaded_length = trail.record(
        description="LL: dispersed loaded length for EUDL",
        formula="L_load = max(L_min, L_c + 2 * slope * (cushion + ballast))",
        inputs={
            "span_centreline_m": span_c,
            "dispersal_slope_h_per_v": DISPERSAL_SLOPE_H_PER_V,
            "cushion_m": params.cushion_m,
            "ballast_depth_m": BALLAST_DEPTH_M,
            "min_loaded_length_m": MIN_LOADED_LENGTH_M,
        },
        value=dispersed_loaded_length_m(span_c, params.cushion_m),
        unit="m",
        citation=CITATION_DISPERSAL,
    )
    width = trail.record(
        description="LL: lateral distribution width (never negative — additive dispersal)",
        formula="W = min(sleeper + 2 * slope * (cushion + ballast), barrel_length)",
        inputs={
            "sleeper_length_m": SLEEPER_LENGTH_M,
            "cushion_m": params.cushion_m,
            "ballast_depth_m": BALLAST_DEPTH_M,
            "barrel_length_m": geometry.barrel_length_m,
        },
        value=lateral_distribution_width_m(params.cushion_m, geometry.barrel_length_m),
        unit="m",
        citation=CITATION_DISPERSAL,
    )
    eudl_bm = trail.record(
        description="LL: EUDL for bending moment at the dispersed loaded length (per track)",
        formula="EUDL_BM = table(L_load)",
        inputs={"loaded_length_m": loaded_length, "tracks": params.tracks},
        value=loading_standard.eudl_bm_kn(loaded_length),
        unit="kN",
        citation=loading_standard.citation,
    )
    eudl_shear = trail.record(
        description="LL: EUDL for shear at the dispersed loaded length (per track) — "
        "recorded for the member-check slice",
        formula="EUDL_S = table(L_load)",
        inputs={"loaded_length_m": loaded_length},
        value=loading_standard.eudl_shear_kn(loaded_length),
        unit="kN",
        citation=loading_standard.citation,
    )
    cda = trail.record(
        description="LL: coefficient of dynamic augment incl. cushion reduction",
        formula="CDA = cda(L_load, cushion)",
        inputs={"loaded_length_m": loaded_length, "cushion_m": params.cushion_m},
        value=loading_standard.cda(loaded_length, params.cushion_m),
        unit="fraction",
        citation=loading_standard.citation,
    )
    intensity = trail.record(
        description="LL: design live-load intensity on the top slab incl. CDA",
        formula="w_LL = EUDL_BM * tracks * (1 + CDA) / (L_load * W)",
        inputs={
            "eudl_bm_kn": eudl_bm,
            "tracks": params.tracks,
            "cda": cda,
            "loaded_length_m": loaded_length,
            "lateral_width_m": width,
        },
        value=eudl_bm * params.tracks * (1.0 + cda) / (loaded_length * width),
        unit="kN/m^2",
        citation=loading_standard.citation,
    )
    return LoadCase(
        name=CASE_LL,
        description="25t Loading-2008 EUDL dispersed through the cushion, with CDA",
        top_slab_udl_kn_m2=intensity,
        wall_pressure_top_kn_m2=0.0,
        wall_pressure_bottom_kn_m2=0.0,
        wall_axial_kn_per_m=0.0,
        bottom_slab_applied_udl_kn_m2=0.0,
        base_reaction_kn_m2=intensity,
        bottom_slab_net_udl_kn_m2=intensity,
        citations=[loading_standard.citation, CITATION_DISPERSAL, CITATION_RIGID_BASE],
        notes=(
            f"Loaded length {loaded_length:g} m, lateral width {width:g} m, CDA {cda:g}. "
            f"EUDL(shear) {eudl_shear:g} kN recorded in the trail for the checks slice; "
            "frame analysis uses EUDL(BM)."
        ),
    )


def _earth_pressure_cases(
    params: CulvertParams, geometry: BoxGeometry, height_c: float, trail: TrailRecorder
) -> list[LoadCase]:
    phi = math.radians(params.angle_of_friction_deg)
    k0 = trail.record(
        description="Earth pressure coefficient at rest (Jaky)",
        formula="K0 = 1 - sin(phi)",
        inputs={"angle_of_friction_deg": params.angle_of_friction_deg},
        value=1.0 - math.sin(phi),
        unit="-",
        citation=CITATION_EARTH_PRESSURE,
    )
    ka = trail.record(
        description="Active earth pressure coefficient (Rankine)",
        formula="Ka = (1 - sin(phi)) / (1 + sin(phi))",
        inputs={"angle_of_friction_deg": params.angle_of_friction_deg},
        value=(1.0 - math.sin(phi)) / (1.0 + math.sin(phi)),
        unit="-",
        citation=CITATION_EARTH_PRESSURE,
    )
    depth_top = trail.record(
        description="Fill depth from formation to the top-slab centreline (top wall node)",
        formula="z_top = cushion + t_top / 2 / 1000",
        inputs={
            "cushion_m": params.cushion_m,
            "top_slab_thickness_mm": geometry.top_slab_thickness_mm,
        },
        value=params.cushion_m + geometry.top_slab_thickness_mm / 2.0 / 1000.0,
        unit="m",
        citation=CITATION_EARTH_PRESSURE,
    )
    depth_bottom = trail.record(
        description="Fill depth from formation to the bottom-slab centreline (bottom wall node)",
        formula="z_bottom = z_top + H_c",
        inputs={"z_top_m": depth_top, "height_centreline_m": height_c},
        value=depth_top + height_c,
        unit="m",
        citation=CITATION_EARTH_PRESSURE,
    )

    cases: list[LoadCase] = []
    for name, coefficient, label in (
        (CASE_EP_AT_REST, k0, "at rest (K0)"),
        (CASE_EP_ACTIVE, ka, "active (Ka)"),
    ):
        p_top = trail.record(
            description=f"{name}: wall pressure at the top node, earth {label}",
            formula="p = K * gamma_soil * z_top",
            inputs={
                "K": coefficient,
                "soil_unit_weight_kn_m3": params.soil_unit_weight_kn_m3,
                "z_top_m": depth_top,
            },
            value=coefficient * params.soil_unit_weight_kn_m3 * depth_top,
            unit="kN/m^2",
            citation=CITATION_EARTH_PRESSURE,
        )
        p_bottom = trail.record(
            description=f"{name}: wall pressure at the bottom node, earth {label}",
            formula="p = K * gamma_soil * z_bottom",
            inputs={
                "K": coefficient,
                "soil_unit_weight_kn_m3": params.soil_unit_weight_kn_m3,
                "z_bottom_m": depth_bottom,
            },
            value=coefficient * params.soil_unit_weight_kn_m3 * depth_bottom,
            unit="kN/m^2",
            citation=CITATION_EARTH_PRESSURE,
        )
        cases.append(
            LoadCase(
                name=name,
                description=f"Lateral earth pressure {label} on both walls, fill as surcharge",
                top_slab_udl_kn_m2=0.0,
                wall_pressure_top_kn_m2=p_top,
                wall_pressure_bottom_kn_m2=p_bottom,
                wall_axial_kn_per_m=0.0,
                bottom_slab_applied_udl_kn_m2=0.0,
                base_reaction_kn_m2=0.0,
                bottom_slab_net_udl_kn_m2=0.0,
                citations=[CITATION_EARTH_PRESSURE],
                notes="Trapezoid varies linearly between the node pressures.",
            )
        )
    return cases


def _ll_surcharge_cases(params: CulvertParams, trail: TrailRecorder) -> list[LoadCase]:
    phi = math.radians(params.angle_of_friction_deg)
    surcharge = trail.record(
        description="Equivalent live-load surcharge at formation level (BG single line)",
        formula="q_s = 13.7 t/m * g / 3.0 m",
        inputs={"surcharge_t_per_m": 13.7, "distribution_width_m": 3.0},
        value=LL_SURCHARGE_FORMATION_KN_M2,
        unit="kN/m^2",
        citation=CITATION_LL_SURCHARGE,
    )
    cases: list[LoadCase] = []
    for name, coefficient, label in (
        (CASE_LL_SURCHARGE, 1.0 - math.sin(phi), "K0 (with at-rest earth pressure)"),
        (
            CASE_LL_SURCHARGE_ACTIVE,
            (1.0 - math.sin(phi)) / (1.0 + math.sin(phi)),
            "Ka (with active earth pressure)",
        ),
    ):
        pressure = trail.record(
            description=f"{name}: uniform wall pressure from the live-load surcharge, {label}",
            formula="p = K * q_s",
            inputs={"K": coefficient, "q_s_kn_m2": surcharge},
            value=coefficient * surcharge,
            unit="kN/m^2",
            citation=CITATION_LL_SURCHARGE,
        )
        cases.append(
            LoadCase(
                name=name,
                description=f"Live-load surcharge on both walls, {label}",
                top_slab_udl_kn_m2=0.0,
                wall_pressure_top_kn_m2=pressure,
                wall_pressure_bottom_kn_m2=pressure,
                wall_axial_kn_per_m=0.0,
                bottom_slab_applied_udl_kn_m2=0.0,
                base_reaction_kn_m2=0.0,
                bottom_slab_net_udl_kn_m2=0.0,
                citations=[CITATION_LL_SURCHARGE, CITATION_EARTH_PRESSURE],
                notes="Uniform with depth (conservative worked-example simplification).",
            )
        )
    return cases


def _water_case(geometry: BoxGeometry, height_c: float, trail: TrailRecorder) -> LoadCase:
    pressure_bottom = trail.record(
        description="WATER: hydrostatic pressure at the bottom node (box full to soffit), "
        "outward on the walls",
        formula="p = -gamma_w * H_clear",
        inputs={
            "gamma_w_kn_m3": GAMMA_WATER_KN_M3,
            "clear_height_m": geometry.clear_height_m,
        },
        value=-GAMMA_WATER_KN_M3 * geometry.clear_height_m,
        unit="kN/m^2",
        citation=CITATION_UNIT_WEIGHTS,
    )
    weight = trail.record(
        description="WATER: water weight on the bottom slab (cancelled by the base reaction)",
        formula="w = gamma_w * H_clear",
        inputs={
            "gamma_w_kn_m3": GAMMA_WATER_KN_M3,
            "clear_height_m": geometry.clear_height_m,
        },
        value=GAMMA_WATER_KN_M3 * geometry.clear_height_m,
        unit="kN/m^2",
        citation=CITATION_UNIT_WEIGHTS,
    )
    return LoadCase(
        name=CASE_WATER,
        description="Box full — water inside to the top-slab soffit (outward wall pressure)",
        top_slab_udl_kn_m2=0.0,
        wall_pressure_top_kn_m2=0.0,
        wall_pressure_bottom_kn_m2=pressure_bottom,
        wall_axial_kn_per_m=0.0,
        bottom_slab_applied_udl_kn_m2=weight,
        base_reaction_kn_m2=weight,
        bottom_slab_net_udl_kn_m2=0.0,
        citations=[CITATION_UNIT_WEIGHTS, CITATION_RIGID_BASE],
        notes=(
            "Hydrostatic trapezoid applied over the centreline wall height (0 at the top "
            "node); water weight and its base reaction cancel — no net bottom bending."
        ),
    )


# --- combinations -------------------------------------------------------------


def _combinations() -> list[LoadCombination]:
    def combo(name: str, description: str, case_names: list[str]) -> LoadCombination:
        return LoadCombination(
            name=name,
            description=description,
            case_factors={case: 1.0 for case in case_names},
            citation=CITATION_COMBINATIONS,
        )

    permanent = [CASE_DL, CASE_FILL, CASE_SIDL]
    return [
        combo(
            "C1 Box empty - at-rest earth + LL",
            "Maximum vertical with at-rest lateral restraint, box empty",
            [*permanent, CASE_LL, CASE_EP_AT_REST, CASE_LL_SURCHARGE],
        ),
        combo(
            "C2 Box empty - active earth + LL",
            "Maximum vertical with minimum (active) lateral restraint — governs slab midspans",
            [*permanent, CASE_LL, CASE_EP_ACTIVE, CASE_LL_SURCHARGE_ACTIVE],
        ),
        combo(
            "C3 Box empty - at-rest earth, LL surcharge only",
            "Train approaching but not on the box — maximum lateral, minimum vertical",
            [*permanent, CASE_EP_AT_REST, CASE_LL_SURCHARGE],
        ),
        combo(
            "C4 Box full - at-rest earth + LL",
            "Box running full — water offsets the inward earth pressure",
            [*permanent, CASE_LL, CASE_EP_AT_REST, CASE_LL_SURCHARGE, CASE_WATER],
        ),
        combo(
            "C5 Box full - active earth, no LL",
            "Box full with minimum inward pressure — maximum outward wall bending",
            [*permanent, CASE_EP_ACTIVE, CASE_WATER],
        ),
    ]
