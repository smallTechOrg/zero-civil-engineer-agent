"""Deterministic proportioning of the RCC slab / T-beam deck.

Mirroring the retaining-wall engine's check-governed philosophy, the deck is
sized so an auto-sized design passes its own checks:

* **solid_slab** — the overall depth is the larger of the span/12 proportion and
  the flexure/shear demand from the design moment and shear (iterated to
  convergence, since the self-weight moment depends on the depth).
* **t_beam** — the deck-slab (flange) thickness is set first (min 200 mm), then
  the rib depth is the larger of the span/10 proportion and the flexure/shear
  demand (iterated). The effective flange width follows IS 456 cl. 23.1.2.

User overrides are never grown: a deliberately thin slab/rib flows through to a
FAIL row and a return-for-revision verdict (the under-design demo case). Pure
deterministic Python — no LLM, no I/O.
"""

from __future__ import annotations

import math
from typing import NamedTuple

from pydantic import BaseModel

from components.base import Assumption, CalcStep
from components.slab_tbeam._engine_common import (
    ASSUMED_BAR_DIA_MM,
    CITATION_FLANGE,
    CITATION_PROPORTIONING,
    CITATION_USER_INPUT,
    DECK_SLAB_MIN_THICKNESS_MM,
    RIB_MIN_WIDTH_MM,
    SOLID_SLAB_SPAN_DEPTH_RATIO,
    TBEAM_RIB_SPAN_DEPTH_RATIO,
    Trail,
    permissible_shear_stress,
    working_stress_constants,
)
from components.slab_tbeam.analysis import compute_deck_forces
from components.slab_tbeam.params import SlabTbeamGeometry, SlabTbeamParams

_STEP_MM = 25.0
_MIN_OVERALL_MM = 200.0
_MAX_PASSES = 10


class DeckSizingResult(BaseModel):
    """Everything `size_deck` returns — geometry plus its full provenance."""

    geometry: SlabTbeamGeometry
    assumptions: list[Assumption]
    trail: list[CalcStep]
    warnings: list[str]


class _Sized(NamedTuple):
    overall_mm: float
    overall_auto_mm: float
    slab_mm: float
    slab_auto_mm: float
    rib_width_mm: float
    rib_width_auto_mm: float
    rib_depth_mm: float
    rib_depth_auto_mm: float
    flange_width_mm: float
    girder_spacing_mm: float
    d_req_flexure_mm: float
    d_req_shear_mm: float
    design_moment_knm: float
    design_shear_kn: float


def _round25_up(value_mm: float) -> float:
    return math.ceil(round(value_mm / _STEP_MM, 6)) * _STEP_MM


def _flange_width_mm(span_mm: float, rib_width_mm: float, slab_mm: float, spacing_mm: float) -> float:
    """IS 456 cl. 23.1.2 effective flange width, capped at the girder spacing."""
    bf = span_mm / 6.0 + rib_width_mm + 6.0 * slab_mm
    return min(spacing_mm, bf)


def _make_geometry(
    params: SlabTbeamParams,
    *,
    overall_mm: float,
    slab_mm: float,
    rib_width_mm: float,
    rib_depth_mm: float,
) -> SlabTbeamGeometry:
    deck_width_mm = params.carriageway_width_m * 1000.0
    if params.deck_type == "solid_slab":
        return SlabTbeamGeometry(
            span_mm=params.span_m * 1000.0,
            deck_type="solid_slab",
            overall_depth_mm=overall_mm,
            slab_depth_mm=overall_mm,
            rib_width_mm=0.0,
            rib_depth_mm=0.0,
            flange_width_mm=deck_width_mm,
            number_of_girders=1,
            girder_spacing_mm=deck_width_mm,
            deck_width_mm=deck_width_mm,
        )
    spacing_mm = deck_width_mm / params.number_of_girders
    flange_mm = _flange_width_mm(params.span_m * 1000.0, rib_width_mm, slab_mm, spacing_mm)
    return SlabTbeamGeometry(
        span_mm=params.span_m * 1000.0,
        deck_type="t_beam",
        overall_depth_mm=overall_mm,
        slab_depth_mm=slab_mm,
        rib_width_mm=rib_width_mm,
        rib_depth_mm=rib_depth_mm,
        flange_width_mm=flange_mm,
        number_of_girders=params.number_of_girders,
        girder_spacing_mm=spacing_mm,
        deck_width_mm=deck_width_mm,
    )


