"""RDSO load-case analysis of the fabricated rolling-stock member.

Given `RollingStockMemberParams` and a proportioned `RollingStockMemberGeometry`,
computes the design actions from TWO declared RDSO wagon-design load cases and the
resulting working-stress section stresses:

* **Vertical payload case** — the member's share of the vertical payload + tare
  load, applied as a UDL over the span and augmented by the RDSO dynamic-augment
  (impact) factor, plus the member self-weight. Governs bending and shear.
* **Longitudinal buffing case** — the member's share of the RDSO draft-gear
  buffing (compressive) / draft (tensile) load, applied as an axial force.
  Governs the axial stress and, with the vertical bending, the combined
  interaction.

From the design actions and the exact elastic section properties it derives the
extreme-fibre bending stress, the average web shear stress, the gross-section
axial stress and the combined axial+bending interaction ratio, each against its
IS 800 working-stress permissible value, and records which RDSO load case governs.

`compute_forces` is the pure numeric core (reused by the sizing loop);
`analyse_member` wraps it with the CalcStep trail and Assumptions and returns the
`RollingStockMemberAnalysis` model the calc sheet, checks and proof-check consume.
"""

from __future__ import annotations

from typing import NamedTuple

from pydantic import BaseModel, Field

from components.base import Assumption, coerce
from components.rolling_stock_member._engine_common import (
    CITATION_AXIAL,
    CITATION_BENDING,
    CITATION_BUFFING_LOAD,
    CITATION_COMBINED,
    CITATION_SECTION,
    CITATION_SELF_WEIGHT,
    CITATION_SHEAR,
    CITATION_VERTICAL_LOAD,
    INTERACTION_LIMIT,
    RDSO_PROOF_BUFFING_LOAD_KN,
    STEEL_UNIT_WEIGHT_KN_M3,
    VERTICAL_IMPACT_FACTOR,
    WEB_SLENDERNESS_LIMIT,
    Trail,
    permissible,
    section_properties,
)
from components.rolling_stock_member.params import (
    RollingStockMemberGeometry,
    RollingStockMemberParams,
    member_kind_label,
)

# Governing-load-case labels (stable strings — surfaced in the type summary).
GOVERNING_VERTICAL = "Vertical payload (RDSO wagon vertical load + dynamic augment)"
GOVERNING_BUFFING = "Longitudinal buffing (RDSO draft-gear buffing load)"


class RollingStockMemberAnalysis(BaseModel):
    """RDSO load-case analysis of one member — the rehydratable model.

    Field names are normative (calc sheet, checks, proof-check and summary read them).
    """

    member_length_m: float = Field(description="Effective member span, m")
    member_kind: str = Field(description="Underframe member type")

    # --- vertical payload case (per member) ---
    self_weight_kn_m: float = Field(description="Member self-weight UDL, kN/m")
    vertical_load_kn: float = Field(description="Design vertical load (payload+tare share), kN")
    impact_factor: float = Field(description="RDSO vertical dynamic-augment (impact) factor")
    dead_moment_knm: float = Field(description="Self-weight mid-span bending moment, kN*m")
    dead_shear_kn: float = Field(description="Self-weight end shear, kN")
    live_moment_knm: float = Field(description="Payload+impact mid-span moment, kN*m")
    live_shear_kn: float = Field(description="Payload+impact end shear, kN")
    design_moment_knm: float = Field(description="Design bending moment (dead+live), kN*m")
    design_shear_kn: float = Field(description="Design shear force (dead+live), kN")

    # --- longitudinal buffing case ---
    buffing_load_kn: float = Field(description="Design longitudinal buffing/draft load, kN")

    # --- section properties ---
    section_area_mm2: float = Field(description="Cross-sectional area of the member, mm^2")
    inertia_mm4: float = Field(description="Second moment of area, mm^4")
    section_modulus_cm3: float = Field(description="Elastic section modulus Z, cm^3")
    overall_depth_mm: float = Field(description="Overall member depth, mm")

    # --- stresses vs permissibles ---
    max_bending_stress_mpa: float = Field(description="Extreme-fibre bending stress, N/mm^2")
    permissible_bending_stress_mpa: float = Field(description="Permissible bending stress, N/mm^2")
    max_shear_stress_mpa: float = Field(description="Average web shear stress, N/mm^2")
    permissible_shear_stress_mpa: float = Field(description="Permissible average shear stress, N/mm^2")
    max_axial_stress_mpa: float = Field(description="Gross-section axial stress, N/mm^2")
    permissible_axial_stress_mpa: float = Field(description="Permissible axial stress, N/mm^2")
    interaction_ratio: float = Field(description="Combined axial+bending interaction ratio")
    interaction_limit: float = Field(description="Interaction (unity-check) limit")

    web_slenderness: float = Field(description="Web depth / thickness ratio")
    web_slenderness_limit: float = Field(description="Permissible web slenderness")

    governing_load_case: str = Field(description="Which RDSO load case governs the section")

    assumptions: list[Assumption] = Field(default_factory=list)
    trail: list = Field(default_factory=list, description="CalcStep trail")


