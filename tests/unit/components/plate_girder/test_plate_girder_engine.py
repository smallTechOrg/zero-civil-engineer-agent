"""Plate-girder engine — sizing convergence, load analysis, checks (incl. under-design)."""

import pytest

from components.plate_girder._engine_common import section_properties
from components.plate_girder.analysis import analyse_girder, compute_forces
from components.plate_girder.checks import run_girder_checks
from components.plate_girder.params import PlateGirderParams
from components.plate_girder.sizing import size_girder

AUTO = PlateGirderParams(span_m=24.0)


def test_auto_sized_girder_is_in_the_depth_band_and_passes_all_checks():
    result = size_girder(AUTO)
    g = result.geometry
    # Web depth in the span/10 - span/12 band.
    assert AUTO.span_m * 1000.0 / 12.5 <= g.web_depth_mm <= AUTO.span_m * 1000.0 / 9.5
    assert g.overall_depth_mm == pytest.approx(g.web_depth_mm + 2 * g.flange_thickness_mm)
    assert g.number_of_girders == 2

    analysis = analyse_girder(AUTO, g)
    checks = run_girder_checks(analysis, g, AUTO)
    assert all(c.status == "PASS" for c in checks.checks), [
        (c.kind, c.status) for c in checks.checks
    ]
    # Every sizing/analysis assumption is engine-sourced and provenanced.
    assert result.assumptions
    assert all(a.source == "engine_default" for a in result.assumptions)


def test_kinds_present_and_stresses_are_within_permissible():
    g = size_girder(AUTO).geometry
    analysis = analyse_girder(AUTO, g)
    checks = run_girder_checks(analysis, g, AUTO)
    kinds = {c.kind for c in checks.checks}
    assert kinds == {"bending", "shear", "deflection", "web_slenderness", "fatigue"}
    assert analysis.max_bending_stress_mpa <= analysis.permissible_bending_stress_mpa
    assert analysis.max_shear_stress_mpa <= analysis.permissible_shear_stress_mpa
    assert analysis.max_deflection_mm <= analysis.deflection_limit_mm


def test_section_properties_match_the_recorded_analysis():
    g = size_girder(AUTO).geometry
    analysis = analyse_girder(AUTO, g)
    section = section_properties(
        web_depth_mm=g.web_depth_mm, web_thickness_mm=g.web_thickness_mm,
        flange_width_mm=g.flange_width_mm, flange_thickness_mm=g.flange_thickness_mm,
    )
    assert analysis.section_modulus_cm3 == pytest.approx(section.section_modulus_mm3 / 1000.0, rel=1e-6)
    assert analysis.inertia_mm4 == pytest.approx(section.inertia_mm4, rel=1e-6)


def test_live_load_uses_the_25t_eudl_and_cda_at_span_length():
    g = size_girder(AUTO).geometry
    core = compute_forces(AUTO, g)
    # loaded length equals the span, CDA is the open-deck (no cushion) value.
    assert core.loaded_length_m == pytest.approx(AUTO.span_m)
    assert core.cda == pytest.approx(0.15 + 8.0 / (6.0 + AUTO.span_m), rel=1e-9)
    assert core.eudl_bm_kn > 0 and core.eudl_shear_kn > 0
    # Design moment = dead + live+impact, shared per girder.
    assert core.design_moment_knm == pytest.approx(core.dead_moment_knm + core.live_moment_knm)


def test_longer_span_needs_a_deeper_section():
    short = size_girder(PlateGirderParams(span_m=12.0)).geometry
    long = size_girder(PlateGirderParams(span_m=40.0)).geometry
    assert long.web_depth_mm > short.web_depth_mm
    assert long.overall_depth_mm > short.overall_depth_mm


def test_e350_permits_higher_stresses_than_e250():
    g = size_girder(AUTO).geometry
    a250 = analyse_girder(PlateGirderParams(span_m=24.0, steel_grade="E250"), g)
    a350 = analyse_girder(PlateGirderParams(span_m=24.0, steel_grade="E350"), g)
    assert a350.permissible_bending_stress_mpa > a250.permissible_bending_stress_mpa
    assert a350.permissible_shear_stress_mpa > a250.permissible_shear_stress_mpa


def test_thin_flange_override_fails_bending_the_under_design_case():
    """A deliberately thin/narrow flange -> the section modulus is too small ->
    the bending check FAILs (the under-design demo case)."""
    under = PlateGirderParams(
        span_m=24.0, flange_thickness_mm=12.0, flange_width_mm=250.0
    )
    result = size_girder(under)
    g = result.geometry
    analysis = analyse_girder(under, g)
    checks = run_girder_checks(analysis, g, under)
    bending = next(c for c in checks.checks if c.kind == "bending")
    assert bending.status == "FAIL"
    assert analysis.max_bending_stress_mpa > analysis.permissible_bending_stress_mpa
    # The override is flagged as a possible under-design in the warnings.
    assert any("under-design" in w.lower() or "thinner" in w.lower() for w in result.warnings)


def test_every_check_trail_ref_resolves_within_the_check_trail():
    g = size_girder(AUTO).geometry
    analysis = analyse_girder(AUTO, g)
    checks = run_girder_checks(analysis, g, AUTO)
    trail_ids = {s.step_id for s in checks.trail}
    for c in checks.checks:
        assert c.trail_ref in trail_ids
        assert c.trail_ref.startswith("K")


def test_trail_prefixes_are_segmented():
    result = size_girder(AUTO)
    analysis = analyse_girder(AUTO, result.geometry)
    checks = run_girder_checks(analysis, result.geometry, AUTO)
    assert all(s.step_id.startswith("S") for s in result.trail)
    assert all(s.step_id.startswith("A") for s in analysis.trail)
    assert all(s.step_id.startswith("K") for s in checks.trail)
