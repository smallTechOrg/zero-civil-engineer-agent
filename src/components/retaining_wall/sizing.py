"""Deterministic proportioning of the RCC cantilever retaining wall.

Mirroring the culvert engine's check-governed philosophy, the wall is sized so an
auto-sized design passes its own checks:

1. **Stem base thickness** — driven by the working-stress flexure demand at the
   stem base (so an auto-sized stem always passes flexure).
2. **Base slab thickness** — the larger of the standard H/12 proportion and the
   flexure demand of the heel/toe cantilevers (iterated to convergence, since the
   heel moment depends on the base width, which depends on the slab thickness).
3. **Base geometry** — the base width is grown (toe = B/3, heel the remainder)
   until the wall passes overturning (FoS >= 2.0), no-tension and bearing
   (p_max <= SBC); a shear key is then added, if needed, until sliding passes
   (FoS >= 1.5).

User overrides are never grown: a deliberately thin stem flows through to a FAIL
row and a return-for-revision verdict (the under-design demo case). Pure
deterministic Python — no LLM, no I/O.
"""

from __future__ import annotations

import math
from typing import NamedTuple

from pydantic import BaseModel

from components.base import Assumption, CalcStep
from components.retaining_wall._engine_common import (
    ASSUMED_BAR_DIA_MM,
    CITATION_PROPORTIONING,
    CITATION_USER_INPUT,
    Trail,
    active_coefficient,
    working_stress_constants,
)
from components.retaining_wall.analysis import (
    compute_stability,
    slab_design_moments,
    total_surcharge,
)
from components.retaining_wall.params import RetainingWallGeometry, RetainingWallParams

_STEP_MM = 50.0
_MIN_MEMBER_MM = 300.0
_MIN_STEM_TOP_MM = 200.0
_MIN_HEEL_M = 0.3
_KEY_STEP_M = 0.15
_KEY_MAX_M = 0.6
_BASE_STEP_M = 0.1
_MAX_BASE_THICKNESS_PASSES = 8

FOS_OVERTURNING_MIN = 2.0
FOS_SLIDING_MIN = 1.5


class WallSizingResult(BaseModel):
    """Everything `size_wall` returns — geometry plus its full provenance."""

    geometry: RetainingWallGeometry
    assumptions: list[Assumption]
    trail: list[CalcStep]
    warnings: list[str]


class _Sized(NamedTuple):
    """The converged sizing numbers (before trail recording)."""

    total_height_mm: float
    base_thickness_mm: float
    base_thickness_auto_mm: float
    stem_base_mm: float
    stem_base_auto_mm: float
    stem_base_d_req_mm: float
    stem_top_mm: float
    stem_top_auto_mm: float
    toe_mm: float
    heel_mm: float
    key_mm: float
    stem_moment_knm: float
    q_n_mm2: float
    converged: bool


def _round50_up(value_mm: float) -> float:
    return math.ceil(round(value_mm / _STEP_MM, 6)) * _STEP_MM


def _flexure_thickness_mm(moment_knm: float, q_n_mm2: float, cover_mm: float) -> float:
    d_req = math.sqrt(moment_knm * 1e6 / (q_n_mm2 * 1000.0)) if moment_knm > 0 else 0.0
    return _round50_up(d_req + cover_mm + ASSUMED_BAR_DIA_MM / 2.0)


def _make_geometry(
    *,
    total_height_mm: float,
    base_thickness_mm: float,
    stem_base_mm: float,
    stem_top_mm: float,
    toe_mm: float,
    heel_mm: float,
    key_mm: float,
) -> RetainingWallGeometry:
    return RetainingWallGeometry(
        stem_top_thickness_mm=stem_top_mm,
        stem_base_thickness_mm=stem_base_mm,
        base_thickness_mm=base_thickness_mm,
        toe_length_mm=toe_mm,
        heel_length_mm=heel_mm,
        base_width_mm=toe_mm + stem_base_mm + heel_mm,
        total_height_mm=total_height_mm,
        key_depth_mm=key_mm,
    )


def _overturning_bearing_ok(params: RetainingWallParams, geometry: RetainingWallGeometry) -> bool:
    core = compute_stability(params, geometry)
    b = geometry.base_width_mm / 1000.0
    return (
        core.fos_overturning >= FOS_OVERTURNING_MIN
        and abs(core.eccentricity_m) <= b / 6.0 + 1e-9
        and core.max_base_pressure_kn_m2 <= params.safe_bearing_capacity_kn_m2 + 1e-6
    )


