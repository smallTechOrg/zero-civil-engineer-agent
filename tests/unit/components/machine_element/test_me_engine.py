"""Machine-element engine — sizing, analysis, checks (incl. under-design cases)."""

import pytest

from components.machine_element.analysis import analyse_element, compute_core
from components.machine_element.checks import run_element_checks
from components.machine_element.params import MachineElementParams
from components.machine_element.sizing import size_element

AUTO = MachineElementParams(power_kw=20.0, speed_rpm=1000.0)
WELD = MachineElementParams(
    power_kw=100.0, speed_rpm=100.0, element_kind="welded_joint", hub_diameter_mm=120.0
)


def test_auto_sized_shaft_passes_all_checks():
    result = size_element(AUTO)
    g = result.geometry
    assert g.element_kind == "shaft"
    assert g.diameter_mm > g.step_diameter_mm > 0
    assert g.length_mm > 2 * g.step_length_mm
    assert g.keyway_width_mm > 0  # has_keyway default True

    analysis = analyse_element(AUTO, g)
    checks = run_element_checks(analysis, g, AUTO)
    assert all(c.status == "PASS" for c in checks.checks), [
        (c.kind, c.status) for c in checks.checks
    ]
    assert result.assumptions
    assert all(a.source == "engine_default" for a in result.assumptions)


def test_shaft_check_kinds_and_factors_of_safety():
    g = size_element(AUTO).geometry
    analysis = analyse_element(AUTO, g)
    checks = run_element_checks(analysis, g, AUTO)
    kinds = {c.kind for c in checks.checks}
    assert kinds == {"combined_stress", "fatigue", "stress_concentration"}
    assert analysis.max_stress_mpa <= analysis.permissible_stress_mpa
    assert analysis.factor_of_safety >= analysis.required_fos
    assert analysis.fatigue_applicable
    assert analysis.fatigue_fos >= analysis.required_fatigue_fos


def test_torque_from_power_and_speed():
    g = size_element(AUTO).geometry
    core = compute_core(AUTO, g)
    # T[N.m] = 9550 * P / N ; core.torque_nmm is in N.mm.
    expected_nmm = 9549.2965 * AUTO.power_kw / AUTO.speed_rpm * 1000.0
    assert core.torque_nmm == pytest.approx(expected_nmm, rel=1e-3)
    assert core.equiv_twisting_moment_nmm >= core.torque_nmm  # combined >= pure torsion


def test_higher_power_needs_a_bigger_shaft():
    small = size_element(MachineElementParams(power_kw=5.0, speed_rpm=1000.0)).geometry
    large = size_element(MachineElementParams(power_kw=200.0, speed_rpm=1000.0)).geometry
    assert large.diameter_mm > small.diameter_mm


def test_en24_permits_higher_stress_than_40c8():
    g = size_element(AUTO).geometry
    a_40c8 = analyse_element(MachineElementParams(power_kw=20.0, speed_rpm=1000.0, material_grade="40C8"), g)
    a_en24 = analyse_element(MachineElementParams(power_kw=20.0, speed_rpm=1000.0, material_grade="EN24"), g)
    assert a_en24.shear_yield_mpa > a_40c8.shear_yield_mpa
    assert a_en24.permissible_stress_mpa > a_40c8.permissible_stress_mpa


def test_thin_diameter_override_fails_combined_stress_the_under_design_case():
    under = MachineElementParams(power_kw=20.0, speed_rpm=1000.0, diameter_mm=25.0)
    result = size_element(under)
    g = result.geometry
    analysis = analyse_element(under, g)
    checks = run_element_checks(analysis, g, under)
    combined = next(c for c in checks.checks if c.kind == "combined_stress")
    assert combined.status == "FAIL"
    assert analysis.max_stress_mpa > analysis.permissible_stress_mpa
    assert analysis.factor_of_safety < analysis.required_fos
    assert any("under-design" in w.lower() or "smaller" in w.lower() for w in result.warnings)


def test_welded_joint_auto_passes_and_has_weld_kinds():
    result = size_element(WELD)
    g = result.geometry
    assert g.element_kind == "welded_joint"
    assert g.weld_size_mm > 0 and g.weld_throat_mm == pytest.approx(0.707 * g.weld_size_mm, rel=1e-3)
    analysis = analyse_element(WELD, g)
    checks = run_element_checks(analysis, g, WELD)
    kinds = {c.kind for c in checks.checks}
    assert kinds == {"weld_shear", "weld_detail"}
    weld_shear = next(c for c in checks.checks if c.kind == "weld_shear")
    assert weld_shear.status == "PASS"
    assert analysis.max_stress_mpa <= analysis.permissible_stress_mpa


def test_thin_weld_override_fails_weld_shear():
    under = MachineElementParams(
        power_kw=100.0, speed_rpm=100.0, element_kind="welded_joint",
        hub_diameter_mm=120.0, weld_size_mm=3.0,
    )
    result = size_element(under)
    g = result.geometry
    analysis = analyse_element(under, g)
    checks = run_element_checks(analysis, g, under)
    weld_shear = next(c for c in checks.checks if c.kind == "weld_shear")
    assert weld_shear.status == "FAIL"
    assert analysis.factor_of_safety < analysis.required_fos
    assert any("under-design" in w.lower() or "smaller" in w.lower() for w in result.warnings)


def test_every_check_trail_ref_resolves_within_the_check_trail():
    g = size_element(AUTO).geometry
    analysis = analyse_element(AUTO, g)
    checks = run_element_checks(analysis, g, AUTO)
    trail_ids = {s.step_id for s in checks.trail}
    for c in checks.checks:
        assert c.trail_ref in trail_ids
        assert c.trail_ref.startswith("K")


def test_trail_prefixes_are_segmented():
    result = size_element(AUTO)
    analysis = analyse_element(AUTO, result.geometry)
    checks = run_element_checks(analysis, result.geometry, AUTO)
    assert all(s.step_id.startswith("S") for s in result.trail)
    assert all(s.step_id.startswith("A") for s in analysis.trail)
    assert all(s.step_id.startswith("K") for s in checks.trail)
