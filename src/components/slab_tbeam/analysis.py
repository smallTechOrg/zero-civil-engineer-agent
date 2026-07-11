"""Dead-load + 25t live-load analysis of the RCC slab / T-beam deck.

Given `SlabTbeamParams` and a proportioned `SlabTbeamGeometry`, computes the
design bending moment and shear on the governing member:

* **solid_slab** — designed per 1 m width of deck. The track live load is spread
  laterally over an effective distribution width; the moment/shear are then per
  metre width.
* **t_beam** — designed per longitudinal girder. The track live load is
  apportioned to the critical girder by a distribution fraction (tributary width
  / distribution width, capped at the whole track).

Live load uses the pluggable 25t Loading-2008 standard
(`engine.loading.get_loading_standard`): EUDL for bending moment and for shear at
the loaded length (= the effective span), amplified by the coefficient of dynamic
augment (CDA). No fill cushion sits on the deck, so full CDA is applied
(conservative; flagged for verification).

`compute_deck_forces` is the pure numeric core (reused by the sizing loop and the
checks); `analyse_deck` wraps it with the CalcStep trail and Assumptions and
returns the `SlabTbeamAnalysis` model the calc sheet, checks and proof-check
consume.
"""

from __future__ import annotations

from typing import NamedTuple

from pydantic import BaseModel, Field

from components.base import Assumption, coerce
from components.slab_tbeam._engine_common import (
    CITATION_DEAD_LOAD,
    CITATION_DISTRIBUTION,
    CITATION_LIVE_LOAD,
    CONCRETE_UNIT_WEIGHT_KN_M3,
    TRACK_LATERAL_DISTRIBUTION_WIDTH_M,
    TRACK_SIDL_KN_M2,
    Trail,
)
from components.slab_tbeam.params import SlabTbeamGeometry, SlabTbeamParams
from engine.loading import get_loading_standard


class SlabTbeamAnalysis(BaseModel):
    """Dead + live load analysis — the rehydratable analysis model.

    Field names are normative (calc sheet, checks and proof-check read them). All
    moments are kN*m and shears kN, on the governing member (per m width for a
    solid slab, per girder for a T-beam).
    """

    deck_type: str = Field(description="'solid_slab' | 't_beam'")
    effective_span_m: float = Field(description="Effective span, m")
    loaded_length_m: float = Field(description="Loaded length for the EUDL lookup, m")
    loading_standard: str = Field(description="Live-load standard name")

    eudl_bm_kn: float = Field(description="EUDL for bending moment at the loaded length, kN/track")
    eudl_shear_kn: float = Field(description="EUDL for shear at the loaded length, kN/track")
    cda: float = Field(description="Coefficient of dynamic augment (impact fraction)")

    distribution_width_m: float = Field(description="Lateral live-load distribution width, m")
    distribution_fraction: float = Field(description="Fraction of the track load on the design member")

    design_width_mm: float = Field(description="Compression width b for flexure, mm")
    web_width_mm: float = Field(description="Web width b_w for shear, mm")
    tributary_width_m: float = Field(description="Deck width carried by the design member, m")

    dead_udl_kn_m: float = Field(description="Total dead-load intensity on the design member, kN/m")
    self_weight_kn_m: float = Field(description="RCC self-weight intensity, kN/m")
    sidl_kn_m: float = Field(description="Superimposed (permanent-way) dead-load intensity, kN/m")

    dead_moment_knm: float = Field(description="Dead-load design bending moment, kN*m")
    dead_shear_kn: float = Field(description="Dead-load design shear, kN")
    live_moment_knm: float = Field(description="Live-load (incl. CDA) design bending moment, kN*m")
    live_shear_kn: float = Field(description="Live-load (incl. CDA) design shear, kN")
    design_moment_knm: float = Field(description="Total design bending moment, kN*m")
    design_shear_kn: float = Field(description="Total design shear, kN")

    needs_verification: bool = Field(
        default=True, description="Loading transcription / allowances pending verification"
    )
    assumptions: list[Assumption] = Field(default_factory=list)
    trail: list = Field(default_factory=list, description="CalcStep trail")


