"""Type-specific summary for the M-00004 standard box culvert.

Shape (spec/capabilities/m00004-box-culvert.md):
    {"kind": "m00004_standard", "config_id", "thickness_mm", "haunch_mm",
     "barrel_length_mm", "provisional_flags": [...], "verdict"}
"""

from __future__ import annotations

from components.base import coerce
from components.m00004_box_culvert.params import M00004Geometry


def type_summary(*, geometry: M00004Geometry, verdict: str) -> dict:
    """Standard-reproduction summary for the type-summary panel."""
    geometry = coerce(M00004Geometry, geometry)
    return {
        "kind": "m00004_standard",
        "config_id": geometry.config_id,
        "thickness_mm": round(geometry.thickness_mm, 1),
        "haunch_mm": round(geometry.haunch_mm, 1),
        "barrel_length_mm": round(geometry.barrel_length_mm, 1),
        "concrete_grade_resolved": geometry.concrete_grade_resolved,
        "provisional_flags": list(geometry.provisional_flags),
        "verdict": verdict,
    }
