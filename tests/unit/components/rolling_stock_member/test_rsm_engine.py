"""Rolling-stock member engine — sizing convergence, RDSO load cases, checks."""

import pytest

from components.rolling_stock_member._engine_common import (
    VERTICAL_IMPACT_FACTOR,
    section_properties,
)
from components.rolling_stock_member.analysis import (
    GOVERNING_BUFFING,
    GOVERNING_VERTICAL,
    analyse_member,
    compute_forces,
)
from components.rolling_stock_member.checks import run_member_checks
from components.rolling_stock_member.params import RollingStockMemberParams
from components.rolling_stock_member.sizing import size_member

AUTO = RollingStockMemberParams(member_length_m=6.0)


def test_auto_sized_member_passes_all_checks():
    result = size_member(AUTO)
    g = result.geometry
    # Web depth in the member-length proportion band (bounded 250-1000 mm).
    assert 250.0 <= g.web_depth_mm <= 1000.0
    assert g.overall_depth_mm == pytest.approx(g.web_depth_mm + 2 * g.flange_thickness_mm)
    assert g.weld_size_mm >= 6.0

    analysis = analyse_member(AUTO, g)
    checks = run_member_checks(analysis, g, AUTO)
    assert all(c.status == "PASS" for c in checks.checks), [
        (c.kind, c.status) for c in checks.checks
    ]
    # Every sizing/analysis assumption is engine-sourced and provenanced.
    assert result.assumptions
    assert all(a.source == "engine_default" for a in result.assumptions)


def test_kinds_present_and_stresses_are_within_permissible():
    g = size_member(AUTO).geometry
    analysis = analyse_member(AUTO, g)
    checks = run_member_checks(analysis, g, AUTO)
    kinds = {c.kind for c in checks.checks}
    assert kinds == {"bending", "shear", "axial", "combined", "weld_fatigue"}
    assert analysis.max_bending_stress_mpa <= analysis.permissible_bending_stress_mpa
    assert analysis.max_shear_stress_mpa <= analysis.permissible_shear_stress_mpa
    assert analysis.max_axial_stress_mpa <= analysis.permissible_axial_stress_mpa
    assert analysis.interaction_ratio <= analysis.interaction_limit


def test_section_properties_match_the_recorded_analysis():
    g = size_member(AUTO).geometry
    analysis = analyse_member(AUTO, g)
    section = section_properties(
        web_depth_mm=g.web_depth_mm, web_thickness_mm=g.web_thickness_mm,
        flange_width_mm=g.flange_width_mm, flange_thickness_mm=g.flange_thickness_mm,
    )
    assert analysis.section_modulus_cm3 == pytest.approx(section.section_modulus_mm3 / 1000.0, rel=1e-6)
    assert analysis.inertia_mm4 == pytest.approx(section.inertia_mm4, rel=1e-6)


def test_vertical_case_uses_the_rdso_impact_factor():
    g = size_member(AUTO).geometry
    core = compute_forces(AUTO, g)
    assert core.impact_factor == pytest.approx(VERTICAL_IMPACT_FACTOR)
    # Design moment = self-weight dead moment + payload live+impact moment.
    assert core.design_moment_knm == pytest.approx(core.dead_moment_knm + core.live_moment_knm)
    assert core.design_shear_kn == pytest.approx(core.dead_shear_kn + core.live_shear_kn)


def test_buffing_case_sets_the_axial_stress():
    g = size_member(AUTO).geometry
    core = compute_forces(AUTO, g)
    # Axial stress is the buffing load over the gross area.
    assert core.max_axial_stress_mpa == pytest.approx(
        core.buffing_load_kn * 1e3 / core.section_area_mm2
    )
    # Interaction is the sum of the axial and bending utilisations.
    assert core.interaction_ratio == pytest.approx(
        core.max_axial_stress_mpa / core.permissible_axial_stress_mpa
        + core.max_bending_stress_mpa / core.permissible_bending_stress_mpa
    )


def test_governing_load_case_reflects_the_dominant_case():
    # Default (moderate buffing) -> vertical payload governs.
    a_v = analyse_member(AUTO, size_member(AUTO).geometry)
    assert a_v.governing_load_case == GOVERNING_VERTICAL
    # Tiny vertical, heavy buffing -> the longitudinal buffing case governs.
    heavy = RollingStockMemberParams(
        member_length_m=8.0, design_vertical_load_kn=10.0, design_buffing_load_kn=2500.0
    )
    a_b = analyse_member(heavy, size_member(heavy).geometry)
    assert a_b.governing_load_case == GOVERNING_BUFFING


def test_longer_member_needs_a_deeper_section():
    short = size_member(RollingStockMemberParams(member_length_m=3.0)).geometry
    long = size_member(RollingStockMemberParams(member_length_m=12.0)).geometry
    assert long.web_depth_mm > short.web_depth_mm
    assert long.overall_depth_mm > short.overall_depth_mm


def test_e350_permits_higher_stresses_than_e250():
    g = size_member(AUTO).geometry
    a250 = analyse_member(RollingStockMemberParams(member_length_m=6.0, steel_grade="E250"), g)
    a350 = analyse_member(RollingStockMemberParams(member_length_m=6.0, steel_grade="E350"), g)
    assert a350.permissible_bending_stress_mpa > a250.permissible_bending_stress_mpa
    assert a350.permissible_shear_stress_mpa > a250.permissible_shear_stress_mpa
    assert a350.permissible_axial_stress_mpa > a250.permissible_axial_stress_mpa


def test_thin_flange_override_fails_bending_the_under_design_case():
    """A deliberately thin/narrow flange -> the section modulus is too small ->
    the bending (and combined) check FAILs (the under-design demo case)."""
    under = RollingStockMemberParams(
        member_length_m=3.0, flange_thickness_mm=8.0, flange_width_mm=100.0,
        design_buffing_load_kn=1500.0,
    )
    result = size_member(under)
    g = result.geometry
    analysis = analyse_member(under, g)
    checks = run_member_checks(analysis, g, under)
    bending = next(c for c in checks.checks if c.kind == "bending")
    assert bending.status == "FAIL"
    assert analysis.max_bending_stress_mpa > analysis.permissible_bending_stress_mpa
    # The override is flagged as a possible under-design in the warnings.
    assert any("under-design" in w.lower() or "thinner" in w.lower() for w in result.warnings)


def test_every_check_trail_ref_resolves_within_the_check_trail():
    g = size_member(AUTO).geometry
    analysis = analyse_member(AUTO, g)
    checks = run_member_checks(analysis, g, AUTO)
    trail_ids = {s.step_id for s in checks.trail}
    for c in checks.checks:
        assert c.trail_ref in trail_ids
        assert c.trail_ref.startswith("K")


def test_trail_prefixes_are_segmented():
    result = size_member(AUTO)
    analysis = analyse_member(AUTO, result.geometry)
    checks = run_member_checks(analysis, result.geometry, AUTO)
    assert all(s.step_id.startswith("S") for s in result.trail)
    assert all(s.step_id.startswith("A") for s in analysis.trail)
    assert all(s.step_id.startswith("K") for s in checks.trail)