def _least_key_mm(params: RetainingWallParams, geometry: RetainingWallGeometry) -> float | None:
    """Smallest 0.15 m shear-key depth carrying sliding to FoS >= 1.5, or None if
    even the maximum key falls short at this base width."""
    if compute_stability(params, geometry).fos_sliding >= FOS_SLIDING_MIN:
        return 0.0
    key = _KEY_STEP_M
    while key <= _KEY_MAX_M + 1e-9:
        trial = geometry.model_copy(update={"key_depth_mm": round(key * 1000.0)})
        if compute_stability(params, trial).fos_sliding >= FOS_SLIDING_MIN:
            return round(key * 1000.0)
        key += _KEY_STEP_M
    return None


def _size_base_and_key(
    params: RetainingWallParams,
    *,
    total_height_mm: float,
    base_thickness_mm: float,
    stem_base_mm: float,
    stem_top_mm: float,
) -> tuple[float, float, float, bool]:
    """(toe_mm, heel_mm, key_mm, converged): grow B (toe = B/3, heel the rest) until
    overturning + bearing pass AND sliding is satisfiable with a bounded shear key."""
    h = total_height_mm / 1000.0
    ts_base = stem_base_mm / 1000.0
    b0 = max(0.4 * h, 1.5 * (ts_base + _MIN_HEEL_M))
    b = math.ceil(b0 / _BASE_STEP_M) * _BASE_STEP_M
    b_max = 2.5 * h
    while b <= b_max + 1e-9:
        lt = b / 3.0
        lh = b - lt - ts_base
        if lh >= _MIN_HEEL_M:
            geometry = _make_geometry(
                total_height_mm=total_height_mm,
                base_thickness_mm=base_thickness_mm,
                stem_base_mm=stem_base_mm,
                stem_top_mm=stem_top_mm,
                toe_mm=round(lt * 1000.0),
                heel_mm=round(lh * 1000.0),
                key_mm=0.0,
            )
            if _overturning_bearing_ok(params, geometry):
                key_mm = _least_key_mm(params, geometry)
                if key_mm is not None:
                    return round(lt * 1000.0), round(lh * 1000.0), key_mm, True
        b += _BASE_STEP_M
    lt = b_max / 3.0
    lh = max(_MIN_HEEL_M, b_max - lt - ts_base)
    return round(lt * 1000.0), round(lh * 1000.0), round(_KEY_MAX_M * 1000.0), False


