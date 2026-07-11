"""Deterministic proportioning of the welded steel plate girder.

Mirroring the platform's check-governed philosophy, the girder is sized so an
auto-sized design passes its own checks:

1. **Web depth** — a standard span/11 proportion (bounded), the classic
   plate-girder depth band span/10-span/12.
2. **Web thickness** — the larger of the average-shear demand
   (t_w >= V / (d_w * tau_perm)) and the slenderness cap (d_w / limit), floored at
   a minimum plate thickness.
3. **Flanges** — the flange area is taken as the larger of the bending demand
   (from the required section modulus) and the serviceability demand (the second
   moment of area the span/600 deflection limit requires), then split into a
   width ~ d_w/3 and a thickness.

The self-weight couples into the design actions, so the section is iterated to
convergence. User overrides are never grown: a deliberately thin flange or web
flows through to a FAIL row and a return-for-revision verdict (the under-design
demo case). Pure deterministic Python — no LLM, no I/O.
"""

from __future__ import annotations

from typing import NamedTuple

from pydantic import BaseModel

from components.base import Assumption, CalcStep
from components.plate_girder._engine_common import (
    CITATION_PROPORTIONING,
    CITATION_USER_INPUT,
    DEFLECTION_LIMIT_RATIO,
    E_STEEL_MPA,
    WEB_SLENDERNESS_LIMIT,
    Trail,
    permissible,
    round_up,
)
from components.plate_girder.analysis import compute_forces
from components.plate_girder.params import PlateGirderGeometry, PlateGirderParams

_THICK_STEP = 2.0
_WIDTH_STEP = 10.0
_DEPTH_STEP = 50.0
_STIFF_STEP = 50.0
_MIN_WEB_DEPTH_MM = 400.0
_MIN_WEB_THICKNESS_MM = 8.0
_MIN_FLANGE_WIDTH_MM = 200.0
_MAX_FLANGE_WIDTH_MM = 900.0
_MIN_FLANGE_THICKNESS_MM = 12.0
_MAX_PASSES = 12

# Deck width used to lay the girders out (BG single-track deck) — a layout
# assumption; the load is shared equally per girder regardless of spacing.
DECK_WIDTH_MM = 3600.0


class GirderSizingResult(BaseModel):
    """Everything `size_girder` returns — geometry plus its full provenance."""

    geometry: PlateGirderGeometry
    assumptions: list[Assumption]
    trail: list[CalcStep]
    warnings: list[str]


class _Sized(NamedTuple):
    span_mm: float
    web_depth_mm: float
    web_depth_auto_mm: float
    web_thickness_mm: float
    web_thickness_auto_mm: float
    flange_width_mm: float
    flange_width_auto_mm: float
    flange_thickness_mm: float
    flange_thickness_auto_mm: float
    flange_area_req_mm2: float
    girder_spacing_mm: float
    stiffener_spacing_mm: float


def _make_geometry(
    *,
    span_mm: float,
    web_depth_mm: float,
    web_thickness_mm: float,
    flange_width_mm: float,
    flange_thickness_mm: float,
    number_of_girders: int,
    girder_spacing_mm: float,
    stiffener_spacing_mm: float,
) -> PlateGirderGeometry:
    return PlateGirderGeometry(
        span_mm=span_mm,
        web_depth_mm=web_depth_mm,
        web_thickness_mm=web_thickness_mm,
        flange_width_mm=flange_width_mm,
        flange_thickness_mm=flange_thickness_mm,
        overall_depth_mm=web_depth_mm + 2.0 * flange_thickness_mm,
        number_of_girders=number_of_girders,
        girder_spacing_mm=girder_spacing_mm,
        stiffener_spacing_mm=stiffener_spacing_mm,
    )


