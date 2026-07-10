"""Retaining-wall engine — sizing, earth-pressure/analysis, checks, calc sheet.

Three scenarios per capability (happy / edge / error) plus the under-design FAIL
case the proof-check depends on. Pure deterministic (no LLM, production driver
not needed — no DB).
"""

import json
import time
from pathlib import Path

import pytest

from components.retaining_wall.analysis import analyse_wall, compute_stability
from components.retaining_wall.calcsheet import compose_calc_sheet
from components.retaining_wall.checks import run_wall_checks
from components.retaining_wall.params import RetainingWallGeometry, RetainingWallParams
from components.retaining_wall.sizing import (
    FOS_OVERTURNING_MIN,
    FOS_SLIDING_MIN,
    size_wall,
)
from components.retaining_wall.summary import type_summary

CANONICAL = dict(
    retained_height_m=5.0, safe_bearing_capacity_kn_m2=200.0, backfill_friction_angle_deg=30.0
)


def _sound(**overrides) -> RetainingWallParams:
    return RetainingWallParams(**{**CANONICAL, **overrides})


# --- sizing --------------------------------------------------------------------


def test_sizing_produces_a_self_consistent_geometry_that_passes_its_own_checks():
    params = _sound()
    result = size_wall(params)
    g = result.geometry
    assert g.base_width_mm == g.toe_length_mm + g.stem_base_thickness_mm + g.heel_length_mm
    assert g.total_height_mm == 5000.0
    assert g.stem_top_thickness_mm >= 200.0
    assert result.trail and result.assumptions
    analysis = analyse_wall(params, g)
    checks = run_wall_checks(analysis, g, params)
    assert all(c.status == "PASS" for c in checks.checks)


def test_sizing_edge_shortest_wall_still_stable():
    params = RetainingWallParams(
        retained_height_m=1.5, safe_bearing_capacity_kn_m2=300.0, backfill_friction_angle_deg=35.0
    )
    result = size_wall(params)
    analysis = analyse_wall(params, result.geometry)
    assert analysis.fos_overturning >= FOS_OVERTURNING_MIN
    assert analysis.fos_sliding >= FOS_SLIDING_MIN


def test_sizing_completes_quickly_across_the_range():
    started = time.perf_counter()
    for h in (2.0, 4.0, 6.0, 8.0):
        size_wall(RetainingWallParams(
            retained_height_m=h, safe_bearing_capacity_kn_m2=150.0, backfill_friction_angle_deg=28.0
        ))
    assert time.perf_counter() - started < 5.0


def test_thinner_stem_override_raises_a_warning_but_still_sizes():
    result = size_wall(_sound(stem_base_thickness_mm=250.0))
    assert result.geometry.stem_base_thickness_mm == 250.0
    assert any("thinner" in w.lower() for w in result.warnings)


# --- analysis (earth pressure) --------------------------------------------------


def test_analysis_uses_rankine_for_level_backfill():
    params = _sound(track_surcharge=False)
    g = size_wall(params).geometry
    analysis = analyse_wall(params, g)
    # Rankine Ka for phi=30 -> 1/3.
    assert analysis.ka == pytest.approx(1.0 / 3.0, rel=1e-4)
    assert "Rankine" in analysis.method
    assert analysis.active_vertical_kn == 0.0


def test_analysis_uses_coulomb_for_sloped_backfill():
    params = _sound(backfill_slope_deg=15.0)
    g = size_wall(params).geometry
    analysis = analyse_wall(params, g)
    assert "Coulomb" in analysis.method
    # A sloped backfill raises Ka above the level-Rankine value.
    assert analysis.ka > (1.0 - 0.5) / (1.0 + 0.5)
    assert analysis.active_vertical_kn > 0.0


def test_track_surcharge_increases_the_horizontal_thrust():
    g = size_wall(_sound()).geometry
    with_surcharge = analyse_wall(_sound(track_surcharge=True), g)
    without = analyse_wall(_sound(track_surcharge=False), g)
    assert with_surcharge.surcharge_thrust_kn > 0.0
    assert without.surcharge_thrust_kn == 0.0
    assert with_surcharge.total_horizontal_kn > without.total_horizontal_kn