class ForceCore(NamedTuple):
    """The pure numeric analysis result (no trail) — shared by sizing + analyse."""

    member_length_m: float
    self_weight_kn_m: float
    vertical_load_kn: float
    impact_factor: float
    dead_moment_knm: float
    dead_shear_kn: float
    live_moment_knm: float
    live_shear_kn: float
    design_moment_knm: float
    design_shear_kn: float
    buffing_load_kn: float
    section_area_mm2: float
    inertia_mm4: float
    section_modulus_mm3: float
    overall_depth_mm: float
    max_bending_stress_mpa: float
    permissible_bending_stress_mpa: float
    max_shear_stress_mpa: float
    permissible_shear_stress_mpa: float
    max_axial_stress_mpa: float
    permissible_axial_stress_mpa: float
    interaction_ratio: float
    web_slenderness: float
    governing_load_case: str


def compute_forces(
    params: RollingStockMemberParams, geometry: RollingStockMemberGeometry
) -> ForceCore:
    """Deterministic RDSO load-case actions, stresses and interaction for a member."""
    span_m = geometry.member_length_mm / 1000.0
    perm = permissible(params.steel_grade)

    section = section_properties(
        web_depth_mm=geometry.web_depth_mm,
        web_thickness_mm=geometry.web_thickness_mm,
        flange_width_mm=geometry.flange_width_mm,
        flange_thickness_mm=geometry.flange_thickness_mm,
    )

    # --- vertical payload case ---
    self_weight = section.area_mm2 * 1e-6 * STEEL_UNIT_WEIGHT_KN_M3  # kN/m
    dead_moment = self_weight * span_m**2 / 8.0
    dead_shear = self_weight * span_m / 2.0

    vertical_load = params.design_vertical_load_kn  # total, treated as a UDL over the span
    impact = VERTICAL_IMPACT_FACTOR
    live_moment = impact * vertical_load * span_m / 8.0
    live_shear = impact * vertical_load / 2.0

    design_moment = dead_moment + live_moment
    design_shear = dead_shear + live_shear

    # --- longitudinal buffing case ---
    buffing = params.design_buffing_load_kn

    # --- stresses ---
    bending_stress = design_moment * 1e6 / section.section_modulus_mm3  # N/mm^2
    web_area = geometry.web_depth_mm * geometry.web_thickness_mm  # mm^2
    shear_stress = design_shear * 1e3 / web_area  # N/mm^2
    axial_stress = buffing * 1e3 / section.area_mm2  # N/mm^2

    # --- combined interaction (unity check) ---
    interaction = axial_stress / perm.sigma_axial_n_mm2 + bending_stress / perm.sigma_bending_n_mm2

    # --- which RDSO load case governs the section ---
    vertical_util = max(
        bending_stress / perm.sigma_bending_n_mm2, shear_stress / perm.sigma_shear_n_mm2
    )
    buffing_util = axial_stress / perm.sigma_axial_n_mm2
    governing = GOVERNING_VERTICAL if vertical_util >= buffing_util else GOVERNING_BUFFING

    web_slenderness = geometry.web_depth_mm / geometry.web_thickness_mm

    return ForceCore(
        member_length_m=span_m,
        self_weight_kn_m=self_weight,
        vertical_load_kn=vertical_load,
        impact_factor=impact,
        dead_moment_knm=dead_moment,
        dead_shear_kn=dead_shear,
        live_moment_knm=live_moment,
        live_shear_kn=live_shear,
        design_moment_knm=design_moment,
        design_shear_kn=design_shear,
        buffing_load_kn=buffing,
        section_area_mm2=section.area_mm2,
        inertia_mm4=section.inertia_mm4,
        section_modulus_mm3=section.section_modulus_mm3,
        overall_depth_mm=section.overall_depth_mm,
        max_bending_stress_mpa=bending_stress,
        permissible_bending_stress_mpa=perm.sigma_bending_n_mm2,
        max_shear_stress_mpa=shear_stress,
        permissible_shear_stress_mpa=perm.sigma_shear_n_mm2,
        max_axial_stress_mpa=axial_stress,
        permissible_axial_stress_mpa=perm.sigma_axial_n_mm2,
        interaction_ratio=interaction,
        web_slenderness=web_slenderness,
        governing_load_case=governing,
    )


