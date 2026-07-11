"""Welded steel plate-girder parameter and geometry models + intake schema.

`PlateGirderParams` is the single validated parameter model (extraction target,
engine input, drawing input, audit record). The two critical fields (`span_m`,
`steel_grade`) carry no default — they must come from the user, asked for in
that order. `None` on a section field means "auto-size". Field names, defaults
and hard ranges are normative per spec/capabilities/plate-girder.md.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from domain.culvert import Gauge, LoadingStandard

# The critical fields, never guessed/defaulted — asked for in this order.
CRITICAL_FIELDS = ("span_m", "steel_grade")

# Unusual-value threshold (flag and proceed — not a hard limit).
SPAN_WARNING_M = 45.0

SteelGradeLiteral = Literal["E250", "E350"]
DeckTypeLiteral = Literal["deck", "through"]


class PlateGirderParams(BaseModel):
    """Validated design parameters for one welded steel plate-girder run."""

    model_config = ConfigDict(extra="forbid")

    # --- critical (user-supplied, never defaulted) ---
    span_m: float = Field(
        ..., ge=6.0, le=60.0, description="Effective (simply-supported) span, m"
    )
    steel_grade: SteelGradeLiteral = Field(
        ..., description="Structural steel grade (E250 / E350)"
    )

    # --- loading / configuration defaults ---
    loading_standard: LoadingStandard = Field(
        default=LoadingStandard.T25_2008, description="Railway loading standard"
    )
    gauge: Gauge = Field(default=Gauge.BG, description="Track gauge (BG only in POC)")
    deck_type: DeckTypeLiteral = Field(
        default="deck",
        description="'deck' (girders below the track) or 'through' (track between girders)",
    )
    number_of_girders: int = Field(
        default=2, ge=2, le=6, description="Number of main plate girders across the deck"
    )

    # --- section overrides (None = auto-size) ---
    web_depth_mm: float | None = Field(
        default=None, description="Web depth override, mm; None = auto-size"
    )
    web_thickness_mm: float | None = Field(
        default=None, description="Web thickness override, mm; None = auto-size"
    )
    flange_width_mm: float | None = Field(
        default=None, description="Flange width override, mm; None = auto-size"
    )
    flange_thickness_mm: float | None = Field(
        default=None, description="Flange thickness override, mm; None = auto-size"
    )

    @field_validator(
        "web_depth_mm",
        "web_thickness_mm",
        "flange_width_mm",
        "flange_thickness_mm",
    )
    @classmethod
    def _override_must_be_positive(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("section override must be a positive value in mm")
        return value


class PlateGirderGeometry(BaseModel):
    """Fully-proportioned welded I plate girder — the one geometry source for the GA
    drawing, the 3D model and the audit record. All `_mm` fields are millimetres."""

    span_mm: float = Field(description="Effective span, mm")
    web_depth_mm: float = Field(description="Web plate depth (clear between flanges), mm")
    web_thickness_mm: float = Field(description="Web plate thickness, mm")
    flange_width_mm: float = Field(description="Flange plate width, mm")
    flange_thickness_mm: float = Field(description="Flange plate thickness, mm")
    overall_depth_mm: float = Field(
        description="Overall girder depth = web depth + 2 x flange thickness, mm"
    )
    number_of_girders: int = Field(description="Number of main girders across the deck")
    girder_spacing_mm: float = Field(description="Centre-to-centre spacing of the girders, mm")
    stiffener_spacing_mm: float = Field(
        description="Intermediate transverse web-stiffener spacing, mm"
    )


# --------------------------------------------------------------------------- intake schema
class PlateGirderExtractionResult(BaseModel):
    """Every PlateGirderParams field, optional — the Gemini structured-output schema.

    A field is set ONLY when the conversation explicitly states it; the model
    never invents, guesses or defaults a value."""

    span_m: float | None = Field(
        default=None,
        description=(
            "Effective (simply-supported) span in METRES. Convert stated units "
            "(e.g. '24000 mm' -> 24.0). Synonyms: span, clear span, effective span, "
            "girder span ('a 24 m span' -> 24.0)."
        ),
    )
    loading_standard: str | None = Field(
        default=None, description="Railway loading standard, e.g. '25t-2008'."
    )
    gauge: str | None = Field(default=None, description="Track gauge, 'BG'.")
    deck_type: str | None = Field(
        default=None,
        description="'deck' (deck-type girder) or 'through' (through-type girder).",
    )
    number_of_girders: int | None = Field(
        default=None, description="Number of main girders across the deck (2 to 6)."
    )
    steel_grade: str | None = Field(
        default=None, description="Structural steel grade, one of: E250, E350."
    )
    web_depth_mm: float | None = Field(
        default=None, description="Web depth override, in MILLIMETRES."
    )
    web_thickness_mm: float | None = Field(
        default=None, description="Web thickness override, in MILLIMETRES."
    )
    flange_width_mm: float | None = Field(
        default=None, description="Flange width override, in MILLIMETRES."
    )
    flange_thickness_mm: float | None = Field(
        default=None,
        description="Flange thickness override, in MILLIMETRES ('flange only 20 mm' -> 20).",
    )


# Templated, deterministic clarify questions (no LLM — demo-safe), with ranges.
CLARIFICATION_QUESTIONS: dict[str, str] = {
    "span_m": (
        "What is the effective span of the girder — the simply-supported span between "
        "bearing centres? Welded plate girders typically run about 6 m to 60 m."
    ),
    "steel_grade": (
        "What steel grade should the girder be designed in — E250 or E350 (per IS 2062)?"
    ),
}


def unusual_value_warnings(params: PlateGirderParams) -> list[str]:
    """Param-level unusual-value flags. The run proceeds; the UI shows them."""
    warnings: list[str] = []
    if params.span_m > SPAN_WARNING_M:
        warnings.append(
            f"Span {params.span_m:g} m exceeds {SPAN_WARNING_M:g} m — a long-span plate "
            "girder; the design proceeds but deflection and fatigue tend to govern and a "
            "truss or box girder may be more economical, warranting special review."
        )
    return warnings
