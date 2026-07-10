"""Fixture — published RCC cantilever retaining-wall worked example (+/-5%).

SOURCE (named per the fixture contract): the classical cantilever retaining-wall
worked example reproduced across the standard Indian RCC design texts — B.C.
Punmia, "Reinforced Concrete Structures" (Cantilever Retaining Walls chapter);
N. Krishna Raju, "Reinforced Concrete Design"; and Bowles, "Foundation Analysis
and Design" — for a level cohesionless backfill analysed by Rankine on the
vertical virtual back through the heel, working-stress (IS 456) section design.

TRANSCRIPTION HONESTY (same discipline as the culvert V3 fixture): the expected
values below were INDEPENDENTLY RE-DERIVED by hand from the classical closed-form
formulae in this file's comments — they are the coefficients the printed worked
examples reproduce. Verify the numbers against the printed source before demo day.

Wall (a realistic, sensible section — all dimensions in metres, per m run):
  H = 5.0 (total, base underside to top of fill), base slab Db = 0.5,
  stem height Hs = 4.5, toe Lt = 0.9, stem base ts_base = 0.5, stem top = 0.2,
  heel Lh = 1.6, base width B = 3.0, no shear key.
  Backfill: gamma = 18 kN/m^3, phi = 30 deg (level), no surcharge.
  gamma_concrete = 25, mu = 0.5, M25 / Fe415, clear cover 50 mm.
  Ka = (1-sin30)/(1+sin30) = 1/3 ; Kp = 3.

Hand derivation (per m run):
  Weights and their lever arms about the toe (x from the toe edge):
    base slab  : 3.0*0.5*25 = 37.500 kN  @ 1.500 m -> 56.250
    stem rect  : 0.2*4.5*25 = 22.500 kN  @ 1.300 m -> 29.250
    stem taper : 0.5*0.3*4.5*25 = 16.875 kN @ 1.100 m -> 18.5625
    soil/heel  : 1.6*4.5*18 = 129.600 kN @ 2.200 m -> 285.120
    SUM W = 206.475 kN ; Mr = 389.1825 kN*m
  Active thrust: Pa = 0.5*(1/3)*18*5^2 = 75.0 kN @ H/3 = 1.6667 m
    Mo = 125.0 kN*m
  FoS overturning = 389.1825 / 125.0                       = 3.114
  Sliding: passive over the toe embedment Db, Pp = 0.5*3*18*0.5^2 = 6.75 kN
    FoS sliding = (0.5*206.475 + 6.75) / 75.0              = 1.467
  Bearing: x_res = (Mr-Mo)/W = 264.1825/206.475 = 1.2795 m ; e = 0.2205 m
    p_max = (206.475/3)*(1 + 6*0.2205/3)                   = 99.18 kN/m^2
  Stem flexure: M = Ka*gamma*Hs^3/6 = (1/3)*18*4.5^3/6 = 91.125 kN*m/m
    M25/Fe415: sigma_cbc 8.5, sigma_st 230, j = 0.9038 ; d = 500-50-10 = 440 mm
    As = M/(sigma_st*j*d) = 91.125e6/(230*0.9038*440)      = 996 mm^2/m

Tolerance: +/-5 % per the spec/capabilities/retaining-wall.md fixture contract.
"""

import re

import pytest

from components.retaining_wall.analysis import analyse_wall
from components.retaining_wall.checks import run_wall_checks
from components.retaining_wall.params import RetainingWallGeometry, RetainingWallParams

RW_TOL = 0.05  # +/-5 %

WORKED_EXAMPLE_PARAMS = RetainingWallParams(
    retained_height_m=5.0,
    safe_bearing_capacity_kn_m2=200.0,
    backfill_friction_angle_deg=30.0,
    backfill_unit_weight_kn_m3=18.0,
    backfill_slope_deg=0.0,
    track_surcharge=False,
    surcharge_kn_m2=0.0,
    base_friction_coeff=0.5,
    concrete_grade="M25",
    steel_grade="Fe415",
    clear_cover_mm=50.0,
)
WORKED_EXAMPLE_GEOMETRY = RetainingWallGeometry(
    stem_top_thickness_mm=200.0,
    stem_base_thickness_mm=500.0,
    base_thickness_mm=500.0,
    toe_length_mm=900.0,
    heel_length_mm=1600.0,
    base_width_mm=3000.0,
    total_height_mm=5000.0,
    key_depth_mm=0.0,
)

# Published / hand-re-derived expected values.
EXPECTED_FOS_OVERTURNING = 3.114
EXPECTED_FOS_SLIDING = 1.467
EXPECTED_MAX_BEARING = 99.18  # kN/m^2
EXPECTED_STEM_STEEL_MM2 = 996.0  # mm^2/m


@pytest.fixture(scope="module")
def analysis():
    return analyse_wall(WORKED_EXAMPLE_PARAMS, WORKED_EXAMPLE_GEOMETRY)


def test_fos_overturning_within_5pct(analysis):
    assert analysis.fos_overturning == pytest.approx(EXPECTED_FOS_OVERTURNING, rel=RW_TOL)


def test_fos_sliding_within_5pct(analysis):
    assert analysis.fos_sliding == pytest.approx(EXPECTED_FOS_SLIDING, rel=RW_TOL)


def test_max_bearing_pressure_within_5pct(analysis):
    assert analysis.max_base_pressure_kn_m2 == pytest.approx(EXPECTED_MAX_BEARING, rel=RW_TOL)


def test_stem_steel_area_within_5pct(analysis):
    checks = run_wall_checks(analysis, WORKED_EXAMPLE_GEOMETRY, WORKED_EXAMPLE_PARAMS)
    stem_steel = next(c for c in checks.checks if c.member == "stem" and c.kind == "min_steel")
    match = re.search(r"As_req = (\d+(?:\.\d+)?)", stem_steel.computed)
    assert match, f"could not read stem As from: {stem_steel.computed!r}"
    assert float(match.group(1)) == pytest.approx(EXPECTED_STEM_STEEL_MM2, rel=RW_TOL)


def test_stem_moment_matches_the_classical_coefficient(analysis):
    # M = Ka * gamma * Hs^3 / 6 with Hs = 4.5 m.
    assert analysis.stem_moment_knm == pytest.approx(91.125, rel=RW_TOL)
