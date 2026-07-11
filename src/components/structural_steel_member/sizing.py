"""Deterministic proportioning of the fabricated welded-I cantilever member.

Mirroring the platform's check-governed philosophy, the member is sized so an
auto-sized design passes its own IS 800 / IS 816 checks:

1. **Web (clear) depth** — the larger of a length proportion (L/12) and a
   moment-scaled depth (~ k*sqrt(M)), capped at a fraction of the length so the
   drawing stays a slender cantilever. The moment-scaled law keeps the fillet-weld
   bending stress bounded regardless of the moment magnitude.
2. **Flange width** — proportioned to the depth AND grown until the
   weak-axis slenderness KL/r_min meets the compression-slenderness target
   (a compression member is slenderness-governed).
3. **Web thickness** — the larger of the average-shear demand and an unstiffened-web
   slenderness cap, floored at a minimum plate thickness.
4. **Flanges (thickness)** — from the section modulus the bending demand requires,
   RESERVING capacity for the co-existent axial force so the combined interaction
   also passes.
5. **Fillet weld** — sized so the base weld-group throat stress meets the IS 816
   permissible, floored at the IS 816 minimum and capped at the flange thickness.

The self-weight couples into the design actions, so the section is iterated to
convergence. User overrides are never grown: a deliberately thin flange/web or an
undersized weld flows through to a FAIL row and a return-for-revision verdict (the
under-design demo case). Pure deterministic Python — no LLM, no I/O.
"""

from __future__ import annotations

import math
from typing import NamedTuple

from pydantic import BaseModel

from components.base import Assumption, CalcStep
from components.structural_steel_member._engine_common import (
    CANTILEVER_EFFECTIVE_LENGTH_FACTOR,
    CITATION_PROPORTIONING,
    CITATION_USER_INPUT,
    FILLET_THROAT_FACTOR,
    PERMISSIBLE_WELD_STRESS_MPA,
    STEEL_UNIT_WEIGHT_KN_M3,
    Trail,
    min_weld_size,
    permissible,
    permissible_axial_stress,
    round_up,
    section_properties,
    weld_group_line_props,
)
from components.structural_steel_member.analysis import compute_forces
from components.structural_steel_member.params import (
    SteelMemberGeometry,
    SteelMemberParams,
)

# Proportioning steps and bounds (mm).
_DEPTH_STEP = 25.0
_THICK_STEP = 2.0
_WIDTH_STEP = 10.0
_WELD_STEP = 1.0
_MIN_WEB_DEPTH_MM = 150.0
_MAX_WEB_DEPTH_MM = 1500.0
_MIN_WEB_THICKNESS_MM = 6.0
_MIN_FLANGE_WIDTH_MM = 90.0
_MAX_FLANGE_WIDTH_MM = 450.0
_MIN_FLANGE_THICKNESS_MM = 8.0
_MAX_FLANGE_THICKNESS_MM = 63.0
_MIN_WELD_MM = 5.0
_MAX_WELD_MM = 20.0
_MAX_PASSES = 16

# Depth law constants.
_DEPTH_MOMENT_COEFF = 55.0  # web depth ~ coeff * sqrt(M_knm)
_DEPTH_LENGTH_DIVISOR = 12.0  # web depth floor ~ L/12
_DEPTH_CAP_FRACTION = 0.55  # web depth capped at a fraction of the length

# Unstiffened-web slenderness cap d_web / t_web (working-stress practice).
_WEB_SLENDERNESS_CAP = 90.0

# Compression-slenderness target the flange width is proportioned to (leaves
# margin below the SLENDERNESS_LIMIT of 180).
_SLENDERNESS_TARGET = 150.0

# Reserve factor + floor applied to the bending demand so the co-existent axial
# force leaves the combined interaction below 1.0 (the flange-area estimate; the
# actual combined ratio is then verified and the flange grown if needed).
_COMBINED_RESERVE_FACTOR = 0.85
_AXIAL_RATIO_FLOOR = 0.2

