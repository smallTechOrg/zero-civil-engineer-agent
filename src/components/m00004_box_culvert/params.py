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

    # --- materials (title-block / notes only) ---
    concrete_grade: ConcreteGrade = Field(default=ConcreteGrade.M30)
    steel_grade: SteelGrade = Field(default=SteelGrade.FE500)


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
