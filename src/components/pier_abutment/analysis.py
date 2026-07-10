"""Load + stability analysis of the pier / abutment substructure.

Given `PierAbutmentParams` and a proportioned `PierAbutmentGeometry`, computes the
vertical loads (superstructure reaction + self weight + backfill for an abutment)
and their stabilising moments about the toe, the longitudinal (braking) thrust,
the abutment earth pressure + track surcharge, the factors of safety against
overturning and sliding, the base-pressure distribution (no tension), and the
pier-section direct compressive stress.

`compute_stability` is the pure numeric core (reused by the sizing loop and the
proof-check cross-check); `analyse_substructure` wraps it with the CalcStep trail
and Assumptions and returns the `PierAbutmentAnalysis` model the calc sheet,
checks and proof-check consume.

Sign / geometry convention (normative): x is measured horizontally from the toe
edge of the footing (x = 0, the front/traffic-facing edge) toward the heel edge
(x = B = footing length). The footing is symmetric about the pier centre-line, so
the pier and all self-weight act at x = B/2. Moments about the toe are positive
when they resist overturning (stabilising). For an abutment the backfill sits over
the rear (heel) projection and its active thrust acts toward the toe.
"""

from __future__ import annotations

import math
from typing import NamedTuple

from pydantic import BaseModel, Field

from components.base import Assumption, coerce
from components.pier_abutment._engine_common import (
    CITATION_DIRECT_STRESS,
    CITATION_LONGITUDINAL,
    CITATION_RANKINE,
    CITATION_STABILITY,
    CITATION_SURCHARGE,
    CONCRETE_UNIT_WEIGHT_KN_M3,
    LONGITUDINAL_FORCE_FRACTION,
    TRACK_SURCHARGE_EQUIVALENT_HEIGHT_M,
    Trail,
    permissible_direct_stress,
    rankine_ka,
    rankine_kp,
)
from components.pier_abutment.params import PierAbutmentGeometry, PierAbutmentParams

MM_PER_M = 1000.0


class VerticalLoad(BaseModel):
    """One stabilising vertical load and its lever arm about the toe."""

    name: str = Field(description="What this load represents")
    force_kn: float = Field(description="Vertical force, kN")
    lever_arm_m: float = Field(description="Horizontal distance of its line of action from the toe, m")
    moment_knm: float = Field(description="Stabilising moment about the toe = force x lever arm, kN*m")


class HorizontalLoad(BaseModel):
    """One destabilising horizontal load and its height above the founding level."""

    name: str = Field(description="What this load represents")
    force_kn: float = Field(description="Horizontal force, kN")
    height_m: float = Field(description="Height of its line of action above the founding level, m")
    moment_knm: float = Field(description="Overturning moment about the toe = force x height, kN*m")