# Combined-interaction ratio the auto flange thickness is grown to satisfy.
_COMBINED_DESIGN_TARGET = 0.95

# Fraction of the permissible weld stress the auto weld is sized to (leaves a
# margin so the final resultant weld stress sits comfortably below the permissible).
_WELD_DESIGN_FRACTION = 0.92

# Flange-width proportion of the web depth (before the slenderness top-up).
_FLANGE_WIDTH_FRACTION = 0.4


class MemberSizingResult(BaseModel):
    """Everything `size_member` returns — geometry plus its full provenance."""

    geometry: SteelMemberGeometry
    assumptions: list[Assumption]
    trail: list[CalcStep]
    warnings: list[str]


class _Sized(NamedTuple):
    length_mm: float
    web_depth_mm: float
    web_depth_auto_mm: float
    web_thickness_mm: float
    web_thickness_auto_mm: float
    flange_width_mm: float
    flange_width_auto_mm: float
    flange_thickness_mm: float
    flange_thickness_auto_mm: float
    weld_size_mm: float
    weld_size_auto_mm: float


def _make_geometry(
    *,
    member_type: str,
    length_mm: float,
    web_depth_mm: float,
    web_thickness_mm: float,
    flange_width_mm: float,
    flange_thickness_mm: float,
    weld_size_mm: float,
) -> SteelMemberGeometry:
    return SteelMemberGeometry(
        member_type=member_type,
        cantilever_length_mm=length_mm,
        web_depth_mm=web_depth_mm,
        web_thickness_mm=web_thickness_mm,
        flange_width_mm=flange_width_mm,
        flange_thickness_mm=flange_thickness_mm,
        overall_depth_mm=web_depth_mm + 2.0 * flange_thickness_mm,
        weld_size_mm=weld_size_mm,
    )


def _flange_width_for_slenderness(
    length_mm: float, web_depth: float, web_thickness: float
) -> float:
    """Smallest flange width (proportioned + slenderness-governed) meeting the target
    weak-axis slenderness, using a nominal flange thickness for r_min."""
    proportion = round_up(_FLANGE_WIDTH_FRACTION * web_depth, _WIDTH_STEP)
    nominal_tf = max(_MIN_FLANGE_THICKNESS_MM, round_up(web_depth / 40.0, _THICK_STEP))
    width = max(_MIN_FLANGE_WIDTH_MM, proportion)
    while width <= _MAX_FLANGE_WIDTH_MM:
        section = section_properties(
            web_depth_mm=web_depth,
            web_thickness_mm=web_thickness,
            flange_width_mm=width,
            flange_thickness_mm=nominal_tf,
        )
        r_min = section.radius_of_gyration_min_mm
        slenderness = (
            CANTILEVER_EFFECTIVE_LENGTH_FACTOR * length_mm / r_min if r_min > 0 else 1e9
        )
        if slenderness <= _SLENDERNESS_TARGET:
            return width
        width += _WIDTH_STEP
    return _MAX_FLANGE_WIDTH_MM


def _required_weld_size(
    *, overall_depth: float, web_depth: float, flange_width: float,
    moment_knm: float, shear_kn: float, axial_kn: float,
) -> float:
    """Fillet-weld leg the base weld group needs to meet the IS 816 permissible."""
    lines = weld_group_line_props(
        overall_depth_mm=overall_depth, web_depth_mm=web_depth, flange_width_mm=flange_width
    )
    normal = (axial_kn * 1e3) / lines.length_mm + (moment_knm * 1e6) / lines.modulus_line_mm2
    shear = (shear_kn * 1e3) / lines.length_mm
    resultant_per_unit_throat = math.hypot(normal, shear)  # = f_r * throat
    required_throat = resultant_per_unit_throat / (
        _WELD_DESIGN_FRACTION * PERMISSIBLE_WELD_STRESS_MPA
    )
    return required_throat / FILLET_THROAT_FACTOR


