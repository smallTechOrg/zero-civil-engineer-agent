"""Extraction schema, merge rules, and the deterministic clarify question.

The LLM extracts (`ExtractionResult`), Python merges and Pydantic decides
validity (`CulvertParams`) — per spec/agent.md `extract`/`clarify` and
spec/capabilities/nl-design-intake.md. Criticals are never guessed or defaulted.
"""

from dataclasses import dataclass

from pydantic import BaseModel, Field, ValidationError

from domain.culvert import CulvertParams

# Priority order for the one clarifying question: span → height → cushion.
CRITICAL_FIELDS = ("clear_span_m", "clear_height_m", "cushion_m")

_KNOWN_FIELDS = frozenset(CulvertParams.model_fields)


class ExtractionResult(BaseModel):
    """Every CulvertParams field, optional — the Gemini structured-output schema.

    A field is set ONLY when the conversation explicitly states it; the model
    must never invent, guess, or default a value.
    """

    clear_span_m: float | None = Field(
        default=None,
        description=(
            "Clear span between inside wall faces, in METRES. Convert stated units "
            "(e.g. '4000 mm span' -> 4.0). Synonyms: span, clear opening, vent width."
        ),
    )
    clear_height_m: float | None = Field(
        default=None,
        description=(
            "Clear inside height between slab soffits, in METRES. Convert mm to m. "
            "Synonyms: height, clear height, vent height."
        ),
    )
    cushion_m: float | None = Field(
        default=None,
        description=(
            "Earth cushion from top of top slab to formation level, in METRES. "
            "Synonyms: cushion, fill, earth fill, cover fill ('increase the fill to 4 m' -> 4.0)."
        ),
    )
    gauge: str | None = Field(
        default=None,
        description="Track gauge: exactly 'BG' when broad gauge / BG is mentioned.",
    )
    tracks: int | None = Field(
        default=None,
        description="Number of tracks: 1 when 'single line' / 'single track' is mentioned.",
    )
    loading_standard: str | None = Field(
        default=None,
        description=(
            "Railway loading standard: exactly '25t-2008' when 25t / 25 tonne / "
            "25t Loading-2008 loading is mentioned."
        ),
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
    soil_unit_weight_kn_m3: float | None = Field(
        default=None, description="Unit weight of fill soil, kN/m3."
    )
    angle_of_friction_deg: float | None = Field(
        default=None, description="Angle of internal friction of fill, degrees."
    )
    formation_width_m: float | None = Field(
        default=None, description="Formation width, in METRES."
    )
    side_slope_h_per_v: float | None = Field(
        default=None, description="Embankment side slope, horizontal per vertical (e.g. 2 for 2H:1V)."
    )
    top_slab_thickness_mm: float | None = Field(
        default=None,
        description="Top slab thickness override, in MILLIMETRES ('top slab only 200 mm' -> 200).",
    )
    bottom_slab_thickness_mm: float | None = Field(
        default=None, description="Bottom slab thickness override, in MILLIMETRES."
    )
    wall_thickness_mm: float | None = Field(
        default=None, description="Side wall thickness override, in MILLIMETRES."
    )
    haunch_mm: float | None = Field(
        default=None, description="Haunch leg size at inside corners, in MILLIMETRES."
    )


@dataclass
class MergeOutcome:
    merged: dict
    preset_fields: list[str]
    missing_critical: list[str]


def merge_params(
    extracted: dict, prior_params: dict | None, preset_values: dict
) -> MergeOutcome:
    """Merge order: this turn's values ← override prior accepted params ← override preset.

    Presets may never supply a critical field (criticals come from the user —
    directly this turn or carried from the session's last completed run).
    """
    turn = {k: v for k, v in extracted.items() if k in _KNOWN_FIELDS and v is not None}
    prior = {
        k: v for k, v in (prior_params or {}).items() if k in _KNOWN_FIELDS and v is not None
    }
    preset = {
        k: v
        for k, v in preset_values.items()
        if k in _KNOWN_FIELDS and k not in CRITICAL_FIELDS and v is not None
    }

    merged = {**preset, **prior, **turn}
    preset_fields = [k for k in preset if k not in prior and k not in turn]
    missing_critical = [f for f in CRITICAL_FIELDS if merged.get(f) is None]
    return MergeOutcome(merged=merged, preset_fields=preset_fields, missing_critical=missing_critical)


def validation_error_message(exc: ValidationError) -> str:
    """One transparent line per invalid field, naming the violated limit."""
    parts = []
    for err in exc.errors():
        loc = ".".join(str(piece) for piece in err["loc"]) or "params"
        parts.append(f"{loc}: {err['msg']} (got {err.get('input')!r})")
    return "; ".join(parts)


# Templated, deterministic clarify questions (no LLM — demo-safe), with typical ranges.
CLARIFICATION_QUESTIONS: dict[str, str] = {
    "clear_span_m": (
        "What is the clear span of the box? "
        "Standard RDSO single-cell spans run 1 m to 6 m."
    ),
    "clear_height_m": (
        "What is the clear height of the box? "
        "Standard RDSO single-cell heights run 1 m to 6 m."
    ),
    "cushion_m": (
        "What is the cushion — the earth fill from the top of the top slab to "
        "formation level? Typical cushions run 0 m to 8 m."
    ),
}


def select_clarification(missing_critical: list[str]) -> tuple[str, str]:
    """Pick the single highest-priority missing critical and its pointed question."""
    for field in CRITICAL_FIELDS:
        if field in missing_critical:
            return field, CLARIFICATION_QUESTIONS[field]
    raise ValueError("select_clarification called with no missing critical field")
