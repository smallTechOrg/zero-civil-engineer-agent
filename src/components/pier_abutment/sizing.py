"""Deterministic proportioning of the pier / abutment substructure.

Mirroring the retaining-wall engine's check-governed philosophy, an auto-sized
substructure passes its own checks:

1. **Footing & cap thickness** — proportioned to the total height.
2. **Pier section** — sized from the axial demand (superstructure reaction +
   self weight) so the direct compressive stress sits comfortably below the
   permissible working-stress value.
3. **Spread footing plan** — a symmetric projection grown about the pier until
   the substructure passes overturning (FoS >= 2.0), sliding (FoS >= 1.5),
   bearing (p_max <= SBC) and no-tension (p_min >= 0).

User overrides are never grown: a deliberately small footing (or a weak soil that
the bounded footing cannot satisfy) flows through to a FAIL row and a
return-for-revision verdict (the under-design demo case). Pure deterministic
Python — no LLM, no I/O.
"""

from __future__ import annotations

import math
from typing import NamedTuple

from pydantic import BaseModel

from components.base import Assumption, CalcStep
from components.pier_abutment._engine_common import (
    CITATION_DIRECT_STRESS,
    CITATION_PROPORTIONING,
    CITATION_USER_INPUT,
    CONCRETE_UNIT_WEIGHT_KN_M3,
    Trail,
    permissible_direct_stress,
)
from components.pier_abutment.analysis import compute_stability
from components.pier_abutment.params import PierAbutmentGeometry, PierAbutmentParams

MM_PER_M = 1000.0
_STEP_MM = 50.0
_MIN_PIER_MM = 600.0
_MIN_FOOTING_THICK_MM = 500.0
_MIN_CAP_MM = 500.0
_CAP_OVERHANG_MM = 300.0  # cap projects this far beyond the pier each side
_UTIL_TARGET = 0.5  # auto-size the pier to ~half the permissible direct stress
_MIN_PROJ_M = 0.5
_PROJ_STEP_M = 0.25
_MAX_PROJ_M = 12.0
_AXIAL_PASSES = 4

FOS_OVERTURNING_MIN = 2.0
FOS_SLIDING_MIN = 1.5


class PierAbutmentSizingResult(BaseModel):
    """Everything `size_substructure` returns — geometry plus its full provenance."""

    geometry: PierAbutmentGeometry
    assumptions: list[Assumption]
    trail: list[CalcStep]
    warnings: list[str]


class _Sized(NamedTuple):
    total_height_mm: float
    footing_thickness_mm: float
    footing_thickness_auto_mm: float
    cap_thickness_mm: float
    cap_thickness_auto_mm: float
    pier_width_mm: float
    pier_width_auto_mm: float
    pier_length_mm: float
    pier_length_auto_mm: float
    cap_width_mm: float
    cap_length_mm: float
    footing_length_mm: float
    footing_length_auto_mm: float
    footing_width_mm: float
    footing_width_auto_mm: float
    pier_area_req_mm2: float
    converged: bool


def _round50_up(value_mm: float) -> float:
    return math.ceil(round(value_mm / _STEP_MM, 6)) * _STEP_MM


def _make_geometry(
    *,
    total_height_mm: float,
    component_kind: str,
    footing_thickness_mm: float,
    cap_thickness_mm: float,
    pier_width_mm: float,
    pier_length_mm: float,
    footing_length_mm: float,
    footing_width_mm: float,
) -> PierAbutmentGeometry:
    return PierAbutmentGeometry(
        total_height_mm=total_height_mm,
        component_kind=component_kind,
        pier_width_mm=pier_width_mm,
        pier_length_mm=pier_length_mm,
        cap_thickness_mm=cap_thickness_mm,
        cap_width_mm=pier_width_mm + 2.0 * _CAP_OVERHANG_MM,
        cap_length_mm=pier_length_mm + 2.0 * _CAP_OVERHANG_MM,
        footing_length_mm=footing_length_mm,
        footing_width_mm=footing_width_mm,
        footing_thickness_mm=footing_thickness_mm,
    )


