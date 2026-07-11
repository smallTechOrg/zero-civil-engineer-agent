"""Steel-member engine — sizing convergence, analysis, checks (incl. under-design)."""

import pytest

from components.structural_steel_member._engine_common import (
    permissible_axial_stress,
    section_properties,
    sigma_ac_table_value,
)
from components.structural_steel_member.analysis import analyse_member, compute_forces
from components.structural_steel_member.checks import run_member_checks
from components.structural_steel_member.params import SteelMemberParams
from components.structural_steel_member.sizing import size_member

AUTO = SteelMemberParams(cantilever_length_m=6.0, transverse_load_kn=20.0)

# Under-design demo cases (verified by the scratch probe).
UNDER_BENDING = SteelMemberParams(
    cantilever_length_m=2.0, transverse_load_kn=120.0,
    web_depth_mm=250.0, flange_thickness_mm=8.0, flange_width_mm=180.0,
)
UNDER_WELD = SteelMemberParams(cantilever_length_m=2.0, transverse_load_kn=120.0, weld_size_mm=5.0)
SLENDER = SteelMemberParams(cantilever_length_m=11.0, transverse_load_kn=25.0, member_type="ohe_mast")


def test_auto_sized_member_passes_all_checks_and_is_provenanced():
    result = size_member(AUTO)
    g = result.geometry
    assert g.overall_depth_mm == pytest.approx(g.web_depth_mm + 2 * g.flange_thickness_mm)
    assert g.overall_depth_mm < g.cantilever_length_mm  # slender cantilever
    assert g.weld_size_mm > 0

    analysis = analyse_member(AUTO, g)
    checks = run_member_checks(analysis, g, AUTO)
    assert all(c.status == "PASS" for c in checks.checks), [
        (c.kind, c.status) for c in checks.checks
    ]
    # Every sizing assumption is engine-sourced and provenanced.
    assert result.assumptions
    assert all(a.source == "engine_default" for a in result.assumptions)


def test_all_check_kinds_present_and_stresses_within_permissible():
    g = size_member(AUTO).geometry
    analysis = analyse_member(AUTO, g)
    checks = run_member_checks(analysis, g, AUTO)
    kinds = {c.kind for c in checks.checks}
    assert kinds == {"axial", "bending", "shear", "combined", "weld", "slenderness"}
    assert analysis.max_axial_stress_mpa <= analysis.permissible_axial_stress_mpa
    assert analysis.max_bending_stress_mpa <= analysis.permissible_bending_stress_mpa
    assert analysis.max_shear_stress_mpa <= analysis.permissible_shear_stress_mpa
    assert analysis.weld_stress_mpa <= analysis.permissible_weld_stress_mpa
    assert analysis.combined_ratio <= analysis.combined_limit


def test_section_properties_match_the_recorded_analysis():
    g = size_member(AUTO).geometry
    analysis = analyse_member(AUTO, g)
    section = section_properties(
        web_depth_mm=g.web_depth_mm, web_thickness_mm=g.web_thickness_mm,
        flange_width_mm=g.flange_width_mm, flange_thickness_mm=g.flange_thickness_mm,
    )
    assert analysis.section_modulus_cm3 == pytest.approx(section.section_modulus_mm3 / 1000.0, rel=1e-6)
    assert analysis.inertia_xx_mm4 == pytest.approx(section.inertia_xx_mm4, rel=1e-6)
    assert analysis.radius_of_gyration_min_mm == pytest.approx(section.radius_of_gyration_min_mm, rel=1e-6)


def test_permissible_axial_uses_merchant_rankine_and_cross_checks_the_table():
    g = size_member(AUTO).geometry
    analysis = analyse_member(AUTO, g)
    # The recorded permissible axial stress equals the Merchant-Rankine formula.
    formula = permissible_axial_stress(250.0, analysis.slenderness_ratio)
    assert analysis.permissible_axial_stress_mpa == pytest.approx(formula, rel=1e-4)
    # The transcribed fy=250 sigma_ac table cross-checks the formula within +/-10%.
    table = sigma_ac_table_value(analysis.slenderness_ratio)
    assert table == pytest.approx(formula, rel=0.10)
    assert analysis.sigma_ac_table_mpa == pytest.approx(table, rel=1e-6)