# --- checks (stability + section design) ---------------------------------------


def test_checks_sound_wall_all_pass_with_expected_row_kinds():
    params = _sound()
    g = size_wall(params).geometry
    analysis = analyse_wall(params, g)
    checks = run_wall_checks(analysis, g, params)
    kinds = {c.kind for c in checks.checks}
    assert {"overturning", "sliding", "bearing", "bearing_tension", "flexure", "shear",
            "min_steel", "cover"} <= kinds
    assert all(c.status == "PASS" for c in checks.checks)
    assert checks.trail and checks.assumptions


def test_checks_under_design_thin_stem_fails_flexure_and_shear():
    params = _sound(stem_base_thickness_mm=250.0)
    g = size_wall(params).geometry
    analysis = analyse_wall(params, g)
    checks = run_wall_checks(analysis, g, params)
    failing = [c for c in checks.checks if c.status == "FAIL"]
    assert failing, "a 250 mm stem on a 5 m wall must fail"
    assert all(c.member == "stem" for c in failing)
    assert {"flexure", "shear"} <= {c.kind for c in failing}


def test_checks_error_effective_depth_non_positive_raises():
    params = _sound(stem_base_thickness_mm=55.0, base_thickness_mm=500.0)
    g = RetainingWallGeometry(
        stem_top_thickness_mm=55.0, stem_base_thickness_mm=55.0, base_thickness_mm=500.0,
        toe_length_mm=900.0, heel_length_mm=1600.0, base_width_mm=2555.0,
        total_height_mm=5000.0, key_depth_mm=0.0,
    )
    analysis = analyse_wall(params, g)
    with pytest.raises(ValueError):
        run_wall_checks(analysis, g, params)


def test_compute_stability_matches_analysis_model_numbers():
    params = _sound()
    g = size_wall(params).geometry
    core = compute_stability(params, g)
    analysis = analyse_wall(params, g)
    assert core.fos_overturning == pytest.approx(analysis.fos_overturning, rel=1e-3)
    assert core.max_base_pressure_kn_m2 == pytest.approx(analysis.max_base_pressure_kn_m2, rel=1e-3)


# --- calc sheet ----------------------------------------------------------------


def test_calc_sheet_writes_the_pinned_json_shape(tmp_path: Path):
    params = _sound()
    sizing = size_wall(params)
    g = sizing.geometry
    analysis_out = analyse_wall(params, g)
    checks = run_wall_checks(analysis_out, g, params)
    path = compose_calc_sheet(
        trail=[
            [s.model_dump() for s in sizing.trail],
            [s.model_dump() for s in analysis_out.trail],
            [s.model_dump() for s in checks.trail],
        ],
        checks=[c.model_dump() for c in checks.checks],
        assumptions=[a.model_dump() for a in sizing.assumptions],
        warnings=sizing.warnings,
        params=params,
        geometry=g,
        out_dir=tmp_path,
    )
    assert path.name == "calc_sheet.json" and path.is_file()
    doc = json.loads(path.read_text())
    assert [s["id"] for s in doc["sections"]] == [
        "design_basis", "earth_pressure", "stability", "section_checks",
    ]
    # Every check line carries a status and a trail_ref that resolves.
    step_ids = {s["step_id"] for s in doc["trail"]}
    for line in next(s for s in doc["sections"] if s["id"] == "section_checks")["lines"]:
        assert line["status"] in {"PASS", "FAIL"}
        assert line["trail_ref"] in step_ids


# --- type summary --------------------------------------------------------------


def test_type_summary_shape_and_bearing_flag():
    params = _sound()
    g = size_wall(params).geometry
    analysis = analyse_wall(params, g)
    summary = type_summary(params=params, analysis=analysis, verdict="recommended_for_approval")
    assert set(summary) == {
        "kind", "fos_overturning", "fos_sliding", "max_bearing_pressure_kn_m2",
        "sbc_kn_m2", "bearing_ok", "verdict",
    }
    assert summary["kind"] == "stability"
    assert summary["bearing_ok"] is True
    assert summary["max_bearing_pressure_kn_m2"] <= summary["sbc_kn_m2"]