class PierAbutmentAnalysis(BaseModel):
    """Load + stability analysis — the rehydratable analysis model.

    Field names are normative (calc sheet, checks and proof-check read them).
    """

    component_kind: str = Field(description="'pier' | 'abutment'")
    ka: float = Field(description="Active earth-pressure coefficient (abutment)")
    kp: float = Field(description="Passive earth-pressure coefficient")
    surcharge_kn_m2: float = Field(description="Equivalent uniform track surcharge behind the abutment, kN/m^2")
    retained_height_m: float = Field(description="Height of soil retained behind an abutment, m (0 for a pier)")

    longitudinal_force_kn: float = Field(description="Longitudinal (braking) force at bearing level, kN")
    earth_thrust_kn: float = Field(description="Active earth thrust behind the abutment, kN")
    surcharge_thrust_kn: float = Field(description="Horizontal thrust from the track surcharge, kN")
    horizontal_loads: list[HorizontalLoad] = Field(description="Destabilising horizontal loads")
    total_horizontal_kn: float = Field(description="Total destabilising horizontal force, kN")

    vertical_loads: list[VerticalLoad] = Field(description="Stabilising vertical loads")
    total_vertical_kn: float = Field(description="Sum of vertical loads, kN")
    resisting_moment_knm: float = Field(description="Total stabilising moment about the toe, kN*m")
    overturning_moment_knm: float = Field(description="Total overturning moment about the toe, kN*m")
    fos_overturning: float = Field(description="Factor of safety against overturning")

    passive_resistance_kn: float = Field(description="Passive resistance at the footing depth, kN")
    sliding_resistance_kn: float = Field(description="Base friction + passive resistance, kN")
    fos_sliding: float = Field(description="Factor of safety against sliding")

    resultant_from_toe_m: float = Field(description="Distance of the resultant from the toe, m")
    eccentricity_m: float = Field(description="Eccentricity of the resultant from the base centre, m")
    footing_length_m: float = Field(description="Footing length B (longitudinal), m")
    footing_width_m: float = Field(description="Footing width L (transverse), m")
    base_area_m2: float = Field(description="Footing plan area A = B x L, m^2")
    max_base_pressure_kn_m2: float = Field(description="Maximum (toe) base pressure, kN/m^2")
    min_base_pressure_kn_m2: float = Field(description="Minimum (heel) base pressure, kN/m^2")

    pier_axial_kn: float = Field(description="Axial load at the pier base (top of footing), kN")
    pier_area_m2: float = Field(description="Pier cross-sectional area, m^2")
    pier_direct_stress_n_mm2: float = Field(description="Direct compressive stress in the pier, N/mm^2")
    permissible_direct_stress_n_mm2: float = Field(description="Permissible direct compressive stress, N/mm^2")

    assumptions: list[Assumption] = Field(default_factory=list)
    trail: list = Field(default_factory=list, description="CalcStep trail")


class StabilityCore(NamedTuple):
    """The pure numeric stability result (no trail) — shared by sizing + analyse + proof."""

    component_kind: str
    ka: float
    kp: float
    surcharge_kn_m2: float
    retained_height_m: float
    longitudinal_force_kn: float
    earth_thrust_kn: float
    surcharge_thrust_kn: float
    horizontal_loads: list[HorizontalLoad]
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
    footing_length_m: float
    footing_width_m: float
    base_area_m2: float
    max_base_pressure_kn_m2: float
    min_base_pressure_kn_m2: float
    pier_axial_kn: float
    pier_area_m2: float
    pier_direct_stress_n_mm2: float
    permissible_direct_stress_n_mm2: float


def track_surcharge(params: PierAbutmentParams) -> float:
    """Equivalent uniform surcharge kN/m^2 behind an abutment (0 for a pier)."""
    if params.component_kind != "abutment":
        return 0.0
    return params.backfill_unit_weight_kn_m3 * TRACK_SURCHARGE_EQUIVALENT_HEIGHT_M


