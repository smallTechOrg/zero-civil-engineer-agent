"""Deterministic geometry for the M-00004 standard box culvert.

This is a STANDARD-DRIVEN component, not a load-engineered one: `size` selects
the enclosing/nearest standard catalogue config and reproduces its detailing on
the entered opening. Thickness, haunch and the bar schedule come ONLY from the
selected config (PROVISIONAL); the opening, outer dimensions and derived barrel
length are pure geometry. No load analysis, no code-check math.

Every catalogue-derived value is recorded as a PROVISIONAL `Assumption`; the
appendage dimensions are fixed engine constants (from the RDSO pilot) recorded as
`engine_default` assumptions. A `CalcStep` trail (ids `S..`) records the geometry
derivation.
"""

from __future__ import annotations

from pydantic import BaseModel

from components.base import Assumption, CalcStep, SizingOutput, coerce
from components.m00004_box_culvert import catalog
from components.m00004_box_culvert.params import (
    APRON_LEN_MM,
    APRON_THICKNESS_MM,
    CURTAIN_DEPTH_MM,
    CURTAIN_THICKNESS_MM,
    WING_LEN_MM,
    M00004Geometry,
    M00004Params,
)

# --------------------------------------------------------------------------- citations
VERIFY_TAG = "PROVISIONAL - verify against RDSO/M-00004"
CITATION_USER_INPUT = "User design requirement - validated against the M-00004 standard box range"
CITATION_CATALOGUE = (
    "RDSO/M-00004 standard box-culvert annexure (digitized PROVISIONAL subset) - "
    f"{VERIFY_TAG}"
)
CITATION_GEOMETRY = "Standard single-cell box geometry (derived from the selected config + site data)"
CITATION_PILOT_CONSTANT = (
    "Fixed appendage constant from the M-00004 pilot GA (return/wing wall, apron, "
    f"curtain wall) - {VERIFY_TAG}"
)


class _Trail:
    """Ordered CalcStep recorder with a per-segment id namespace (`S`, `A`, `K`)
    so the sizing/analysis/checks trails never collide when merged."""

    def __init__(self, prefix: str) -> None:
        self._prefix = prefix
        self._steps: list[CalcStep] = []

    def record(self, *, description, formula, inputs, value, unit, citation) -> float:
        step_id = f"{self._prefix}{len(self._steps) + 1:02d}"
        self._steps.append(
            CalcStep(
                step_id=step_id,
                description=description,
                formula=formula,
                inputs=inputs,
                value=value,
                unit=unit,
                citation=citation,
            )
        )
        return value

    @property
    def steps(self) -> list[CalcStep]:
        return list(self._steps)


class M00004SizingResult(BaseModel):
    """Everything `size` returns — geometry plus its full PROVISIONAL provenance."""

    geometry: M00004Geometry
    assumptions: list[Assumption]
    trail: list[CalcStep]
    warnings: list[str]


def _derive_geometry(params: M00004Params, config: dict, flags: list[str]) -> M00004Geometry:
    thickness_mm = float(config["thickness_cm"]) * 10.0
    haunch_mm = float(config["haunch_mm"])
    clear_span_mm = params.clear_span_m * 1000.0
    clear_height_mm = params.clear_height_m * 1000.0
    outer_width_mm = clear_span_mm + 2.0 * thickness_mm
    outer_height_mm = clear_height_mm + 2.0 * thickness_mm
    cushion_mm = params.cushion_m * 1000.0
    formation_width_mm = params.formation_width_m * 1000.0
    barrel_length_mm = (
        formation_width_mm + 2.0 * (cushion_mm + outer_height_mm) * params.side_slope_h_per_v
    )
    return M00004Geometry(
        clear_span_mm=clear_span_mm,
        clear_height_mm=clear_height_mm,
        thickness_mm=thickness_mm,
        haunch_mm=haunch_mm,
        outer_width_mm=outer_width_mm,
        outer_height_mm=outer_height_mm,
        barrel_length_mm=barrel_length_mm,
        config_id=config["id"],
        bar_schedule={mark: dict(v) for mark, v in config["bars"].items()},
        wing_len_mm=WING_LEN_MM,
        apron_len_mm=APRON_LEN_MM,
        apron_thickness_mm=APRON_THICKNESS_MM,
        curtain_thickness_mm=CURTAIN_THICKNESS_MM,
        curtain_depth_mm=CURTAIN_DEPTH_MM,
        provisional_flags=list(flags),
    )


