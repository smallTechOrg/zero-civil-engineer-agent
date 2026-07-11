"""Type-specific strength summary for the rolling-stock member Strength panel.

Shape (PINNED — the frontend TypeSummaryPanel + the api snapshot render exactly
these keys):
    {"kind": "strength_summary", "max_bending_stress_mpa",
     "permissible_bending_stress_mpa", "bending_ok", "max_shear_stress_mpa",
     "permissible_shear_stress_mpa", "shear_ok", "governing_load_case", "verdict"}
"""

from __future__ import annotations

from components.base import coerce
from components.rolling_stock_member.analysis import RollingStockMemberAnalysis


def type_summary(*, analysis: RollingStockMemberAnalysis, verdict: str) -> dict:
    analysis = coerce(RollingStockMemberAnalysis, analysis)
    return {
        "kind": "strength_summary",
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
        "governing_load_case": analysis.governing_load_case,
        "verdict": verdict,
    }