def _grow_flange_for_interaction(
    *, params: SteelMemberParams, fy: float, sigma_bc: float, length_mm: float,
    web_depth: float, web_thickness: float, flange_width: float, start_thickness: float,
) -> float:
    """Smallest flange thickness (>= start) whose ACTUAL section makes bending and
    the combined axial+bending interaction meet the design target (self-consistent
    with the member self-weight and slenderness)."""
    length_m = length_mm / 1000.0
    tf = max(_MIN_FLANGE_THICKNESS_MM, start_thickness)
    while tf <= _MAX_FLANGE_THICKNESS_MM:
        section = section_properties(
            web_depth_mm=web_depth, web_thickness_mm=web_thickness,
            flange_width_mm=flange_width, flange_thickness_mm=tf,
        )
        self_weight = section.area_mm2 * 1e-6 * STEEL_UNIT_WEIGHT_KN_M3
        moment = params.transverse_load_kn * length_m + self_weight * length_m**2 / 2.0
        sigma_bc_cal = moment * 1e6 / section.section_modulus_mm3
        sigma_ac_cal = params.axial_load_kn * 1e3 / section.area_mm2
        slenderness = (
            CANTILEVER_EFFECTIVE_LENGTH_FACTOR * length_mm / section.radius_of_gyration_min_mm
            if section.radius_of_gyration_min_mm > 0
            else 1e9
        )
        sigma_ac = permissible_axial_stress(fy, slenderness)
        combined = (sigma_ac_cal / sigma_ac if sigma_ac > 0 else 1e9) + sigma_bc_cal / sigma_bc
        if sigma_bc_cal <= sigma_bc and combined <= _COMBINED_DESIGN_TARGET:
            return tf
        tf += _THICK_STEP
    return _MAX_FLANGE_THICKNESS_MM


