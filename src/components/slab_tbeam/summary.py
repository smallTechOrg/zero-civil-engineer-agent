"""Type-specific flexure/shear summary for the slab / T-beam deck panel.

Shape (matches the frontend TypeSummaryPanel + the api snapshot):
    {"kind": "flexure_summary", "design_moment_knm", "required_depth_mm",
     "provided_depth_mm", "flexure_ok", "design_shear_kn", "shear_stress_mpa",
     "permissible_shear_mpa", "shear_ok", "steel_area_mm2", "min_steel_mm2",
     "verdict"}
"""

from __future__ import annotations

import math

from components.base import CheckResult, coerce
from components.slab_tbeam._engine_common import (
    ASSUMED_BAR_DIA_MM,
    MIN_STEEL_PCT_GROSS,
    permissible_shear_stress,
    working_stress_constants,
)
from components.slab_tbeam.analysis import SlabTbeamAnalysis
from components.slab_tbeam.params import SlabTbeamGeometry, SlabTbeamParams


def _flexure_status(checks: list[CheckResult]) -> bool:
    row = next((c for c in checks if c.kind == "flexure"), None)
    return bool(row and row.status == "PASS")


def _shear_status(checks: list[CheckResult]) -> bool:
    row = next((c for c in checks if c.kind == "shear"), None)
    return bool(row and row.status == "PASS")


def type_summary(
    *,
    params: SlabTbeamParams,
    geometry: SlabTbeamGeometry,
    analysis: SlabTbeamAnalysis,
    checks: list[CheckResult],
    verdict: str,
) -> dict:
    params = coerce(SlabTbeamParams, params)
    geometry = coerce(SlabTbeamGeometry, geometry)
    analysis = coerce(SlabTbeamAnalysis, analysis)
    rows = [coerce(CheckResult, c) for c in checks]
    wsc = working_stress_constants(params.concrete_grade, params.steel_grade)

    moment = analysis.design_moment_knm
    shear = analysis.design_shear_kn
    b = analysis.design_width_mm
    bw = analysis.web_width_mm
    d = geometry.overall_depth_mm - params.clear_cover_mm - ASSUMED_BAR_DIA_MM / 2.0
    d = max(d, 1.0)

    tau_perm, _has_stirrups = permissible_shear_stress(params.concrete_grade, geometry.deck_type)
    required_depth = math.sqrt(moment * 1e6 / (wsc.q_n_mm2 * b)) if moment > 0 else 0.0
    shear_stress = shear * 1e3 / (bw * d)
    steel_area = moment * 1e6 / (wsc.sigma_st * wsc.j * d) if moment > 0 else 0.0
    min_steel = MIN_STEEL_PCT_GROSS / 100.0 * bw * geometry.overall_depth_mm

    return {
        "kind": "flexure_summary",
        "design_moment_knm": round(moment, 1),
        "required_depth_mm": round(required_depth, 1),
        "provided_depth_mm": round(d, 1),
        "flexure_ok": _flexure_status(rows),
        "design_shear_kn": round(shear, 1),
        "shear_stress_mpa": round(shear_stress, 3),
        "permissible_shear_mpa": round(tau_perm, 3),
        "shear_ok": _shear_status(rows),
        "steel_area_mm2": round(steel_area, 0),
        "min_steel_mm2": round(min_steel, 0),
        "verdict": verdict,
    }