def _proportion(params: PlateGirderParams) -> _Sized:
    """Converge the section (web + flanges) so the auto design passes its checks."""
    span_mm = round(params.span_m * 1000.0, 3)
    n = params.number_of_girders
    perm = permissible(params.steel_grade)

    web_depth_auto = max(_MIN_WEB_DEPTH_MM, round_up(span_mm / 11.0, _DEPTH_STEP))
    web_depth = params.web_depth_mm if params.web_depth_mm is not None else web_depth_auto

    flange_width_auto = min(
        _MAX_FLANGE_WIDTH_MM,
        max(_MIN_FLANGE_WIDTH_MM, round_up(web_depth / 3.0, _WIDTH_STEP)),
    )
    flange_width = (
        params.flange_width_mm if params.flange_width_mm is not None else flange_width_auto
    )

    girder_spacing = round(DECK_WIDTH_MM / n)
    stiffener_spacing = max(_STIFF_STEP, round_up(web_depth, _STIFF_STEP))

    # Seed the iteration with sensible plate sizes.
    web_thickness = params.web_thickness_mm if params.web_thickness_mm is not None else max(
        _MIN_WEB_THICKNESS_MM, round_up(web_depth / WEB_SLENDERNESS_LIMIT, _THICK_STEP)
    )
    flange_thickness = (
        params.flange_thickness_mm if params.flange_thickness_mm is not None else 20.0
    )

    web_thickness_auto = web_thickness
    flange_thickness_auto = flange_thickness
    flange_area_req = 0.0

    for _ in range(_MAX_PASSES):
        geometry = _make_geometry(
            span_mm=span_mm,
            web_depth_mm=web_depth,
            web_thickness_mm=web_thickness,
            flange_width_mm=flange_width,
            flange_thickness_mm=flange_thickness,
            number_of_girders=n,
            girder_spacing_mm=girder_spacing,
            stiffener_spacing_mm=stiffener_spacing,
        )
        core = compute_forces(params, geometry)

        # Web thickness: shear demand OR slenderness, floored at the minimum.
        t_w_shear = core.design_shear_kn * 1e3 / (web_depth * perm.sigma_shear_n_mm2)
        t_w_slender = web_depth / WEB_SLENDERNESS_LIMIT
        web_thickness_auto = round_up(
            max(t_w_shear, t_w_slender, _MIN_WEB_THICKNESS_MM), _THICK_STEP
        )
        new_web_thickness = (
            params.web_thickness_mm if params.web_thickness_mm is not None else web_thickness_auto
        )

        # Flange area: bending (section modulus) OR deflection (second moment).
        z_req_mm3 = core.design_moment_knm * 1e6 / perm.sigma_bending_n_mm2
        a_f_bending = max(
            0.0, (z_req_mm3 - new_web_thickness * web_depth**2 / 6.0) / web_depth
        )
        # Deflection: I >= 5 * w_ll * L^3 * ratio / (384 E).
        w_ll_n_mm = core.eudl_bm_kn * (1.0 + core.cda) / n * 1e3 / span_mm
        i_req = 5.0 * w_ll_n_mm * span_mm**3 * DEFLECTION_LIMIT_RATIO / (384.0 * E_STEEL_MPA)
        i_web = new_web_thickness * web_depth**3 / 12.0
        a_f_defl = max(0.0, 2.0 * (i_req - i_web) / web_depth**2)
        flange_area_req = max(a_f_bending, a_f_defl)

        flange_thickness_auto = round_up(
            max(flange_area_req / flange_width, _MIN_FLANGE_THICKNESS_MM), _THICK_STEP
        )
        new_flange_thickness = (
            params.flange_thickness_mm
            if params.flange_thickness_mm is not None
            else flange_thickness_auto
        )

        if (
            abs(new_web_thickness - web_thickness) < 1e-9
            and abs(new_flange_thickness - flange_thickness) < 1e-9
        ):
            web_thickness = new_web_thickness
            flange_thickness = new_flange_thickness
            break
        web_thickness = new_web_thickness
        flange_thickness = new_flange_thickness

    return _Sized(
        span_mm=span_mm,
        web_depth_mm=web_depth,
        web_depth_auto_mm=web_depth_auto,
        web_thickness_mm=web_thickness,
        web_thickness_auto_mm=web_thickness_auto,
        flange_width_mm=flange_width,
        flange_width_auto_mm=flange_width_auto,
        flange_thickness_mm=flange_thickness,
        flange_thickness_auto_mm=flange_thickness_auto,
        flange_area_req_mm2=flange_area_req,
        girder_spacing_mm=girder_spacing,
        stiffener_spacing_mm=stiffener_spacing,
    )