def _proportion(params: SteelMemberParams) -> _Sized:
    """Converge the section (web + flanges + weld) so the auto design passes."""
    length_mm = round(params.cantilever_length_m * 1000.0, 3)
    length_m = params.cantilever_length_m
    perm = permissible(params.steel_grade)
    fy = perm.fy_n_mm2

    moment0 = params.transverse_load_kn * length_m  # kN*m (self-weight added in-loop)
    web_depth_auto = round_up(
        min(
            _DEPTH_CAP_FRACTION * length_mm,
            max(length_mm / _DEPTH_LENGTH_DIVISOR, _DEPTH_MOMENT_COEFF * math.sqrt(moment0)),
        ),
        _DEPTH_STEP,
    )
    web_depth_auto = min(_MAX_WEB_DEPTH_MM, max(_MIN_WEB_DEPTH_MM, web_depth_auto))
    web_depth = params.web_depth_mm if params.web_depth_mm is not None else web_depth_auto

    web_thickness_seed = max(
        _MIN_WEB_THICKNESS_MM, round_up(web_depth / _WEB_SLENDERNESS_CAP, _THICK_STEP)
    )
    flange_width_auto = _flange_width_for_slenderness(length_mm, web_depth, web_thickness_seed)
    flange_width = (
        params.flange_width_mm if params.flange_width_mm is not None else flange_width_auto
    )

    web_thickness = (
        params.web_thickness_mm if params.web_thickness_mm is not None else web_thickness_seed
    )
    flange_thickness = (
        params.flange_thickness_mm
        if params.flange_thickness_mm is not None
        else _MIN_FLANGE_THICKNESS_MM
    )
    weld_size = params.weld_size_mm if params.weld_size_mm is not None else _MIN_WELD_MM

    web_thickness_auto = web_thickness_seed
    flange_thickness_auto = flange_thickness
    weld_size_auto = weld_size

    for _ in range(_MAX_PASSES):
        geometry = _make_geometry(
            member_type=params.member_type,
            length_mm=length_mm,
            web_depth_mm=web_depth,
            web_thickness_mm=web_thickness,
            flange_width_mm=flange_width,
            flange_thickness_mm=flange_thickness,
            weld_size_mm=weld_size,
        )
        core = compute_forces(params, geometry)

        # Web thickness: shear demand OR unstiffened-web slenderness, floored.
        t_w_shear = core.design_shear_kn * 1e3 / (web_depth * perm.sigma_shear_n_mm2)
        t_w_slender = web_depth / _WEB_SLENDERNESS_CAP
        web_thickness_auto = round_up(
            max(t_w_shear, t_w_slender, _MIN_WEB_THICKNESS_MM), _THICK_STEP
        )
        new_web_thickness = (
            params.web_thickness_mm
            if params.web_thickness_mm is not None
            else web_thickness_auto
        )

        # Flange thickness: an initial section-modulus estimate reserving capacity
        # for axial, then GROWN until the ACTUAL combined interaction meets the
        # design target (the elastic-modulus estimate can undershoot for a
        # high-axial member).
        axial_ratio = (
            core.max_axial_stress_mpa / core.permissible_axial_stress_mpa
            if core.permissible_axial_stress_mpa > 0
            else 1.0
        )
        available = max(_AXIAL_RATIO_FLOOR, 1.0 - axial_ratio) * _COMBINED_RESERVE_FACTOR
        z_req_mm3 = core.design_moment_knm * 1e6 / (perm.sigma_bending_n_mm2 * available)
        a_f_bending = max(
            0.0, (z_req_mm3 - new_web_thickness * web_depth**2 / 6.0) / web_depth
        )
        flange_thickness_auto = _grow_flange_for_interaction(
            params=params, fy=fy, sigma_bc=perm.sigma_bending_n_mm2,
            length_mm=length_mm, web_depth=web_depth, web_thickness=new_web_thickness,
            flange_width=flange_width,
            start_thickness=round_up(
                max(a_f_bending / flange_width, _MIN_FLANGE_THICKNESS_MM), _THICK_STEP
            ),
        )
        new_flange_thickness = (
            params.flange_thickness_mm
            if params.flange_thickness_mm is not None
            else flange_thickness_auto
        )

        # Fillet weld: sized to the base weld-group demand, floored and capped.
        overall = web_depth + 2.0 * new_flange_thickness
        required_weld = _required_weld_size(
            overall_depth=overall, web_depth=web_depth, flange_width=flange_width,
            moment_knm=core.design_moment_knm, shear_kn=core.design_shear_kn,
            axial_kn=core.design_axial_kn,
        )
        weld_floor = max(_MIN_WELD_MM, min_weld_size(max(new_web_thickness, new_flange_thickness)))
        weld_cap = min(_MAX_WELD_MM, new_flange_thickness)
        weld_size_auto = min(
            weld_cap, max(weld_floor, round_up(required_weld, _WELD_STEP))
        )
        new_weld_size = params.weld_size_mm if params.weld_size_mm is not None else weld_size_auto

        converged = (
            abs(new_web_thickness - web_thickness) < 1e-9
            and abs(new_flange_thickness - flange_thickness) < 1e-9
            and abs(new_weld_size - weld_size) < 1e-9
        )
        web_thickness = new_web_thickness
        flange_thickness = new_flange_thickness
        weld_size = new_weld_size
        if converged:
            break

    return _Sized(
        length_mm=length_mm,
        web_depth_mm=web_depth,
        web_depth_auto_mm=web_depth_auto,
        web_thickness_mm=web_thickness,
        web_thickness_auto_mm=web_thickness_auto,
        flange_width_mm=flange_width,
        flange_width_auto_mm=flange_width_auto,
        flange_thickness_mm=flange_thickness,
        flange_thickness_auto_mm=flange_thickness_auto,
        weld_size_mm=weld_size,
        weld_size_auto_mm=weld_size_auto,
    )


