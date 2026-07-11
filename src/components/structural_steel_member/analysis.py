"""Design-action + stress analysis of the fabricated welded-I cantilever member.

Given `SteelMemberParams` and a proportioned `SteelMemberGeometry`, computes, in
member-local axes, the design actions and the working-stress checks' governing
quantities:

* **Bending** — M = P*L (transverse tip load over the cantilever) plus the member
  self-weight moment (steel at 78.5 kN/m^3), and the extreme-fibre stress M/Z.
* **Shear** — V = P plus the self-weight shear, and the average web shear V/A_web.
* **Axial** — the co-existent axial load N and the direct stress N/A, against the
  permissible axial compressive stress at the member slenderness KL/r_min.
* **Combined** — the IS 800 axial+bending interaction ratio.
* **Weld** — the base fillet-weld-group throat stress (combined normal + shear).

`compute_forces` is the pure numeric core (reused by the sizing loop);
`analyse_member` wraps it with the CalcStep trail and Assumptions and returns the
`SteelMemberAnalysis` model the calc sheet, checks and proof-check consume.
"""

from __future__ import annotations

from typing import NamedTuple

from pydantic import BaseModel, Field

from components.base import Assumption, coerce
from components.structural_steel_member._engine_common import (
    CANTILEVER_EFFECTIVE_LENGTH_FACTOR,
    CITATION_ACTIONS,
    CITATION_AXIAL,
    CITATION_BENDING,
    CITATION_COMBINED,
    CITATION_DEAD_LOAD,
    CITATION_SECTION,
    CITATION_SHEAR,
    CITATION_SLENDERNESS,
    CITATION_WELD,
    PERMISSIBLE_WELD_STRESS_MPA,
    SIGMA_AC_TABLE_NEEDS_VERIFICATION,
    SLENDERNESS_LIMIT,
    STEEL_UNIT_WEIGHT_KN_M3,
    Trail,
    permissible,
    permissible_axial_stress,
    section_properties,
    sigma_ac_table_value,
    weld_stresses,
)
from components.structural_steel_member.params import (
    SteelMemberGeometry,
    SteelMemberParams,
)

COMBINED_LIMIT = 1.0


class SteelMemberAnalysis(BaseModel):
    """Design actions + working-stress quantities for one member — the rehydratable
    model. Field names are normative (calc sheet, checks, proof-check and summary
    read them)."""

    member_type: str = Field(description="'bracket' | 'gantry_post' | 'ohe_mast'")
    cantilever_length_m: float = Field(description="Cantilever length, m")

    # --- actions (member-local) ---
    self_weight_kn_m: float = Field(description="Member self-weight UDL, kN/m")
    transverse_load_kn: float = Field(description="Transverse tip load, kN")
    axial_load_kn: float = Field(description="Co-existent axial load, kN")
    design_moment_knm: float = Field(description="Design bending moment at the base, kN*m")
    design_shear_kn: float = Field(description="Design shear at the base, kN")
    design_axial_kn: float = Field(description="Design axial force, kN")

    # --- section properties ---
    section_area_mm2: float = Field(description="Cross-sectional area, mm^2")
    inertia_xx_mm4: float = Field(description="Strong-axis second moment of area, mm^4")
    section_modulus_cm3: float = Field(description="Elastic section modulus Z, cm^3")
    inertia_yy_mm4: float = Field(description="Weak-axis second moment of area, mm^4")
    radius_of_gyration_min_mm: float = Field(description="Minimum radius of gyration, mm")
    overall_depth_mm: float = Field(description="Overall section depth, mm")

    # --- slenderness ---
    slenderness_ratio: float = Field(description="KL / r_min")
    slenderness_limit: float = Field(description="Permissible slenderness limit")

    # --- stresses & permissibles ---
    max_axial_stress_mpa: float = Field(description="Direct axial stress N/A, N/mm^2")
    permissible_axial_stress_mpa: float = Field(description="Permissible axial stress, N/mm^2")
    sigma_ac_table_mpa: float = Field(
        description="Transcribed sigma_ac table value at this slenderness (cross-check)"
    )
    max_bending_stress_mpa: float = Field(description="Extreme-fibre bending stress, N/mm^2")
    permissible_bending_stress_mpa: float = Field(description="Permissible bending stress, N/mm^2")
    max_shear_stress_mpa: float = Field(description="Average web shear stress, N/mm^2")
    permissible_shear_stress_mpa: float = Field(description="Permissible shear stress, N/mm^2")
    combined_ratio: float = Field(description="Axial + bending interaction ratio")
    combined_limit: float = Field(description="Interaction ratio limit (1.0)")

    # --- weld ---
    weld_size_mm: float = Field(description="Fillet-weld leg size, mm")
    weld_throat_mm: float = Field(description="Fillet-weld throat thickness, mm")
    weld_normal_stress_mpa: float = Field(description="Weld normal stress (axial+bending), N/mm^2")
    weld_shear_stress_mpa: float = Field(description="Weld shear stress, N/mm^2")
    weld_stress_mpa: float = Field(description="Resultant weld throat stress, N/mm^2")
    permissible_weld_stress_mpa: float = Field(description="Permissible fillet-weld stress, N/mm^2")

    assumptions: list[Assumption] = Field(default_factory=list)
    trail: list = Field(default_factory=list, description="CalcStep trail")


