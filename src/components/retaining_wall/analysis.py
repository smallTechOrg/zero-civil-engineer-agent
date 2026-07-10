"""Earth-pressure + stability analysis of the RCC cantilever retaining wall.

Given `RetainingWallParams` and a proportioned `RetainingWallGeometry`, computes
the active (Rankine level / Coulomb sloped) and passive earth pressures, the
vertical loads and their moments about the toe, the factors of safety against
overturning and sliding, and the base-pressure distribution — all per 1 m run of
wall. The virtual-back method is used: the active thrust acts on the vertical
plane through the heel over the full wall height H, and the soil column above the
heel is a stabilising vertical load.

`compute_stability` is the pure numeric core (reused by the sizing loop);
`analyse_wall` wraps it with the CalcStep trail and Assumptions and returns the
`RetainingWallAnalysis` model the calc sheet, checks and proof-check consume.

Sign / geometry convention (normative): x is measured horizontally from the toe
edge of the base (x = 0) toward the heel edge (x = B). The stem earth (back) face
is vertical at x = toe + stem_base; the exposed front face is battered. Moments
about the toe are positive when they resist overturning (stabilising).
"""

from __future__ import annotations

import math
from typing import NamedTuple

from pydantic import BaseModel, Field

from components.base import Assumption, coerce
from components.retaining_wall._engine_common import (
    CITATION_STABILITY,
    CITATION_SURCHARGE,
    CONCRETE_UNIT_WEIGHT_KN_M3,
    TRACK_SURCHARGE_EQUIVALENT_HEIGHT_M,
    Trail,
    active_coefficient,
    rankine_kp,
)
from components.retaining_wall.params import RetainingWallGeometry, RetainingWallParams


class VerticalLoad(BaseModel):
    """One stabilising vertical load and its lever arm about the toe."""

    name: str = Field(description="What this load represents")
    force_kn: float = Field(description="Vertical force per m run, kN")
    lever_arm_m: float = Field(description="Horizontal distance of its line of action from the toe, m")
    moment_knm: float = Field(description="Stabilising moment about the toe = force x lever arm, kN*m")


class RetainingWallAnalysis(BaseModel):
    """Earth-pressure + stability analysis — the rehydratable analysis model.

    Field names are normative (calc sheet, checks and proof-check read them).
    """

    ka: float = Field(description="Active earth-pressure coefficient")
    kp: float = Field(description="Passive earth-pressure coefficient")
    method: str = Field(description="Active-pressure method (Rankine / Coulomb)")
    surcharge_kn_m2: float = Field(description="Total equivalent uniform surcharge, kN/m^2")
    surcharge_equiv_height_m: float = Field(description="Surcharge as an equivalent height of fill, m")

    active_thrust_kn: float = Field(description="Total active thrust on the virtual back, kN/m")
    active_thrust_arm_m: float = Field(description="Height of the active thrust above the base, m")
    active_horizontal_kn: float = Field(description="Horizontal component of the active thrust, kN/m")
    active_vertical_kn: float = Field(description="Vertical component of the active thrust, kN/m")
    surcharge_thrust_kn: float = Field(description="Horizontal thrust from surcharge, kN/m")
    total_horizontal_kn: float = Field(description="Total destabilising horizontal force, kN/m")

    vertical_loads: list[VerticalLoad] = Field(description="Stabilising vertical loads")
    total_vertical_kn: float = Field(description="Sum of vertical loads (incl. active vertical comp), kN/m")
    resisting_moment_knm: float = Field(description="Total stabilising moment about the toe, kN*m/m")
    overturning_moment_knm: float = Field(description="Total overturning moment about the toe, kN*m/m")
    fos_overturning: float = Field(description="Factor of safety against overturning")

    passive_resistance_kn: float = Field(description="Passive resistance at the toe/key, kN/m")
    sliding_resistance_kn: float = Field(description="Base friction + passive resistance, kN/m")
    fos_sliding: float = Field(description="Factor of safety against sliding")

    resultant_from_toe_m: float = Field(description="Distance of the resultant from the toe, m")
    eccentricity_m: float = Field(description="Eccentricity of the resultant from the base centre, m")
    base_width_m: float = Field(description="Overall base width, m")
    max_base_pressure_kn_m2: float = Field(description="Maximum (toe) base pressure, kN/m^2")
    min_base_pressure_kn_m2: float = Field(description="Minimum (heel) base pressure, kN/m^2")

    stem_moment_knm: float = Field(description="Design bending moment at the stem base, kN*m/m")
    stem_shear_kn: float = Field(description="Design shear at the stem base, kN/m")

    assumptions: list[Assumption] = Field(default_factory=list)
    trail: list = Field(default_factory=list, description="CalcStep trail")