def _demand_depth_mm(params: SlabTbeamParams, geometry: SlabTbeamGeometry) -> tuple[float, float, float, float]:
    """(overall_req, d_req_flexure, d_req_shear, ...) from the design forces."""
    wsc = working_stress_constants(params.concrete_grade, params.steel_grade)
    forces = compute_deck_forces(params, geometry)
    b = geometry.flange_width_mm if geometry.deck_type == "t_beam" else 1000.0
    bw = geometry.rib_width_mm if geometry.deck_type == "t_beam" else 1000.0
    tau_perm, _has_stirrups = permissible_shear_stress(params.concrete_grade, geometry.deck_type)
    m = forces.design_moment_knm
    v = forces.design_shear_kn
    d_req_flex = math.sqrt(m * 1e6 / (wsc.q_n_mm2 * b)) if m > 0 else 0.0
    d_req_shear = v * 1e3 / (tau_perm * bw) if v > 0 else 0.0
    overall_req = max(d_req_flex, d_req_shear) + params.clear_cover_mm + ASSUMED_BAR_DIA_MM / 2.0
    return overall_req, d_req_flex, d_req_shear, forces.design_moment_knm


def _proportion(params: SlabTbeamParams) -> _Sized:
    span_mm = params.span_m * 1000.0
    deck_width_mm = params.carriageway_width_m * 1000.0

    if params.deck_type == "solid_slab":
        proportion_mm = max(_round25_up(span_mm / SOLID_SLAB_SPAN_DEPTH_RATIO), _MIN_OVERALL_MM)
        overall_auto = proportion_mm
        d_req_flex = d_req_shear = design_moment = design_shear = 0.0
        for _ in range(_MAX_PASSES):
            overall = params.slab_depth_mm if params.slab_depth_mm is not None else overall_auto
            geometry = _make_geometry(params, overall_mm=overall, slab_mm=overall, rib_width_mm=0.0, rib_depth_mm=0.0)
            overall_req, d_req_flex, d_req_shear, design_moment = _demand_depth_mm(params, geometry)
            forces = compute_deck_forces(params, geometry)
            design_shear = forces.design_shear_kn
            new_auto = max(proportion_mm, _round25_up(overall_req))
            if params.slab_depth_mm is not None or new_auto <= overall_auto + 1e-9:
                overall_auto = new_auto
                break
            overall_auto = new_auto
        overall_final = params.slab_depth_mm if params.slab_depth_mm is not None else overall_auto
        return _Sized(
            overall_mm=overall_final, overall_auto_mm=overall_auto,
            slab_mm=overall_final, slab_auto_mm=overall_auto,
            rib_width_mm=0.0, rib_width_auto_mm=0.0,
            rib_depth_mm=0.0, rib_depth_auto_mm=0.0,
            flange_width_mm=deck_width_mm, girder_spacing_mm=deck_width_mm,
            d_req_flexure_mm=d_req_flex, d_req_shear_mm=d_req_shear,
            design_moment_knm=design_moment, design_shear_kn=design_shear,
        )

    # --- t_beam ---
    slab_override = params.flange_thickness_mm if params.flange_thickness_mm is not None else params.slab_depth_mm
    slab_auto = max(DECK_SLAB_MIN_THICKNESS_MM, _round25_up(deck_width_mm / params.number_of_girders / 20.0))
    slab_mm = slab_override if slab_override is not None else slab_auto
    rib_width_auto = max(RIB_MIN_WIDTH_MM, _round25_up(span_mm / 40.0))
    rib_width_mm = params.rib_width_mm if params.rib_width_mm is not None else rib_width_auto

    rib_proportion = max(_round25_up(span_mm / TBEAM_RIB_SPAN_DEPTH_RATIO), _STEP_MM)
    rib_depth_auto = rib_proportion
    d_req_flex = d_req_shear = design_moment = design_shear = 0.0
    for _ in range(_MAX_PASSES):
        rib_depth = params.rib_depth_mm if params.rib_depth_mm is not None else rib_depth_auto
        overall = slab_mm + rib_depth
        geometry = _make_geometry(params, overall_mm=overall, slab_mm=slab_mm, rib_width_mm=rib_width_mm, rib_depth_mm=rib_depth)
        overall_req, d_req_flex, d_req_shear, design_moment = _demand_depth_mm(params, geometry)
        forces = compute_deck_forces(params, geometry)
        design_shear = forces.design_shear_kn
        new_auto = max(rib_proportion, _round25_up(overall_req - slab_mm))
        if params.rib_depth_mm is not None or new_auto <= rib_depth_auto + 1e-9:
            rib_depth_auto = new_auto
            break
        rib_depth_auto = new_auto
    rib_depth_final = params.rib_depth_mm if params.rib_depth_mm is not None else rib_depth_auto
    overall_final = slab_mm + rib_depth_final
    geometry = _make_geometry(params, overall_mm=overall_final, slab_mm=slab_mm, rib_width_mm=rib_width_mm, rib_depth_mm=rib_depth_final)
    return _Sized(
        overall_mm=overall_final, overall_auto_mm=slab_mm + rib_depth_auto,
        slab_mm=slab_mm, slab_auto_mm=slab_auto,
        rib_width_mm=rib_width_mm, rib_width_auto_mm=rib_width_auto,
        rib_depth_mm=rib_depth_final, rib_depth_auto_mm=rib_depth_auto,
        flange_width_mm=geometry.flange_width_mm, girder_spacing_mm=geometry.girder_spacing_mm,
        d_req_flexure_mm=d_req_flex, d_req_shear_mm=d_req_shear,
        design_moment_knm=design_moment, design_shear_kn=design_shear,
    )


