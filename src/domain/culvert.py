"""Culvert domain models — the typed core the engine, drawing, 3D and graph slices share.

`CulvertParams` is the single parameter model (extraction schema, engine input,
drawing input, audit record). Field names, defaults and hard ranges are normative
per spec/data.md. `BoxGeometry`, `Assumption` and `CalcStep` are the engine's
outputs consumed by the drawing, calc-sheet and 3D-model slices.
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Gauge(str, Enum):
    """Track gauge — BG (broad gauge) only in the POC."""

    BG = "BG"


class LoadingStandard(str, Enum):
    """Railway loading standard — 25t Loading-2008 only in the POC (pluggable later)."""

    T25_2008 = "25t-2008"


class ConcreteGrade(str, Enum):
    M25 = "M25"
    M30 = "M30"
    M35 = "M35"


class SteelGrade(str, Enum):
    FE415 = "Fe415"
    FE500 = "Fe500"


AssumptionSource = Literal["user", "preset", "engine_default"]


class CulvertParams(BaseModel):
    """Validated design parameters for one single-cell RCC box culvert run.

    The three critical fields (`clear_span_m`, `clear_height_m`, `cushion_m`)
    must come from the user — they carry no default. `None` on a thickness field
    means "auto-size" (the engine decides and records an Assumption).
    """

    model_config = ConfigDict(extra="forbid")

    clear_span_m: float = Field(
        ..., ge=1.0, le=8.0, description="Clear (inside) span between wall faces, m"
    )
    clear_height_m: float = Field(
        ..., ge=1.0, le=6.0, description="Clear (inside) height between slab soffits, m"
    )
    cushion_m: float = Field(
        ..., ge=0.0, le=10.0, description="Fill from top of top slab to formation level, m"
    )
    gauge: Gauge = Field(default=Gauge.BG, description="Track gauge (BG only in POC)")
    tracks: int = Field(default=1, ge=1, le=1, description="Number of tracks (1 only in POC)")
    loading_standard: LoadingStandard = Field(
        default=LoadingStandard.T25_2008, description="Railway loading standard"
    )
    concrete_grade: ConcreteGrade = Field(default=ConcreteGrade.M30)
    steel_grade: SteelGrade = Field(default=SteelGrade.FE500)
    clear_cover_mm: float = Field(default=50, ge=40, le=75, description="Clear cover to reinforcement, mm")
    soil_unit_weight_kn_m3: float = Field(
        default=18.0, ge=15, le=22, description="Unit weight of fill, kN/m³"
    )
    angle_of_friction_deg: float = Field(
        default=30.0, ge=25, le=40, description="Angle of internal friction of fill, degrees"
    )
    formation_width_m: float = Field(
        default=6.85, gt=0, description="Formation width (BG single line default), m — drives barrel length"
    )
    side_slope_h_per_v: float = Field(
        default=2.0, ge=0, description="Embankment side slope, horizontal per vertical — drives barrel length"
    )
    top_slab_thickness_mm: float | None = Field(
        default=None, description="Top slab thickness override, mm; None = auto-size"
    )
    bottom_slab_thickness_mm: float | None = Field(
        default=None, description="Bottom slab thickness override, mm; None = auto-size"
    )
    wall_thickness_mm: float | None = Field(
        default=None, description="Side wall thickness override, mm; None = auto-size"
    )
    haunch_mm: float = Field(
        default=150, ge=0, le=300, description="Haunch leg size at inside corners, mm"
    )

    @field_validator("top_slab_thickness_mm", "bottom_slab_thickness_mm", "wall_thickness_mm")
    @classmethod
    def _thickness_override_must_be_positive(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("thickness override must be a positive value in mm")
        return value


class BoxGeometry(BaseModel):
    """Fully-sized single-cell box — the one geometry source for the GA drawing,
    the 3D model, and the audit record. All `_m` fields are metres, `_mm` millimetres.
    """

    clear_span_m: float = Field(description="Clear inside opening between wall faces, m")
    clear_height_m: float = Field(description="Clear inside opening between slab soffits, m")
    cushion_m: float = Field(description="Fill from top of top slab to formation level, m")
    top_slab_thickness_mm: float = Field(description="Top slab thickness (sized or overridden), mm")
    bottom_slab_thickness_mm: float = Field(description="Bottom slab thickness (sized or overridden), mm")
    wall_thickness_mm: float = Field(description="Side wall thickness (sized or overridden), mm")
    haunch_mm: float = Field(description="45-degree haunch leg size at each inside corner (both legs equal), mm")
    external_width_m: float = Field(description="Overall box width = clear span + 2 x wall thickness, m")
    external_height_m: float = Field(
        description="Overall box height = clear height + top slab + bottom slab, m"
    )
    barrel_length_m: float = Field(
        description="Box length along the track axis = formation width + 2 x side slope x "
        "(cushion + external height), m"
    )


class Assumption(BaseModel):
    """One defaulted value made explicit — shown in the calc sheet and audit record.

    The engine only ever emits `source="engine_default"`; the graph tags
    user/preset-sourced values itself.
    """

    field: str
    value: float | int | str
    source: AssumptionSource
    note: str


class CalcStep(BaseModel):
    """One traceable computation: formula, substituted inputs, result, and citation.

    Phase 2's calc sheet renders these as the drill-down trail — no number in any
    artefact may lack a CalcStep.
    """

    step_id: str
    description: str
    formula: str
    inputs: dict[str, float | int | str]
    value: float
    unit: str
    citation: str


# ---------------------------------------------------------------------------
# Phase 2 — frame-analysis models (engine.analyse_frame outputs).
#
# Sign conventions (normative for every consumer, incl. the FE cross-check):
# * Design bending moments are POSITIVE when they produce TENSION ON THE
#   INSIDE FACE of the member (the face toward the box interior). Under
#   gravity load this makes slab midspan moments positive and corner moments
#   negative. The two members meeting at a corner share ONE design moment
#   (moment continuity around the closed frame), so corner values are equal
#   on the slab end and the wall end.
# * Member-local frames: slabs run left -> right (origin at the left corner
#   node); walls run bottom -> top (origin at the bottom corner node). Loads
#   toward the box interior are positive in every local frame.
# * All forces are per 1 m strip of barrel: moments kN*m/m, shears kN/m,
#   pressures kN/m^2 (== kN/m on the 1 m strip).
# ---------------------------------------------------------------------------


class LoadCase(BaseModel):
    """One elementary load case on the 1 m-strip closed-frame model.

    Rich enough for an independent FE program to rebuild the loading without
    reading any other data: apply `top_slab_udl_kn_m2` downward on the top
    slab, `bottom_slab_net_udl_kn_m2` upward on the bottom slab, and the
    trapezoid `wall_pressure_top/bottom_kn_m2` horizontally toward the box
    interior on BOTH walls (symmetric). `wall_axial_kn_per_m` is axial only
    (wall self-weight) — it reaches the base reaction but bends nothing.
    """

    name: str = Field(description="Case id, e.g. 'DL', 'SIDL', 'LL+CDA', 'EP_at_rest'")
    description: str = Field(description="What physical loading this case represents")
    top_slab_udl_kn_m2: float = Field(
        description="Uniform load on the top slab, kN/m^2, positive DOWNWARD (toward interior)"
    )
    wall_pressure_top_kn_m2: float = Field(
        description="Lateral pressure on each wall at the top-slab centreline level, kN/m^2, "
        "positive INWARD (toward the box interior); applied on both walls symmetrically"
    )
    wall_pressure_bottom_kn_m2: float = Field(
        description="Lateral pressure on each wall at the bottom-slab centreline level, kN/m^2, "
        "positive INWARD; varies linearly (trapezoid) between top and bottom values"
    )
    wall_axial_kn_per_m: float = Field(
        description="Axial (vertical) load per wall from this case, kN per m strip — e.g. wall "
        "self-weight; contributes to the base reaction but produces no frame bending"
    )
    bottom_slab_applied_udl_kn_m2: float = Field(
        description="Load applied directly on the bottom slab, kN/m^2, positive DOWNWARD — "
        "e.g. bottom-slab self-weight, water inside the box"
    )
    base_reaction_kn_m2: float = Field(
        description="Uniform upward subgrade reaction closing vertical equilibrium over the "
        "centreline span (rigid-base uniform-reaction assumption), kN/m^2"
    )
    bottom_slab_net_udl_kn_m2: float = Field(
        description="Net load bending the bottom slab = base_reaction - bottom_slab_applied, "
        "kN/m^2, positive UPWARD (toward interior)"
    )
    citations: list[str] = Field(
        description="Source citations for every value in this case (code clause / table / "
        "document with ACS level where applicable)"
    )
    notes: str = Field(default="", description="Modelling notes (dispersal widths, bounds, etc.)")


class LoadCombination(BaseModel):
    """One analysed service combination (IRS working-stress practice — all factors 1.0)."""

    name: str = Field(description="Combination id, e.g. 'C1: Box empty - earth at rest + LL'")
    description: str = Field(description="What state of the structure this combination covers")
    case_factors: dict[str, float] = Field(
        description="LoadCase name -> factor; the combined member loads are the factored sums"
    )
    citation: str = Field(description="Basis for the combination (IRS working-stress practice)")


class MemberForces(BaseModel):
    """End/midspan design forces for one member under one combination.

    Locals: slabs start=left corner, end=right corner; walls start=bottom
    corner, end=top corner. Moments are design-convention (tension-inside
    positive, kN*m/m); shears are the member-local values at the start/end
    nodes, kN/m (positive = dM/dx in the local frame; use magnitudes for
    design). The single 'wall' entry represents BOTH walls (symmetric model).
    """

    member: str = Field(description="'top_slab' | 'bottom_slab' | 'wall'")
    end_moment_start_knm: float = Field(
        description="Design moment at the start node (slab left corner / wall bottom corner), kN*m/m"
    )
    end_moment_end_knm: float = Field(
        description="Design moment at the end node (slab right corner / wall top corner), kN*m/m"
    )
    midspan_moment_knm: float = Field(
        description="Design moment at member mid-length, kN*m/m (tension-inside positive)"
    )
    end_shear_start_kn: float = Field(description="Shear at the start node, kN/m (local sign)")
    end_shear_end_kn: float = Field(description="Shear at the end node, kN/m (local sign)")


class CombinationForces(BaseModel):
    """All member forces for one combination — one entry per member."""

    combination: str = Field(description="LoadCombination.name these forces belong to")
    members: list[MemberForces] = Field(
        description="Forces for top_slab, bottom_slab and wall (one wall entry covers both)"
    )


class SectionEnvelope(BaseModel):
    """Design envelope at one critical section of one member, across all combinations."""

    member: str = Field(description="'top_slab' | 'bottom_slab' | 'wall'")
    section: str = Field(
        description="Critical-section id: slabs 'end' | 'haunch_face' | 'midspan'; walls "
        "'bottom_end' | 'bottom_haunch_face' | 'midheight' | 'top_haunch_face' | 'top_end'"
    )
    position_m: float = Field(
        description="Distance from the member-local origin (slab left corner / wall bottom), m"
    )
    max_moment_knm: float = Field(description="Maximum design moment over all combinations, kN*m/m")
    max_moment_combination: str = Field(description="Combination governing max_moment_knm")
    min_moment_knm: float = Field(description="Minimum design moment over all combinations, kN*m/m")
    min_moment_combination: str = Field(description="Combination governing min_moment_knm")
    max_abs_shear_kn: float = Field(
        description="Maximum absolute shear over all combinations at this section, kN/m"
    )
    max_shear_combination: str = Field(description="Combination governing max_abs_shear_kn")


class FrameModel(BaseModel):
    """The analysis model — everything an independent FE re-solve needs to match like-for-like."""

    span_centreline_m: float = Field(
        description="Frame span, wall centreline to wall centreline = clear span + wall thickness, m"
    )
    height_centreline_m: float = Field(
        description="Frame height, slab centreline to slab centreline = clear height + "
        "(top slab + bottom slab)/2, m"
    )
    strip_width_m: float = Field(description="Analysis strip width along the barrel (1.0 m)")
    top_slab_thickness_mm: float = Field(description="Top slab thickness used for stiffness, mm")
    bottom_slab_thickness_mm: float = Field(
        description="Bottom slab thickness used for stiffness, mm"
    )
    wall_thickness_mm: float = Field(description="Wall thickness used for stiffness, mm")
    i_top_m4: float = Field(description="Top slab second moment of area per m strip = t^3/12, m^4")
    i_bottom_m4: float = Field(description="Bottom slab second moment of area per m strip, m^4")
    i_wall_m4: float = Field(description="Wall second moment of area per m strip, m^4")
    modulus_note: str = Field(
        description="Young's modulus treatment — only stiffness RATIOS matter (E cancels)"
    )
    boundary_note: str = Field(
        description="Support/boundary idealisation (rigid-base uniform reaction, no sway, "
        "axial deformation neglected, haunches neglected in stiffness)"
    )
    sign_convention: str = Field(
        description="Design moment sign convention (tension-inside positive) and member locals"
    )


class AnalysisResult(BaseModel):
    """engine.analyse_frame output — load cases, combinations, member forces, envelopes,
    the frame model, and the full calc trail. See the sign-convention block above."""

    load_cases: list[LoadCase] = Field(description="Elementary cases, FE-rebuildable")
    combinations: list[LoadCombination] = Field(
        description="Analysed service combinations incl. box empty/full variants"
    )
    member_forces: list[CombinationForces] = Field(
        description="Solved design forces per combination and member"
    )
    envelopes: list[SectionEnvelope] = Field(
        description="Max/min design moments and max shear at critical sections, governing "
        "combination named"
    )
    frame_model: FrameModel = Field(description="Analysis geometry/stiffness actually used")
    assumptions: list[Assumption] = Field(
        description="Modelling assumptions made explicit (uniform base reaction, SIDL values, ...)"
    )
    trail: list[CalcStep] = Field(
        description="CalcStep trail for every computed number — merged into the run's calc sheet"
    )


# Unusual-value thresholds per spec/data.md (flag and proceed — not hard limits).
SPAN_WARNING_THRESHOLD_M = 6.0
CUSHION_WARNING_THRESHOLD_M = 8.0


def unusual_value_warnings(params: CulvertParams) -> list[str]:
    """Param-level unusual-value flags per spec/data.md. The run proceeds; the UI shows them."""
    warnings: list[str] = []
    if params.clear_span_m > SPAN_WARNING_THRESHOLD_M:
        warnings.append(
            f"Clear span {params.clear_span_m:g} m exceeds {SPAN_WARNING_THRESHOLD_M:g} m — "
            "beyond the RDSO B-10152/R standard single-cell box family; the design proceeds "
            "but warrants special review."
        )
    if params.cushion_m > CUSHION_WARNING_THRESHOLD_M:
        warnings.append(
            f"Cushion {params.cushion_m:g} m exceeds {CUSHION_WARNING_THRESHOLD_M:g} m — "
            "abnormally high fill for a box culvert; the design proceeds but warrants "
            "special review."
        )
    return warnings