class StabilityCore(NamedTuple):
    """The pure numeric stability result (no trail) — shared by sizing + analyse."""

    ka: float
    kp: float
    method: str
    citation: str
    surcharge_kn_m2: float
    surcharge_equiv_height_m: float
    active_thrust_kn: float
    active_thrust_arm_m: float
    active_horizontal_kn: float
    active_vertical_kn: float
    surcharge_thrust_kn: float
    total_horizontal_kn: float
    vertical_loads: list[VerticalLoad]
    total_vertical_kn: float
    resisting_moment_knm: float
    overturning_moment_knm: float
    fos_overturning: float
    passive_resistance_kn: float
    sliding_resistance_kn: float
    fos_sliding: float
    resultant_from_toe_m: float
    eccentricity_m: float
    base_width_m: float
    max_base_pressure_kn_m2: float
    min_base_pressure_kn_m2: float
    stem_moment_knm: float
    stem_shear_kn: float
    stem_height_m: float


def total_surcharge(params: RetainingWallParams) -> tuple[float, float]:
    """(uniform surcharge kN/m^2, equivalent height of fill m) incl. track surcharge."""
    q = params.surcharge_kn_m2
    if params.track_surcharge:
        q += params.backfill_unit_weight_kn_m3 * TRACK_SURCHARGE_EQUIVALENT_HEIGHT_M
    equiv_height = q / params.backfill_unit_weight_kn_m3 if params.backfill_unit_weight_kn_m3 else 0.0
    return q, equiv_height


