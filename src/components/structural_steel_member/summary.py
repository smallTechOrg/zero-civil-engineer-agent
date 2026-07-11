"""Type-specific utilisation summary for the steel-member Stress panel.

PINNED shape (a sibling frontend slice renders exactly these keys; floats 1 dp):
    {"kind": "utilisation_summary",
     "max_bending_stress_mpa", "permissible_bending_stress_mpa", "bending_ok",
     "max_shear_stress_mpa", "permissible_shear_stress_mpa", "shear_ok",
     "max_axial_stress_mpa", "permissible_axial_stress_mpa", "axial_ok",
     "weld_stress_mpa", "permissible_weld_stress_mpa", "weld_ok",
     "verdict"}
"""

from __future__ import annotations

from components.base import coerce
from components.structural_steel_member.analysis import SteelMemberAnalysis


def type_summary(*, analysis: SteelMemberAnalysis, verdict: str) -> dict:
    analysis = coerce(SteelMemberAnalysis, analysis)
    return {
        "kind": "utilisation_summary",
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
        "max_axial_stress_mpa": round(analysis.max_axial_stress_mpa, 1),
        "permissible_axial_stress_mpa": round(analysis.permissible_axial_stress_mpa, 1),
        "axial_ok": bool(
            analysis.max_axial_stress_mpa <= analysis.permissible_axial_stress_mpa
        ),
        "weld_stress_mpa": round(analysis.weld_stress_mpa, 1),
        "permissible_weld_stress_mpa": round(analysis.permissible_weld_stress_mpa, 1),
        "weld_ok": bool(analysis.weld_stress_mpa <= analysis.permissible_weld_stress_mpa),
        "verdict": verdict,
    }