def test_actions_include_self_weight_and_axial():
    g = size_member(AUTO).geometry
    core = compute_forces(AUTO, g)
    # Moment = P*L + self-weight moment; shear = P + self-weight shear.
    assert core.self_weight_kn_m > 0
    assert core.design_moment_knm > AUTO.transverse_load_kn * AUTO.cantilever_length_m
    assert core.design_axial_kn == pytest.approx(AUTO.axial_load_kn)
    assert core.max_axial_stress_mpa > 0


def test_longer_member_needs_a_deeper_section():
    short = size_member(SteelMemberParams(cantilever_length_m=2.0, transverse_load_kn=30.0)).geometry
    long = size_member(SteelMemberParams(cantilever_length_m=8.0, transverse_load_kn=30.0)).geometry
    assert long.web_depth_mm > short.web_depth_mm
    assert long.overall_depth_mm > short.overall_depth_mm


def test_e350_permits_higher_stresses_than_e250():
    g = size_member(AUTO).geometry
    a250 = analyse_member(SteelMemberParams(cantilever_length_m=6.0, transverse_load_kn=20.0, steel_grade="E250"), g)
    a350 = analyse_member(SteelMemberParams(cantilever_length_m=6.0, transverse_load_kn=20.0, steel_grade="E350"), g)
    assert a350.permissible_bending_stress_mpa > a250.permissible_bending_stress_mpa
    assert a350.permissible_shear_stress_mpa > a250.permissible_shear_stress_mpa


def test_zero_axial_load_is_a_valid_edge_case():
    params = SteelMemberParams(cantilever_length_m=4.0, transverse_load_kn=30.0, axial_load_kn=0.0)
    g = size_member(params).geometry
    analysis = analyse_member(params, g)
    checks = run_member_checks(analysis, g, params)
    assert analysis.max_axial_stress_mpa == pytest.approx(0.0)
    axial = next(c for c in checks.checks if c.kind == "axial")
    assert axial.status == "PASS"


def test_thin_section_override_fails_bending_the_under_design_case():
    """A shallow, thin, narrow flange -> the section modulus is too small -> the
    bending check FAILs (the under-design demo case) naming the member."""
    result = size_member(UNDER_BENDING)
    g = result.geometry
    analysis = analyse_member(UNDER_BENDING, g)
    checks = run_member_checks(analysis, g, UNDER_BENDING)
    bending = next(c for c in checks.checks if c.kind == "bending")
    assert bending.status == "FAIL"
    assert bending.member == "member"
    assert analysis.max_bending_stress_mpa > analysis.permissible_bending_stress_mpa
    assert result.warnings  # the overrides are flagged as possible under-design


def test_small_weld_override_fails_only_the_weld():
    """An undersized fillet weld -> the weld-group throat stress exceeds the IS 816
    permissible while the section itself is adequate (a connection under-design)."""
    result = size_member(UNDER_WELD)
    g = result.geometry
    assert g.weld_size_mm == 5.0
    analysis = analyse_member(UNDER_WELD, g)
    checks = run_member_checks(analysis, g, UNDER_WELD)
    weld = next(c for c in checks.checks if c.kind == "weld")
    assert weld.status == "FAIL"
    assert weld.member == "weld"
    assert analysis.weld_stress_mpa > analysis.permissible_weld_stress_mpa
    # The section strength checks still pass — it is specifically the connection.
    assert next(c for c in checks.checks if c.kind == "bending").status == "PASS"


def test_very_long_slender_member_fails_slenderness():
    """A very long cantilever I-section is too slender (KL/r > 180) — an honest
    limitation flagged as a slenderness non-conformity (a tubular/lattice member
    would be indicated)."""
    g = size_member(SLENDER).geometry
    analysis = analyse_member(SLENDER, g)
    checks = run_member_checks(analysis, g, SLENDER)
    slender = next(c for c in checks.checks if c.kind == "slenderness")
    assert slender.status == "FAIL"
    assert analysis.slenderness_ratio > analysis.slenderness_limit


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