def compute_stability(
    params: RetainingWallParams, geometry: RetainingWallGeometry
) -> StabilityCore:
    """Deterministic earth-pressure + stability numbers for a given geometry."""
    gamma = params.backfill_unit_weight_kn_m3
    gamma_c = CONCRETE_UNIT_WEIGHT_KN_M3
    beta = params.backfill_slope_deg
    mu = params.base_friction_coeff

    ka, method, citation = active_coefficient(params.backfill_friction_angle_deg, beta)
    kp = rankine_kp(params.backfill_friction_angle_deg)

    h = geometry.total_height_mm / 1000.0
    db = geometry.base_thickness_mm / 1000.0
    hs = h - db
    lt = geometry.toe_length_mm / 1000.0
    lh = geometry.heel_length_mm / 1000.0
    ts_base = geometry.stem_base_thickness_mm / 1000.0
    ts_top = geometry.stem_top_thickness_mm / 1000.0
    b = geometry.base_width_mm / 1000.0
    key = geometry.key_depth_mm / 1000.0
    delta = ts_base - ts_top

    q, q_equiv = total_surcharge(params)

    # --- stabilising vertical loads and their moments about the toe ---
    loads: list[VerticalLoad] = []

    def _add(name: str, force: float, arm: float) -> None:
        loads.append(
            VerticalLoad(
                name=name,
                force_kn=round(force, 4),
                lever_arm_m=round(arm, 4),
                moment_knm=round(force * arm, 4),
            )
        )

    _add("Base slab", gamma_c * b * db, b / 2.0)
    _add("Stem (rectangular part)", gamma_c * ts_top * hs, lt + delta + ts_top / 2.0)
    if delta > 1e-9:
        _add("Stem (battered front)", gamma_c * 0.5 * delta * hs, lt + 2.0 * delta / 3.0)
    _add("Backfill over heel", gamma * lh * hs, b - lh / 2.0)
    if beta > 0.0:
        slope_wedge = gamma * 0.5 * lh * lh * math.tan(math.radians(beta))
        _add("Sloped backfill wedge", slope_wedge, b - lh / 3.0)

    # --- active thrust on the virtual back (through the heel), full height H ---
    active_thrust = 0.5 * ka * gamma * h * h
    active_arm = h / 3.0
    beta_rad = math.radians(beta)
    active_h = active_thrust * math.cos(beta_rad)
    active_v = active_thrust * math.sin(beta_rad)
    if active_v > 1e-9:
        # The vertical component of the inclined active thrust acts at the heel edge.
        loads.append(
            VerticalLoad(
                name="Active thrust vertical component",
                force_kn=round(active_v, 4),
                lever_arm_m=round(b, 4),
                moment_knm=round(active_v * b, 4),
            )
        )

    surcharge_thrust = ka * q * h
    total_horizontal = active_h + surcharge_thrust

    total_vertical = sum(load.force_kn for load in loads)
    resisting_moment = sum(load.moment_knm for load in loads)
    overturning_moment = active_h * active_arm + surcharge_thrust * (h / 2.0)
    fos_ot = resisting_moment / overturning_moment if overturning_moment else math.inf

    # --- sliding: base friction + passive over (base depth + key) ---
    passive_depth = db + key
    passive = 0.5 * kp * gamma * passive_depth * passive_depth
    sliding_resistance = mu * total_vertical + passive
    fos_sliding = sliding_resistance / total_horizontal if total_horizontal else math.inf

    # --- base pressure distribution ---
    net_moment = resisting_moment - overturning_moment
    x_resultant = net_moment / total_vertical if total_vertical else 0.0
    ecc = b / 2.0 - x_resultant
    p_avg = total_vertical / b if b else 0.0
    p_max = p_avg * (1.0 + 6.0 * ecc / b)
    p_min = p_avg * (1.0 - 6.0 * ecc / b)

    # --- stem design earth-pressure forces (over the stem height hs) ---
    stem_moment = ka * gamma * hs**3 / 6.0 + ka * q * hs**2 / 2.0
    stem_shear = ka * gamma * hs**2 / 2.0 + ka * q * hs

    return StabilityCore(
        ka=ka,
        kp=kp,
        method=method,
        citation=citation,
        surcharge_kn_m2=q,
        surcharge_equiv_height_m=q_equiv,
        active_thrust_kn=active_thrust,
        active_thrust_arm_m=active_arm,
        active_horizontal_kn=active_h,
        active_vertical_kn=active_v,
        surcharge_thrust_kn=surcharge_thrust,
        total_horizontal_kn=total_horizontal,
        vertical_loads=loads,
        total_vertical_kn=total_vertical,
        resisting_moment_knm=resisting_moment,
        overturning_moment_knm=overturning_moment,
        fos_overturning=fos_ot,
        passive_resistance_kn=passive,
        sliding_resistance_kn=sliding_resistance,
        fos_sliding=fos_sliding,
        resultant_from_toe_m=x_resultant,
        eccentricity_m=ecc,
        base_width_m=b,
        max_base_pressure_kn_m2=p_max,
        min_base_pressure_kn_m2=p_min,
        stem_moment_knm=stem_moment,
        stem_shear_kn=stem_shear,
        stem_height_m=hs,
    )


