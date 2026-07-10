"""Pier & abutment substructure parameter and geometry models + intake schema.

`PierAbutmentParams` is the single validated parameter model (extraction target,
engine input, drawing input, audit record). The three critical fields
(`pier_height_m`, `superstructure_reaction_kn`, `safe_bearing_capacity_kn_m2`)
carry no default — they must come from the user. `None` on a geometry field means
"auto-size". Field names, defaults and hard ranges are normative per
spec/capabilities/pier-abutment.md.

The substructure carries the superstructure reaction (a PARAM — delivered FROM
the deck) through the pier/abutment shaft and its spread footing to the founding
soil. Stability (overturning / sliding / base bearing) governs, exactly like a
retaining wall, with the vertical deck reaction added on top.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from domain.culvert import ConcreteGrade, SteelGrade

# Priority order for the single clarifying question (never guessed/defaulted).
CRITICAL_FIELDS = (
    "pier_height_m",
    "superstructure_reaction_kn",
    "safe_bearing_capacity_kn_m2",
)

# Unusual-value thresholds (flag and proceed — not hard limits).
PIER_HEIGHT_WARNING_M = 15.0
REACTION_WARNING_KN = 12000.0
SBC_WARNING_KN_M2 = 100.0


class PierAbutmentParams(BaseModel):
    """Validated design parameters for one pier / abutment substructure run."""

    model_config = ConfigDict(extra="forbid")

    # --- critical (user-supplied, never defaulted) ---
    pier_height_m: float = Field(
        ...,
        ge=2.0,
        le=30.0,
        description="Total height, founding level (underside of footing) to bearing level, m",
    )
    superstructure_reaction_kn: float = Field(
        ...,
        ge=100.0,
        le=20000.0,
        description="Total vertical DL+LL reaction delivered to this substructure, kN",
    )
    safe_bearing_capacity_kn_m2: float = Field(
        ...,
        ge=50.0,
        le=1000.0,
        description="Safe bearing capacity of the founding soil, kN/m^2",
    )

    # --- type + loading context ---
    component_kind: Literal["pier", "abutment"] = Field(
        default="pier", description="Substructure type: intermediate pier or end abutment"
    )
    span_m: float = Field(
        default=20.0,
        ge=3.0,
        le=60.0,
        description="Span carried (longitudinal/braking reference; for an abutment, "
        "the backfill height reference), m",
    )
    backfill_friction_angle_deg: float = Field(
        default=30.0,
        ge=25.0,
        le=40.0,
        description="Angle of internal friction of the backfill (abutment earth pressure only), deg",
    )
    backfill_unit_weight_kn_m3: float = Field(
        default=18.0, ge=15.0, le=22.0, description="Unit weight of the retained backfill, kN/m^3"
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
    pier_width_mm: float | None = Field(
        default=None, description="Pier/stem width ALONG traffic (longitudinal), mm; None = auto"
    )
    pier_length_mm: float | None = Field(
        default=None, description="Pier/stem length ACROSS traffic (transverse), mm; None = auto"
    )
    cap_thickness_mm: float | None = Field(
        default=None, description="Pier/abutment cap thickness, mm; None = auto"
    )
    footing_length_mm: float | None = Field(
        default=None, description="Spread-footing length ALONG traffic (longitudinal), mm; None = auto"
    )
    footing_width_mm: float | None = Field(
        default=None, description="Spread-footing width ACROSS traffic (transverse), mm; None = auto"
    )
    footing_thickness_mm: float | None = Field(
        default=None, description="Spread-footing thickness, mm; None = auto"
    )

    @field_validator(
        "pier_width_mm",
        "pier_length_mm",
        "cap_thickness_mm",
        "footing_length_mm",
        "footing_width_mm",
        "footing_thickness_mm",
    )
    @classmethod
    def _override_must_be_positive(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("geometry override must be a positive value in mm")
        return value


class PierAbutmentGeometry(BaseModel):
    """Fully-proportioned substructure — the one geometry source for the GA
    drawing, the 3D model and the audit record. All `_mm` fields are millimetres.

    Coordinate convention (normative for analysis / drawing / 3D):
    x = longitudinal (along traffic, the overturning direction); the footing is
    symmetric about the pier centre-line. `footing_length_mm` is the longitudinal
    dimension B used in the base-pressure formula p = W/A(1 +/- 6e/B).
    """

    total_height_mm: float = Field(description="Founding level to bearing level, mm")
    component_kind: str = Field(description="'pier' | 'abutment'")
    pier_width_mm: float = Field(description="Pier/stem width along traffic (longitudinal), mm")
    pier_length_mm: float = Field(description="Pier/stem length across traffic (transverse), mm")
    cap_thickness_mm: float = Field(description="Cap thickness, mm")
    cap_width_mm: float = Field(description="Cap width along traffic (longitudinal), mm")
    cap_length_mm: float = Field(description="Cap length across traffic (transverse), mm")
    footing_length_mm: float = Field(description="Footing length along traffic (longitudinal = B), mm")
    footing_width_mm: float = Field(description="Footing width across traffic (transverse = L), mm")
    footing_thickness_mm: float = Field(description="Footing thickness, mm")


# --------------------------------------------------------------------------- intake schema
class PierAbutmentExtractionResult(BaseModel):
    """Every PierAbutmentParams field, optional — the Gemini structured-output
    schema. A field is set ONLY when the conversation explicitly states it; the
    model never invents, guesses or defaults a value."""

    pier_height_m: float | None = Field(
        default=None,
        description=(
            "Total substructure height in METRES, founding level to bearing level. "
            "Convert stated units (e.g. '9000 mm' -> 9.0). Synonyms: pier height, "
            "abutment height, height of pier."
        ),
    )
    superstructure_reaction_kn: float | None = Field(
        default=None,
        description=(
            "Total vertical reaction from the superstructure delivered to this "
            "substructure, in kN. Synonyms: deck reaction, bearing reaction, DL+LL "
            "reaction ('reaction 4000 kN' -> 4000). Convert tonnes to kN (x9.81) if stated in t."
        ),
    )
    safe_bearing_capacity_kn_m2: float | None = Field(
        default=None,
        description=(
            "Safe bearing capacity of the founding soil in kN/m^2. Synonyms: SBC, "
            "bearing capacity, allowable bearing pressure ('SBC 300' -> 300)."
        ),
    )
    component_kind: str | None = Field(
        default=None,
        description="'pier' for an intermediate pier, 'abutment' for an end abutment with backfill.",
    )
    span_m: float | None = Field(
        default=None, description="Span carried by the superstructure, in METRES."
    )
    backfill_friction_angle_deg: float | None = Field(
        default=None,
        description="Angle of internal friction (phi) of the abutment backfill, in DEGREES.",
    )
    backfill_unit_weight_kn_m3: float | None = Field(
        default=None, description="Unit weight of the backfill soil, kN/m^3."
    )
    base_friction_coeff: float | None = Field(
        default=None, description="Coefficient of friction between the footing base and soil (mu)."
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
    pier_width_mm: float | None = Field(
        default=None, description="Pier width along traffic override, in MILLIMETRES."
    )
    pier_length_mm: float | None = Field(
        default=None, description="Pier length across traffic override, in MILLIMETRES."
    )
    cap_thickness_mm: float | None = Field(
        default=None, description="Cap thickness override, in MILLIMETRES."
    )
    footing_length_mm: float | None = Field(
        default=None, description="Footing length (longitudinal) override, in MILLIMETRES."
    )
    footing_width_mm: float | None = Field(
        default=None, description="Footing width (transverse) override, in MILLIMETRES."
    )
    footing_thickness_mm: float | None = Field(
        default=None, description="Footing thickness override, in MILLIMETRES."
    )


# Templated, deterministic clarify questions (no LLM — demo-safe), with ranges.
CLARIFICATION_QUESTIONS: dict[str, str] = {
    "pier_height_m": (
        "What is the height of the pier / abutment — founding level to bearing "
        "level? Railway substructures typically run about 4 m to 15 m."
    ),
    "superstructure_reaction_kn": (
        "What is the total vertical reaction the superstructure delivers to this "
        "substructure (DL + LL)? Single-span railway decks commonly deliver "
        "1000 kN to 8000 kN per support."
    ),
    "safe_bearing_capacity_kn_m2": (
        "What is the safe bearing capacity (SBC) of the founding soil? "
        "Typical values run 150 kN/m^2 to 450 kN/m^2."
    ),
}


def unusual_value_warnings(params: PierAbutmentParams) -> list[str]:
    """Param-level unusual-value flags. The run proceeds; the UI shows them."""
    warnings: list[str] = []
    if params.pier_height_m > PIER_HEIGHT_WARNING_M:
        warnings.append(
            f"Pier height {params.pier_height_m:g} m exceeds {PIER_HEIGHT_WARNING_M:g} m — "
            "a tall substructure; the design proceeds but slenderness and second-order "
            "effects warrant special review."
        )
    if params.superstructure_reaction_kn > REACTION_WARNING_KN:
        warnings.append(
            f"Superstructure reaction {params.superstructure_reaction_kn:g} kN exceeds "
            f"{REACTION_WARNING_KN:g} kN — a heavy deck; the design proceeds but the "
            "footing and bearing pressures will be large."
        )
    if params.safe_bearing_capacity_kn_m2 < SBC_WARNING_KN_M2:
        warnings.append(
            f"Safe bearing capacity {params.safe_bearing_capacity_kn_m2:g} kN/m^2 is below "
            f"{SBC_WARNING_KN_M2:g} kN/m^2 — weak founding soil; the design proceeds but "
            "bearing pressure will govern and may need a much wider footing or piles."
        )
    return warnings