def _stability_ok(params: PierAbutmentParams, geometry: PierAbutmentGeometry) -> bool:
    core = compute_stability(params, geometry)
    b = geometry.footing_length_mm / MM_PER_M
    return (
        core.fos_overturning >= FOS_OVERTURNING_MIN
        and core.fos_sliding >= FOS_SLIDING_MIN
        and abs(core.eccentricity_m) <= b / 6.0 + 1e-9
        and core.max_base_pressure_kn_m2 <= params.safe_bearing_capacity_kn_m2 + 1e-6
        and core.min_base_pressure_kn_m2 >= -1e-6
    )


def _grow_footing(
    params: PierAbutmentParams,
    *,
    total_height_mm: float,
    footing_thickness_mm: float,
    cap_thickness_mm: float,
    pier_width_mm: float,
    pier_length_mm: float,
) -> tuple[float, float, bool]:
    """Grow a symmetric projection about the pier until the substructure passes
    overturning + sliding + bearing + no-tension. Returns (length_mm, width_mm, converged)."""
    proj = _MIN_PROJ_M
    while proj <= _MAX_PROJ_M + 1e-9:
        length = pier_width_mm + 2.0 * proj * MM_PER_M
        width = pier_length_mm + 2.0 * proj * MM_PER_M
        geometry = _make_geometry(
            total_height_mm=total_height_mm,
            component_kind=params.component_kind,
            footing_thickness_mm=footing_thickness_mm,
            cap_thickness_mm=cap_thickness_mm,
            pier_width_mm=pier_width_mm,
            pier_length_mm=pier_length_mm,
            footing_length_mm=round(length),
            footing_width_mm=round(width),
        )
        if _stability_ok(params, geometry):
            return round(length), round(width), True
        proj += _PROJ_STEP_M
    length = pier_width_mm + 2.0 * _MAX_PROJ_M * MM_PER_M
    width = pier_length_mm + 2.0 * _MAX_PROJ_M * MM_PER_M
    return round(length), round(width), False


