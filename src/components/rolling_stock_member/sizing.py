"""Deterministic proportioning of the fabricated rolling-stock member.

Mirroring the platform's check-governed philosophy, the welded I member is sized
so an auto-sized design passes its own checks:

1. **Web depth** — a member-length proportion (~span/12), bounded.
2. **Web thickness** — the larger of the vertical-case average-shear demand and
   the slenderness cap, floored at a minimum plate thickness.
3. **Flanges** — the flange area is grown until the section satisfies the bending
   demand (required section modulus), the buffing-case axial-area demand, AND the
   combined axial+bending interaction (unity check) with a working margin.

The self-weight and the combined interaction couple into the design actions, so
the section is iterated to convergence. User overrides are never grown: a
deliberately thin flange or web flows through to a FAIL row and a
return-for-revision verdict (the under-design demo case). Pure deterministic
Python — no LLM, no I/O.
"""

from __future__ import annotations

from typing import NamedTuple

from pydantic import BaseModel

from components.base import Assumption, CalcStep
from components.rolling_stock_member._engine_common import (
    CITATION_PROPORTIONING,
    CITATION_USER_INPUT,
    WEB_SLENDERNESS_LIMIT,
    Trail,
    fillet_weld_size_mm,
    permissible,
    round_up,
)
from components.rolling_stock_member.analysis import compute_forces
from components.rolling_stock_member.params import (
    RollingStockMemberGeometry,
    RollingStockMemberParams,
    member_kind_label,
)

_THICK_STEP = 2.0
_WIDTH_STEP = 10.0
_DEPTH_STEP = 25.0
_MIN_WEB_DEPTH_MM = 250.0
_MAX_WEB_DEPTH_MM = 1000.0
_MIN_WEB_THICKNESS_MM = 6.0
_MIN_FLANGE_WIDTH_MM = 100.0
_MAX_FLANGE_WIDTH_MM = 300.0
_MIN_FLANGE_THICKNESS_MM = 8.0
_MAX_THICKNESS_MM = 100.0
_MAX_PASSES = 80
_UTIL_TARGET = 0.9


class MemberSizingResult(BaseModel):
    """Everything `size_member` returns — geometry plus its full provenance."""

    geometry: RollingStockMemberGeometry
    assumptions: list[Assumption]
    trail: list[CalcStep]
    warnings: list[str]


class _Sized(NamedTuple):
    member_length_mm: float
    web_depth_mm: float
    web_depth_auto_mm: float
    web_thickness_mm: float
    web_thickness_auto_mm: float
    flange_width_mm: float
    flange_width_auto_mm: float
    flange_thickness_mm: float
    flange_thickness_auto_mm: float
    weld_size_mm: float


def _make_geometry(
    *,
    member_length_mm: float,
    member_kind: str,
    web_depth_mm: float,
    web_thickness_mm: float,
    flange_width_mm: float,
    flange_thickness_mm: float,
) -> RollingStockMemberGeometry:
    return RollingStockMemberGeometry(
        member_length_mm=member_length_mm,
        member_kind=member_kind,
        web_depth_mm=web_depth_mm,
        web_thickness_mm=web_thickness_mm,
        flange_width_mm=flange_width_mm,
        flange_thickness_mm=flange_thickness_mm,
        overall_depth_mm=web_depth_mm + 2.0 * flange_thickness_mm,
        weld_size_mm=fillet_weld_size_mm(web_thickness_mm, flange_thickness_mm),
    )


