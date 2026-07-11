"""Fabricated structural-steel member parameter and geometry models + intake schema.

`SteelMemberParams` is the single validated parameter model (extraction target,
engine input, drawing input, audit record). The two critical fields
(`cantilever_length_m` and `transverse_load_kn`) carry no default — they must come
from the user (they drive the one clarifying question, in priority order). `None`
on a section field means "auto-size". Field names, defaults and hard ranges are
normative per spec/capabilities/structural-steel-member.md.

The member is a fabricated welded-I cantilever (bracket / gantry post / OHE mast)
carrying, in member-local axes, a transverse load `transverse_load_kn` at its tip
(bending + shear) and a co-existent axial load `axial_load_kn` (compression),
connected to its base by a fillet-welded group. Working-stress design to IS 800,
weld to IS 816.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Priority order for the single clarifying question (never guessed/defaulted).
CRITICAL_FIELDS = ("cantilever_length_m", "transverse_load_kn")

# Unusual-value thresholds (flag and proceed — not hard limits).
LENGTH_WARNING_M = 10.0
TRANSVERSE_LOAD_WARNING_KN = 600.0
AXIAL_LOAD_WARNING_KN = 2500.0

MemberTypeLiteral = Literal["bracket", "gantry_post", "ohe_mast"]
SteelGradeLiteral = Literal["E250", "E350"]


class SteelMemberParams(BaseModel):
    """Validated design parameters for one fabricated structural-steel member run."""

    model_config = ConfigDict(extra="forbid")

    # --- critical (user-supplied, never defaulted) ---
    cantilever_length_m: float = Field(
        ...,
        ge=0.5,
        le=12.0,
        description="Cantilever projection / height from the welded base to the load point, m",
    )
    transverse_load_kn: float = Field(
        ...,
        ge=1.0,
        le=2000.0,
        description="Governing transverse service load at the tip (bending + shear), kN",
    )

    # --- type + co-existent action defaults ---
    member_type: MemberTypeLiteral = Field(
        default="gantry_post",
        description="Fabricated member type: welded bracket, gantry post, or OHE mast",
    )
    axial_load_kn: float = Field(
        default=80.0,
        ge=0.0,
        le=5000.0,
        description="Co-existent axial (compression) service load along the member, kN",
    )

    # --- materials ---
    steel_grade: SteelGradeLiteral = Field(
        default="E250", description="Structural steel grade (E250 / E350)"
    )

    # --- section overrides (None = auto-size) ---
    web_depth_mm: float | None = Field(
        default=None, description="Clear web depth override, mm; None = auto-size"
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
    weld_size_mm: float | None = Field(
        default=None, description="Fillet-weld leg size override, mm; None = auto-size"
    )

    @field_validator(
        "web_depth_mm",
        "web_thickness_mm",
        "flange_width_mm",
        "flange_thickness_mm",
        "weld_size_mm",
    )
    @classmethod
    def _override_must_be_positive(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("section/weld override must be a positive value in mm")
        return value


class SteelMemberGeometry(BaseModel):
    """Fully-proportioned welded-I cantilever member — the one geometry source for
    the fabrication drawing, the 3D model and the audit record. All `_mm` fields
    are millimetres."""

    member_type: str = Field(description="'bracket' | 'gantry_post' | 'ohe_mast'")
    cantilever_length_mm: float = Field(description="Cantilever projection / height, mm")
    web_depth_mm: float = Field(description="Clear web depth between flanges, mm")
    web_thickness_mm: float = Field(description="Web plate thickness, mm")
    flange_width_mm: float = Field(description="Flange plate width, mm")
    flange_thickness_mm: float = Field(description="Flange plate thickness, mm")
    overall_depth_mm: float = Field(
        description="Overall section depth = web depth + 2 x flange thickness, mm"
    )
    weld_size_mm: float = Field(description="Base fillet-weld leg size, mm")


# --------------------------------------------------------------------------- intake schema
class SteelMemberExtractionResult(BaseModel):
    """Every SteelMemberParams field, optional — the Gemini structured-output schema.

    A field is set ONLY when the conversation explicitly states it; the model
    never invents, guesses or defaults a value."""

    cantilever_length_m: float | None = Field(
        default=None,
        description=(
            "Cantilever projection or member height in METRES, from the welded base "
            "to the load point. Convert stated units (e.g. '1500 mm' -> 1.5). "
            "Synonyms: arm, projection, cantilever length, post height, mast height."
        ),
    )
    transverse_load_kn: float | None = Field(
        default=None,
        description=(
            "Governing transverse (bending) service load at the tip, in kN. Synonyms: "
            "tip load, point load, lateral load, wind/surge load ('a 25 kN load' -> 25). "
            "Convert tonnes to kN (x9.81) if stated in t."
        ),
    )
    member_type: str | None = Field(
        default=None,
        description="'bracket', 'gantry_post', or 'ohe_mast' (the fabricated member type).",
    )
    axial_load_kn: float | None = Field(
        default=None,
        description="Co-existent axial (compression) load along the member, in kN.",
    )
    steel_grade: str | None = Field(
        default=None, description="Structural steel grade, one of: E250, E350."
    )
    web_depth_mm: float | None = Field(
        default=None, description="Clear web depth override, in MILLIMETRES."
    )
    web_thickness_mm: float | None = Field(
        default=None, description="Web thickness override, in MILLIMETRES."
    )
    flange_width_mm: float | None = Field(
        default=None, description="Flange width override, in MILLIMETRES."
    )
    flange_thickness_mm: float | None = Field(
        default=None, description="Flange thickness override, in MILLIMETRES."
    )
    weld_size_mm: float | None = Field(
        default=None, description="Fillet-weld leg size override, in MILLIMETRES."
    )


# Templated, deterministic clarify questions (no LLM — demo-safe), with ranges.
CLARIFICATION_QUESTIONS: dict[str, str] = {
    "cantilever_length_m": (
        "What is the cantilever length (projection or height) of the member — from "
        "the welded base connection to the point of load? Fabricated brackets/posts/"
        "masts typically run about 0.5 m to 12 m."
    ),
    "transverse_load_kn": (
        "What is the governing transverse (bending) service load at the tip of the "
        "member? Fabricated steel members commonly carry about 5 kN to 600 kN."
    ),
}


def unusual_value_warnings(params: SteelMemberParams) -> list[str]:
    """Param-level unusual-value flags. The run proceeds; the UI shows them."""
    warnings: list[str] = []
    if params.cantilever_length_m > LENGTH_WARNING_M:
        warnings.append(
            f"Cantilever length {params.cantilever_length_m:g} m exceeds "
            f"{LENGTH_WARNING_M:g} m — a long cantilever; the design proceeds but "
            "slenderness and second-order (P-delta) effects tend to govern and warrant "
            "special review."
        )
    if params.transverse_load_kn > TRANSVERSE_LOAD_WARNING_KN:
        warnings.append(
            f"Transverse load {params.transverse_load_kn:g} kN exceeds "
            f"{TRANSVERSE_LOAD_WARNING_KN:g} kN — a heavy tip load; the design proceeds "
            "but a fillet-welded end connection may be inadequate and a bolted or "
            "full-penetration moment connection may be required."
        )
    if params.axial_load_kn > AXIAL_LOAD_WARNING_KN:
        warnings.append(
            f"Axial load {params.axial_load_kn:g} kN exceeds {AXIAL_LOAD_WARNING_KN:g} "
            "kN — a heavily-loaded compression member; the design proceeds but buckling "
            "and the combined interaction will govern."
        )
    return warnings
