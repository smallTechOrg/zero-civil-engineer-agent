"""RCC cantilever retaining-wall parameter and geometry models + intake schema.

`RetainingWallParams` is the single validated parameter model (extraction
target, engine input, drawing input, audit record). The three critical fields
(`retained_height_m`, `safe_bearing_capacity_kn_m2`, `backfill_friction_angle_deg`)
carry no default — they must come from the user. `None` on a thickness/length
field means "auto-size". Field names, defaults and hard ranges are normative per
spec/capabilities/retaining-wall.md.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from domain.culvert import ConcreteGrade, SteelGrade

# Priority order for the single clarifying question (never guessed/defaulted).
CRITICAL_FIELDS = (
    "retained_height_m",
    "safe_bearing_capacity_kn_m2",
    "backfill_friction_angle_deg",
)

# Unusual-value thresholds (flag and proceed — not hard limits).
RETAINED_HEIGHT_WARNING_M = 6.0
SBC_WARNING_KN_M2 = 100.0


class RetainingWallParams(BaseModel):
    """Validated design parameters for one RCC cantilever retaining-wall run."""

    model_config = ConfigDict(extra="forbid")

    # --- critical (user-supplied, never defaulted) ---
    retained_height_m: float = Field(
        ..., ge=1.5, le=8.0, description="Total wall height, base underside to top of fill, m"
    )
    safe_bearing_capacity_kn_m2: float = Field(
        ..., ge=50.0, le=600.0, description="Safe bearing capacity of the founding soil, kN/m^2"
    )
    backfill_friction_angle_deg: float = Field(
        ..., ge=25.0, le=40.0, description="Angle of internal friction of the backfill, degrees"
    )

    # --- soil / loading defaults ---
    backfill_unit_weight_kn_m3: float = Field(
        default=18.0, ge=15.0, le=22.0, description="Unit weight of the retained backfill, kN/m^3"
    )
    backfill_slope_deg: float = Field(
        default=0.0, ge=0.0, le=20.0, description="Surcharge/backfill slope beta above the wall, degrees"
    )
    track_surcharge: bool = Field(
        default=True, description="Apply BG single-line track surcharge (equivalent height of fill)"
    )
    surcharge_kn_m2: float = Field(
        default=0.0, ge=0.0, le=50.0, description="Additional uniform surcharge on the backfill, kN/m^2"
    )
    base_friction_coeff: float = Field(
        default=0.5, ge=0.4, le=0.6, description="Coefficient of friction concrete-on-soil at the base"
    )

    # --- materials ---
    concrete_grade: ConcreteGrade = Field(default=ConcreteGrade.M30)
    steel_grade: SteelGrade = Field(default=SteelGrade.FE500)
    clear_cover_mm: float = Field(
        default=50.0, ge=40.0, le=75.0, description="Clear cover to reinforcement, mm"
    )

    # --- geometry overrides (None = auto-size) ---
    stem_top_thickness_mm: float | None = Field(
        default=None, description="Stem top thickness override, mm; None = auto-size"
    )
    stem_base_thickness_mm: float | None = Field(
        default=None, description="Stem base thickness override, mm; None = auto-size"
    )
    base_thickness_mm: float | None = Field(
        default=None, description="Base slab thickness override, mm; None = auto-size"
    )
    toe_length_mm: float | None = Field(
        default=None, description="Toe projection override, mm; None = auto-size"
    )
    heel_length_mm: float | None = Field(
        default=None, description="Heel projection override, mm; None = auto-size"
    )

    @field_validator(
        "stem_top_thickness_mm",
        "stem_base_thickness_mm",
        "base_thickness_mm",
        "toe_length_mm",
        "heel_length_mm",
    )
    @classmethod
    def _override_must_be_positive(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("geometry override must be a positive value in mm")
        return value


class RetainingWallGeometry(BaseModel):
    """Fully-proportioned cantilever wall — the one geometry source for the GA
    drawing, the 3D model and the audit record. All `_mm` fields are millimetres."""

    stem_top_thickness_mm: float = Field(description="Stem thickness at the top, mm")
    stem_base_thickness_mm: float = Field(description="Stem thickness at the base, mm")
    base_thickness_mm: float = Field(description="Base slab (raft) thickness, mm")
    toe_length_mm: float = Field(description="Toe projection in front of the stem, mm")
    heel_length_mm: float = Field(description="Heel projection behind the stem, mm")
    base_width_mm: float = Field(description="Overall base width = toe + stem base + heel, mm")
    total_height_mm: float = Field(
        description="Total wall height, base underside to top of stem/fill, mm"
    )
    key_depth_mm: float = Field(default=0.0, description="Shear-key depth below the base, mm (0 = none)")


# --------------------------------------------------------------------------- intake schema
class RWExtractionResult(BaseModel):
    """Every RetainingWallParams field, optional — the Gemini structured-output
    schema. A field is set ONLY when the conversation explicitly states it; the
    model never invents, guesses or defaults a value."""

    retained_height_m: float | None = Field(
        default=None,
        description=(
            "Total retained wall height in METRES. Convert stated units (e.g. "
            "'5000 mm' -> 5.0). Synonyms: retained height, wall height, height of "
            "earth retained ('retain 5 m of earth' -> 5.0)."
        ),
    )
    safe_bearing_capacity_kn_m2: float | None = Field(
        default=None,
        description=(
            "Safe bearing capacity of the founding soil in kN/m^2. Synonyms: SBC, "
            "bearing capacity, allowable bearing pressure ('SBC 200' -> 200)."
        ),
    )
    backfill_friction_angle_deg: float | None = Field(
        default=None,
        description=(
            "Angle of internal friction / angle of repose of the backfill, in "
            "DEGREES. Synonyms: phi, angle of repose, friction angle ('phi 30' -> 30)."
        ),
    )
    backfill_unit_weight_kn_m3: float | None = Field(
        default=None, description="Unit weight of the retained backfill soil, kN/m^3."
    )
    backfill_slope_deg: float | None = Field(
        default=None, description="Backfill/surcharge slope beta above the wall, degrees."
    )
    track_surcharge: bool | None = Field(
        default=None,
        description=(
            "True when a railway (BG/track) surcharge is mentioned; False when the "
            "request explicitly says no track surcharge."
        ),
    )
    surcharge_kn_m2: float | None = Field(
        default=None, description="Additional uniform surcharge on the backfill, kN/m^2."
    )
    base_friction_coeff: float | None = Field(
        default=None, description="Coefficient of friction between base and soil (mu)."
    )
    concrete_grade: str | None = Field(
        default=None, description="Concrete grade, one of: M25, M30, M35."
    )
    steel_grade: str | None = Field(
        default=None, description="Steel grade, one of: Fe415, Fe500."
    )
    clear_cover_mm: float | None = Field(
        default=None, description="Clear cover to reinforcement, in MILLIMETRES."
    )
    stem_top_thickness_mm: float | None = Field(
        default=None, description="Stem top thickness override, in MILLIMETRES."
    )
    stem_base_thickness_mm: float | None = Field(
        default=None,
        description="Stem base thickness override, in MILLIMETRES ('stem base only 250 mm' -> 250).",
    )
    base_thickness_mm: float | None = Field(
        default=None, description="Base slab thickness override, in MILLIMETRES."
    )
    toe_length_mm: float | None = Field(
        default=None, description="Toe projection override, in MILLIMETRES."
    )
    heel_length_mm: float | None = Field(
        default=None, description="Heel projection override, in MILLIMETRES."
    )


# Templated, deterministic clarify questions (no LLM — demo-safe), with ranges.
CLARIFICATION_QUESTIONS: dict[str, str] = {
    "retained_height_m": (
        "What is the retained height of the wall — the total height of earth to be "
        "retained? Standard RCC cantilever walls run about 1.5 m to 8 m."
    ),
    "safe_bearing_capacity_kn_m2": (
        "What is the safe bearing capacity (SBC) of the founding soil? "
        "Typical values run 100 kN/m^2 to 400 kN/m^2."
    ),
    "backfill_friction_angle_deg": (
        "What is the angle of internal friction (phi) of the backfill? "
        "Granular railway backfill is typically 30 to 35 degrees."
    ),
}


def unusual_value_warnings(params: RetainingWallParams) -> list[str]:
    """Param-level unusual-value flags. The run proceeds; the UI shows them."""
    warnings: list[str] = []
    if params.retained_height_m > RETAINED_HEIGHT_WARNING_M:
        warnings.append(
            f"Retained height {params.retained_height_m:g} m exceeds "
            f"{RETAINED_HEIGHT_WARNING_M:g} m — a tall cantilever wall; the design "
            "proceeds but a counterfort wall may be more economical and warrants "
            "special review."
        )
    if params.safe_bearing_capacity_kn_m2 < SBC_WARNING_KN_M2:
        warnings.append(
            f"Safe bearing capacity {params.safe_bearing_capacity_kn_m2:g} kN/m^2 is "
            f"below {SBC_WARNING_KN_M2:g} kN/m^2 — weak founding soil; the design "
            "proceeds but bearing pressure will govern and may need a wider base."
        )
    return warnings