def compute_stability(
    params: PierAbutmentParams, geometry: PierAbutmentGeometry
) -> StabilityCore:
    """Deterministic load + stability numbers for a given geometry."""
    gamma = params.backfill_unit_weight_kn_m3
    gamma_c = CONCRETE_UNIT_WEIGHT_KN_M3
    mu = params.base_friction_coeff
    kind = params.component_kind

    ka = rankine_ka(params.backfill_friction_angle_deg)
    kp = rankine_kp(params.backfill_friction_angle_deg)

    h = geometry.total_height_mm / MM_PER_M
    df = geometry.footing_thickness_mm / MM_PER_M
    ct = geometry.cap_thickness_mm / MM_PER_M
    shaft_h = h - df - ct
    b = geometry.footing_length_mm / MM_PER_M  # longitudinal (overturning direction)
    lw = geometry.footing_width_mm / MM_PER_M  # transverse
    pw = geometry.pier_width_mm / MM_PER_M
    pl = geometry.pier_length_mm / MM_PER_M
    cw = geometry.cap_width_mm / MM_PER_M
    cl = geometry.cap_length_mm / MM_PER_M

    # --- stabilising vertical loads (all act on the pier centre-line, x = B/2) ---
    x_c = b / 2.0
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

    footing_w = gamma_c * b * lw * df
    shaft_w = gamma_c * pw * pl * shaft_h
    cap_w = gamma_c * cw * cl * ct
    _add("Footing self-weight", footing_w, x_c)
    _add("Pier/stem self-weight", shaft_w, x_c)
    _add("Cap self-weight", cap_w, x_c)
    _add("Superstructure reaction", params.superstructure_reaction_kn, x_c)

    # --- abutment backfill over the rear (heel) projection ---
    retained_height = 0.0
    q = track_surcharge(params)
    if kind == "abutment":
        retained_height = h - df  # soil from top of footing to bearing/deck level
        heel_proj = max(0.0, (b - pw) / 2.0)  # rear projection behind the stem
        backfill_w = gamma * heel_proj * retained_height * lw
        # centroid of the rear projection: arm = B - heel/2
        _add("Backfill over heel", backfill_w, b - heel_proj / 2.0)

    total_vertical = sum(load.force_kn for load in loads)
    resisting_moment = sum(load.moment_knm for load in loads)

    # --- destabilising horizontal loads and their overturning moments ---
    horiz: list[HorizontalLoad] = []

    def _addh(name: str, force: float, height: float) -> None:
        horiz.append(
            HorizontalLoad(
                name=name,
                force_kn=round(force, 4),
                height_m=round(height, 4),
                moment_knm=round(force * height, 4),
            )
        )

    longitudinal = LONGITUDINAL_FORCE_FRACTION * params.superstructure_reaction_kn
    _addh("Longitudinal / braking force", longitudinal, h)  # acts at bearing level

    earth_thrust = 0.0
    surcharge_thrust = 0.0
    if kind == "abutment":
        earth_thrust = 0.5 * ka * gamma * retained_height * retained_height * lw
        # thrust acts at retained_height/3 above the top of the footing
        _addh("Active earth thrust", earth_thrust, df + retained_height / 3.0)
        surcharge_thrust = ka * q * retained_height * lw
        if surcharge_thrust > 0:
            _addh("Track-surcharge thrust", surcharge_thrust, df + retained_height / 2.0)

    total_horizontal = sum(load.force_kn for load in horiz)
    overturning_moment = sum(load.moment_knm for load in horiz)
    fos_ot = resisting_moment / overturning_moment if overturning_moment else math.inf

    # --- sliding: base friction + passive over the footing depth ---
    passive = 0.5 * kp * gamma * df * df * lw
    sliding_resistance = mu * total_vertical + passive
    fos_sliding = sliding_resistance / total_horizontal if total_horizontal else math.inf

    # --- base pressure distribution (longitudinal eccentricity) ---
    net_moment = resisting_moment - overturning_moment
    x_resultant = net_moment / total_vertical if total_vertical else 0.0
    ecc = b / 2.0 - x_resultant
    area = b * lw
    p_avg = total_vertical / area if area else 0.0
    p_max = p_avg * (1.0 + 6.0 * ecc / b)
    p_min = p_avg * (1.0 - 6.0 * ecc / b)

    # --- pier-section direct compressive stress (axial at the top of the footing) ---
    pier_axial = params.superstructure_reaction_kn + shaft_w + cap_w
    pier_area = pw * pl
    sigma_cc_perm = permissible_direct_stress(params.concrete_grade)
    # stress N/mm^2 = axial_N / area_mm^2 = (axial_kN*1e3) / (area_m2*1e6)
    pier_stress = (pier_axial * 1e3) / (pier_area * 1e6) if pier_area else math.inf

    return StabilityCore(
        component_kind=kind,
        ka=ka,
        kp=kp,
        surcharge_kn_m2=q,
        retained_height_m=retained_height,
        longitudinal_force_kn=longitudinal,
        earth_thrust_kn=earth_thrust,
        surcharge_thrust_kn=surcharge_thrust,
        horizontal_loads=horiz,
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
        footing_length_m=b,
        footing_width_m=lw,
        base_area_m2=area,
        max_base_pressure_kn_m2=p_max,
        min_base_pressure_kn_m2=p_min,
        pier_axial_kn=pier_axial,
        pier_area_m2=pier_area,
        pier_direct_stress_n_mm2=pier_stress,
        permissible_direct_stress_n_mm2=sigma_cc_perm,
    )


