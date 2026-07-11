"""Fixture — fabricated welded-I steel member governing quantities vs an
independent hand calculation (+/-5%, +/-10% for the transcribed code table).

SOURCE (named per the fixture contract): the classical working-stress steel-member
method reproduced across the standard steel-design texts — Punmia/Jain "Design of
Steel Structures" and Duggal "Limit State Design of Steel Structures"
(working-stress chapters) for the elastic section properties, the axial /
bending / shear permissible-stress basis, and the IS 816 fillet-weld-group "weld
treated as a line" method. The permissible axial compressive stress sigma_ac uses
the Merchant-Rankine formula IS 800 used to tabulate its sigma_ac values (n = 1.4);
the transcribed fy=250 sigma_ac table (flagged needs_verification — see the module
docstring) is cross-checked within +/-10%.

TRANSCRIPTION HONESTY: the expected values below were INDEPENDENTLY RE-DERIVED by
hand from the closed-form formulae in this file's comments. They are checked
within +/-5% (+/-10% for the transcribed sigma_ac table).

Stated member (all mm, a welded-I cantilever gantry post):
  cantilever length L = 6.0 m ; web (clear) 500 x 8 ; flanges 300 x 16 ;
  overall depth D = 500 + 2 x 16 = 532 ; base fillet weld s = 10 mm ; E250 steel ;
  transverse tip load P = 20 kN ; co-existent axial N = 100 kN.

Hand derivation:
  Area A = t_w*d_w + 2*b_f*t_f = 8*500 + 2*300*16 = 4000 + 9600 = 13600 mm^2.
  Strong-axis second moment:
    I_xx = t_w*d_w^3/12 + 2*[b_f*t_f^3/12 + b_f*t_f*((d_w+t_f)/2)^2]
         = 8*500^3/12 + 2*[300*16^3/12 + 300*16*(258)^2]
         = 8.3333e7 + 2*[1.024e5 + 3.1951e8] = 8.3333e7 + 6.3923e8 = 7.2256e8 mm^4.
  Section modulus Z = I_xx/(D/2) = 7.2256e8/266 = 2.7164e6 mm^3 = 2716 cm^3.
  Weak-axis: I_yy = d_w*t_w^3/12 + 2*(t_f*b_f^3/12) = 2.133e4 + 7.20e7 = 7.202e7 mm^4.
    r_min = sqrt(I_yy/A) = sqrt(7.202e7/13600) = 72.77 mm.
  Slenderness lambda = K*L/r_min = 2*6000/72.77 = 164.9 (cantilever K = 2.0).
  Self-weight w = A*gamma = 13600e-6*78.5 = 1.0676 kN/m.
  Design moment M = P*L + w*L^2/2 = 20*6 + 1.0676*6^2/2 = 120 + 19.2 = 139.2 kN*m.
  Design shear  V = P + w*L = 20 + 1.0676*6 = 26.4 kN.
  Bending stress sigma_bc = M/Z = 139.2e6/2.7164e6 = 51.3 N/mm^2.
  Axial stress   sigma_ac,cal = N/A = 100e3/13600 = 7.35 N/mm^2.
  Web shear tau = V/(d_w*t_w) = 26.4e3/(500*8) = 6.60 N/mm^2.
  Permissible axial (Merchant-Rankine, fy 250, lambda 164.9):
    fcc = pi^2 E/lambda^2 = pi^2*2e5/164.9^2 = 72.6 N/mm^2 ;
    sigma_ac = 0.6*fcc*fy/(fcc^1.4 + fy^1.4)^(1/1.4) = 38.8 N/mm^2
    (transcribed table at lambda 164.9 ~ 39.0 N/mm^2 — within +/-10%).
  Combined interaction = 7.35/38.8 + 51.3/165 = 0.19 + 0.31 = 0.50.
  Fillet-weld group (weld as a line, unit throat):
    L_w = 2*b_f + 2*d_w = 2*300 + 2*500 = 1600 mm ;
    I_w,line = 2*b_f*(D/2)^2 + 2*d_w^3/12 = 4.2454e7 + 2.0833e7 = 6.329e7 mm^3 ;
    Z_w,line = I_w,line/(D/2) = 6.329e7/266 = 2.379e5 mm^2 ; throat = 0.707*10 = 7.07 mm ;
    A_w = 7.07*1600 = 11312 mm^2 ; Z_w = 7.07*2.379e5 = 1.682e6 mm^3 ;
    normal f = N/A_w + M/Z_w = 8.84 + 82.8 = 91.6 ; shear f = V/A_w = 2.33 ;
    resultant f_r = sqrt(91.6^2 + 2.33^2) = 91.6 N/mm^2.
  Required section modulus at the permissible bending stress (E250, 165 N/mm^2):
    Z_req = M/sigma_bc = 139.2e6/165 = 8.44e5 mm^3 = 844 cm^3
    (provided 2716 cm^3 > required -> the section is adequate in bending).

Tolerance: +/-5 % (+/-10 % for the transcribed sigma_ac table value).
"""

import pytest

from components.structural_steel_member.analysis import analyse_member
from components.structural_steel_member.params import SteelMemberGeometry, SteelMemberParams