def _proportion(params: RetainingWallParams) -> _Sized:
    """Converge the member thicknesses + base geometry (no trail recording)."""
    h = params.retained_height_m
    total_height_mm = round(h * 1000.0, 3)
    ka, _m, _c = active_coefficient(params.backfill_friction_angle_deg, params.backfill_slope_deg)
    q, _q = total_surcharge(params)
    wsc = working_stress_constants(params.concrete_grade, params.steel_grade)

    base_h12 = max(_round50_up(total_height_mm / 12.0), _MIN_MEMBER_MM)
    toe_override = params.toe_length_mm is not None
    heel_override = params.heel_length_mm is not None

    base_auto = base_h12
    stem_base_auto = stem_top_auto = stem_moment = d_req = 0.0
    toe_mm = heel_mm = key_mm = 0.0
    converged = False

    for _ in range(_MAX_BASE_THICKNESS_PASSES):
        db = params.base_thickness_mm if params.base_thickness_mm is not None else base_auto
        hs = h - db / 1000.0

        stem_moment = ka * params.backfill_unit_weight_kn_m3 * hs**3 / 6.0 + ka * q * hs**2 / 2.0
        d_req = math.sqrt(stem_moment * 1e6 / (wsc.q_n_mm2 * 1000.0)) if stem_moment > 0 else 0.0
        stem_base_auto = max(_MIN_MEMBER_MM, _round50_up(d_req + params.clear_cover_mm + ASSUMED_BAR_DIA_MM / 2.0))
        stem_base = params.stem_base_thickness_mm if params.stem_base_thickness_mm is not None else stem_base_auto

        stem_top_auto = min(stem_base, max(_MIN_STEM_TOP_MM, _round50_up(0.4 * stem_base)))
        stem_top = params.stem_top_thickness_mm if params.stem_top_thickness_mm is not None else stem_top_auto

        if toe_override and heel_override:
            toe_mm, heel_mm, key_mm, converged = params.toe_length_mm, params.heel_length_mm, 0.0, True
        else:
            toe_mm, heel_mm, key_mm, converged = _size_base_and_key(
                params, total_height_mm=total_height_mm,
                base_thickness_mm=db, stem_base_mm=stem_base, stem_top_mm=stem_top,
            )
            if toe_override:
                toe_mm = params.toe_length_mm
            if heel_override:
                heel_mm = params.heel_length_mm

        geometry = _make_geometry(
            total_height_mm=total_height_mm, base_thickness_mm=db,
            stem_base_mm=stem_base, stem_top_mm=stem_top,
            toe_mm=toe_mm, heel_mm=heel_mm, key_mm=key_mm,
        )
        m_heel, m_toe = slab_design_moments(params, geometry)
        slab_flex = _flexure_thickness_mm(max(m_heel, m_toe), wsc.q_n_mm2, params.clear_cover_mm)
        base_auto = max(base_h12, slab_flex)

        if params.base_thickness_mm is not None or base_auto <= db + 1e-9:
            break  # override never grows; auto has converged

    # If toe/heel were overridden the key still needs sizing on the final geometry.
    if toe_override and heel_override:
        db_final = params.base_thickness_mm if params.base_thickness_mm is not None else base_auto
        geometry = _make_geometry(
            total_height_mm=total_height_mm, base_thickness_mm=db_final,
            stem_base_mm=(params.stem_base_thickness_mm if params.stem_base_thickness_mm is not None else stem_base_auto),
            stem_top_mm=(params.stem_top_thickness_mm if params.stem_top_thickness_mm is not None else stem_top_auto),
            toe_mm=toe_mm, heel_mm=heel_mm, key_mm=0.0,
        )
        least = _least_key_mm(params, geometry)
        key_mm = least if least is not None else round(_KEY_MAX_M * 1000.0)

    return _Sized(
        total_height_mm=total_height_mm,
        base_thickness_mm=(params.base_thickness_mm if params.base_thickness_mm is not None else base_auto),
        base_thickness_auto_mm=base_auto,
        stem_base_mm=(params.stem_base_thickness_mm if params.stem_base_thickness_mm is not None else stem_base_auto),
        stem_base_auto_mm=stem_base_auto,
        stem_base_d_req_mm=d_req,
        stem_top_mm=(params.stem_top_thickness_mm if params.stem_top_thickness_mm is not None else stem_top_auto),
        stem_top_auto_mm=stem_top_auto,
        toe_mm=toe_mm,
        heel_mm=heel_mm,
        key_mm=key_mm,
        stem_moment_knm=stem_moment,
        q_n_mm2=wsc.q_n_mm2,
        converged=converged,
    )


