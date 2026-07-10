"""Fixture — RCC slab deck worked example, validated against an INDEPENDENT
hand computation of the governing design moment, required effective depth and
tensile steel (+/-10 %).

SOURCE (named per the fixture contract): the classical simply-supported RCC
bridge-deck design procedure reproduced across the standard Indian bridge-design
texts — D. Johnson Victor, "Essentials of Bridge Engineering"; N. Krishna Raju,
"Design of Bridges" (RCC deck-slab / T-beam chapters) — combined with the IRS
Bridge Rules 25t Loading-2008 EUDL/CDA convention (M_max = EUDL_bm * L / 8;
impact factor 1 + CDA). Working-stress (IS 456) section design.

TRANSCRIPTION HONESTY (same discipline as the culvert / retaining-wall fixtures):
the expected values below were INDEPENDENTLY RE-DERIVED by hand from the
closed-form formulae in this file's comments; the 25t EUDL table value used is
itself flagged `needs_verification` in the loading layer and must be checked
against the source PDF before demo day.

Solid RCC slab deck (per 1 m width, all lengths in mm unless noted):
  Effective span L = 6.0 m, deck width 5.0 m, M30 / Fe500, clear cover 40 mm.
  Overall (and effective) depth fixed at D = 1000 mm so the check is independent
  of the auto-sizing loop; d = 1000 - 40 - 20/2 = 950 mm.

Hand derivation (per 1 m width):
  Live load — EUDL for BM at L = 6 m (25t-2008 table) = 786.8 kN/track.
    CDA = 0.15 + 8/(6 + L) = 0.15 + 8/12 = 0.8167 (no fill on the deck).
    M_LL(track) = EUDL_bm * L / 8 * (1 + CDA)
                = 786.8 * 6 / 8 * 1.8167 = 1071.9 kN*m.
    Distributed over a 3.0 m track width -> M_LL = 1071.9 / 3.0 = 357.3 kN*m/m.
  Dead load — self-weight 1.0 m * 25 = 25 kN/m^2 + permanent-way 12 kN/m^2
    -> w_DL = 37 kN/m per m width ; M_DL = 37 * 6^2 / 8 = 166.5 kN*m/m.
  Design moment M = 166.5 + 357.3 = 523.8 kN*m/m.
  Working stress (M30/Fe500): sigma_cbc 10, sigma_st 275, m = 9.333,
    k = 0.2534, j = 0.9155, Q = 1.160 N/mm^2.
    d_req = sqrt(M / (Q * b)) = sqrt(523.8e6 / (1.160 * 1000)) = 672 mm.
    As = M / (sigma_st * j * d) = 523.8e6 / (275 * 0.9155 * 950) = 2190 mm^2/m.

Tolerance: +/-10 % on the governing quantities.
"""

import re

import pytest

from components.slab_tbeam.analysis import analyse_deck
from components.slab_tbeam.checks import run_deck_checks
from components.slab_tbeam.params import SlabTbeamGeometry, SlabTbeamParams

TOL = 0.10  # +/-10 %

PARAMS = SlabTbeamParams(
    span_m=6.0,
    deck_type="solid_slab",
    carriageway_width_m=5.0,
    concrete_grade="M30",
    steel_grade="Fe500",
    clear_cover_mm=40.0,
)
GEOMETRY = SlabTbeamGeometry(
    span_mm=6000.0,
    deck_type="solid_slab",
    overall_depth_mm=1000.0,
    slab_depth_mm=1000.0,
    flange_width_mm=5000.0,
    number_of_girders=1,
    girder_spacing_mm=5000.0,
    deck_width_mm=5000.0,
)

EXPECTED_LIVE_MOMENT = 357.3  # kN*m/m
EXPECTED_DESIGN_MOMENT = 523.8  # kN*m/m
EXPECTED_REQUIRED_DEPTH = 672.0  # mm
EXPECTED_STEEL = 2190.0  # mm^2/m


@pytest.fixture(scope="module")
def analysis():
    return analyse_deck(PARAMS, GEOMETRY)


def test_live_load_moment_matches_the_25t_eudl_convention(analysis):
    assert analysis.live_moment_knm == pytest.approx(EXPECTED_LIVE_MOMENT, rel=TOL)


def test_design_moment_within_tolerance(analysis):
    assert analysis.design_moment_knm == pytest.approx(EXPECTED_DESIGN_MOMENT, rel=TOL)


def test_required_effective_depth_within_tolerance(analysis):
    checks = run_deck_checks(analysis, GEOMETRY, PARAMS)
    flexure = next(c for c in checks.checks if c.kind == "flexure")
    match = re.search(r"d_req = (\d+(?:\.\d+)?)", flexure.computed)
    assert match, f"could not read d_req from: {flexure.computed!r}"
    assert float(match.group(1)) == pytest.approx(EXPECTED_REQUIRED_DEPTH, rel=TOL)


def test_tensile_steel_area_within_tolerance(analysis):
    checks = run_deck_checks(analysis, GEOMETRY, PARAMS)
    steel = next(c for c in checks.checks if c.kind == "min_steel")
    match = re.search(r"As_req = (\d+(?:\.\d+)?)", steel.computed)
    assert match, f"could not read As from: {steel.computed!r}"
    assert float(match.group(1)) == pytest.approx(EXPECTED_STEEL, rel=TOL)


def test_loading_transcription_is_flagged_needs_verification(analysis):
    # Honesty: the 25t table values and deck allowances remain pending verification.
    assert analysis.needs_verification is True