SSM_TOL = 0.05  # +/-5 %
TABLE_TOL = 0.10  # +/-10 % for a transcribed code-table value

WORKED_EXAMPLE_PARAMS = SteelMemberParams(
    cantilever_length_m=6.0,
    transverse_load_kn=20.0,
    axial_load_kn=100.0,
    steel_grade="E250",
    member_type="gantry_post",
    web_depth_mm=500.0,
    web_thickness_mm=8.0,
    flange_width_mm=300.0,
    flange_thickness_mm=16.0,
    weld_size_mm=10.0,
)
WORKED_EXAMPLE_GEOMETRY = SteelMemberGeometry(
    member_type="gantry_post",
    cantilever_length_mm=6000.0,
    web_depth_mm=500.0,
    web_thickness_mm=8.0,
    flange_width_mm=300.0,
    flange_thickness_mm=16.0,
    overall_depth_mm=532.0,
    weld_size_mm=10.0,
)

# Independently hand-re-derived expected values.
EXPECTED_INERTIA_XX_MM4 = 7.2256e8
EXPECTED_SECTION_MODULUS_CM3 = 2716.0
EXPECTED_RADIUS_OF_GYRATION_MM = 72.77
EXPECTED_SLENDERNESS = 164.9
EXPECTED_DESIGN_MOMENT_KNM = 139.2
EXPECTED_MAX_BENDING_STRESS_MPA = 51.3
EXPECTED_MAX_AXIAL_STRESS_MPA = 7.35
EXPECTED_MAX_SHEAR_STRESS_MPA = 6.60
EXPECTED_PERMISSIBLE_AXIAL_MPA = 38.8  # Merchant-Rankine
EXPECTED_SIGMA_AC_TABLE_MPA = 39.0  # transcribed table (needs_verification)
EXPECTED_COMBINED_RATIO = 0.50
EXPECTED_WELD_STRESS_MPA = 91.6
EXPECTED_REQUIRED_MODULUS_CM3 = 844.0  # M / sigma_bc


@pytest.fixture(scope="module")
def analysis():
    return analyse_member(WORKED_EXAMPLE_PARAMS, WORKED_EXAMPLE_GEOMETRY)


def test_second_moment_of_area_within_5pct(analysis):
    assert analysis.inertia_xx_mm4 == pytest.approx(EXPECTED_INERTIA_XX_MM4, rel=SSM_TOL)


def test_section_modulus_within_5pct(analysis):
    assert analysis.section_modulus_cm3 == pytest.approx(EXPECTED_SECTION_MODULUS_CM3, rel=SSM_TOL)


def test_radius_of_gyration_and_slenderness_within_5pct(analysis):
    assert analysis.radius_of_gyration_min_mm == pytest.approx(EXPECTED_RADIUS_OF_GYRATION_MM, rel=SSM_TOL)
    assert analysis.slenderness_ratio == pytest.approx(EXPECTED_SLENDERNESS, rel=SSM_TOL)


def test_design_moment_within_5pct(analysis):
    assert analysis.design_moment_knm == pytest.approx(EXPECTED_DESIGN_MOMENT_KNM, rel=SSM_TOL)


def test_section_stresses_within_5pct(analysis):
    assert analysis.max_bending_stress_mpa == pytest.approx(EXPECTED_MAX_BENDING_STRESS_MPA, rel=SSM_TOL)
    assert analysis.max_axial_stress_mpa == pytest.approx(EXPECTED_MAX_AXIAL_STRESS_MPA, rel=SSM_TOL)
    assert analysis.max_shear_stress_mpa == pytest.approx(EXPECTED_MAX_SHEAR_STRESS_MPA, rel=SSM_TOL)


def test_permissible_axial_stress_within_5pct_and_table_within_10pct(analysis):
    assert analysis.permissible_axial_stress_mpa == pytest.approx(EXPECTED_PERMISSIBLE_AXIAL_MPA, rel=SSM_TOL)
    # The transcribed fy=250 sigma_ac table row (needs_verification) — looser +/-10 %.
    assert analysis.sigma_ac_table_mpa == pytest.approx(EXPECTED_SIGMA_AC_TABLE_MPA, rel=TABLE_TOL)


def test_combined_interaction_within_5pct(analysis):
    assert analysis.combined_ratio == pytest.approx(EXPECTED_COMBINED_RATIO, rel=SSM_TOL)


def test_fillet_weld_resultant_stress_within_5pct(analysis):
    assert analysis.weld_stress_mpa == pytest.approx(EXPECTED_WELD_STRESS_MPA, rel=SSM_TOL)


def test_required_section_modulus_within_5pct(analysis):
    # Governing quantity: the section modulus the design moment demands at the
    # permissible bending stress (independent of the provided section).
    z_req_cm3 = analysis.design_moment_knm * 1e6 / analysis.permissible_bending_stress_mpa / 1000.0
    assert z_req_cm3 == pytest.approx(EXPECTED_REQUIRED_MODULUS_CM3, rel=SSM_TOL)
    # And the provided section modulus exceeds it — the section is adequate.
    assert analysis.section_modulus_cm3 > z_req_cm3