def slab_design_moments(
    params: RetainingWallParams,
    geometry: RetainingWallGeometry,
    core: StabilityCore | None = None,
) -> tuple[float, float]:
    """(M_heel, M_toe) design cantilever moments from the net (load - base
    pressure) distribution — shared by the base-thickness sizing and the checks."""
    if core is None:
        core = compute_stability(params, geometry)
    gamma = params.backfill_unit_weight_kn_m3
    gamma_c = CONCRETE_UNIT_WEIGHT_KN_M3
    q = core.surcharge_kn_m2
    h = geometry.total_height_mm / 1000.0
    db = geometry.base_thickness_mm / 1000.0
    hs = h - db
    b = geometry.base_width_mm / 1000.0
    lt = geometry.toe_length_mm / 1000.0
    lh = geometry.heel_length_mm / 1000.0
    p_max = core.max_base_pressure_kn_m2
    p_min = core.min_base_pressure_kn_m2

    def pressure_at(x: float) -> float:
        return p_max - (p_max - p_min) * x / b if b else 0.0

    # Heel: downward soil + surcharge + self weight minus upward base pressure.
    w_down = gamma * hs + q + gamma_c * db
    w1 = w_down - pressure_at(b - lh)
    w2 = w_down - p_min
    m_heel = abs(w1 * lh**2 / 2.0 + (w2 - w1) * lh**2 / 3.0)

    # Toe: upward base pressure minus self weight.
    wa = p_max - gamma_c * db
    wb = pressure_at(lt) - gamma_c * db
    m_toe = abs(wb * lt**2 / 2.0 + (wa - wb) * lt**2 / 3.0)
    return m_heel, m_toe