def analyse_member(
    params: RollingStockMemberParams, geometry: RollingStockMemberGeometry
) -> RollingStockMemberAnalysis:
    """Full analysis with the CalcStep trail + modelling assumptions."""
    params = coerce(RollingStockMemberParams, params)
    geometry = coerce(RollingStockMemberGeometry, geometry)
    core = compute_forces(params, geometry)
    trail = Trail("A")
    span_m = core.member_length_m

    trail.record(
        description="Member self-weight UDL (fabricated steel section)",
        formula="w_sw = A_section * gamma_steel",
        inputs={
            "A_section_mm2": round(core.section_area_mm2, 1),
            "gamma_steel_kn_m3": STEEL_UNIT_WEIGHT_KN_M3,
        },
        value=round(core.self_weight_kn_m, 4),
        unit="kN/m",
        citation=CITATION_SELF_WEIGHT,
    )
    trail.record(
        description="Vertical payload case: design vertical load (payload + tare share)",
        formula="W_v = design_vertical_load (member share)",
        inputs={"design_vertical_load_kn": core.vertical_load_kn},
        value=round(core.vertical_load_kn, 3),
        unit="kN",
        citation=CITATION_VERTICAL_LOAD,
    )
    trail.record(
        description="Vertical payload case: RDSO dynamic-augment (impact) factor",
        formula="k_dyn = RDSO wagon-design vertical impact factor",
        inputs={"k_dyn": core.impact_factor},
        value=round(core.impact_factor, 4),
        unit="-",
        citation=CITATION_VERTICAL_LOAD,
    )
    trail.record(
        description="Vertical payload case: design bending moment",
        formula="M = w_sw*L^2/8 + k_dyn*W_v*L/8",
        inputs={
            "w_sw_kn_m": round(core.self_weight_kn_m, 4),
            "W_v_kn": core.vertical_load_kn,
            "k_dyn": core.impact_factor,
            "L_m": round(span_m, 3),
        },
        value=round(core.design_moment_knm, 3),
        unit="kN*m",
        citation=CITATION_VERTICAL_LOAD,
    )
    trail.record(
        description="Vertical payload case: design shear force",
        formula="V = w_sw*L/2 + k_dyn*W_v/2",
        inputs={
            "w_sw_kn_m": round(core.self_weight_kn_m, 4),
            "W_v_kn": core.vertical_load_kn,
            "k_dyn": core.impact_factor,
            "L_m": round(span_m, 3),
        },
        value=round(core.design_shear_kn, 3),
        unit="kN",
        citation=CITATION_VERTICAL_LOAD,
    )
    trail.record(
        description="Longitudinal buffing case: design axial (buffing/draft) load",
        formula="P = design_buffing_load (member share of the RDSO draft-gear load)",
        inputs={"design_buffing_load_kn": core.buffing_load_kn},
        value=round(core.buffing_load_kn, 3),
        unit="kN",
        citation=CITATION_BUFFING_LOAD,
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
        description="Extreme-fibre bending stress (vertical payload case)",
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
        description="Average web shear stress (vertical payload case)",
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
        description="Gross-section axial stress (longitudinal buffing case)",
        formula="sigma_a = P / A",
        inputs={
            "P_kn": round(core.buffing_load_kn, 3),
            "A_mm2": round(core.section_area_mm2, 1),
        },
        value=round(core.max_axial_stress_mpa, 3),
        unit="N/mm^2",
        citation=CITATION_AXIAL,
    )
    trail.record(
        description="Combined axial + bending interaction ratio (unity check)",
        formula="R = sigma_a/sigma_ac + sigma_b/sigma_bc",
        inputs={
            "sigma_a_n_mm2": round(core.max_axial_stress_mpa, 3),
            "sigma_ac_n_mm2": core.permissible_axial_stress_mpa,
            "sigma_b_n_mm2": round(core.max_bending_stress_mpa, 3),
            "sigma_bc_n_mm2": core.permissible_bending_stress_mpa,
        },
        value=round(core.interaction_ratio, 4),
        unit="-",
        citation=CITATION_COMBINED,
    )

    assumptions = [
        Assumption(
            field="steel_unit_weight_kn_m3",
            value=STEEL_UNIT_WEIGHT_KN_M3,
            source="engine_default",
            note=f"Fabricated-steel self-weight taken as {STEEL_UNIT_WEIGHT_KN_M3:g} kN/m^3 (IS 800 / IS 875).",
        ),
        Assumption(
            field="vertical_impact_factor_needs_verification",
            value=core.impact_factor,
            source="engine_default",
            note=(
                f"RDSO wagon-design vertical dynamic-augment (impact) factor taken as "
                f"{core.impact_factor:g} — a TRANSCRIBED RDSO value that NEEDS VERIFICATION "
                "against the source RDSO specification before demo day."
            ),
        ),
        Assumption(
            field="buffing_load_distribution_needs_verification",
            value=f"{core.buffing_load_kn:g} kN (member share)",
            source="engine_default",
            note=(
                f"The RDSO complete-underframe proof buffing load (~{RDSO_PROOF_BUFFING_LOAD_KN:g} "
                "kN) is shared across the centre sill / sole bars; this member carries the stated "
                f"{core.buffing_load_kn:g} kN share — a TRANSCRIBED RDSO value / distribution that "
                "NEEDS VERIFICATION against the draft-gear load path before demo day."
            ),
        ),
        Assumption(
            field="axial_slenderness_scope",
            value="stocky member (0.6 fy)",
            source="engine_default",
            note=(
                "Permissible axial stress taken at the stocky-member value (~0.6 fy); a full "
                "column-buckling (slenderness) reduction and the bending-amplification factor "
                "in the interaction check are beyond this POC scope and are graded observations."
            ),
        ),
        Assumption(
            field="member_kind",
            value=geometry.member_kind,
            source="engine_default",
            note=(
                f"Member modelled as a doubly-symmetric welded I-section acting as a "
                f"{member_kind_label(geometry.member_kind)}, simply supported over its span."
            ),
        ),
    ]

    return RollingStockMemberAnalysis(
        member_length_m=round(span_m, 4),
        member_kind=geometry.member_kind,
        self_weight_kn_m=round(core.self_weight_kn_m, 4),
        vertical_load_kn=round(core.vertical_load_kn, 4),
        impact_factor=round(core.impact_factor, 4),
        dead_moment_knm=round(core.dead_moment_knm, 4),
        dead_shear_kn=round(core.dead_shear_kn, 4),
        live_moment_knm=round(core.live_moment_knm, 4),
        live_shear_kn=round(core.live_shear_kn, 4),
        design_moment_knm=round(core.design_moment_knm, 4),
        design_shear_kn=round(core.design_shear_kn, 4),
        buffing_load_kn=round(core.buffing_load_kn, 4),
        section_area_mm2=round(core.section_area_mm2, 2),
        inertia_mm4=round(core.inertia_mm4, 2),
        section_modulus_cm3=round(core.section_modulus_mm3 / 1000.0, 3),
        overall_depth_mm=round(core.overall_depth_mm, 3),
        max_bending_stress_mpa=round(core.max_bending_stress_mpa, 4),
        permissible_bending_stress_mpa=round(core.permissible_bending_stress_mpa, 4),
        max_shear_stress_mpa=round(core.max_shear_stress_mpa, 4),
        permissible_shear_stress_mpa=round(core.permissible_shear_stress_mpa, 4),
        max_axial_stress_mpa=round(core.max_axial_stress_mpa, 4),
        permissible_axial_stress_mpa=round(core.permissible_axial_stress_mpa, 4),
        interaction_ratio=round(core.interaction_ratio, 4),
        interaction_limit=INTERACTION_LIMIT,
        web_slenderness=round(core.web_slenderness, 4),
        web_slenderness_limit=WEB_SLENDERNESS_LIMIT,
        governing_load_case=core.governing_load_case,
        assumptions=assumptions,
        trail=trail.steps,
    )
