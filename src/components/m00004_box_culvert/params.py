"""M-00004 standard box-culvert parameter and geometry models.

`M00004Params` is the single validated parameter model for the params-direct
(form) intake path — no natural-language prompt, no LLM. The three critical
fields (`clear_span_m`, `clear_height_m`, `cushion_m`) select the standard
catalogue config; the remaining fields carry sensible standard defaults. Field
names, defaults and hard ranges are normative per
spec/capabilities/m00004-box-culvert.md.

`M00004Geometry` is the single geometry source for the GA drawing, the 3D
solid and the PDF sheet. Thickness, haunch and the bar schedule come ONLY from
the selected standard config (this is a standard-driven, not load-engineered,
component); every catalogue-derived value is PROVISIONAL and flagged as such.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from domain.culvert import ConcreteGrade, SteelGrade

# Interface conformance: declared critical fields. The clarify path is
# UNREACHABLE on this component (the form enforces them client-side and the API
# rejects a missing/invalid params object with 422), but the tuple is declared
# so the module structurally satisfies the ComponentModule protocol.
CRITICAL_FIELDS = ("clear_span_m", "clear_height_m", "cushion_m")

# Fixed engine constants for the standard appendages (from the RDSO pilot).
# Recorded as Assumptions in sizing.py, not exposed as form fields.
WING_LEN_MM = 2500.0  # return/wing-wall length beyond each barrel end
APRON_LEN_MM = 2500.0  # apron-floor length beyond each end
APRON_THICKNESS_MM = 300.0
CURTAIN_THICKNESS_MM = 400.0
CURTAIN_DEPTH_MM = 1000.0

# Nominal clear cover to reinforcement (mm) — assumption for the bar layout.
CLEAR_COVER_MM = 50.0

# --------------------------------------------------------------------------- Phase-2 engine constants
# Standard RDSO/M-00004 GA-sheet detailing constants (elevation / plan / details).
# Every derived value backed by these is PROVISIONAL (verify against RDSO/M-00004).
WEARING_COURSE_THICKNESS_MM = 150.0  # wearing course on the top slab / formation
PCC_THICKNESS_MM = 150.0  # PCC levelling course under the box
STONE_PITCHING_THICKNESS_MM = 300.0  # stone pitching w/ cement grouting on the slopes
BASE_COURSE_THICKNESS_MM = 150.0  # base course under the pitching/apron
BED_SLOPE_RUN = 100.0  # bed slope 1 in BED_SLOPE_RUN (1 in 100)
WEEP_HOLE_DIA_MM = 75.0  # 75-dia PVC weep holes
WEEP_HOLE_SPACING_MM = 1000.0  # weep holes @ 1000 c/c
DROP_WALL_DEPTH_MM = 1500.0  # drop-wall depth below bed at the outlet
HFL_ABOVE_BED_FACTOR = 0.75  # HFL above bed = factor x clear height (PROVISIONAL; hydraulics unverified)
RETURN_WALL_BASE_FACTOR = 0.5  # return-wall base width = factor x outer height (PROVISIONAL taper basis)


class ExposureCondition(str, Enum):
    """Component-local exposure class — drives the M40 concrete-grade derivation.

    Title-block / notes + concrete-grade derivation only; not a structural input.
    """

    MODERATE = "moderate"
    SEVERE = "severe"
    VERY_SEVERE = "very_severe"


class M00004Params(BaseModel):
    """Validated design parameters for one M-00004 standard box-culvert run."""

    model_config = ConfigDict(extra="forbid")

    # --- critical (user-supplied; select the standard config) ---
    clear_span_m: float = Field(
        ..., ge=1.0, le=8.0, description="Clear (inside) span between wall faces, m"
    )
    clear_height_m: float = Field(
        ..., ge=1.0, le=8.0, description="Clear (inside) height between slab soffits, m"
    )
    cushion_m: float = Field(
        ..., ge=0.0, le=6.0, description="Earth fill over the top slab, m — selects the standard fill tier"
    )

    # --- optional site / loading ---
    surcharge_kn_m2: float = Field(
        default=0.0, ge=0.0, le=50.0,
        description="Uniform surcharge on the fill, kN/m^2 (catalogue subset is surcharge = 0)",
    )
    formation_width_m: float = Field(
        default=6.85, gt=0.0, description="BG single-line formation width, m — drives barrel length"
    )
    side_slope_h_per_v: float = Field(
        default=2.0, ge=0.0, description="Embankment side slope H:V — drives barrel length"
    )

    # --- materials (title-block / notes + concrete-grade derivation) ---
    concrete_grade: ConcreteGrade | None = Field(
        default=None,
        description="None = derive per exposure/size (M35 typical / M40 very-severe / "
        "M30 below 1 m); a set value overrides. M25/M30/M35/M40.",
    )
    steel_grade: SteelGrade = Field(
        default=SteelGrade.FE415, description="Fe415 (RDSO/M-00004 default) or Fe500"
    )
    exposure: ExposureCondition = Field(
        default=ExposureCondition.SEVERE,
        description="Exposure class (moderate / severe / very_severe) — drives the M40 "
        "concrete-grade derivation branch; title-block/notes + derivation only",
    )


class M00004Geometry(BaseModel):
    """Standard single-cell box + appendages — the one geometry source for the
    GA drawing, the 3D solid and the PDF sheet. All `_mm` fields are millimetres.

    `thickness_mm`, `haunch_mm` and `bar_schedule` come ONLY from the selected
    catalogue config (PROVISIONAL). The opening is drawn at the entered size.
    """

    clear_span_mm: float = Field(description="Clear inside span (entered), mm")
    clear_height_mm: float = Field(description="Clear inside height (entered), mm")
    thickness_mm: float = Field(description="Slab/wall thickness from the standard config (PROVISIONAL), mm")
    haunch_mm: float = Field(description="45-degree haunch leg from the standard config (PROVISIONAL), mm")
    outer_width_mm: float = Field(description="Overall width = clear span + 2 x thickness, mm")
    outer_height_mm: float = Field(description="Overall height = clear height + 2 x thickness, mm")
    barrel_length_mm: float = Field(
        description="Box length along the track axis = formation width + 2 x side slope x "
        "(cushion + outer height), mm"
    )
    config_id: str = Field(description="Selected standard catalogue config id")
    bar_schedule: dict[str, dict[str, float]] = Field(
        description="Selected config's PROVISIONAL bar schedule: mark -> {dia_mm, spacing_mm}"
    )
    wing_len_mm: float = Field(default=WING_LEN_MM, description="Return/wing-wall length beyond each end, mm")
    apron_len_mm: float = Field(default=APRON_LEN_MM, description="Apron-floor length beyond each end, mm")
    apron_thickness_mm: float = Field(default=APRON_THICKNESS_MM, description="Apron slab thickness, mm")
    curtain_thickness_mm: float = Field(default=CURTAIN_THICKNESS_MM, description="Curtain-wall thickness, mm")
    curtain_depth_mm: float = Field(default=CURTAIN_DEPTH_MM, description="Curtain-wall depth below bed, mm")

    # --- Phase-2 GA-sheet fields (single source for every new diagram/model) ---
    concrete_grade_resolved: str = Field(
        description="Resolved concrete grade value (e.g. 'M35') — the one grade rendered everywhere"
    )
    cushion_mm: float = Field(description="cushion_m x 1000 — fill over the top slab (elevation), mm")
    formation_width_mm: float = Field(
        description="formation_width_m x 1000 — formation level width (elevation), mm"
    )
    side_slope_h_per_v: float = Field(
        description="Echo of the param — earth-bank slope (elevation) + wing-wall splay (plan)"
    )
    wearing_course_thickness_mm: float = Field(
        default=WEARING_COURSE_THICKNESS_MM, description="Wearing course on the top slab / formation, mm"
    )
    pcc_thickness_mm: float = Field(
        default=PCC_THICKNESS_MM, description="PCC levelling course under the box, mm"
    )
    stone_pitching_thickness_mm: float = Field(
        default=STONE_PITCHING_THICKNESS_MM, description="Stone pitching on the embankment slopes, mm"
    )
    base_course_thickness_mm: float = Field(
        default=BASE_COURSE_THICKNESS_MM, description="Base course under the pitching/apron, mm"
    )
    bed_slope_run: float = Field(
        default=BED_SLOPE_RUN, description="Bed slope 1 in bed_slope_run (elevation callout)"
    )
    weep_hole_dia_mm: float = Field(
        default=WEEP_HOLE_DIA_MM, description="75-dia PVC weep holes (plan + typical details), mm"
    )
    weep_hole_spacing_mm: float = Field(
        default=WEEP_HOLE_SPACING_MM, description="Weep holes @ 1000 c/c (plan + typical details), mm"
    )
    drop_wall_depth_mm: float = Field(
        default=DROP_WALL_DEPTH_MM, description="Drop-wall depth below bed at the outlet, mm"
    )
    hfl_above_bed_mm: float = Field(
        description="Derived HFL_ABOVE_BED_FACTOR x clear_height_mm (PROVISIONAL) — elevation HFL line, mm"
    )
    return_wall_base_width_mm: float = Field(
        description="Derived RETURN_WALL_BASE_FACTOR x outer_height_mm (PROVISIONAL) — return-wall base, mm"
    )
    return_wall_top_width_mm: float = Field(
        description="= thickness_mm — return-wall taper top width, mm"
    )

    provisional_flags: list[str] = Field(
        default_factory=list,
        description="Config-selection / extrapolation PROVISIONAL flags (empty = exact standard config)",
    )


def unusual_value_warnings(params: M00004Params) -> list[str]:
    """Param-level unusual-value flags. The run proceeds; the UI shows them.

    These mirror the out-of-catalogue conditions so a form-only run still surfaces
    the PROVISIONAL context even before sizing runs.
    """
    warnings: list[str] = []
    if params.cushion_m > 2.0:
        warnings.append(
            f"Fill {params.cushion_m:g} m exceeds the digitized range (0-2 m) — the nearest "
            "standard (2 m) config is reproduced; PROVISIONAL, verify against RDSO/M-00004."
        )
    if params.clear_span_m > 6.0 or params.clear_height_m > 6.0:
        warnings.append(
            f"Box {params.clear_span_m:g}x{params.clear_height_m:g} m exceeds the digitized "
            "range (<=6x6 m) — the 6x6 m standard config is reproduced; PROVISIONAL, verify "
            "against RDSO/M-00004."
        )
    if params.surcharge_kn_m2 > 0:
        warnings.append(
            f"Surcharge {params.surcharge_kn_m2:g} kN/m^2 is not covered by the digitized subset "
            "(surcharge = 0); PROVISIONAL, verify against RDSO/M-00004."
        )
    return warnings
