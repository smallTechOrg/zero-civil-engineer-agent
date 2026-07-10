"""Type-specific stability summary for the retaining-wall Stability panel.

Shape (matches the frontend TypeSummaryPanel + the api snapshot):
    {"kind": "stability", "fos_overturning", "fos_sliding",
     "max_bearing_pressure_kn_m2", "sbc_kn_m2", "bearing_ok", "verdict"}
"""

from __future__ import annotations

from components.base import coerce
from components.retaining_wall.analysis import RetainingWallAnalysis
from components.retaining_wall.params import RetainingWallParams


def type_summary(
    *,
    params: RetainingWallParams,
    analysis: RetainingWallAnalysis,
    verdict: str,
) -> dict:
    params = coerce(RetainingWallParams, params)
    analysis = coerce(RetainingWallAnalysis, analysis)
    sbc = params.safe_bearing_capacity_kn_m2
    max_pressure = analysis.max_base_pressure_kn_m2
    return {
        "kind": "stability",
        "fos_overturning": round(analysis.fos_overturning, 2),
        "fos_sliding": round(analysis.fos_sliding, 2),
        "max_bearing_pressure_kn_m2": round(max_pressure, 1),
        "sbc_kn_m2": round(sbc, 1),
        "bearing_ok": bool(
            max_pressure <= sbc and analysis.min_base_pressure_kn_m2 >= -1e-6
        ),
        "verdict": verdict,
    }