def size_member(params: SteelMemberParams) -> MemberSizingResult:
    """Proportion the member and return the geometry with its full provenance."""
    s = _proportion(params)
    trail = Trail("S")
    assumptions: list[Assumption] = []
    warnings: list[str] = []

    trail.record(
        description="Cantilever length",
        formula="L = cantilever_length_m (user requirement)",
        inputs={"cantilever_length_m": params.cantilever_length_m},
        value=s.length_mm,
        unit="mm",
        citation=CITATION_USER_INPUT,
    )
    trail.record(
        description="Governing transverse load",
        formula="P = transverse_load_kn (user requirement)",
        inputs={"transverse_load_kn": params.transverse_load_kn},
        value=params.transverse_load_kn,
        unit="kN",
        citation=CITATION_USER_INPUT,
    )
    _record_member(
        trail, "Clear web depth", params.web_depth_mm, s.web_depth_auto_mm,
        "d_web = clamp(min(0.55L, max(L/12, 55*sqrt(M))))",
        {"length_mm": s.length_mm},
    )
    _record_member(
        trail, "Flange width", params.flange_width_mm, s.flange_width_auto_mm,
        "b_f = max(0.4*d_web, width for KL/r <= 150), 90-450 mm",
        {"web_depth_mm": s.web_depth_mm},
    )
    _record_member(
        trail, "Web thickness", params.web_thickness_mm, s.web_thickness_auto_mm,
        "t_web = ceil2(max(V/(d*tau_perm), d/90, 6 mm))",
        {"web_depth_mm": s.web_depth_mm},
    )
    _record_member(
        trail, "Flange thickness", params.flange_thickness_mm, s.flange_thickness_auto_mm,
        "t_f = ceil2(max(A_f/b_f, 8 mm)); A_f from Z_req reserving axial capacity",
        {"flange_width_mm": s.flange_width_mm},
    )
    _record_member(
        trail, "Fillet-weld leg", params.weld_size_mm, s.weld_size_auto_mm,
        "s = clamp(ceil1(required throat/0.707), IS 816 min, flange thickness)",
        {"overall_depth_mm": s.web_depth_mm + 2.0 * s.flange_thickness_mm}, unit="mm",
    )
    overall_depth = s.web_depth_mm + 2.0 * s.flange_thickness_mm
    trail.record(
        description="Overall section depth",
        formula="D = d_web + 2 * t_flange",
        inputs={"web_depth_mm": s.web_depth_mm, "flange_thickness_mm": s.flange_thickness_mm},
        value=round(overall_depth, 1),
        unit="mm",
        citation=CITATION_PROPORTIONING,
    )

    geometry = _make_geometry(
        member_type=params.member_type,
        length_mm=s.length_mm,
        web_depth_mm=s.web_depth_mm,
        web_thickness_mm=s.web_thickness_mm,
        flange_width_mm=s.flange_width_mm,
        flange_thickness_mm=s.flange_thickness_mm,
        weld_size_mm=s.weld_size_mm,
    )

    _finalise_member(assumptions, warnings, "web_depth_mm", "Clear web depth",
                     params.web_depth_mm, s.web_depth_auto_mm)
    _finalise_member(assumptions, warnings, "flange_width_mm", "Flange width",
                     params.flange_width_mm, s.flange_width_auto_mm)
    _finalise_member(assumptions, warnings, "web_thickness_mm", "Web thickness",
                     params.web_thickness_mm, s.web_thickness_auto_mm)
    _finalise_member(assumptions, warnings, "flange_thickness_mm", "Flange thickness",
                     params.flange_thickness_mm, s.flange_thickness_auto_mm)
    _finalise_member(assumptions, warnings, "weld_size_mm", "Fillet-weld leg",
                     params.weld_size_mm, s.weld_size_auto_mm)

    return MemberSizingResult(
        geometry=geometry, assumptions=assumptions, trail=trail.steps, warnings=warnings
    )


def _record_member(trail, label, override, auto, formula, inputs, unit="mm") -> None:
    if override is None:
        trail.record(description=f"{label} — auto-sized", formula=formula, inputs=inputs,
                     value=round(auto, 1), unit=unit, citation=CITATION_PROPORTIONING)
    else:
        trail.record(
            description=f"{label} — user override (auto-size reference {auto:g} mm)",
            formula="t = user override",
            inputs={**inputs, "override_mm": override, "auto_sized_mm": auto},
            value=round(override, 1), unit=unit, citation=CITATION_USER_INPUT,
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
            "member/weld checks will verify it."
        )