def _auto_section(params: RollingStockMemberParams) -> tuple[float, float, float, float]:
    """Grow a check-passing auto section, ignoring any user overrides.

    Returns (web_depth, web_thickness, flange_width, flange_thickness) in mm. Web
    thickness and flange thickness only ever grow, so the loop converges on the
    smallest section that keeps every utilisation within the working target."""
    span_mm = round(params.member_length_m * 1000.0, 3)
    perm = permissible(params.steel_grade)

    web_depth = min(
        _MAX_WEB_DEPTH_MM, max(_MIN_WEB_DEPTH_MM, round_up(span_mm / 12.0, _DEPTH_STEP))
    )
    flange_width = min(
        _MAX_FLANGE_WIDTH_MM, max(_MIN_FLANGE_WIDTH_MM, round_up(web_depth * 0.6, _WIDTH_STEP))
    )
    web_thickness = max(
        _MIN_WEB_THICKNESS_MM, round_up(web_depth / WEB_SLENDERNESS_LIMIT, _THICK_STEP)
    )
    flange_thickness = _MIN_FLANGE_THICKNESS_MM

    for _ in range(_MAX_PASSES):
        geometry = _make_geometry(
            member_length_mm=span_mm,
            member_kind=params.member_kind,
            web_depth_mm=web_depth,
            web_thickness_mm=web_thickness,
            flange_width_mm=flange_width,
            flange_thickness_mm=flange_thickness,
        )
        core = compute_forces(params, geometry)

        # Web thickness: vertical-case shear demand OR slenderness, floored.
        tw_desired = round_up(
            max(
                core.design_shear_kn * 1e3 / (web_depth * perm.sigma_shear_n_mm2),
                web_depth / WEB_SLENDERNESS_LIMIT,
                _MIN_WEB_THICKNESS_MM,
            ),
            _THICK_STEP,
        )

        # Flange area: bending (section modulus) + buffing (axial area) demands.
        z_req = core.design_moment_knm * 1e6 / perm.sigma_bending_n_mm2
        a_f_bending = max(0.0, (z_req - web_thickness * web_depth**2 / 6.0) / web_depth)
        area_axial = core.buffing_load_kn * 1e3 / perm.sigma_axial_n_mm2
        a_f_axial = max(0.0, (area_axial - web_thickness * web_depth) / 2.0)
        tf_desired = round_up(
            max((a_f_bending + a_f_axial) / flange_width, _MIN_FLANGE_THICKNESS_MM), _THICK_STEP
        )

        # Grow one step further while any working stress / interaction is over target.
        over_target = (
            core.interaction_ratio > _UTIL_TARGET
            or core.max_bending_stress_mpa > _UTIL_TARGET * perm.sigma_bending_n_mm2
            or core.max_axial_stress_mpa > _UTIL_TARGET * perm.sigma_axial_n_mm2
        )
        if over_target:
            tf_desired = max(tf_desired, round_up(flange_thickness + _THICK_STEP, _THICK_STEP))

        new_web_thickness = min(_MAX_THICKNESS_MM, max(web_thickness, tw_desired))
        new_flange_thickness = min(_MAX_THICKNESS_MM, max(flange_thickness, tf_desired))
        if new_web_thickness == web_thickness and new_flange_thickness == flange_thickness:
            break
        web_thickness = new_web_thickness
        flange_thickness = new_flange_thickness

    return web_depth, web_thickness, flange_width, flange_thickness


def _proportion(params: RollingStockMemberParams) -> _Sized:
    """Auto-size the section, then apply any user overrides on top of the reference."""
    span_mm = round(params.member_length_m * 1000.0, 3)
    web_depth_auto, web_thickness_auto, flange_width_auto, flange_thickness_auto = _auto_section(
        params
    )

    web_depth = params.web_depth_mm if params.web_depth_mm is not None else web_depth_auto
    web_thickness = (
        params.web_thickness_mm if params.web_thickness_mm is not None else web_thickness_auto
    )
    flange_width = (
        params.flange_width_mm if params.flange_width_mm is not None else flange_width_auto
    )
    flange_thickness = (
        params.flange_thickness_mm
        if params.flange_thickness_mm is not None
        else flange_thickness_auto
    )

    return _Sized(
        member_length_mm=span_mm,
        web_depth_mm=web_depth,
        web_depth_auto_mm=web_depth_auto,
        web_thickness_mm=web_thickness,
        web_thickness_auto_mm=web_thickness_auto,
        flange_width_mm=flange_width,
        flange_width_auto_mm=flange_width_auto,
        flange_thickness_mm=flange_thickness,
        flange_thickness_auto_mm=flange_thickness_auto,
        weld_size_mm=fillet_weld_size_mm(web_thickness, flange_thickness),
    )