def size_deck(params: SlabTbeamParams) -> DeckSizingResult:
    """Proportion the deck and return the geometry with its full provenance."""
    from components.base import coerce

    params = coerce(SlabTbeamParams, params)
    s = _proportion(params)
    trail = Trail("S")
    assumptions: list[Assumption] = []
    warnings: list[str] = []

    geometry = _make_geometry(
        params, overall_mm=s.overall_mm, slab_mm=s.slab_mm,
        rib_width_mm=s.rib_width_mm, rib_depth_mm=s.rib_depth_mm,
    )

    trail.record(
        description="Effective span of the deck",
        formula="L = span_m (user requirement)",
        inputs={"span_m": params.span_m},
        value=geometry.span_mm, unit="mm", citation=CITATION_USER_INPUT,
    )
    trail.record(
        description="Required effective depth (flexure)",
        formula="d_req = sqrt(M / (Q*b))",
        inputs={"M_knm": round(s.design_moment_knm, 2)},
        value=round(s.d_req_flexure_mm, 1), unit="mm", citation=CITATION_PROPORTIONING,
    )
    trail.record(
        description="Required effective depth (shear)",
        formula="d_req = V / (tau_c * b_w)",
        inputs={"V_kn": round(s.design_shear_kn, 2)},
        value=round(s.d_req_shear_mm, 1), unit="mm", citation=CITATION_PROPORTIONING,
    )

    if params.deck_type == "solid_slab":
        _record_member(trail, "Overall slab depth", params.slab_depth_mm, s.overall_auto_mm,
                       "t = ceil25(max(span/12, flexure/shear demand))", {"span_mm": geometry.span_mm})
        _finalise_member(assumptions, warnings, "slab_depth_mm", "Overall slab depth",
                         params.slab_depth_mm, s.overall_auto_mm)
    else:
        _record_member(trail, "Deck-slab (flange) thickness",
                       params.flange_thickness_mm if params.flange_thickness_mm is not None else params.slab_depth_mm,
                       s.slab_auto_mm, "t_flange = max(200 mm, ceil25(spacing/20))",
                       {"spacing_mm": round(s.girder_spacing_mm, 1)})
        _record_member(trail, "Rib (web) width", params.rib_width_mm, s.rib_width_auto_mm,
                       "b_w = max(300 mm, ceil25(span/40))", {"span_mm": geometry.span_mm})
        _record_member(trail, "Rib depth below the slab", params.rib_depth_mm, s.rib_depth_auto_mm,
                       "d_rib = ceil25(max(span/10, flexure/shear demand - flange))",
                       {"span_mm": geometry.span_mm})
        trail.record(
            description="Effective flange width",
            formula="bf = min(spacing, span/6 + b_w + 6*Df)",
            inputs={
                "span_mm": geometry.span_mm, "rib_width_mm": geometry.rib_width_mm,
                "slab_mm": geometry.slab_depth_mm, "spacing_mm": round(s.girder_spacing_mm, 1),
            },
            value=round(geometry.flange_width_mm, 1), unit="mm", citation=CITATION_FLANGE,
        )
        _finalise_member(assumptions, warnings, "flange_thickness_mm", "Deck-slab (flange) thickness",
                         params.flange_thickness_mm if params.flange_thickness_mm is not None else params.slab_depth_mm,
                         s.slab_auto_mm)
        _finalise_member(assumptions, warnings, "rib_width_mm", "Rib width",
                         params.rib_width_mm, s.rib_width_auto_mm)
        _finalise_member(assumptions, warnings, "rib_depth_mm", "Rib depth",
                         params.rib_depth_mm, s.rib_depth_auto_mm)
        assumptions.append(Assumption(
            field="number_of_girders", value=params.number_of_girders, source="user",
            note=(f"{params.number_of_girders} longitudinal girders at "
                  f"{s.girder_spacing_mm:g} mm centres across the {geometry.deck_width_mm:g} mm deck."),
        ))

    return DeckSizingResult(geometry=geometry, assumptions=assumptions, trail=trail.steps, warnings=warnings)


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
            f"{auto:g} mm (flexure/shear-governed) — possible under-design; the member "
            "checks will verify it."
        )
