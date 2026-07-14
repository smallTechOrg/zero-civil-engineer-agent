"""Minimal 'analysis' record for the standard-driven M-00004 box culvert.

This component is STANDARD-DRIVEN: there is NO load analysis, no rigid-frame
solve and no code-check math. `analyse` returns a small record stating the
standard basis (the selected config, its PROVISIONAL detailing source and the
derived geometry) so the shared pipeline has a rehydratable analysis model to
thread to the checks, calc sheet and proof-check. Every catalogue-derived value
is PROVISIONAL.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from components.base import AnalysisOutput, CalcStep, coerce
from components.m00004_box_culvert.params import M00004Geometry, M00004Params
from components.m00004_box_culvert.sizing import CITATION_CATALOGUE

STANDARD_BASIS = (
    "Standard-driven reproduction of RDSO/M-00004: thickness, haunch and the a1..h "
    "reinforcement schedule are reproduced from the selected standard config, not "
    "engineered from loads. No frame analysis is performed. PROVISIONAL - verify "
    "against RDSO/M-00004."
)


class M00004Analysis(BaseModel):
    """The standard-basis record (no load analysis)."""

    basis: str = Field(description="Statement of the standard-driven basis")
    config_id: str = Field(description="Selected standard config id")
    thickness_mm: float = Field(description="Slab/wall thickness from the config (PROVISIONAL)")
    haunch_mm: float = Field(description="Haunch leg from the config (PROVISIONAL)")
    barrel_length_mm: float = Field(description="Derived barrel length")
    provisional_flags: list[str] = Field(default_factory=list)
    load_analysis_performed: bool = Field(default=False)


def analyse(params: M00004Params, geometry: M00004Geometry) -> AnalysisOutput:
    """Return the standard-basis record — a deterministic, no-load 'analysis'."""
    params = coerce(M00004Params, params)
    geometry = coerce(M00004Geometry, geometry)
    analysis = M00004Analysis(
        basis=STANDARD_BASIS,
        config_id=geometry.config_id,
        thickness_mm=geometry.thickness_mm,
        haunch_mm=geometry.haunch_mm,
        barrel_length_mm=geometry.barrel_length_mm,
        provisional_flags=list(geometry.provisional_flags),
        load_analysis_performed=False,
    )
    trail = [
        CalcStep(
            step_id="A01",
            description="Standard basis (no load analysis performed)",
            formula="analysis = standard reproduction of config " + geometry.config_id,
            inputs={"config_id": geometry.config_id, "thickness_mm": geometry.thickness_mm},
            value=geometry.thickness_mm,
            unit="mm",
            citation=CITATION_CATALOGUE,
        )
    ]
    return AnalysisOutput(analysis=analysis, assumptions=[], trail=trail)