def size(params: M00004Params) -> M00004SizingResult:
    """Select the standard config and derive the box geometry with provenance."""
    params = coerce(M00004Params, params)
    config, flags = catalog.select_config(
        params.clear_span_m, params.clear_height_m, params.cushion_m, params.surcharge_kn_m2
    )
    geometry = _derive_geometry(params, config, flags)

    trail = _Trail("S")
    trail.record(
        description="Standard config selection (fill tier -> enclosing box)",
        formula="select_config(span, height, cushion, surcharge) per M-00004 selection rule",
        inputs={
            "clear_span_m": params.clear_span_m,
            "clear_height_m": params.clear_height_m,
            "cushion_m": params.cushion_m,
            "surcharge_kn_m2": params.surcharge_kn_m2,
            "config_id": config["id"],
        },
        value=float(config["thickness_cm"]),
        unit="cm (slab/wall thickness of selected config)",
        citation=CITATION_CATALOGUE,
    )
    trail.record(
        description="Slab/wall thickness (from the selected standard config)",
        formula="t = thickness_cm x 10",
        inputs={"thickness_cm": config["thickness_cm"]},
        value=geometry.thickness_mm,
        unit="mm",
        citation=CITATION_CATALOGUE,
    )
    trail.record(
        description="Haunch leg (from the selected standard config)",
        formula="B = config.haunch_mm",
        inputs={"config_id": config["id"]},
        value=geometry.haunch_mm,
        unit="mm",
        citation=CITATION_CATALOGUE,
    )
    trail.record(
        description="Overall (outer) box width",
        formula="outer_width = clear_span + 2 x thickness",
        inputs={"clear_span_mm": geometry.clear_span_mm, "thickness_mm": geometry.thickness_mm},
        value=geometry.outer_width_mm,
        unit="mm",
        citation=CITATION_GEOMETRY,
    )
    trail.record(
        description="Overall (outer) box height",
        formula="outer_height = clear_height + 2 x thickness",
        inputs={"clear_height_mm": geometry.clear_height_mm, "thickness_mm": geometry.thickness_mm},
        value=geometry.outer_height_mm,
        unit="mm",
        citation=CITATION_GEOMETRY,
    )
    trail.record(
        description="Derived barrel length (embankment cross-section)",
        formula="L = formation_width + 2 x side_slope x (cushion + outer_height)",
        inputs={
            "formation_width_m": params.formation_width_m,
            "side_slope_h_per_v": params.side_slope_h_per_v,
            "cushion_m": params.cushion_m,
            "outer_height_mm": geometry.outer_height_mm,
        },
        value=geometry.barrel_length_mm,
        unit="mm",
        citation=CITATION_GEOMETRY,
    )

    assumptions = _assumptions(config, geometry, flags)
    warnings = list(flags)
    return M00004SizingResult(
        geometry=geometry, assumptions=assumptions, trail=trail.steps, warnings=warnings
    )


def _assumptions(config: dict, geometry: M00004Geometry, flags: list[str]) -> list[Assumption]:
    assumptions: list[Assumption] = [
        Assumption(
            field="config_id",
            value=config["id"],
            source="preset",
            note=(
                f"Standard config {config['id']} ({config['span_m']:g}x{config['height_m']:g} m, "
                f"fill {config['fill_m']:g} m) selected from the digitized M-00004 subset - "
                f"{VERIFY_TAG}."
            ),
        ),
        Assumption(
            field="thickness_mm",
            value=geometry.thickness_mm,
            source="preset",
            note=f"Slab/wall thickness reproduced from standard config {config['id']} - {VERIFY_TAG}.",
        ),
        Assumption(
            field="haunch_mm",
            value=geometry.haunch_mm,
            source="preset",
            note=f"Haunch leg reproduced from standard config {config['id']} - {VERIFY_TAG}.",
        ),
        Assumption(
            field="bar_schedule",
            value=", ".join(sorted(geometry.bar_schedule)),
            source="preset",
            note=(
                "Reinforcement schedule (a1..h) is a PROVISIONAL demonstration set from the "
                f"digitized subset, NOT transcribed from the annexure - {VERIFY_TAG}."
            ),
        ),
        Assumption(
            field="wing_len_mm",
            value=geometry.wing_len_mm,
            source="engine_default",
            note=f"Return/wing-wall length fixed engine constant (pilot GA) - {VERIFY_TAG}.",
        ),
        Assumption(
            field="apron_len_mm",
            value=geometry.apron_len_mm,
            source="engine_default",
            note=f"Apron-floor length fixed engine constant (pilot GA) - {VERIFY_TAG}.",
        ),
        Assumption(
            field="apron_thickness_mm",
            value=geometry.apron_thickness_mm,
            source="engine_default",
            note=f"Apron thickness fixed engine constant (pilot GA) - {VERIFY_TAG}.",
        ),
        Assumption(
            field="curtain_thickness_mm",
            value=geometry.curtain_thickness_mm,
            source="engine_default",
            note=f"Curtain-wall thickness fixed engine constant (pilot GA) - {VERIFY_TAG}.",
        ),
        Assumption(
            field="curtain_depth_mm",
            value=geometry.curtain_depth_mm,
            source="engine_default",
            note=f"Curtain-wall depth fixed engine constant (pilot GA) - {VERIFY_TAG}.",
        ),
    ]
    for flag in flags:
        assumptions.append(
            Assumption(
                field="provisional_flag",
                value=flag,
                source="engine_default",
                note=f"Config-selection PROVISIONAL flag - {VERIFY_TAG}.",
            )
        )
    return assumptions


def size_output(params: M00004Params) -> SizingOutput:
    """`size` wrapped in the shared `SizingOutput` (used by the module adapter)."""
    result = size(params)
    return SizingOutput(
        geometry=result.geometry,
        assumptions=list(result.assumptions),
        trail=list(result.trail),
        warnings=list(result.warnings),
    )