class ForceCore(NamedTuple):
    """The pure numeric analysis result (no trail) — shared by sizing + analyse."""

    member_type: str
    cantilever_length_m: float
    self_weight_kn_m: float
    transverse_load_kn: float
    axial_load_kn: float
    design_moment_knm: float
    design_shear_kn: float
    design_axial_kn: float
    section_area_mm2: float
    inertia_xx_mm4: float
    section_modulus_mm3: float
    inertia_yy_mm4: float
    radius_of_gyration_min_mm: float
    overall_depth_mm: float
    slenderness_ratio: float
    max_axial_stress_mpa: float
    permissible_axial_stress_mpa: float
    sigma_ac_table_mpa: float
    max_bending_stress_mpa: float
    permissible_bending_stress_mpa: float
    max_shear_stress_mpa: float
    permissible_shear_stress_mpa: float
    combined_ratio: float
    weld_size_mm: float
    weld_throat_mm: float
    weld_normal_stress_mpa: float
    weld_shear_stress_mpa: float
    weld_stress_mpa: float
    permissible_weld_stress_mpa: float


def compute_forces(
    params: SteelMemberParams, geometry: SteelMemberGeometry
) -> ForceCore:
    """Deterministic design actions, stresses, slenderness and weld stress."""
    perm = permissible(params.steel_grade)
    fy = perm.fy_n_mm2
    length_m = geometry.cantilever_length_mm / 1000.0
    length_mm = geometry.cantilever_length_mm

    section = section_properties(
        web_depth_mm=geometry.web_depth_mm,
        web_thickness_mm=geometry.web_thickness_mm,
        flange_width_mm=geometry.flange_width_mm,
        flange_thickness_mm=geometry.flange_thickness_mm,
    )

    # --- actions (member-local, cantilever) ---
    self_weight = section.area_mm2 * 1e-6 * STEEL_UNIT_WEIGHT_KN_M3  # kN/m
    p = params.transverse_load_kn
    n = params.axial_load_kn
    design_moment = p * length_m + self_weight * length_m**2 / 2.0
    design_shear = p + self_weight * length_m
    design_axial = n

    # --- section stresses ---
    axial_stress = design_axial * 1e3 / section.area_mm2  # N/mm^2
    bending_stress = design_moment * 1e6 / section.section_modulus_mm3  # N/mm^2
    web_area = geometry.web_depth_mm * geometry.web_thickness_mm  # mm^2
    shear_stress = design_shear * 1e3 / web_area  # N/mm^2

    # --- slenderness & permissible axial ---
    slenderness = (
        CANTILEVER_EFFECTIVE_LENGTH_FACTOR * length_mm / section.radius_of_gyration_min_mm
        if section.radius_of_gyration_min_mm > 0
        else 0.0
    )
    perm_axial = permissible_axial_stress(fy, slenderness)
    sigma_ac_table = sigma_ac_table_value(slenderness)

    # --- combined interaction ---
    combined = axial_stress / perm_axial + bending_stress / perm.sigma_bending_n_mm2

    # --- weld group ---
    welds = weld_stresses(
        weld_size_mm=geometry.weld_size_mm,
        overall_depth_mm=geometry.overall_depth_mm,
        web_depth_mm=geometry.web_depth_mm,
        flange_width_mm=geometry.flange_width_mm,
        moment_knm=design_moment,
        shear_kn=design_shear,
        axial_kn=design_axial,
    )

    return ForceCore(
        member_type=geometry.member_type,
        cantilever_length_m=length_m,
        self_weight_kn_m=self_weight,
        transverse_load_kn=p,
        axial_load_kn=n,
        design_moment_knm=design_moment,
        design_shear_kn=design_shear,
        design_axial_kn=design_axial,
        section_area_mm2=section.area_mm2,
        inertia_xx_mm4=section.inertia_xx_mm4,
        section_modulus_mm3=section.section_modulus_mm3,
        inertia_yy_mm4=section.inertia_yy_mm4,
        radius_of_gyration_min_mm=section.radius_of_gyration_min_mm,
        overall_depth_mm=section.overall_depth_mm,
        slenderness_ratio=slenderness,
        max_axial_stress_mpa=axial_stress,
        permissible_axial_stress_mpa=perm_axial,
        sigma_ac_table_mpa=sigma_ac_table,
        max_bending_stress_mpa=bending_stress,
        permissible_bending_stress_mpa=perm.sigma_bending_n_mm2,
        max_shear_stress_mpa=shear_stress,
        permissible_shear_stress_mpa=perm.sigma_shear_n_mm2,
        combined_ratio=combined,
        weld_size_mm=geometry.weld_size_mm,
        weld_throat_mm=welds.throat_mm,
        weld_normal_stress_mpa=welds.normal_stress_mpa,
        weld_shear_stress_mpa=welds.shear_stress_mpa,
        weld_stress_mpa=welds.resultant_stress_mpa,
        permissible_weld_stress_mpa=PERMISSIBLE_WELD_STRESS_MPA,
    )


