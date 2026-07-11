"""Machine-element parameter and geometry models + intake schema.

`MachineElementParams` is the single validated parameter model (extraction
target, engine input, drawing input, audit record). The one critical field
(`power_kw`) carries no default — it must come from the user. `None` on a
diameter / weld-size field means "auto-size". Field names, defaults and hard
ranges are normative per spec/capabilities/machine-element.md.

TWO element kinds are supported, both driven by the transmitted power + speed:

* `shaft` — a transmission shaft carrying a mounted (overhung) gear/pulley:
  combined bending + torsion by the maximum-shear-stress theory, a static factor
  of safety against shear yield, AND a rotating-shaft fatigue (endurance) check.
* `welded_joint` — a hub fillet-welded to a plate and transmitting the same
  torque: torsional shear in the circular weld group vs the permissible weld
  shear stress (fillet throat = 0.707 x leg).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# The single critical field, never guessed/defaulted (the transmitted power).
CRITICAL_FIELDS = ("power_kw",)

# Unusual-value thresholds (flag and proceed — not hard limits).
POWER_WARNING_KW = 1000.0
SPEED_WARNING_RPM = 6000.0

ElementKindLiteral = Literal["shaft", "welded_joint"]
MaterialGradeLiteral = Literal["40C8", "EN24"]


class MachineElementParams(BaseModel):
    """Validated design parameters for one machine-element run."""

    model_config = ConfigDict(extra="forbid")

    # --- critical (user-supplied, never defaulted) ---
    power_kw: float = Field(
        ..., ge=0.05, le=5000.0, description="Transmitted power, kW"
    )

    # --- driving / configuration ---
    speed_rpm: float = Field(
        default=1450.0, ge=10.0, le=30000.0, description="Rotational speed, rev/min"
    )
    element_kind: ElementKindLiteral = Field(
        default="shaft",
        description="'shaft' (transmission shaft) or 'welded_joint' (welded coupling hub)",
    )
    material_grade: MaterialGradeLiteral = Field(
        default="40C8", description="Shaft/weld steel grade (40C8 plain carbon / EN24 alloy)"
    )
    required_factor_of_safety: float = Field(
        default=2.0, ge=1.1, le=6.0, description="Design factor of safety against shear yield"
    )

    # --- shaft loading model (mounted overhung gear/pulley) ---
    mounting_pcd_mm: float = Field(
        default=200.0, ge=20.0, le=2000.0,
        description="Pitch-circle diameter of the mounted gear/pulley, mm",
    )
    overhang_mm: float = Field(
        default=150.0, ge=0.0, le=3000.0,
        description="Overhang of the mounted load from the nearest bearing, mm",
    )
    bending_shock_factor: float = Field(
        default=1.5, ge=1.0, le=3.0, description="Bending combined-shock/fatigue factor Cm"
    )
    torsion_shock_factor: float = Field(
        default=1.0, ge=1.0, le=3.0, description="Torsion combined-shock/fatigue factor Ct"
    )
    has_keyway: bool = Field(
        default=True, description="A keyway/keyseat is cut in the shaft (drawing + GD&T note)"
    )

    # --- welded-joint model ---
    hub_diameter_mm: float = Field(
        default=120.0, ge=20.0, le=1000.0,
        description="Diameter of the fillet-welded hub (welded_joint), mm",
    )

    # --- overrides (None = auto-size) ---
    diameter_mm: float | None = Field(
        default=None, description="Shaft governing diameter override, mm; None = auto-size"
    )
    weld_size_mm: float | None = Field(
        default=None, description="Fillet-weld leg size override, mm; None = auto-size"
    )

    @field_validator("diameter_mm", "weld_size_mm")
    @classmethod
    def _override_must_be_positive(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("override must be a positive value in mm")
        return value


class MachineElementGeometry(BaseModel):
    """Fully-proportioned machine element — the one geometry source for the detail
    drawing, the 3D model and the audit record. All `_mm` fields are millimetres.

    Shaft fields (`diameter_mm`, `length_mm`, `step_*`, `keyway_*`) are populated
    for `element_kind == 'shaft'`; weld fields (`hub_diameter_mm`, `weld_size_mm`,
    `weld_throat_mm`, `plate_thickness_mm`) for `element_kind == 'welded_joint'`.
    The irrelevant kind's fields are zero.
    """

    element_kind: str = Field(description="'shaft' | 'welded_joint'")

    # --- shaft ---
    diameter_mm: float = Field(description="Governing (major) shaft diameter, mm")
    length_mm: float = Field(description="Overall element length (shaft) / plate size (weld), mm")
    step_diameter_mm: float = Field(description="Stepped journal diameter, mm (0 for a weld)")
    step_length_mm: float = Field(description="Length of each end journal, mm (0 for a weld)")
    fillet_radius_mm: float = Field(description="Shoulder fillet radius, mm (0 for a weld)")
    keyway_width_mm: float = Field(description="Keyway width, mm (0 if none)")
    keyway_depth_mm: float = Field(description="Keyway depth, mm (0 if none)")

    # --- welded joint ---
    hub_diameter_mm: float = Field(description="Welded hub diameter, mm (0 for a shaft)")
    weld_size_mm: float = Field(description="Fillet-weld leg size, mm (0 for a shaft)")
    weld_throat_mm: float = Field(description="Fillet-weld effective throat 0.707 s, mm (0 for a shaft)")
    plate_thickness_mm: float = Field(description="Backing-plate thickness, mm (0 for a shaft)")


# --------------------------------------------------------------------------- intake schema
class MachineElementExtractionResult(BaseModel):
    """Every MachineElementParams field, optional — the Gemini structured-output
    schema. A field is set ONLY when the conversation explicitly states it; the
    model never invents, guesses or defaults a value."""

    power_kw: float | None = Field(
        default=None,
        description=(
            "Transmitted power in KILOWATTS. Convert stated units (e.g. '15000 W' -> 15, "
            "'20 HP' -> 14.9). Synonyms: power, rating, transmitted power ('drives 20 kW' -> 20)."
        ),
    )
    speed_rpm: float | None = Field(
        default=None,
        description="Rotational speed in REV/MIN. Synonyms: speed, rpm, running speed ('1450 rpm' -> 1450).",
    )
    element_kind: str | None = Field(
        default=None,
        description="'shaft' for a transmission shaft, 'welded_joint' for a welded coupling hub.",
    )
    material_grade: str | None = Field(
        default=None, description="Steel grade, one of: 40C8 (plain carbon), EN24 (alloy)."
    )
    required_factor_of_safety: float | None = Field(
        default=None, description="Design factor of safety against yield ('FoS 2.5' -> 2.5)."
    )
    mounting_pcd_mm: float | None = Field(
        default=None, description="Pitch-circle diameter of the mounted gear/pulley, in MILLIMETRES."
    )
    overhang_mm: float | None = Field(
        default=None, description="Overhang of the mounted load from the bearing, in MILLIMETRES."
    )
    bending_shock_factor: float | None = Field(
        default=None, description="Bending combined-shock/fatigue factor Cm (e.g. 1.5)."
    )
    torsion_shock_factor: float | None = Field(
        default=None, description="Torsion combined-shock/fatigue factor Ct (e.g. 1.0)."
    )
    has_keyway: bool | None = Field(
        default=None, description="True if the shaft carries a keyway/keyseat."
    )
    hub_diameter_mm: float | None = Field(
        default=None, description="Welded-hub diameter (welded_joint), in MILLIMETRES."
    )
    diameter_mm: float | None = Field(
        default=None, description="Shaft diameter override, in MILLIMETRES."
    )
    weld_size_mm: float | None = Field(
        default=None, description="Fillet-weld leg-size override, in MILLIMETRES."
    )


# Templated, deterministic clarify questions (no LLM — demo-safe), with ranges.
CLARIFICATION_QUESTIONS: dict[str, str] = {
    "power_kw": (
        "What power does the machine element transmit — the rated power in kW? "
        "Transmission shafts and couplings commonly run from a fraction of a kW up "
        "to a few hundred kW."
    ),
}


def unusual_value_warnings(params: MachineElementParams) -> list[str]:
    """Param-level unusual-value flags. The run proceeds; the UI shows them."""
    warnings: list[str] = []
    if params.power_kw > POWER_WARNING_KW:
        warnings.append(
            f"Transmitted power {params.power_kw:g} kW exceeds {POWER_WARNING_KW:g} kW — a "
            "heavy drive; the design proceeds but the shaft/weld will be large and a "
            "detailed critical-speed and coupling review is warranted."
        )
    if params.speed_rpm > SPEED_WARNING_RPM:
        warnings.append(
            f"Speed {params.speed_rpm:g} rpm exceeds {SPEED_WARNING_RPM:g} rpm — a high-speed "
            "shaft; the design proceeds but whirling/critical-speed effects warrant special review."
        )
    return warnings
