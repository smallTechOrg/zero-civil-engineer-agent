"""Type-specific stress summary for the plate-girder Stress panel.

Shape (matches the frontend TypeSummaryPanel + the api snapshot):
    {"kind": "stress_summary", "max_bending_stress_mpa", "permissible_bending_stress_mpa",
     "bending_ok", "max_shear_stress_mpa", "permissible_shear_stress_mpa", "shear_ok",
     "max_deflection_mm", "deflection_limit_mm", "deflection_ok", "verdict"}
"""

from __future__ import annotations

from components.base import coerce
from components.plate_girder.analysis import PlateGirderAnalysis


def type_summary(*, analysis: PlateGirderAnalysis, verdict: str) -> dict:
    analysis = coerce(PlateGirderAnalysis, analysis)
    return {
        "kind": "stress_summary",
        "max_bending_stress_mpa": round(analysis.max_bending_stress_mpa, 1),
        "permissible_bending_stress_mpa": round(analysis.permissible_bending_stress_mpa, 1),
        "bending_ok": bool(
            analysis.max_bending_stress_mpa <= analysis.permissible_bending_stress_mpa
        ),
        "max_shear_stress_mpa": round(analysis.max_shear_stress_mpa, 1),
        "permissible_shear_stress_mpa": round(analysis.permissible_shear_stress_mpa, 1),
        "shear_ok": bool(
            analysis.max_shear_stress_mpa <= analysis.permissible_shear_stress_mpa
        ),
        "max_deflection_mm": round(analysis.max_deflection_mm, 2),
        "deflection_limit_mm": round(analysis.deflection_limit_mm, 2),
        "deflection_ok": bool(analysis.max_deflection_mm <= analysis.deflection_limit_mm),
        "verdict": verdict,
    }