def analyse_substructure(
    params: PierAbutmentParams, geometry: PierAbutmentGeometry
) -> PierAbutmentAnalysis:
    """Full analysis with the CalcStep trail + modelling assumptions."""
    params = coerce(PierAbutmentParams, params)
    geometry = coerce(PierAbutmentGeometry, geometry)
    core = compute_stability(params, geometry)
    trail = Trail("A")

    gamma = params.backfill_unit_weight_kn_m3

    trail.record(
        description="Longitudinal (braking / tractive) force at bearing level",
        formula="F_long = fraction * superstructure_reaction",
        inputs={
            "fraction": LONGITUDINAL_FORCE_FRACTION,
            "reaction_kn": params.superstructure_reaction_kn,
        },
        value=round(core.longitudinal_force_kn, 3),
        unit="kN",
        citation=CITATION_LONGITUDINAL,
    )
    if core.component_kind == "abutment":
        trail.record(
            description="Active earth-pressure coefficient (Rankine, level backfill)",
            formula="Ka = (1 - sin phi) / (1 + sin phi)",
            inputs={"phi_deg": params.backfill_friction_angle_deg},
            value=round(core.ka, 4),
            unit="-",
            citation=CITATION_RANKINE,
        )
        trail.record(
            description="Active earth thrust behind the abutment",
            formula="Pa = 0.5 * Ka * gamma * H_soil^2 * L",
            inputs={
                "Ka": round(core.ka, 4),
                "gamma": gamma,
                "H_soil_m": round(core.retained_height_m, 3),
                "L_m": round(core.footing_width_m, 3),
            },
            value=round(core.earth_thrust_kn, 3),
            unit="kN",
            citation=CITATION_RANKINE,
        )
        if core.surcharge_thrust_kn > 0:
            trail.record(
                description="Track-surcharge thrust behind the abutment",
                formula="Ps = Ka * q * H_soil * L",
                inputs={
                    "Ka": round(core.ka, 4),
                    "q_kn_m2": round(core.surcharge_kn_m2, 3),
                    "H_soil_m": round(core.retained_height_m, 3),
                },
                value=round(core.surcharge_thrust_kn, 3),
                unit="kN",
                citation=CITATION_SURCHARGE,
            )
    trail.record(
        description="Total vertical load on the footing",
        formula="W = superstructure reaction + self weights (+ backfill for an abutment)",
        inputs={"loads": len(core.vertical_loads)},
        value=round(core.total_vertical_kn, 3),
        unit="kN",
        citation=CITATION_STABILITY,
    )
    trail.record(
        description="Resisting (stabilising) moment about the toe",
        formula="Mr = sum(Wi * xi)",
        inputs={"total_vertical_kn": round(core.total_vertical_kn, 3)},
        value=round(core.resisting_moment_knm, 3),
        unit="kN*m",
        citation=CITATION_STABILITY,
    )
    trail.record(
        description="Overturning moment about the toe",
        formula="Mo = sum(Hi * hi)",
        inputs={
            "total_horizontal_kn": round(core.total_horizontal_kn, 3),
        },
        value=round(core.overturning_moment_knm, 3),
        unit="kN*m",
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
        description="Eccentricity of the resultant from the footing centre",
        formula="e = B/2 - (Mr - Mo)/W",
        inputs={
            "footing_length_m": round(core.footing_length_m, 3),
            "resultant_from_toe_m": round(core.resultant_from_toe_m, 3),
        },
        value=round(core.eccentricity_m, 4),
        unit="m",
        citation=CITATION_STABILITY,
    )
    trail.record(
        description="Maximum base pressure (toe)",
        formula="p_max = W/A * (1 + 6e/B)",
        inputs={
            "total_vertical_kn": round(core.total_vertical_kn, 3),
            "base_area_m2": round(core.base_area_m2, 3),
            "eccentricity_m": round(core.eccentricity_m, 4),
        },
        value=round(core.max_base_pressure_kn_m2, 3),
        unit="kN/m^2",
        citation=CITATION_STABILITY,
    )
    trail.record(
        description="Minimum base pressure (heel)",
        formula="p_min = W/A * (1 - 6e/B)",
        inputs={
            "total_vertical_kn": round(core.total_vertical_kn, 3),
            "base_area_m2": round(core.base_area_m2, 3),
            "eccentricity_m": round(core.eccentricity_m, 4),
        },
        value=round(core.min_base_pressure_kn_m2, 3),
        unit="kN/m^2",
        citation=CITATION_STABILITY,
    )
    trail.record(
        description="Direct compressive stress in the pier section",
        formula="sigma_cc = axial / (pier_width * pier_length)",
        inputs={
            "pier_axial_kn": round(core.pier_axial_kn, 3),
            "pier_area_m2": round(core.pier_area_m2, 4),
        },
        value=round(core.pier_direct_stress_n_mm2, 4),
        unit="N/mm^2",
        citation=CITATION_DIRECT_STRESS,
    )

    assumptions = [
        Assumption(
            field="concrete_unit_weight_kn_m3",
            value=CONCRETE_UNIT_WEIGHT_KN_M3,
            source="engine_default",
            note=f"RCC self-weight taken as {CONCRETE_UNIT_WEIGHT_KN_M3:g} kN/m^3 (IS 456).",
        ),
        Assumption(
            field="longitudinal_force_fraction",
            value=LONGITUDINAL_FORCE_FRACTION,
            source="engine_default",
            note=(
                f"Longitudinal (braking / tractive) force taken as "
                f"{LONGITUDINAL_FORCE_FRACTION:g} of the vertical superstructure reaction, "
                "applied at bearing level — a transcribed POC estimate pending verification "
                "against IRS Bridge Rules."
            ),
        ),
        Assumption(
            field="vertical_load_eccentricity",
            value="centred",
            source="engine_default",
            note=(
                "The superstructure reaction and all self weight are taken to act on the "
                "pier centre-line (symmetric spread footing); overturning is driven by the "
                "longitudinal force and, for an abutment, the backfill earth pressure."
            ),
        ),
    ]
    if core.component_kind == "abutment":
        assumptions.append(
            Assumption(
                field="track_surcharge_equivalent_height_m",
                value=TRACK_SURCHARGE_EQUIVALENT_HEIGHT_M,
                source="engine_default",
                note=(
                    f"BG single-line track surcharge behind the abutment taken as "
                    f"{TRACK_SURCHARGE_EQUIVALENT_HEIGHT_M:g} m equivalent height of fill "
                    "(IR Bridge Rules practice)."
                ),
            )
        )

    return PierAbutmentAnalysis(
        component_kind=core.component_kind,
        ka=round(core.ka, 6),
        kp=round(core.kp, 6),
        surcharge_kn_m2=round(core.surcharge_kn_m2, 4),
        retained_height_m=round(core.retained_height_m, 4),
        longitudinal_force_kn=round(core.longitudinal_force_kn, 4),
        earth_thrust_kn=round(core.earth_thrust_kn, 4),
        surcharge_thrust_kn=round(core.surcharge_thrust_kn, 4),
        horizontal_loads=core.horizontal_loads,
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
        footing_length_m=round(core.footing_length_m, 4),
        footing_width_m=round(core.footing_width_m, 4),
        base_area_m2=round(core.base_area_m2, 4),
        max_base_pressure_kn_m2=round(core.max_base_pressure_kn_m2, 4),
        min_base_pressure_kn_m2=round(core.min_base_pressure_kn_m2, 4),
        pier_axial_kn=round(core.pier_axial_kn, 4),
        pier_area_m2=round(core.pier_area_m2, 4),
        pier_direct_stress_n_mm2=round(core.pier_direct_stress_n_mm2, 4),
        permissible_direct_stress_n_mm2=round(core.permissible_direct_stress_n_mm2, 4),
        assumptions=assumptions,
        trail=trail.steps,
    )