def _proportion(params: PierAbutmentParams) -> _Sized:
    total_height_mm = round(params.pier_height_m * MM_PER_M, 3)
    sigma_cc = permissible_direct_stress(params.concrete_grade)
    gamma_c = CONCRETE_UNIT_WEIGHT_KN_M3

    footing_thick_auto = max(_MIN_FOOTING_THICK_MM, _round50_up(0.10 * total_height_mm))
    cap_thick_auto = max(_MIN_CAP_MM, _round50_up(0.08 * total_height_mm))
    footing_thick = (
        params.footing_thickness_mm if params.footing_thickness_mm is not None else footing_thick_auto
    )
    cap_thick = params.cap_thickness_mm if params.cap_thickness_mm is not None else cap_thick_auto
    shaft_h = (total_height_mm - footing_thick - cap_thick) / MM_PER_M
    if shaft_h <= 0:
        # Degenerate override combination — keep a positive shaft so downstream
        # geometry validation can still flag it rather than divide by zero.
        shaft_h = max(shaft_h, 0.1)

    # --- pier section from the axial demand (iterate self weight) ---
    pier_width_auto = pier_length_auto = _MIN_PIER_MM
    area_req = 0.0
    for _ in range(_AXIAL_PASSES):
        pw = (params.pier_width_mm if params.pier_width_mm is not None else pier_width_auto) / MM_PER_M
        pl = (params.pier_length_mm if params.pier_length_mm is not None else pier_length_auto) / MM_PER_M
        cw = pw + 2.0 * _CAP_OVERHANG_MM / MM_PER_M
        cl = pl + 2.0 * _CAP_OVERHANG_MM / MM_PER_M
        shaft_w = gamma_c * pw * pl * shaft_h
        cap_w = gamma_c * cw * cl * (cap_thick / MM_PER_M)
        axial_kn = params.superstructure_reaction_kn + shaft_w + cap_w
        # required area so sigma = axial / area <= UTIL * sigma_cc
        area_req = (axial_kn * 1e3) / (_UTIL_TARGET * sigma_cc)  # mm^2
        side = math.sqrt(area_req)
        pier_width_auto = max(_MIN_PIER_MM, _round50_up(side))
        pier_length_auto = max(pier_width_auto, _round50_up(1.2 * side))

    pier_width = params.pier_width_mm if params.pier_width_mm is not None else pier_width_auto
    pier_length = params.pier_length_mm if params.pier_length_mm is not None else pier_length_auto

    # --- footing plan ---
    length_auto, width_auto, converged = _grow_footing(
        params,
        total_height_mm=total_height_mm,
        footing_thickness_mm=footing_thick,
        cap_thickness_mm=cap_thick,
        pier_width_mm=pier_width,
        pier_length_mm=pier_length,
    )
    footing_length = (
        params.footing_length_mm if params.footing_length_mm is not None else length_auto
    )
    footing_width = params.footing_width_mm if params.footing_width_mm is not None else width_auto
    if params.footing_length_mm is not None or params.footing_width_mm is not None:
        # An overridden footing plan is used as-is; the checks verify it.
        geometry = _make_geometry(
            total_height_mm=total_height_mm,
            component_kind=params.component_kind,
            footing_thickness_mm=footing_thick,
            cap_thickness_mm=cap_thick,
            pier_width_mm=pier_width,
            pier_length_mm=pier_length,
            footing_length_mm=footing_length,
            footing_width_mm=footing_width,
        )
        converged = _stability_ok(params, geometry)

    return _Sized(
        total_height_mm=total_height_mm,
        footing_thickness_mm=footing_thick,
        footing_thickness_auto_mm=footing_thick_auto,
        cap_thickness_mm=cap_thick,
        cap_thickness_auto_mm=cap_thick_auto,
        pier_width_mm=pier_width,
        pier_width_auto_mm=pier_width_auto,
        pier_length_mm=pier_length,
        pier_length_auto_mm=pier_length_auto,
        cap_width_mm=pier_width + 2.0 * _CAP_OVERHANG_MM,
        cap_length_mm=pier_length + 2.0 * _CAP_OVERHANG_MM,
        footing_length_mm=footing_length,
        footing_length_auto_mm=length_auto,
        footing_width_mm=footing_width,
        footing_width_auto_mm=width_auto,
        pier_area_req_mm2=area_req,
        converged=converged,
    )


