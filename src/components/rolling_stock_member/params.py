"""Rolling-stock member parameter and geometry models + intake schema.

`RollingStockMemberParams` is the single validated parameter model (extraction
target, engine input, drawing input, audit record). The one critical field
(`member_length_m`) carries no default — it must come from the user. `None` on a
section field means "auto-size". Field names, defaults and hard ranges are
normative per spec/capabilities/rolling-stock-member.md.

The member is a fabricated (welded) steel I-section forming part of a freight-
stock underframe (a sole bar, a headstock, or an underframe cross member),
designed to RDSO wagon-design load cases (vertical payload with dynamic augment +
longitudinal buffing / draft load) with IS 800 working-stress section checks.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# The single critical field, never guessed/defaulted.
CRITICAL_FIELDS = ("member_length_m",)

# Unusual-value thresholds (flag and proceed — not hard limits).
LENGTH_WARNING_M = 12.0
BUFFING_WARNING_KN = 2000.0
VERTICAL_WARNING_KN = 1000.0

SteelGradeLiteral = Literal["E250", "E350"]
MemberKindLiteral = Literal["sole_bar", "headstock", "underframe_cross_member"]

_MEMBER_KIND_LABELS: dict[str, str] = {
    "sole_bar": "sole bar (longitudinal underframe edge member)",
    "headstock": "headstock (end cross member carrying the draft gear)",
    "underframe_cross_member": "underframe cross member (transverse floor member)",
}


class RollingStockMemberParams(BaseModel):
    """Validated design parameters for one rolling-stock member run."""

    model_config = ConfigDict(extra="forbid")

    # --- critical (user-supplied, never defaulted) ---
    member_length_m: float = Field(
        ...,
        ge=0.5,
        le=15.0,
        description="Effective (simply-supported) span of the member between supports, m",
    )

    # --- type + loading configuration defaults ---
    member_kind: MemberKindLiteral = Field(
        default="sole_bar",
        description="Underframe member type: sole_bar / headstock / underframe_cross_member",
    )
    design_vertical_load_kn: float = Field(
        default=120.0,
        ge=10.0,
        le=2000.0,
        description="Design vertical load (this member's share of payload + tare), kN",
    )
    design_buffing_load_kn: float = Field(
        default=400.0,
        ge=0.0,
        le=3000.0,
        description="Design longitudinal buffing/draft load carried by this member, kN",
    )

    # --- materials ---
    steel_grade: SteelGradeLiteral = Field(
        default="E250", description="Structural steel grade (E250 / E350)"
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


class RollingStockMemberGeometry(BaseModel):
    """Fully-proportioned welded I member — the one geometry source for the
    fabrication drawing, the 3D model and the audit record. All `_mm` fields are
    millimetres."""

    member_length_mm: float = Field(description="Effective member span, mm")
    member_kind: str = Field(description="'sole_bar' | 'headstock' | 'underframe_cross_member'")
    web_depth_mm: float = Field(description="Web plate depth (clear between flanges), mm")
    web_thickness_mm: float = Field(description="Web plate thickness, mm")
    flange_width_mm: float = Field(description="Flange plate width, mm")
    flange_thickness_mm: float = Field(description="Flange plate thickness, mm")
    overall_depth_mm: float = Field(
        description="Overall member depth = web depth + 2 x flange thickness, mm"
    )
    weld_size_mm: float = Field(
        description="Fillet-weld leg joining the web to the flanges, mm"
    )


# --------------------------------------------------------------------------- intake schema
class RollingStockMemberExtractionResult(BaseModel):
    """Every RollingStockMemberParams field, optional — the Gemini structured-output
    schema. A field is set ONLY when the conversation explicitly states it; the
    model never invents, guesses or defaults a value."""

    member_length_m: float | None = Field(
        default=None,
        description=(
            "Effective span of the member between supports, in METRES. Convert stated "
            "units (e.g. '2400 mm' -> 2.4). Synonyms: member length, span, length of "
            "the sole bar / headstock / cross member ('a 2.4 m cross member' -> 2.4)."
        ),
    )
    member_kind: str | None = Field(
        default=None,
        description=(
            "Underframe member type: 'sole_bar', 'headstock', or "
            "'underframe_cross_member'."
        ),
    )
    design_vertical_load_kn: float | None = Field(
        default=None,
        description=(
            "Design vertical load this member carries (payload + tare share), in kN. "
            "Convert tonnes to kN (x9.81) if stated in t."
        ),
    )
    design_buffing_load_kn: float | None = Field(
        default=None,
        description=(
            "Design longitudinal buffing (compressive) / draft (tensile) load carried "
            "by this member, in kN ('buffing load 800 kN' -> 800)."
        ),
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
        description="Flange thickness override, in MILLIMETRES ('flange only 10 mm' -> 10).",
    )


# Templated, deterministic clarify questions (no LLM — demo-safe), with ranges.
CLARIFICATION_QUESTIONS: dict[str, str] = {
    "member_length_m": (
        "What is the length of the member — the effective span between its supports? "
        "Rolling-stock underframe members typically run about 2 m (a headstock or "
        "cross member) to 12 m (a full-length sole bar)."
    ),
}


def member_kind_label(kind: str) -> str:
    """Human-readable description of a member kind (for calc sheet / drawing / memo)."""
    return _MEMBER_KIND_LABELS.get(kind, kind)


def unusual_value_warnings(params: RollingStockMemberParams) -> list[str]:
    """Param-level unusual-value flags. The run proceeds; the UI shows them."""
    warnings: list[str] = []
    if params.member_length_m > LENGTH_WARNING_M:
        warnings.append(
            f"Member length {params.member_length_m:g} m exceeds {LENGTH_WARNING_M:g} m — "
            "a long underframe member; the design proceeds but the sole bar is normally "
            "supported by cross members / body bolsters, so a single simply-supported span "
            "this long warrants review of the support layout."
        )
    if params.design_buffing_load_kn > BUFFING_WARNING_KN:
        warnings.append(
            f"Buffing load {params.design_buffing_load_kn:g} kN exceeds "
            f"{BUFFING_WARNING_KN:g} kN — a heavy longitudinal load for a single member; "
            "the design proceeds but the axial/combined check will tend to govern and "
            "the draft-gear load path warrants special review."
        )
    if params.design_vertical_load_kn > VERTICAL_WARNING_KN:
        warnings.append(
            f"Vertical load {params.design_vertical_load_kn:g} kN exceeds "
            f"{VERTICAL_WARNING_KN:g} kN — a heavy vertical share for a single member; "
            "the design proceeds but bending will tend to govern."
        )
    return warnings