class DeckForces(NamedTuple):
    """The pure numeric force result (no trail) — shared by sizing + analyse + checks."""

    deck_type: str
    effective_span_m: float
    loaded_length_m: float
    loading_standard: str
    eudl_bm_kn: float
    eudl_shear_kn: float
    cda: float
    distribution_width_m: float
    distribution_fraction: float
    design_width_mm: float
    web_width_mm: float
    tributary_width_m: float
    dead_udl_kn_m: float
    self_weight_kn_m: float
    sidl_kn_m: float
    dead_moment_knm: float
    dead_shear_kn: float
    live_moment_knm: float
    live_shear_kn: float
    design_moment_knm: float
    design_shear_kn: float


class LiveLoadResult(NamedTuple):
    """The full-track live-load moment/shear (before lateral distribution)."""

    eudl_bm_kn: float
    eudl_shear_kn: float
    cda: float
    track_moment_knm: float
    track_shear_kn: float


def track_live_load(params: SlabTbeamParams, span_m: float) -> LiveLoadResult:
    """Full-track live-load moment and shear at the given span, incl. CDA.

    IRS convention: the EUDL for bending moment is the total equivalent UDL W
    giving M_max = W*L/8 on a simply supported span; the EUDL for shear gives
    V_max = W_shear/2. Both are amplified by (1 + CDA). No fill on the deck ->
    full CDA (conservative).
    """
    standard = get_loading_standard(params.loading_standard.value)
    eudl_bm = standard.eudl_bm_kn(span_m)
    eudl_shear = standard.eudl_shear_kn(span_m)
    cda = standard.cda(span_m, 0.0)
    impact = 1.0 + cda
    track_moment = eudl_bm * span_m / 8.0 * impact
    track_shear = eudl_shear / 2.0 * impact
    return LiveLoadResult(eudl_bm, eudl_shear, cda, track_moment, track_shear)


def compute_deck_forces(params: SlabTbeamParams, geometry: SlabTbeamGeometry) -> DeckForces:
    """Deterministic dead + live design forces for a given deck geometry."""
    params = coerce(SlabTbeamParams, params)
    geometry = coerce(SlabTbeamGeometry, geometry)

    span = geometry.span_mm / 1000.0
    overall = geometry.overall_depth_mm / 1000.0
    slab = geometry.slab_depth_mm / 1000.0
    rib_w = geometry.rib_width_mm / 1000.0
    rib_d = geometry.rib_depth_mm / 1000.0
    deck_width = geometry.deck_width_mm / 1000.0
    spacing = geometry.girder_spacing_mm / 1000.0
    gamma_c = CONCRETE_UNIT_WEIGHT_KN_M3

    ll = track_live_load(params, span)
    dist_width = min(deck_width, TRACK_LATERAL_DISTRIBUTION_WIDTH_M)

    if geometry.deck_type == "solid_slab":
        # Design per 1 m width of slab.
        tributary = 1.0
        design_width_mm = 1000.0
        web_width_mm = 1000.0
        self_weight = overall * gamma_c  # per 1 m width
        sidl = TRACK_SIDL_KN_M2  # per 1 m width
        dist_fraction = 1.0 / dist_width  # live load per m width
        live_moment = ll.track_moment_knm * dist_fraction
        live_shear = ll.track_shear_kn * dist_fraction
    else:  # t_beam — design per girder
        tributary = spacing
        design_width_mm = geometry.flange_width_mm
        web_width_mm = geometry.rib_width_mm
        self_weight = (slab * spacing + rib_w * rib_d) * gamma_c
        sidl = TRACK_SIDL_KN_M2 * spacing
        dist_fraction = min(1.0, spacing / dist_width)
        live_moment = ll.track_moment_knm * dist_fraction
        live_shear = ll.track_shear_kn * dist_fraction

    dead_udl = self_weight + sidl
    dead_moment = dead_udl * span**2 / 8.0
    dead_shear = dead_udl * span / 2.0

    design_moment = dead_moment + live_moment
    design_shear = dead_shear + live_shear

    return DeckForces(
        deck_type=geometry.deck_type,
        effective_span_m=span,
        loaded_length_m=span,
        loading_standard=params.loading_standard.value,
        eudl_bm_kn=ll.eudl_bm_kn,
        eudl_shear_kn=ll.eudl_shear_kn,
        cda=ll.cda,
        distribution_width_m=dist_width,
        distribution_fraction=dist_fraction,
        design_width_mm=design_width_mm,
        web_width_mm=web_width_mm,
        tributary_width_m=tributary,
        dead_udl_kn_m=dead_udl,
        self_weight_kn_m=self_weight,
        sidl_kn_m=sidl,
        dead_moment_knm=dead_moment,
        dead_shear_kn=dead_shear,
        live_moment_knm=live_moment,
        live_shear_kn=live_shear,
        design_moment_knm=design_moment,
        design_shear_kn=design_shear,
    )


