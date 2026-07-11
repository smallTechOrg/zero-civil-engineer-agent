"""Fixture — transmission-shaft governing quantities vs an independent hand
calculation (+/-5%), including a factor-of-safety FAIL case.

SOURCE (named per the fixture contract): the classical transmission-shaft
worked-example method reproduced across the standard machine-design texts —
Shigley "Mechanical Engineering Design"; Bhandari "Design of Machine Elements";
the PSG / "Design Data Book" combined-stress (ASME maximum-shear-stress) shaft
equations. The material strengths (40C8: fy 330, fu 600 N/mm^2) are transcribed
from the Design Data Book steel tables (flagged `needs_verification` — see the
module docstring; verify against the source before demo day).

TRANSCRIPTION HONESTY: the expected values below were INDEPENDENTLY RE-DERIVED by
hand from the closed-form formulae in this file's comments. They are checked
within +/-5%.

Stated shaft (a transmission shaft with an overhung belt pulley):
  P = 20 kW at N = 1000 rpm ; mounted pulley PCD = 200 mm ; overhang = 150 mm ;
  combined-shock factors Cm = 1.5, Ct = 1.0 ; material 40C8 (fy = 330 N/mm^2) ;
  diameter d = 50 mm (stated) ; design factor of safety = 2.0.

Hand derivation:
  Torque  T = 9550 * P / N = 9550 * 20 / 1000 = 191.0 N.m = 190,986 N.mm.
  Tangential force at the pulley  F_t = T / (PCD/2) = 190986 / 100 = 1909.9 N.
  Net transverse (belt) load  W = 2 * F_t = 3819.7 N   (belt tension-ratio factor 2).
  Overhung bending moment  M = W * overhang = 3819.7 * 150 = 572,958 N.mm.
  Equivalent twisting moment (maximum-shear-stress theory):
    Te = sqrt((Cm*M)^2 + (Ct*T)^2)
       = sqrt((1.5*572958)^2 + (1.0*190986)^2)
       = sqrt(859437^2 + 190986^2) = sqrt(7.386e11 + 3.648e10) = 880,388 N.mm.
  Maximum shear stress  tau = 16 Te / (pi d^3) = 16*880388 / (pi*50^3)
       = 14,086,208 / 392,699 = 35.87 N/mm^2.
  Shear yield  tau_y = 0.5 * fy = 165 N/mm^2.
  Static factor of safety  FoS = tau_y / tau = 165 / 35.87 = 4.60.
  Required diameter for combined stress at FoS 2 (tau_perm = 165/2 = 82.5):
    d_req = (16 Te / (pi tau_perm))^(1/3) = (14,086,208 / 259.18)^(1/3)
          = 37.87 mm  (provided 50 mm > required -> adequate in combined stress).

FAIL case — the SAME shaft forced to d = 25 mm:
  tau = 16*880388 / (pi*25^3) = 14,086,208 / 49,087 = 286.96 N/mm^2.
  FoS = 165 / 286.96 = 0.575 < 2.0  ->  factor-of-safety FAIL (under-design).

Tolerance: +/-5 %.
"""

import pytest

from components.machine_element.analysis import analyse_element
from components.machine_element.sizing import size_element
from components.machine_element.params import MachineElementParams

ME_TOL = 0.05  # +/-5 %

WORKED_PARAMS = MachineElementParams(
    power_kw=20.0, speed_rpm=1000.0, mounting_pcd_mm=200.0, overhang_mm=150.0,
    bending_shock_factor=1.5, torsion_shock_factor=1.0, material_grade="40C8",
    required_factor_of_safety=2.0, diameter_mm=50.0,
)
FAIL_PARAMS = WORKED_PARAMS.model_copy(update={"diameter_mm": 25.0})

# Independently hand-re-derived expected values.
EXPECTED_TORQUE_NMM = 190_986.0
EXPECTED_BENDING_MOMENT_NMM = 572_958.0
EXPECTED_EQUIV_TWISTING_NMM = 880_388.0
EXPECTED_MAX_STRESS_MPA = 35.87
EXPECTED_FACTOR_OF_SAFETY = 4.60
EXPECTED_REQUIRED_DIAMETER_MM = 37.87
EXPECTED_FAIL_STRESS_MPA = 286.96
EXPECTED_FAIL_FACTOR_OF_SAFETY = 0.575


@pytest.fixture(scope="module")
def analysis():
    return analyse_element(WORKED_PARAMS, size_element(WORKED_PARAMS).geometry)


def test_torque_within_5pct(analysis):
    assert analysis.torque_nmm == pytest.approx(EXPECTED_TORQUE_NMM, rel=ME_TOL)


def test_overhung_bending_moment_within_5pct(analysis):
    assert analysis.bending_moment_nmm == pytest.approx(EXPECTED_BENDING_MOMENT_NMM, rel=ME_TOL)


def test_equivalent_twisting_moment_within_5pct(analysis):
    assert analysis.equiv_twisting_moment_nmm == pytest.approx(EXPECTED_EQUIV_TWISTING_NMM, rel=ME_TOL)


def test_max_shear_stress_within_5pct(analysis):
    assert analysis.max_stress_mpa == pytest.approx(EXPECTED_MAX_STRESS_MPA, rel=ME_TOL)


def test_static_factor_of_safety_within_5pct(analysis):
    assert analysis.factor_of_safety == pytest.approx(EXPECTED_FACTOR_OF_SAFETY, rel=ME_TOL)


def test_required_diameter_for_combined_stress_within_5pct(analysis):
    # Governing quantity: the diameter the equivalent twisting moment demands at
    # the permissible shear stress (independent of the provided diameter).
    import math

    d_req = (16.0 * analysis.equiv_twisting_moment_nmm / (math.pi * analysis.permissible_stress_mpa)) ** (1.0 / 3.0)
    assert d_req == pytest.approx(EXPECTED_REQUIRED_DIAMETER_MM, rel=ME_TOL)
    # And the provided diameter exceeds it — the section is adequate in combined stress.
    assert WORKED_PARAMS.diameter_mm > d_req
    assert analysis.factor_of_safety >= analysis.required_fos


def test_under_design_diameter_fails_the_factor_of_safety():
    a = analyse_element(FAIL_PARAMS, size_element(FAIL_PARAMS).geometry)
    assert a.max_stress_mpa == pytest.approx(EXPECTED_FAIL_STRESS_MPA, rel=ME_TOL)
    assert a.factor_of_safety == pytest.approx(EXPECTED_FAIL_FACTOR_OF_SAFETY, rel=ME_TOL)
    # The factor of safety has dropped below the required value — a FAIL.
    assert a.factor_of_safety < a.required_fos
    assert a.max_stress_mpa > a.permissible_stress_mpa
