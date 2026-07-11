"""Fixture — an independently hand-computed pier substructure (+/-10%).

SOURCE (named per the fixture contract): a first-principles closed-form gravity
substructure stability calculation, of the kind reproduced in the standard
railway bridge-substructure design texts (Victor, "Essentials of Bridge
Engineering"; Johnson Victor / IRICEN substructure design notes) and the IRS
Bridge Substructure & Foundation Code worked practice — a pier on a symmetric
spread footing, all vertical loads on the pier centre-line, overturned by the
longitudinal (braking) force about the toe edge, base pressure by p = W/A(1 +/- 6e/B).

TRANSCRIPTION HONESTY (same discipline as the retaining-wall fixture): the
expected values below were INDEPENDENTLY RE-DERIVED BY HAND from the closed-form
formulae in this file's comments. The longitudinal-force fraction (0.15 of the
reaction) and the permissible direct compressive stress are transcribed POC
constants flagged `needs_verification` in the engine — verify them against the
source codes before demo day.

Pier (chosen so the design is sound — all dimensions in metres):
  total height H = 8.0 (founding to bearing), footing B x L x Df = 6.0 x 6.0 x 1.0,
  cap 2.0 x 2.0 x 1.0, pier 1.5 x 1.5, pier shaft height = 8.0 - 1.0 - 1.0 = 6.0.
  gamma_concrete = 25 kN/m^3, mu = 0.5, M30 concrete (sigma_cc = 8.0 N/mm^2).
  Superstructure reaction W_super = 4000 kN. Longitudinal force F = 0.15 * 4000 = 600 kN
  at bearing level (height 8.0 m).

Hand derivation (all vertical loads act at x = B/2 = 3.0 m):
  Weights:
    footing  : 6.0*6.0*1.0*25 = 900.0 kN
    pier/stem: 1.5*1.5*6.0*25 = 337.5 kN
    cap      : 2.0*2.0*1.0*25 = 100.0 kN
    reaction : 4000.0 kN
    SUM W = 5337.5 kN ; Mr = W * 3.0 = 16012.5 kN*m
  Overturning: Mo = F * H = 600 * 8.0 = 4800.0 kN*m
  FoS overturning = 16012.5 / 4800.0                         = 3.336
  Resultant: x_res = (Mr - Mo)/W = 11212.5/5337.5 = 2.1006 m ; e = 3.0 - 2.1006 = 0.8994 m
  Base pressure (A = 36 m^2): p_max = (5337.5/36)*(1 + 6*0.8994/6) = 148.26*1.8994 = 281.6 kN/m^2
  Pier direct stress: axial at pier base = 4000 + 337.5 + 100 = 4437.5 kN over
    1.5*1.5 = 2.25 m^2 = 2.25e6 mm^2 -> 4437.5e3/2.25e6                = 1.972 N/mm^2

Tolerance: +/-10 % per the fixture contract (breadth-first closed-form model).
"""

import pytest

from components.pier_abutment.analysis import analyse_substructure
from components.pier_abutment.params import PierAbutmentGeometry, PierAbutmentParams

PA_TOL = 0.10  # +/-10 %

WORKED_EXAMPLE_PARAMS = PierAbutmentParams(
    pier_height_m=8.0,
    superstructure_reaction_kn=4000.0,
    safe_bearing_capacity_kn_m2=300.0,
    component_kind="pier",
    base_friction_coeff=0.5,
    concrete_grade="M30",
    steel_grade="Fe500",
)
WORKED_EXAMPLE_GEOMETRY = PierAbutmentGeometry(
    total_height_mm=8000.0,
    component_kind="pier",
    pier_width_mm=1500.0,
    pier_length_mm=1500.0,
    cap_thickness_mm=1000.0,
    cap_width_mm=2000.0,
    cap_length_mm=2000.0,
    footing_length_mm=6000.0,
    footing_width_mm=6000.0,
    footing_thickness_mm=1000.0,
)

# Independently hand-re-derived expected values (see the module docstring).
EXPECTED_TOTAL_VERTICAL_KN = 5337.5
EXPECTED_FOS_OVERTURNING = 3.336
EXPECTED_MAX_BEARING = 281.6  # kN/m^2
EXPECTED_PIER_DIRECT_STRESS = 1.972  # N/mm^2


@pytest.fixture(scope="module")
def analysis():
    return analyse_substructure(WORKED_EXAMPLE_PARAMS, WORKED_EXAMPLE_GEOMETRY)


def test_total_vertical_load_within_tol(analysis):
    assert analysis.total_vertical_kn == pytest.approx(EXPECTED_TOTAL_VERTICAL_KN, rel=PA_TOL)


def test_fos_overturning_within_tol(analysis):
    assert analysis.fos_overturning == pytest.approx(EXPECTED_FOS_OVERTURNING, rel=PA_TOL)


def test_max_base_pressure_within_tol(analysis):
    # The governing foundation quantity — max base pressure under the toe.
    assert analysis.max_base_pressure_kn_m2 == pytest.approx(EXPECTED_MAX_BEARING, rel=PA_TOL)


def test_pier_direct_stress_within_tol(analysis):
    assert analysis.pier_direct_stress_n_mm2 == pytest.approx(EXPECTED_PIER_DIRECT_STRESS, rel=PA_TOL)


def test_permissible_direct_stress_is_flagged_for_verification():
    # Honesty: the permissible sigma_cc is a transcribed POC constant (M30 -> 8.0),
    # to be verified digit-for-digit against the source code before demo day.
    from components.pier_abutment._engine_common import CONCRETE_PERMISSIBLE
    from domain.culvert import ConcreteGrade

    row = CONCRETE_PERMISSIBLE[ConcreteGrade.M30]
    assert row.sigma_cc_n_mm2 == 8.0
    assert row.needs_verification is True