def size_wall(params: RetainingWallParams) -> WallSizingResult:
    """Proportion the wall and return the geometry with its full provenance."""
    s = _proportion(params)
    trail = Trail("S")
    assumptions: list[Assumption] = []
    warnings: list[str] = []

    trail.record(
        description="Total wall height (base underside to top of fill)",
        formula="H = retained_height_m (user requirement)",
        inputs={"retained_height_m": params.retained_height_m},
        value=s.total_height_mm, unit="mm", citation=CITATION_USER_INPUT,
    )
    _record_member(trail, "Base slab thickness", params.base_thickness_mm, s.base_thickness_auto_mm,
                   "t_base = ceil50(max(H/12, heel/toe flexure demand, 300 mm))",
                   {"H_mm": s.total_height_mm})
    trail.record(
        description="Required effective depth of the stem at its base (flexure)",
        formula="d_req = sqrt(M_stem / (Q * b))",
        inputs={"M_stem_knm": round(s.stem_moment_knm, 3), "Q_n_mm2": round(s.q_n_mm2, 4)},
        value=round(s.stem_base_d_req_mm, 2), unit="mm", citation=CITATION_PROPORTIONING,
    )
    _record_member(trail, "Stem base thickness", params.stem_base_thickness_mm, s.stem_base_auto_mm,
                   "t_stem_base = ceil50(d_req + cover + bar/2), min 300 mm",
                   {"d_req_mm": round(s.stem_base_d_req_mm, 2), "clear_cover_mm": params.clear_cover_mm})
    _record_member(trail, "Stem top thickness", params.stem_top_thickness_mm, s.stem_top_auto_mm,
                   "t_stem_top = max(200 mm, ceil50(0.4 * t_stem_base))",
                   {"stem_base_mm": s.stem_base_mm})

    toe_override = params.toe_length_mm is not None
    heel_override = params.heel_length_mm is not None
    base_width_mm = s.toe_mm + s.stem_base_mm + s.heel_mm
    trail.record(
        description="Toe projection in front of the stem",
        formula="toe = B/3 (check-governed)" if not toe_override else "toe = user override",
        inputs={"base_width_mm": round(base_width_mm, 1)},
        value=round(s.toe_mm, 1), unit="mm",
        citation=CITATION_PROPORTIONING if not toe_override else CITATION_USER_INPUT,
    )
    trail.record(
        description="Heel projection behind the stem",
        formula="heel = B - toe - t_stem_base" if not heel_override else "heel = user override",
        inputs={"base_width_mm": round(base_width_mm, 1), "toe_mm": round(s.toe_mm, 1)},
        value=round(s.heel_mm, 1), unit="mm",
        citation=CITATION_PROPORTIONING if not heel_override else CITATION_USER_INPUT,
    )
    trail.record(
        description="Overall base width",
        formula="B = toe + t_stem_base + heel",
        inputs={"toe_mm": round(s.toe_mm, 1), "stem_base_mm": s.stem_base_mm, "heel_mm": round(s.heel_mm, 1)},
        value=round(base_width_mm, 1), unit="mm", citation=CITATION_PROPORTIONING,
    )
    if s.key_mm > 0:
        trail.record(
            description="Shear key depth below the base (sliding resistance)",
            formula="key sized so FoS_sliding >= 1.5 via added passive resistance",
            inputs={"base_thickness_mm": s.base_thickness_mm},
            value=round(s.key_mm, 1), unit="mm", citation=CITATION_PROPORTIONING,
        )

    geometry = _make_geometry(
        total_height_mm=s.total_height_mm, base_thickness_mm=s.base_thickness_mm,
        stem_base_mm=s.stem_base_mm, stem_top_mm=s.stem_top_mm,
        toe_mm=s.toe_mm, heel_mm=s.heel_mm, key_mm=s.key_mm,
    )

    _finalise_member(assumptions, warnings, "base_thickness_mm", "Base slab thickness",
                     params.base_thickness_mm, s.base_thickness_auto_mm)
    _finalise_member(assumptions, warnings, "stem_base_thickness_mm", "Stem base thickness",
                     params.stem_base_thickness_mm, s.stem_base_auto_mm)
    _finalise_member(assumptions, warnings, "stem_top_thickness_mm", "Stem top thickness",
                     params.stem_top_thickness_mm, s.stem_top_auto_mm)
    if not toe_override:
        assumptions.append(_auto_assumption("toe_length_mm", "Toe projection", s.toe_mm))
    if not heel_override:
        assumptions.append(_auto_assumption("heel_length_mm", "Heel projection", s.heel_mm))
    if s.key_mm > 0:
        assumptions.append(Assumption(
            field="key_depth_mm", value=round(s.key_mm, 1), source="engine_default",
            note=(f"Shear key {s.key_mm:g} mm deep provided so the wall passes sliding "
                  "(FoS >= 1.5) on added passive resistance; per cantilever-wall practice."),
        ))
    if not s.converged and not (toe_override and heel_override):
        warnings.append(
            "The base could not be proportioned to pass overturning/bearing/sliding within "
            f"{2.5 * params.retained_height_m:g} m of width — the design proceeds and the "
            "proof-check grades it."
        )

    return WallSizingResult(
        geometry=geometry, assumptions=assumptions, trail=trail.steps, warnings=warnings
    )


def _record_member(trail, label, override, auto, formula, inputs) -> None:
    if override is None:
        trail.record(description=f"{label} — auto-sized", formula=formula, inputs=inputs,
                     value=round(auto, 1), unit="mm", citation=CITATION_PROPORTIONING)
    else:
        trail.record(
            description=f"{label} — user override (auto-size reference {auto:g} mm)",
            formula="t = user override",
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
            f"{label} override {override:g} mm is thinner than the auto-sized "
            f"{auto:g} mm (flexure-governed) — possible under-design; the member "
            "checks will verify it."
        )