def analyse_deck(params: SlabTbeamParams, geometry: SlabTbeamGeometry) -> SlabTbeamAnalysis:
    """Full analysis with the CalcStep trail + modelling assumptions."""
    params = coerce(SlabTbeamParams, params)
    geometry = coerce(SlabTbeamGeometry, geometry)
    f = compute_deck_forces(params, geometry)
    trail = Trail("A")

    trail.record(
        description="EUDL for bending moment at the loaded length",
        formula="EUDL_bm = table(25t-2008, L)",
        inputs={"loaded_length_m": round(f.loaded_length_m, 3), "standard": f.loading_standard},
        value=round(f.eudl_bm_kn, 2), unit="kN/track", citation=CITATION_LIVE_LOAD,
    )
    trail.record(
        description="EUDL for shear at the loaded length",
        formula="EUDL_shear = table(25t-2008, L)",
        inputs={"loaded_length_m": round(f.loaded_length_m, 3), "standard": f.loading_standard},
        value=round(f.eudl_shear_kn, 2), unit="kN/track", citation=CITATION_LIVE_LOAD,
    )
    trail.record(
        description="Coefficient of dynamic augment (impact)",
        formula="CDA = 0.15 + 8/(6+L), no fill on the deck -> full CDA",
        inputs={"loaded_length_m": round(f.loaded_length_m, 3)},
        value=round(f.cda, 4), unit="-", citation=CITATION_LIVE_LOAD,
    )
    trail.record(
        description="Lateral live-load distribution width",
        formula="w_dist = min(deck_width, track distribution width)",
        inputs={
            "deck_width_m": round(geometry.deck_width_mm / 1000.0, 3),
            "track_distribution_width_m": round(TRACK_LATERAL_DISTRIBUTION_WIDTH_M, 3),
        },
        value=round(f.distribution_width_m, 3), unit="m", citation=CITATION_DISTRIBUTION,
    )
    trail.record(
        description="Live-load design bending moment on the member",
        formula="M_LL = EUDL_bm*L/8*(1+CDA) x distribution",
        inputs={
            "eudl_bm_kn": round(f.eudl_bm_kn, 2),
            "span_m": round(f.effective_span_m, 3),
            "cda": round(f.cda, 4),
            "distribution_fraction": round(f.distribution_fraction, 4),
        },
        value=round(f.live_moment_knm, 3), unit="kN*m", citation=CITATION_LIVE_LOAD,
    )
    trail.record(
        description="Live-load design shear on the member",
        formula="V_LL = EUDL_shear/2*(1+CDA) x distribution",
        inputs={
            "eudl_shear_kn": round(f.eudl_shear_kn, 2),
            "cda": round(f.cda, 4),
            "distribution_fraction": round(f.distribution_fraction, 4),
        },
        value=round(f.live_shear_kn, 3), unit="kN", citation=CITATION_LIVE_LOAD,
    )
    trail.record(
        description="Dead-load intensity on the member",
        formula="w_DL = RCC self-weight + permanent-way SIDL",
        inputs={
            "self_weight_kn_m": round(f.self_weight_kn_m, 3),
            "sidl_kn_m": round(f.sidl_kn_m, 3),
        },
        value=round(f.dead_udl_kn_m, 3), unit="kN/m", citation=CITATION_DEAD_LOAD,
    )
    trail.record(
        description="Dead-load design bending moment on the member",
        formula="M_DL = w_DL*L^2/8",
        inputs={"w_DL_kn_m": round(f.dead_udl_kn_m, 3), "span_m": round(f.effective_span_m, 3)},
        value=round(f.dead_moment_knm, 3), unit="kN*m", citation=CITATION_DEAD_LOAD,
    )
    trail.record(
        description="Dead-load design shear on the member",
        formula="V_DL = w_DL*L/2",
        inputs={"w_DL_kn_m": round(f.dead_udl_kn_m, 3), "span_m": round(f.effective_span_m, 3)},
        value=round(f.dead_shear_kn, 3), unit="kN", citation=CITATION_DEAD_LOAD,
    )
    trail.record(
        description="Total design bending moment on the member",
        formula="M = M_DL + M_LL",
        inputs={"M_DL_knm": round(f.dead_moment_knm, 3), "M_LL_knm": round(f.live_moment_knm, 3)},
        value=round(f.design_moment_knm, 3), unit="kN*m", citation=CITATION_LIVE_LOAD,
    )
    trail.record(
        description="Total design shear on the member",
        formula="V = V_DL + V_LL",
        inputs={"V_DL_kn": round(f.dead_shear_kn, 3), "V_LL_kn": round(f.live_shear_kn, 3)},
        value=round(f.design_shear_kn, 3), unit="kN", citation=CITATION_LIVE_LOAD,
    )

    assumptions = [
        Assumption(
            field="concrete_unit_weight_kn_m3",
            value=CONCRETE_UNIT_WEIGHT_KN_M3,
            source="engine_default",
            note=f"RCC self-weight taken as {CONCRETE_UNIT_WEIGHT_KN_M3:g} kN/m^3 (IS 456 / IS 875).",
        ),
        Assumption(
            field="track_sidl_kn_m2",
            value=TRACK_SIDL_KN_M2,
            source="engine_default",
            note=(
                f"Permanent-way superimposed dead load taken as {TRACK_SIDL_KN_M2:g} kN/m^2 "
                "(ballast, sleepers, rails and services) — assumed for the POC, pending "
                "verification."
            ),
        ),
        Assumption(
            field="live_load_distribution_width_m",
            value=round(f.distribution_width_m, 3),
            source="engine_default",
            note=(
                "The full-track EUDL is distributed laterally over an effective width of "
                f"{TRACK_LATERAL_DISTRIBUTION_WIDTH_M:g} m (sleeper length + dispersal), capped "
                "at the deck width — assumed for the POC, pending verification."
            ),
        ),
        Assumption(
            field="dynamic_augment_no_fill",
            value=round(f.cda, 4),
            source="engine_default",
            note=(
                "No fill cushion sits on the deck, so the full CDA is applied without the "
                "fill reduction (conservative)."
            ),
        ),
    ]

    return SlabTbeamAnalysis(
        deck_type=f.deck_type,
        effective_span_m=round(f.effective_span_m, 4),
        loaded_length_m=round(f.loaded_length_m, 4),
        loading_standard=f.loading_standard,
        eudl_bm_kn=round(f.eudl_bm_kn, 4),
        eudl_shear_kn=round(f.eudl_shear_kn, 4),
        cda=round(f.cda, 6),
        distribution_width_m=round(f.distribution_width_m, 4),
        distribution_fraction=round(f.distribution_fraction, 6),
        design_width_mm=round(f.design_width_mm, 3),
        web_width_mm=round(f.web_width_mm, 3),
        tributary_width_m=round(f.tributary_width_m, 4),
        dead_udl_kn_m=round(f.dead_udl_kn_m, 4),
        self_weight_kn_m=round(f.self_weight_kn_m, 4),
        sidl_kn_m=round(f.sidl_kn_m, 4),
        dead_moment_knm=round(f.dead_moment_knm, 4),
        dead_shear_kn=round(f.dead_shear_kn, 4),
        live_moment_knm=round(f.live_moment_knm, 4),
        live_shear_kn=round(f.live_shear_kn, 4),
        design_moment_knm=round(f.design_moment_knm, 4),
        design_shear_kn=round(f.design_shear_kn, 4),
        needs_verification=True,
        assumptions=assumptions,
        trail=trail.steps,
    )
