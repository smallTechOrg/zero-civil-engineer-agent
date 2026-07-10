"""RCC slab / T-beam deck parameter and geometry models + intake schema.

`SlabTbeamParams` is the single validated parameter model (extraction target,
engine input, drawing input, audit record). The one critical field (`span_m`)
carries no default — it must come from the user. `None` on a depth/width field
means "auto-size". Field names, defaults and hard ranges are normative and shared
with the spec-writer.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from domain.culvert import ConcreteGrade, Gauge, LoadingStandard, SteelGrade

# Priority order for the single clarifying question (never guessed/defaulted).
CRITICAL_FIELDS = ("span_m",)

# Unusual-value thresholds (flag and proceed — not hard limits).
SPAN_WARNING_M = 20.0
SOLID_SLAB_ECONOMIC_SPAN_M = 10.0


class SlabTbeamParams(BaseModel):
    """Validated design parameters for one RCC slab / T-beam deck run."""

    model_config = ConfigDict(extra="forbid")

    # --- critical (user-supplied, never defaulted) ---
    span_m: float = Field(
        ..., ge=3.0, le=25.0, description="Effective (simply-supported) span of the deck, m"
    )

    # --- deck configuration ---
    deck_type: Literal["solid_slab", "t_beam"] = Field(
        default="solid_slab",
        description="Deck form: a solid RCC slab or a slab-and-girder (T-beam) deck",
    )
    carriageway_width_m: float = Field(
        default=5.0, ge=3.0, le=12.0, description="Overall deck width carrying one track, m"
    )

    # --- loading ---
    loading_standard: LoadingStandard = Field(default=LoadingStandard.T25_2008)
    gauge: Gauge = Field(default=Gauge.BG)

    # --- T-beam configuration ---
    number_of_girders: int = Field(
        default=3, ge=2, le=8, description="Number of longitudinal girders (t_beam only)"
    )

    # --- materials ---
    concrete_grade: ConcreteGrade = Field(default=ConcreteGrade.M30)
    steel_grade: SteelGrade = Field(default=SteelGrade.FE500)
    clear_cover_mm: float = Field(
        default=40.0, ge=30.0, le=75.0, description="Clear cover to reinforcement, mm"
    )

    # --- geometry overrides (None = auto-size) ---
    slab_depth_mm: float | None = Field(
        default=None,
        description=(
            "Deck-slab thickness override, mm; None = auto-size. For a solid_slab this "
            "is the overall depth; for a t_beam it is the deck-slab (flange) thickness."
        ),
    )
    rib_width_mm: float | None = Field(
        default=None, description="T-beam rib (web) width override, mm; None = auto-size"
    )
    rib_depth_mm: float | None = Field(
        default=None, description="T-beam rib depth below the slab override, mm; None = auto-size"
    )
    flange_thickness_mm: float | None = Field(
        default=None,
        description=(
            "T-beam flange (deck-slab) thickness override, mm; None = auto-size. Takes "
            "precedence over slab_depth_mm for a t_beam deck."
        ),
    )

    @field_validator(
        "slab_depth_mm",
        "rib_width_mm",
        "rib_depth_mm",
        "flange_thickness_mm",
    )
    @classmethod
    def _override_must_be_positive(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("geometry override must be a positive value in mm")
        return value


class SlabTbeamGeometry(BaseModel):
    """Fully-proportioned deck — the one geometry source for the GA drawing, the 3D
    model and the audit record. All `_mm` fields are millimetres."""

    span_mm: float = Field(description="Effective span of the deck, mm")
    deck_type: str = Field(description="'solid_slab' | 't_beam'")
    overall_depth_mm: float = Field(description="Overall structural depth of the deck, mm")
    slab_depth_mm: float = Field(description="Deck-slab (flange) thickness, mm")
    rib_width_mm: float = Field(default=0.0, description="Rib (web) width, mm (0 = solid slab)")
    rib_depth_mm: float = Field(default=0.0, description="Rib depth below the slab, mm (0 = solid slab)")
    flange_width_mm: float = Field(description="Effective flange width in compression, mm")
    number_of_girders: int = Field(description="Number of longitudinal girders (1 = solid slab)")
    girder_spacing_mm: float = Field(description="Centre-to-centre spacing of the girders, mm")
    deck_width_mm: float = Field(description="Overall deck width, mm")


# --------------------------------------------------------------------------- intake schema
class SlabTbeamExtractionResult(BaseModel):
    """Every SlabTbeamParams field, optional — the Gemini structured-output schema.
    A field is set ONLY when the conversation explicitly states it; the model never
    invents, guesses or defaults a value."""

    span_m: float | None = Field(
        default=None,
        description=(
            "Effective span of the deck in METRES. Convert stated units (e.g. "
            "'12000 mm' -> 12.0). Synonyms: span, effective span, clear span between "
            "supports ('a 12 m span deck' -> 12.0)."
        ),
    )
    deck_type: str | None = Field(
        default=None,
        description=(
            "Deck form: 'solid_slab' when a solid slab deck is described, 't_beam' when "
            "girders / ribs / a T-beam / slab-and-girder deck is described."
        ),
    )
    carriageway_width_m: float | None = Field(
        default=None, description="Overall deck width carrying the track, in METRES."
    )
    number_of_girders: int | None = Field(
        default=None, description="Number of longitudinal girders for a T-beam deck."
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
    slab_depth_mm: float | None = Field(
        default=None, description="Deck-slab / overall-depth override, in MILLIMETRES."
    )
    rib_width_mm: float | None = Field(
        default=None, description="T-beam rib (web) width override, in MILLIMETRES."
    )
    rib_depth_mm: float | None = Field(
        default=None, description="T-beam rib depth override, in MILLIMETRES."
    )
    flange_thickness_mm: float | None = Field(
        default=None, description="T-beam flange (deck-slab) thickness override, in MILLIMETRES."
    )


# Templated, deterministic clarify questions (no LLM — demo-safe), with ranges.
CLARIFICATION_QUESTIONS: dict[str, str] = {
    "span_m": (
        "What is the effective span of the deck — the distance between the supports? "
        "RCC slab / T-beam railway decks typically run about 3 m to 25 m."
    ),
}


def unusual_value_warnings(params: SlabTbeamParams) -> list[str]:
    """Param-level unusual-value flags. The run proceeds; the UI shows them."""
    warnings: list[str] = []
    if params.span_m > SPAN_WARNING_M:
        warnings.append(
            f"Span {params.span_m:g} m exceeds {SPAN_WARNING_M:g} m — a long deck; the "
            "design proceeds but a prestressed or plate-girder deck may be more "
            "economical and warrants special review."
        )
    if params.deck_type == "solid_slab" and params.span_m > SOLID_SLAB_ECONOMIC_SPAN_M:
        warnings.append(
            f"A solid slab spanning {params.span_m:g} m is beyond the usual economic "
            f"range (~{SOLID_SLAB_ECONOMIC_SPAN_M:g} m) — a T-beam deck is normally "
            "lighter; the design proceeds and the proof-check grades it."
        )
    return warnings
