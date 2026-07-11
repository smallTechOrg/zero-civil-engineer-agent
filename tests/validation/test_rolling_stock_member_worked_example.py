"""Fixture — fabricated rolling-stock member governing quantities vs an
independent hand calculation (+/-5%).

SOURCE (named per the fixture contract): the classical working-stress steel-member
method reproduced across the standard steel-design texts — Punmia/Jain "Design of
Steel Structures" and Duggal "Limit State Design of Steel Structures" (working-
stress section chapters) — combined with the RDSO wagon-design load-case basis
(vertical payload augmented by a dynamic-augment factor + a longitudinal buffing
load). The RDSO vertical impact factor and buffing-load magnitudes are transcribed
constants (flagged `needs_verification` — see the module docstrings; verify against
the source RDSO specification before demo day).

TRANSCRIPTION HONESTY: the expected values below were INDEPENDENTLY RE-DERIVED by
hand from the closed-form formulae in this file's comments. They are checked within
+/-5%.

Stated section (all mm, one welded-I underframe cross member):
  member length L = 2.4 m ; web 300 x 10 ; flanges 150 x 12 ;
  overall depth D = 300 + 2 x 12 = 324 ; E250 steel ;
  design vertical load W_v = 300 kN ; design buffing load P = 800 kN.

Hand derivation:
  Cross-section area A = t_w*d_w + 2*b_f*t_f
    = 10*300 + 2*150*12 = 3000 + 3600 = 6600 mm^2.
  Second moment of area (strong axis):
    I = t_w*d_w^3/12 + 2*[b_f*t_f^3/12 + b_f*t_f*((d_w+t_f)/2)^2]
      = 10*300^3/12 + 2*[150*12^3/12 + 150*12*(156)^2]
      = 2.2500e7 + 2*[21,600 + 4.38048e7] = 2.2500e7 + 8.76528e7 = 1.101528e8 mm^4.
  Elastic section modulus Z = I/(D/2) = 1.101528e8 / 162 = 6.79956e5 mm^3 = 679.96 cm^3.

  Vertical payload case (RDSO dynamic-augment k = 1.30):
    self-weight w_sw = A * gamma_steel = 6600e-6 * 78.5 = 0.5181 kN/m
    M_dead = w_sw*L^2/8 = 0.5181*2.4^2/8 = 0.373 kN*m
    M_live = k*W_v*L/8 = 1.30*300*2.4/8 = 117.0 kN*m
    design moment M = M_dead + M_live = 117.37 kN*m
    extreme-fibre bending stress sigma_b = M/Z = 117.37e6/6.79956e5 = 172.6 N/mm^2
  Longitudinal buffing case:
    axial stress sigma_a = P/A = 800e3/6600 = 121.2 N/mm^2
  Combined interaction (E250: sigma_bc = 165, sigma_ac = 150 N/mm^2):
    R = sigma_a/sigma_ac + sigma_b/sigma_bc = 121.2/150 + 172.6/165 = 0.808 + 1.046 = 1.854
  Governing case: vertical utilisation 1.046 > buffing utilisation 0.808 -> vertical payload.

Tolerance: +/-5 %.
"""

import pytest

from components.rolling_stock_member.analysis import GOVERNING_VERTICAL, analyse_member
from components.rolling_stock_member.params import (
    RollingStockMemberGeometry,
    RollingStockMemberParams,
)

RSM_TOL = 0.05  # +/-5 %

WORKED_EXAMPLE_PARAMS = RollingStockMemberParams(
    member_length_m=2.4,
    member_kind="underframe_cross_member",
    design_vertical_load_kn=300.0,
    design_buffing_load_kn=800.0,
    steel_grade="E250",
    web_depth_mm=300.0,
    web_thickness_mm=10.0,
    flange_width_mm=150.0,
    flange_thickness_mm=12.0,
)
WORKED_EXAMPLE_GEOMETRY = RollingStockMemberGeometry(
    member_length_mm=2400.0,
    member_kind="underframe_cross_member",
    web_depth_mm=300.0,
    web_thickness_mm=10.0,
    flange_width_mm=150.0,
    flange_thickness_mm=12.0,
    overall_depth_mm=324.0,
    weld_size_mm=7.0,
)

# Independently hand-re-derived expected values.
EXPECTED_INERTIA_MM4 = 1.101528e8
EXPECTED_SECTION_MODULUS_CM3 = 679.96
EXPECTED_DESIGN_MOMENT_KNM = 117.37
EXPECTED_MAX_BENDING_STRESS_MPA = 172.6
EXPECTED_MAX_AXIAL_STRESS_MPA = 121.2
EXPECTED_INTERACTION_RATIO = 1.854


@pytest.fixture(scope="module")
def analysis():
    return analyse_member(WORKED_EXAMPLE_PARAMS, WORKED_EXAMPLE_GEOMETRY)


def test_second_moment_of_area_within_5pct(analysis):
    assert analysis.inertia_mm4 == pytest.approx(EXPECTED_INERTIA_MM4, rel=RSM_TOL)


def test_section_modulus_within_5pct(analysis):
    assert analysis.section_modulus_cm3 == pytest.approx(EXPECTED_SECTION_MODULUS_CM3, rel=RSM_TOL)


def test_design_moment_within_5pct(analysis):
    assert analysis.design_moment_knm == pytest.approx(EXPECTED_DESIGN_MOMENT_KNM, rel=RSM_TOL)


def test_governing_bending_stress_within_5pct(analysis):
    # Governing quantity under the stated vertical payload case.
    assert analysis.max_bending_stress_mpa == pytest.approx(
        EXPECTED_MAX_BENDING_STRESS_MPA, rel=RSM_TOL
    )


def test_buffing_axial_stress_within_5pct(analysis):
    assert analysis.max_axial_stress_mpa == pytest.approx(
        EXPECTED_MAX_AXIAL_STRESS_MPA, rel=RSM_TOL
    )


def test_combined_interaction_ratio_within_5pct(analysis):
    assert analysis.interaction_ratio == pytest.approx(EXPECTED_INTERACTION_RATIO, rel=RSM_TOL)
    # The interaction exceeds unity for this deliberately worked (governing) section.
    assert analysis.interaction_ratio > analysis.interaction_limit


def test_governing_load_case_is_the_vertical_payload(analysis):
    assert analysis.governing_load_case == GOVERNING_VERTICAL