def analyse_member(
    params: SteelMemberParams, geometry: SteelMemberGeometry
) -> SteelMemberAnalysis:
    """Full analysis with the CalcStep trail + modelling assumptions."""
    params = coerce(SteelMemberParams, params)
    geometry = coerce(SteelMemberGeometry, geometry)
    core = compute_forces(params, geometry)
    trail = Trail("A")
    length_m = core.cantilever_length_m

    trail.record(
        description="Member self-weight UDL (steel section)",
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
        description="Design bending moment at the base",
        formula="M = P * L + w_sw * L^2 / 2",
        inputs={
            "P_kn": core.transverse_load_kn,
            "L_m": round(length_m, 3),
            "w_sw_kn_m": round(core.self_weight_kn_m, 4),
        },
        value=round(core.design_moment_knm, 3),
        unit="kN*m",
        citation=CITATION_ACTIONS,
    )
    trail.record(
        description="Design shear at the base",
        formula="V = P + w_sw * L",
        inputs={"P_kn": core.transverse_load_kn, "w_sw_kn_m": round(core.self_weight_kn_m, 4)},
        value=round(core.design_shear_kn, 3),
        unit="kN",
        citation=CITATION_ACTIONS,
    )
    trail.record(
        description="Design axial force (co-existent)",
        formula="N = axial_load",
        inputs={"axial_load_kn": core.axial_load_kn},
        value=round(core.design_axial_kn, 3),
        unit="kN",
        citation=CITATION_ACTIONS,
    )
    trail.record(
        description="Elastic section modulus of the welded I-section",
        formula="Z = I_xx / (D/2)",
        inputs={
            "I_xx_mm4": round(core.inertia_xx_mm4, 0),
            "overall_depth_mm": round(core.overall_depth_mm, 1),
        },
        value=round(core.section_modulus_mm3 / 1000.0, 1),
        unit="cm^3",
        citation=CITATION_SECTION,
    )
    trail.record(
        description="Minimum radius of gyration (weak axis)",
        formula="r_min = sqrt(I_yy / A)",
        inputs={
            "I_yy_mm4": round(core.inertia_yy_mm4, 0),
            "A_mm2": round(core.section_area_mm2, 1),
        },
        value=round(core.radius_of_gyration_min_mm, 3),
        unit="mm",
        citation=CITATION_SECTION,
    )
    trail.record(
        description="Slenderness ratio (cantilever effective length K = 2.0)",
        formula="lambda = K * L / r_min",
        inputs={
            "K": CANTILEVER_EFFECTIVE_LENGTH_FACTOR,
            "L_mm": round(length_m * 1000.0, 1),
            "r_min_mm": round(core.radius_of_gyration_min_mm, 3),
        },
        value=round(core.slenderness_ratio, 2),
        unit="-",
        citation=CITATION_SLENDERNESS,
    )
    trail.record(
        description="Direct axial stress",
        formula="sigma_ac,cal = N / A",
        inputs={"N_kn": round(core.design_axial_kn, 3), "A_mm2": round(core.section_area_mm2, 1)},
        value=round(core.max_axial_stress_mpa, 3),
        unit="N/mm^2",
        citation=CITATION_AXIAL,
    )
    trail.record(
        description="Permissible axial compressive stress (Merchant-Rankine)",
        formula="sigma_ac = 0.6 * fcc*fy / (fcc^1.4 + fy^1.4)^(1/1.4), fcc = pi^2 E / lambda^2",
        inputs={
            "lambda": round(core.slenderness_ratio, 2),
            "fy_n_mm2": core.permissible_bending_stress_mpa / 0.66,
        },
        value=round(core.permissible_axial_stress_mpa, 3),
        unit="N/mm^2",
        citation=CITATION_AXIAL,
    )
    trail.record(
        description="Extreme-fibre bending stress",
        formula="sigma_bc,cal = M / Z",
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
        description="Combined axial + bending interaction",
        formula="r = sigma_ac,cal/sigma_ac + sigma_bc,cal/sigma_bc",
        inputs={
            "sigma_ac_cal": round(core.max_axial_stress_mpa, 3),
            "sigma_ac": round(core.permissible_axial_stress_mpa, 3),
            "sigma_bc_cal": round(core.max_bending_stress_mpa, 3),
            "sigma_bc": round(core.permissible_bending_stress_mpa, 3),
        },
        value=round(core.combined_ratio, 4),
        unit="-",
        citation=CITATION_COMBINED,
    )
    trail.record(
        description="Resultant fillet-weld throat stress (base weld group)",
        formula="f_r = sqrt((N/A_w + M/Z_w)^2 + (V/A_w)^2)",
        inputs={
            "weld_size_mm": core.weld_size_mm,
            "throat_mm": round(core.weld_throat_mm, 3),
            "normal_n_mm2": round(core.weld_normal_stress_mpa, 3),
            "shear_n_mm2": round(core.weld_shear_stress_mpa, 3),
        },
        value=round(core.weld_stress_mpa, 3),
        unit="N/mm^2",
        citation=CITATION_WELD,
    )

    fy = core.permissible_bending_stress_mpa / 0.66
    assumptions = [
        Assumption(
            field="steel_unit_weight_kn_m3",
            value=STEEL_UNIT_WEIGHT_KN_M3,
            source="engine_default",
            note=f"Structural steel self-weight taken as {STEEL_UNIT_WEIGHT_KN_M3:g} kN/m^3 (IS 800).",
        ),
        Assumption(
            field="effective_length_factor",
            value=CANTILEVER_EFFECTIVE_LENGTH_FACTOR,
            source="engine_default",
            note=(
                f"Cantilever (fixed-free) effective length factor K = "
                f"{CANTILEVER_EFFECTIVE_LENGTH_FACTOR:g}; buckling about the weak (minor) "
                "axis governs the permissible axial stress."
            ),
        ),
        Assumption(
            field="permissible_axial_stress_needs_verification",
            value=round(core.permissible_axial_stress_mpa, 2),
            source="engine_default",
            note=(
                f"Permissible axial stress {core.permissible_axial_stress_mpa:.1f} N/mm^2 at "
                f"lambda {core.slenderness_ratio:.0f} is computed from the Merchant-Rankine "
                f"formula and cross-checks the TRANSCRIBED IS 800 sigma_ac table value "
                f"{core.sigma_ac_table_mpa:.1f} N/mm^2 (fy 250) — an ASSUMED code table that "
                "NEEDS VERIFICATION against the source code before demo day."
                if SIGMA_AC_TABLE_NEEDS_VERIFICATION
                else "Permissible axial stress from the Merchant-Rankine formula."
            ),
        ),
        Assumption(
            field="permissible_weld_stress_needs_verification",
            value=core.permissible_weld_stress_mpa,
            source="engine_default",
            note=(
                f"Permissible fillet-weld throat stress taken as "
                f"{core.permissible_weld_stress_mpa:g} N/mm^2 (IS 816, shop weld) — a "
                "TRANSCRIBED value that NEEDS VERIFICATION against the source code."
            ),
        ),
        Assumption(
            field="lateral_torsional_buckling_scope",
            value="flagged",
            source="engine_default",
            note=(
                "The permissible bending stress is taken for a laterally-restrained "
                "member (0.66 fy); a full lateral-torsional-buckling reduction for an "
                "unrestrained compression flange is beyond this POC scope and is flagged."
            ),
        ),
    ]

    return SteelMemberAnalysis(
        member_type=core.member_type,
        cantilever_length_m=round(length_m, 4),
        self_weight_kn_m=round(core.self_weight_kn_m, 4),
        transverse_load_kn=round(core.transverse_load_kn, 4),
        axial_load_kn=round(core.axial_load_kn, 4),
        design_moment_knm=round(core.design_moment_knm, 4),
        design_shear_kn=round(core.design_shear_kn, 4),
        design_axial_kn=round(core.design_axial_kn, 4),
        section_area_mm2=round(core.section_area_mm2, 2),
        inertia_xx_mm4=round(core.inertia_xx_mm4, 2),
        section_modulus_cm3=round(core.section_modulus_mm3 / 1000.0, 3),
        inertia_yy_mm4=round(core.inertia_yy_mm4, 2),
        radius_of_gyration_min_mm=round(core.radius_of_gyration_min_mm, 4),
        overall_depth_mm=round(core.overall_depth_mm, 3),
        slenderness_ratio=round(core.slenderness_ratio, 4),
        slenderness_limit=SLENDERNESS_LIMIT,
        max_axial_stress_mpa=round(core.max_axial_stress_mpa, 4),
        permissible_axial_stress_mpa=round(core.permissible_axial_stress_mpa, 4),
        sigma_ac_table_mpa=round(core.sigma_ac_table_mpa, 4),
        max_bending_stress_mpa=round(core.max_bending_stress_mpa, 4),
        permissible_bending_stress_mpa=round(core.permissible_bending_stress_mpa, 4),
        max_shear_stress_mpa=round(core.max_shear_stress_mpa, 4),
        permissible_shear_stress_mpa=round(core.permissible_shear_stress_mpa, 4),
        combined_ratio=round(core.combined_ratio, 4),
        combined_limit=COMBINED_LIMIT,
        weld_size_mm=round(core.weld_size_mm, 3),
        weld_throat_mm=round(core.weld_throat_mm, 4),
        weld_normal_stress_mpa=round(core.weld_normal_stress_mpa, 4),
        weld_shear_stress_mpa=round(core.weld_shear_stress_mpa, 4),
        weld_stress_mpa=round(core.weld_stress_mpa, 4),
        permissible_weld_stress_mpa=round(core.permissible_weld_stress_mpa, 4),
        assumptions=assumptions,
        trail=trail.steps,
    )