def analyse_wall(
    params: RetainingWallParams, geometry: RetainingWallGeometry
) -> RetainingWallAnalysis:
    """Full analysis with the CalcStep trail + modelling assumptions."""
    params = coerce(RetainingWallParams, params)
    geometry = coerce(RetainingWallGeometry, geometry)
    core = compute_stability(params, geometry)
    trail = Trail("A")

    h = geometry.total_height_mm / 1000.0
    gamma = params.backfill_unit_weight_kn_m3

    trail.record(
        description="Earth pressure coefficient — active",
        formula="Ka (Rankine level / Coulomb sloped) from phi and beta",
        inputs={
            "phi_deg": params.backfill_friction_angle_deg,
            "beta_deg": params.backfill_slope_deg,
            "method": core.method,
        },
        value=round(core.ka, 4),
        unit="-",
        citation=core.citation,
    )
    trail.record(
        description="Earth pressure coefficient — passive (Rankine)",
        formula="Kp = (1 + sin phi) / (1 - sin phi)",
        inputs={"phi_deg": params.backfill_friction_angle_deg},
        value=round(core.kp, 4),
        unit="-",
        citation=core.citation,
    )
    if core.surcharge_kn_m2 > 0:
        trail.record(
            description="Equivalent live-load surcharge on the backfill",
            formula="q = surcharge + (track ? gamma * h_eq : 0)",
            inputs={
                "surcharge_kn_m2": params.surcharge_kn_m2,
                "track_surcharge": str(params.track_surcharge),
                "equivalent_height_m": round(TRACK_SURCHARGE_EQUIVALENT_HEIGHT_M, 3),
            },
            value=round(core.surcharge_kn_m2, 3),
            unit="kN/m^2",
            citation=CITATION_SURCHARGE,
        )
    trail.record(
        description="Active earth thrust on the virtual back (full height)",
        formula="Pa = 0.5 * Ka * gamma * H^2",
        inputs={"Ka": round(core.ka, 4), "gamma": gamma, "H_m": round(h, 3)},
        value=round(core.active_thrust_kn, 3),
        unit="kN/m",
        citation=core.citation,
    )
    if core.surcharge_thrust_kn > 0:
        trail.record(
            description="Surcharge thrust on the wall",
            formula="Ps = Ka * q * H",
            inputs={"Ka": round(core.ka, 4), "q_kn_m2": round(core.surcharge_kn_m2, 3), "H_m": round(h, 3)},
            value=round(core.surcharge_thrust_kn, 3),
            unit="kN/m",
            citation=CITATION_SURCHARGE,
        )
    trail.record(
        description="Total vertical load on the base",
        formula="W = sum of concrete + backfill weights (+ active vertical comp)",
        inputs={"loads": len(core.vertical_loads)},
        value=round(core.total_vertical_kn, 3),
        unit="kN/m",
        citation=CITATION_STABILITY,
    )
    trail.record(
        description="Resisting (stabilising) moment about the toe",
        formula="Mr = sum(Wi * xi)",
        inputs={"total_vertical_kn": round(core.total_vertical_kn, 3)},
        value=round(core.resisting_moment_knm, 3),
        unit="kN*m/m",
        citation=CITATION_STABILITY,
    )
    trail.record(
        description="Overturning moment about the toe",
        formula="Mo = Ph * H/3 + Ps * H/2",
        inputs={
            "active_horizontal_kn": round(core.active_horizontal_kn, 3),
            "surcharge_thrust_kn": round(core.surcharge_thrust_kn, 3),
            "H_m": round(h, 3),
        },
        value=round(core.overturning_moment_knm, 3),
        unit="kN*m/m",
        citation=CITATION_STABILITY,
    )
    trail.record(
        description="Factor of safety against overturning",
        formula="FoS_ot = Mr / Mo",
        inputs={
            "Mr_knm": round(core.resisting_moment_knm, 3),
            "Mo_knm": round(core.overturning_moment_knm, 3),
        },
        value=round(core.fos_overturning, 3),
        unit="-",
        citation=CITATION_STABILITY,
    )
    trail.record(
        description="Passive resistance at the toe / shear key",
        formula="Pp = 0.5 * Kp * gamma * (Db + key)^2",
        inputs={
            "Kp": round(core.kp, 4),
            "gamma": gamma,
            "base_thickness_mm": geometry.base_thickness_mm,
            "key_depth_mm": geometry.key_depth_mm,
        },
        value=round(core.passive_resistance_kn, 3),
        unit="kN/m",
        citation=core.citation,
    )
    trail.record(
        description="Factor of safety against sliding",
        formula="FoS_sl = (mu * W + Pp) / H_total",
        inputs={
            "mu": params.base_friction_coeff,
            "total_vertical_kn": round(core.total_vertical_kn, 3),
            "passive_kn": round(core.passive_resistance_kn, 3),
            "horizontal_kn": round(core.total_horizontal_kn, 3),
        },
        value=round(core.fos_sliding, 3),
        unit="-",
        citation=CITATION_STABILITY,
    )
    trail.record(
        description="Eccentricity of the resultant from the base centre",
        formula="e = B/2 - (Mr - Mo)/W",
        inputs={
            "base_width_m": round(core.base_width_m, 3),
            "resultant_from_toe_m": round(core.resultant_from_toe_m, 3),
        },
        value=round(core.eccentricity_m, 4),
        unit="m",
        citation=CITATION_STABILITY,
    )
    trail.record(
        description="Maximum base pressure (toe)",
        formula="p_max = W/B * (1 + 6e/B)",
        inputs={
            "total_vertical_kn": round(core.total_vertical_kn, 3),
            "base_width_m": round(core.base_width_m, 3),
            "eccentricity_m": round(core.eccentricity_m, 4),
        },
        value=round(core.max_base_pressure_kn_m2, 3),
        unit="kN/m^2",
        citation=CITATION_STABILITY,
    )
    trail.record(
        description="Minimum base pressure (heel)",
        formula="p_min = W/B * (1 - 6e/B)",
        inputs={
            "total_vertical_kn": round(core.total_vertical_kn, 3),
            "base_width_m": round(core.base_width_m, 3),
            "eccentricity_m": round(core.eccentricity_m, 4),
        },
        value=round(core.min_base_pressure_kn_m2, 3),
        unit="kN/m^2",
        citation=CITATION_STABILITY,
    )
    trail.record(
        description="Design bending moment at the stem base",
        formula="M_stem = Ka*gamma*hs^3/6 + Ka*q*hs^2/2",
        inputs={
            "Ka": round(core.ka, 4),
            "gamma": gamma,
            "stem_height_m": round(core.stem_height_m, 3),
            "q_kn_m2": round(core.surcharge_kn_m2, 3),
        },
        value=round(core.stem_moment_knm, 3),
        unit="kN*m/m",
        citation=core.citation,
    )
    trail.record(
        description="Design shear at the stem base",
        formula="V_stem = Ka*gamma*hs^2/2 + Ka*q*hs",
        inputs={
            "Ka": round(core.ka, 4),
            "gamma": gamma,
            "stem_height_m": round(core.stem_height_m, 3),
            "q_kn_m2": round(core.surcharge_kn_m2, 3),
        },
        value=round(core.stem_shear_kn, 3),
        unit="kN/m",
        citation=core.citation,
    )

    assumptions = [
        Assumption(
            field="concrete_unit_weight_kn_m3",
            value=CONCRETE_UNIT_WEIGHT_KN_M3,
            source="engine_default",
            note=f"RCC self-weight taken as {CONCRETE_UNIT_WEIGHT_KN_M3:g} kN/m^3 (IS 456 / IS 875).",
        ),
        Assumption(
            field="earth_pressure_method",
            value=core.method,
            source="engine_default",
            note=(
                "Active thrust computed on the vertical virtual back plane through the "
                "heel over the full wall height; the soil column above the heel is a "
                "stabilising vertical load."
            ),
        ),
    ]
    if params.track_surcharge:
        assumptions.append(
            Assumption(
                field="track_surcharge_equivalent_height_m",
                value=TRACK_SURCHARGE_EQUIVALENT_HEIGHT_M,
                source="engine_default",
                note=(
                    f"BG single-line track surcharge taken as {TRACK_SURCHARGE_EQUIVALENT_HEIGHT_M:g} m "
                    "equivalent height of fill (IR Bridge Rules practice)."
                ),
            )
        )

    return RetainingWallAnalysis(
        ka=round(core.ka, 6),
        kp=round(core.kp, 6),
        method=core.method,
        surcharge_kn_m2=round(core.surcharge_kn_m2, 4),
        surcharge_equiv_height_m=round(core.surcharge_equiv_height_m, 4),
        active_thrust_kn=round(core.active_thrust_kn, 4),
        active_thrust_arm_m=round(core.active_thrust_arm_m, 4),
        active_horizontal_kn=round(core.active_horizontal_kn, 4),
        active_vertical_kn=round(core.active_vertical_kn, 4),
        surcharge_thrust_kn=round(core.surcharge_thrust_kn, 4),
        total_horizontal_kn=round(core.total_horizontal_kn, 4),
        vertical_loads=core.vertical_loads,
        total_vertical_kn=round(core.total_vertical_kn, 4),
        resisting_moment_knm=round(core.resisting_moment_knm, 4),
        overturning_moment_knm=round(core.overturning_moment_knm, 4),
        fos_overturning=round(core.fos_overturning, 4),
        passive_resistance_kn=round(core.passive_resistance_kn, 4),
        sliding_resistance_kn=round(core.sliding_resistance_kn, 4),
        fos_sliding=round(core.fos_sliding, 4),
        resultant_from_toe_m=round(core.resultant_from_toe_m, 4),
        eccentricity_m=round(core.eccentricity_m, 4),
        base_width_m=round(core.base_width_m, 4),
        max_base_pressure_kn_m2=round(core.max_base_pressure_kn_m2, 4),
        min_base_pressure_kn_m2=round(core.min_base_pressure_kn_m2, 4),
        stem_moment_knm=round(core.stem_moment_knm, 4),
        stem_shear_kn=round(core.stem_shear_kn, 4),
        assumptions=assumptions,
        trail=trail.steps,
    )