def size_member(params: RollingStockMemberParams) -> MemberSizingResult:
    """Proportion the member and return the geometry with its full provenance."""
    s = _proportion(params)
    trail = Trail("S")
    assumptions: list[Assumption] = []
    warnings: list[str] = []

    trail.record(
        description="Effective member length",
        formula="L = member_length_m (user requirement)",
        inputs={"member_length_m": params.member_length_m},
        value=s.member_length_mm,
        unit="mm",
        citation=CITATION_USER_INPUT,
    )
    _record_member(
        trail, "Web depth", params.web_depth_mm, s.web_depth_auto_mm,
        "d_web = clamp(ceil25(L/12), 250, 1000 mm)",
        {"member_length_mm": s.member_length_mm},
    )
    _record_member(
        trail, "Web thickness", params.web_thickness_mm, s.web_thickness_auto_mm,
        "t_web = ceil2(max(V/(d*tau_perm), d/slenderness_limit, 6 mm))",
        {"web_depth_mm": s.web_depth_mm},
    )
    _record_member(
        trail, "Flange width", params.flange_width_mm, s.flange_width_auto_mm,
        "b_f = clamp(ceil10(0.6*d_web), 100, 300 mm)",
        {"web_depth_mm": s.web_depth_mm},
    )
    _record_member(
        trail, "Flange thickness", params.flange_thickness_mm, s.flange_thickness_auto_mm,
        "t_f grown until bending, axial and combined interaction are within target",
        {"flange_width_mm": s.flange_width_mm},
    )
    overall_depth = s.web_depth_mm + 2.0 * s.flange_thickness_mm
    trail.record(
        description="Overall member depth",
        formula="D = d_web + 2 * t_flange",
        inputs={"web_depth_mm": s.web_depth_mm, "flange_thickness_mm": s.flange_thickness_mm},
        value=round(overall_depth, 1),
        unit="mm",
        citation=CITATION_PROPORTIONING,
    )
    trail.record(
        description="Web-to-flange fillet-weld leg",
        formula="s_weld = max(6 mm, ceil1(0.7 * min(t_web, t_flange)))",
        inputs={"web_thickness_mm": s.web_thickness_mm, "flange_thickness_mm": s.flange_thickness_mm},
        value=round(s.weld_size_mm, 1),
        unit="mm",
        citation=CITATION_PROPORTIONING,
    )

    geometry = _make_geometry(
        member_length_mm=s.member_length_mm,
        member_kind=params.member_kind,
        web_depth_mm=s.web_depth_mm,
        web_thickness_mm=s.web_thickness_mm,
        flange_width_mm=s.flange_width_mm,
        flange_thickness_mm=s.flange_thickness_mm,
    )

    _finalise_member(assumptions, warnings, "web_depth_mm", "Web depth",
                     params.web_depth_mm, s.web_depth_auto_mm)
    _finalise_member(assumptions, warnings, "web_thickness_mm", "Web thickness",
                     params.web_thickness_mm, s.web_thickness_auto_mm)
    _finalise_member(assumptions, warnings, "flange_width_mm", "Flange width",
                     params.flange_width_mm, s.flange_width_auto_mm)
    _finalise_member(assumptions, warnings, "flange_thickness_mm", "Flange thickness",
                     params.flange_thickness_mm, s.flange_thickness_auto_mm)
    assumptions.append(Assumption(
        field="weld_size_mm", value=round(s.weld_size_mm, 1),
        source="engine_default",
        note=(f"Web-to-flange fillet welds sized at a {s.weld_size_mm:g} mm leg "
              "(~0.7 x the thinner plate, 6 mm minimum) — detailed weld-length / "
              "intermittent-weld design is beyond this POC scope."),
    ))
    assumptions.append(Assumption(
        field="member_kind", value=params.member_kind,
        source="engine_default",
        note=(f"Member proportioned as a doubly-symmetric welded I-section acting as a "
              f"{member_kind_label(params.member_kind)}."),
    ))

    return MemberSizingResult(
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
            f"{label} override {override:g} mm is thinner/smaller than the auto-sized "
            f"{auto:g} mm (strength/serviceability-governed) — possible under-design; the "
            "member checks will verify it."
        )