def size_girder(params: PlateGirderParams) -> GirderSizingResult:
    """Proportion the girder and return the geometry with its full provenance."""
    s = _proportion(params)
    trail = Trail("S")
    assumptions: list[Assumption] = []
    warnings: list[str] = []

    trail.record(
        description="Effective span",
        formula="L = span_m (user requirement)",
        inputs={"span_m": params.span_m},
        value=s.span_mm,
        unit="mm",
        citation=CITATION_USER_INPUT,
    )
    _record_member(
        trail, "Web depth", params.web_depth_mm, s.web_depth_auto_mm,
        "d_web = ceil50(span/11), min 400 mm (span/10-span/12 band)",
        {"span_mm": s.span_mm},
    )
    _record_member(
        trail, "Web thickness", params.web_thickness_mm, s.web_thickness_auto_mm,
        "t_web = ceil2(max(V/(d*tau_perm), d/slenderness_limit, 8 mm))",
        {"web_depth_mm": s.web_depth_mm},
    )
    trail.record(
        description="Required flange area (bending / deflection demand)",
        formula="A_f = max((Z_req - t_w*d^2/6)/d, 2*(I_req - I_web)/d^2)",
        inputs={"web_depth_mm": s.web_depth_mm, "flange_width_mm": s.flange_width_mm},
        value=round(s.flange_area_req_mm2, 1),
        unit="mm^2",
        citation=CITATION_PROPORTIONING,
    )
    _record_member(
        trail, "Flange width", params.flange_width_mm, s.flange_width_auto_mm,
        "b_f = ceil10(d_web/3), 200-900 mm",
        {"web_depth_mm": s.web_depth_mm},
    )
    _record_member(
        trail, "Flange thickness", params.flange_thickness_mm, s.flange_thickness_auto_mm,
        "t_f = ceil2(max(A_f / b_f, 12 mm))",
        {"flange_area_req_mm2": round(s.flange_area_req_mm2, 1), "flange_width_mm": s.flange_width_mm},
    )
    overall_depth = s.web_depth_mm + 2.0 * s.flange_thickness_mm
    trail.record(
        description="Overall girder depth",
        formula="D = d_web + 2 * t_flange",
        inputs={"web_depth_mm": s.web_depth_mm, "flange_thickness_mm": s.flange_thickness_mm},
        value=round(overall_depth, 1),
        unit="mm",
        citation=CITATION_PROPORTIONING,
    )
    trail.record(
        description="Intermediate transverse web-stiffener spacing",
        formula="a ~ web depth (bounded)",
        inputs={"web_depth_mm": s.web_depth_mm},
        value=round(s.stiffener_spacing_mm, 1),
        unit="mm",
        citation=CITATION_PROPORTIONING,
    )
    trail.record(
        description="Girder spacing (centre to centre)",
        formula="s = deck_width / number_of_girders",
        inputs={"deck_width_mm": DECK_WIDTH_MM, "number_of_girders": params.number_of_girders},
        value=round(s.girder_spacing_mm, 1),
        unit="mm",
        citation=CITATION_PROPORTIONING,
    )

    geometry = _make_geometry(
        span_mm=s.span_mm,
        web_depth_mm=s.web_depth_mm,
        web_thickness_mm=s.web_thickness_mm,
        flange_width_mm=s.flange_width_mm,
        flange_thickness_mm=s.flange_thickness_mm,
        number_of_girders=params.number_of_girders,
        girder_spacing_mm=s.girder_spacing_mm,
        stiffener_spacing_mm=s.stiffener_spacing_mm,
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
        field="stiffener_spacing_mm", value=round(s.stiffener_spacing_mm, 1),
        source="engine_default",
        note=(f"Intermediate transverse stiffeners at {s.stiffener_spacing_mm:g} mm spacing "
              "(~ web depth) — controls web-panel shear buckling; detailed stiffener design "
              "beyond this POC scope."),
    ))
    assumptions.append(Assumption(
        field="girder_spacing_mm", value=round(s.girder_spacing_mm, 1),
        source="engine_default",
        note=(f"Girders laid out at {s.girder_spacing_mm:g} mm centres for a {DECK_WIDTH_MM:g} mm "
              f"BG deck — a layout assumption; the track load is shared equally per girder."),
    ))

    return GirderSizingResult(
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
