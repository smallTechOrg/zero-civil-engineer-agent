"""Fixture — welded steel plate-girder governing quantities vs an independent
hand calculation (+/-5%).

SOURCE (named per the fixture contract): the classical welded plate-girder
worked-example method reproduced across the standard steel-design texts —
Punmia/Jain "Design of Steel Structures"; Duggal "Limit State Design of Steel
Structures" (working-stress plate-girder chapter); and the standard elastic
section-property formulae for a doubly-symmetric welded I. The 25t Loading-2008
EUDL(BM) and CDA values are read from the transcribed IR Bridge Rules appendix
in `engine.loading.t25_2008` (themselves flagged `needs_verification` — see the
module docstring; verify against the source PDF before demo day).

TRANSCRIPTION HONESTY: the expected values below were INDEPENDENTLY RE-DERIVED by
hand from the closed-form formulae in this file's comments. They are checked
within +/-5%.

Stated section (all mm, per one of two girders sharing a single BG track):
  effective span L = 24.0 m ; web 2000 x 12 ; flanges 500 x 40 ;
  overall depth D = 2000 + 2 x 40 = 2080 ; number of girders n = 2 ; E250 steel.

Hand derivation:
  Cross-section area A = t_w*d_w + 2*b_f*t_f
    = 12*2000 + 2*500*40 = 24000 + 40000 = 64000 mm^2 = 0.064 m^2.
  Second moment of area (strong axis):
    I = t_w*d_w^3/12 + 2*[b_f*t_f^3/12 + b_f*t_f*((d_w+t_f)/2)^2]
      = 12*2000^3/12 + 2*[500*40^3/12 + 500*40*(1020)^2]
      = 8.000e9 + 2*[2.667e6 + 2.0808e10] = 8.000e9 + 4.1621e10 = 4.9621e10 mm^4.
  Elastic section modulus Z = I/(D/2) = 4.9621e10 / 1040 = 4.771e7 mm^3 = 47713 cm^3.

  Dead load (per girder):
    self-weight w_sw = A * gamma_steel = 0.064 * 78.5 = 5.024 kN/m
    deck/track allowance = 30.0 / 2 = 15.0 kN/m ; w_dl = 20.024 kN/m
    M_dl = w_dl*L^2/8 = 20.024*24^2/8 = 1441.7 kN*m
  Live load (25t-2008, loaded length = span = 24 m):
    EUDL(BM) = 2230.2 kN (table row at 24 m) ; CDA = 0.15 + 8/(6+24) = 0.41667
    M_ll = EUDL(BM)*(1+CDA)*L/8/n = 2230.2*1.41667*24/8/2 = 4739.2 kN*m
  Design moment M = M_dl + M_ll = 6180.9 kN*m
  Extreme-fibre bending stress sigma_b = M/Z = 6180.9e6 / 4.771e7 = 129.5 N/mm^2
  Required section modulus at the permissible bending stress (E250, 165 N/mm^2):
    Z_req = M/sigma_perm = 6180.9e6 / 165 = 3.746e7 mm^3 = 37460 cm^3
    (provided 47713 cm^3 > required -> the section is adequate in bending).

Tolerance: +/-5 %.
"""

import pytest

from components.plate_girder.analysis import analyse_girder
from components.plate_girder.params import PlateGirderGeometry, PlateGirderParams

PG_TOL = 0.05  # +/-5 %

WORKED_EXAMPLE_PARAMS = PlateGirderParams(
    span_m=24.0,
    number_of_girders=2,
    steel_grade="E250",
    web_depth_mm=2000.0,
    web_thickness_mm=12.0,
    flange_width_mm=500.0,
    flange_thickness_mm=40.0,
)
WORKED_EXAMPLE_GEOMETRY = PlateGirderGeometry(
    span_mm=24000.0,
    web_depth_mm=2000.0,
    web_thickness_mm=12.0,
    flange_width_mm=500.0,
    flange_thickness_mm=40.0,
    overall_depth_mm=2080.0,
    number_of_girders=2,
    girder_spacing_mm=1800.0,
    stiffener_spacing_mm=2000.0,
)

# Independently hand-re-derived expected values.
EXPECTED_INERTIA_MM4 = 4.9621e10
EXPECTED_SECTION_MODULUS_CM3 = 47713.0
EXPECTED_DESIGN_MOMENT_KNM = 6180.9
EXPECTED_MAX_BENDING_STRESS_MPA = 129.5
EXPECTED_REQUIRED_MODULUS_CM3 = 37460.0  # M / sigma_perm


@pytest.fixture(scope="module")
def analysis():
    return analyse_girder(WORKED_EXAMPLE_PARAMS, WORKED_EXAMPLE_GEOMETRY)


def test_second_moment_of_area_within_5pct(analysis):
    assert analysis.inertia_mm4 == pytest.approx(EXPECTED_INERTIA_MM4, rel=PG_TOL)


def test_section_modulus_within_5pct(analysis):
    assert analysis.section_modulus_cm3 == pytest.approx(EXPECTED_SECTION_MODULUS_CM3, rel=PG_TOL)


def test_design_moment_within_5pct(analysis):
    assert analysis.design_moment_knm == pytest.approx(EXPECTED_DESIGN_MOMENT_KNM, rel=PG_TOL)


def test_max_bending_stress_within_5pct(analysis):
    assert analysis.max_bending_stress_mpa == pytest.approx(EXPECTED_MAX_BENDING_STRESS_MPA, rel=PG_TOL)


def test_required_section_modulus_within_5pct(analysis):
    # Governing quantity: the section modulus the design moment demands at the
    # permissible bending stress (independent of the provided section).
    z_req_cm3 = analysis.design_moment_knm * 1e6 / analysis.permissible_bending_stress_mpa / 1000.0
    assert z_req_cm3 == pytest.approx(EXPECTED_REQUIRED_MODULUS_CM3, rel=PG_TOL)
    # And the provided section modulus exceeds it — the section is adequate.
    assert analysis.section_modulus_cm3 > z_req_cm3