def size_substructure(params: PierAbutmentParams) -> PierAbutmentSizingResult:
    """Proportion the substructure and return the geometry with its full provenance."""
    s = _proportion(params)
    trail = Trail("S")
    assumptions: list[Assumption] = []
    warnings: list[str] = []

    trail.record(
        description="Total substructure height (founding level to bearing level)",
        formula="H = pier_height_m (user requirement)",
        inputs={"pier_height_m": params.pier_height_m},
        value=s.total_height_mm,
        unit="mm",
        citation=CITATION_USER_INPUT,
    )
    _record_member(trail, "Footing thickness", params.footing_thickness_mm, s.footing_thickness_auto_mm,
                   "t_footing = max(500 mm, ceil50(0.10 H))", {"H_mm": s.total_height_mm})
    _record_member(trail, "Cap thickness", params.cap_thickness_mm, s.cap_thickness_auto_mm,
                   "t_cap = max(500 mm, ceil50(0.08 H))", {"H_mm": s.total_height_mm})
    trail.record(
        description="Required pier cross-sectional area (axial working stress)",
        formula="A_req = axial / (UTIL * sigma_cc)",
        inputs={
            "UTIL": _UTIL_TARGET,
            "sigma_cc_n_mm2": permissible_direct_stress(params.concrete_grade),
            "reaction_kn": params.superstructure_reaction_kn,
        },
        value=round(s.pier_area_req_mm2, 1),
        unit="mm^2",
        citation=CITATION_DIRECT_STRESS,
    )
    _record_member(trail, "Pier width (along traffic)", params.pier_width_mm, s.pier_width_auto_mm,
                   "b = max(600 mm, ceil50(sqrt(A_req)))", {"A_req_mm2": round(s.pier_area_req_mm2, 1)})
    _record_member(trail, "Pier length (across traffic)", params.pier_length_mm, s.pier_length_auto_mm,
                   "L = max(b, ceil50(1.2 sqrt(A_req)))", {"A_req_mm2": round(s.pier_area_req_mm2, 1)})
    trail.record(
        description="Cap plan size",
        formula="cap = pier + 2 x 300 mm overhang each side",
        inputs={"pier_width_mm": s.pier_width_mm, "pier_length_mm": s.pier_length_mm},
        value=round(s.cap_width_mm, 1),
        unit="mm",
        citation=CITATION_PROPORTIONING,
    )
    _record_member(trail, "Footing length (longitudinal, B)", params.footing_length_mm, s.footing_length_auto_mm,
                   "B grown so overturning/sliding/bearing/no-tension pass", {"pier_width_mm": s.pier_width_mm})
    _record_member(trail, "Footing width (transverse, L)", params.footing_width_mm, s.footing_width_auto_mm,
                   "L grown symmetrically with B", {"pier_length_mm": s.pier_length_mm})

    geometry = _make_geometry(
        total_height_mm=s.total_height_mm,
        component_kind=params.component_kind,
        footing_thickness_mm=s.footing_thickness_mm,
        cap_thickness_mm=s.cap_thickness_mm,
        pier_width_mm=s.pier_width_mm,
        pier_length_mm=s.pier_length_mm,
        footing_length_mm=s.footing_length_mm,
        footing_width_mm=s.footing_width_mm,
    )

    _finalise_member(assumptions, warnings, "footing_thickness_mm", "Footing thickness",
                     params.footing_thickness_mm, s.footing_thickness_auto_mm)
    _finalise_member(assumptions, warnings, "cap_thickness_mm", "Cap thickness",
                     params.cap_thickness_mm, s.cap_thickness_auto_mm)
    _finalise_member(assumptions, warnings, "pier_width_mm", "Pier width",
                     params.pier_width_mm, s.pier_width_auto_mm)
    _finalise_member(assumptions, warnings, "pier_length_mm", "Pier length",
                     params.pier_length_mm, s.pier_length_auto_mm)
    _finalise_member(assumptions, warnings, "footing_length_mm", "Footing length",
                     params.footing_length_mm, s.footing_length_auto_mm)
    _finalise_member(assumptions, warnings, "footing_width_mm", "Footing width",
                     params.footing_width_mm, s.footing_width_auto_mm)

    if not s.converged and params.footing_length_mm is None and params.footing_width_mm is None:
        warnings.append(
            f"The footing could not be proportioned to pass overturning/sliding/bearing "
            f"within a {_MAX_PROJ_M:g} m projection each side — the design proceeds and the "
            "proof-check grades it (piles or ground improvement may be required)."
        )

    return PierAbutmentSizingResult(
        geometry=geometry, assumptions=assumptions, trail=trail.steps, warnings=warnings
    )


def _record_member(trail, label, override, auto, formula, inputs) -> None:
    if override is None:
        trail.record(description=f"{label} — auto-sized", formula=formula, inputs=inputs,
                     value=round(auto, 1), unit="mm", citation=CITATION_PROPORTIONING)
    else:
        trail.record(
            description=f"{label} — user override (auto-size reference {auto:g} mm)",
            formula="value = user override",
            inputs={**inputs, "override_mm": override, "auto_sized_mm": auto},
            value=round(override, 1), unit="mm", citation=CITATION_USER_INPUT,
        )


def _auto_assumption(field: str, label: str, value: float) -> Assumption:
    return Assumption(
        field=field, value=round(value, 1), source="engine_default",
        note=f"Auto-sized {label.lower()} = {value:g} mm — {CITATION_PROPORTIONING}",
    )


def _finalise_member(assumptions, warnings, field, label, override, auto) -> None:
    if override is None:
        assumptions.append(_auto_assumption(field, label, auto))
    elif override < auto:
        warnings.append(
            f"{label} override {override:g} mm is smaller than the auto-sized {auto:g} mm "
            "— possible under-design; the member checks will verify it."
        )
