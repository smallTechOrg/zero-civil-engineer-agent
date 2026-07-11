"""Slab / T-beam engine — sizing (both deck types), analysis, checks, calc sheet.

Three scenarios per capability (happy / edge / error) plus the under-design FAIL
case the proof-check depends on. Pure deterministic — live load runs through the
real 25t Loading-2008 tables (no LLM, no DB).
"""

import json
import time
from pathlib import Path

import pytest

from components.slab_tbeam.analysis import analyse_deck, compute_deck_forces, track_live_load
from components.slab_tbeam.calcsheet import compose_calc_sheet
from components.slab_tbeam.checks import run_deck_checks
from components.slab_tbeam.params import SlabTbeamParams
from components.slab_tbeam.sizing import size_deck
from components.slab_tbeam.summary import type_summary


def _slab(**overrides) -> SlabTbeamParams:
    return SlabTbeamParams(**{"span_m": 6.0, "deck_type": "solid_slab", **overrides})


def _tbeam(**overrides) -> SlabTbeamParams:
    return SlabTbeamParams(**{"span_m": 12.0, "deck_type": "t_beam", **overrides})


# --- sizing --------------------------------------------------------------------


def test_solid_slab_sizes_to_a_self_consistent_geometry_that_passes_its_own_checks():
    params = _slab()
    result = size_deck(params)
    g = result.geometry
    assert g.deck_type == "solid_slab"
    assert g.span_mm == 6000.0
    assert g.overall_depth_mm == g.slab_depth_mm  # solid slab: no ribs
    assert g.rib_width_mm == 0.0 and g.rib_depth_mm == 0.0
    assert g.number_of_girders == 1
    assert result.trail and result.assumptions
    analysis = analyse_deck(params, g)
    checks = run_deck_checks(analysis, g, params)
    assert all(c.status == "PASS" for c in checks.checks)


def test_t_beam_sizes_slab_ribs_and_effective_flange_and_passes_its_own_checks():
    params = _tbeam(number_of_girders=3)
    result = size_deck(params)
    g = result.geometry
    assert g.deck_type == "t_beam"
    assert g.rib_width_mm > 0 and g.rib_depth_mm > 0
    assert g.overall_depth_mm == pytest.approx(g.slab_depth_mm + g.rib_depth_mm, abs=1.0)
    assert g.number_of_girders == 3
    # IS 456 effective flange width never exceeds the girder spacing.
    assert g.flange_width_mm <= g.girder_spacing_mm + 1e-6
    analysis = analyse_deck(params, g)
    checks = run_deck_checks(analysis, g, params)
    assert all(c.status == "PASS" for c in checks.checks)


def test_sizing_edge_shortest_span_is_shallow_and_passes():
    params = _slab(span_m=3.0)
    result = size_deck(params)
    analysis = analyse_deck(params, result.geometry)
    checks = run_deck_checks(analysis, result.geometry, params)
    assert result.geometry.overall_depth_mm < result.geometry.span_mm
    assert all(c.status == "PASS" for c in checks.checks)


def test_sizing_completes_quickly_across_the_range():
    started = time.perf_counter()
    for span in (4.0, 8.0, 12.0, 20.0):
        size_deck(SlabTbeamParams(span_m=span, deck_type="t_beam"))
    assert time.perf_counter() - started < 5.0


def test_thinner_slab_override_raises_a_warning_but_still_sizes():
    result = size_deck(_slab(span_m=12.0, slab_depth_mm=300.0))
    assert result.geometry.overall_depth_mm == 300.0
    assert any("thinner" in w.lower() for w in result.warnings)


# --- analysis (loading) --------------------------------------------------------


def test_live_load_uses_the_real_25t_tables_and_full_cda_on_the_deck():
    params = _slab(span_m=6.0)
    g = size_deck(params).geometry
    analysis = analyse_deck(params, g)
    # EUDL(BM) at 6 m from the transcribed table is 786.8 kN/track.
    assert analysis.eudl_bm_kn == pytest.approx(786.8, rel=1e-4)
    # CDA = 0.15 + 8/(6+L) with no fill reduction on a deck.
    assert analysis.cda == pytest.approx(0.15 + 8.0 / 12.0, rel=1e-4)
    assert analysis.loading_standard == "25t-2008"


def test_live_load_moment_scales_with_span_and_dominates_over_dead():
    short = analyse_deck(_slab(span_m=5.0), size_deck(_slab(span_m=5.0)).geometry)
    long = analyse_deck(_slab(span_m=9.0), size_deck(_slab(span_m=9.0)).geometry)
    assert long.live_moment_knm > short.live_moment_knm
    assert short.live_moment_knm > 0 and short.dead_moment_knm > 0


def test_t_beam_distribution_apportions_only_part_of_the_track_to_a_girder():
    params = _tbeam(span_m=12.0, number_of_girders=4)
    g = size_deck(params).geometry
    forces = compute_deck_forces(params, g)
    ll = track_live_load(params, 12.0)
    # The critical girder carries only its distribution fraction of the whole track.
    assert 0.0 < forces.distribution_fraction < 1.0
    assert forces.live_moment_knm == pytest.approx(
        ll.track_moment_knm * forces.distribution_fraction, rel=1e-6
    )


# --- checks --------------------------------------------------------------------


def test_checks_sound_deck_all_pass_with_expected_row_kinds():
    params = _slab()
    g = size_deck(params).geometry
    analysis = analyse_deck(params, g)
    checks = run_deck_checks(analysis, g, params)
    kinds = {c.kind for c in checks.checks}
    assert {"flexure", "min_steel", "shear", "deflection", "cover"} <= kinds
    assert all(c.status == "PASS" for c in checks.checks)
    assert checks.trail and checks.assumptions


def test_checks_under_design_thin_slab_fails_flexure():
    params = _slab(span_m=12.0, slab_depth_mm=300.0)
    g = size_deck(params).geometry
    analysis = analyse_deck(params, g)
    checks = run_deck_checks(analysis, g, params)
    failing = [c for c in checks.checks if c.status == "FAIL"]
    assert failing, "a 300 mm slab on a 12 m span must fail"
    assert "flexure" in {c.kind for c in failing}
    assert all(c.member == "deck" for c in failing)


def test_checks_error_effective_depth_non_positive_raises():
    params = _slab(slab_depth_mm=45.0)  # cannot fit 40 mm cover + bar
    g = size_deck(params).geometry
    analysis = analyse_deck(params, g)
    with pytest.raises(ValueError):
        run_deck_checks(analysis, g, params)


def test_t_beam_shear_uses_the_max_permissible_stress_with_stirrups():
    params = _tbeam()
    g = size_deck(params).geometry
    analysis = analyse_deck(params, g)
    checks = run_deck_checks(analysis, g, params)
    shear = next(c for c in checks.checks if c.kind == "shear")
    # A girder carries shear on stirrups up to tau_c,max (> the no-steel tau_c).
    assert "tau_c,max" in shear.limit
    assert shear.status == "PASS"


# --- calc sheet ----------------------------------------------------------------


def test_calc_sheet_writes_the_pinned_json_shape_with_resolving_trail_refs(tmp_path: Path):
    params = _tbeam()
    sizing = size_deck(params)
    g = sizing.geometry
    analysis = analyse_deck(params, g)
    checks = run_deck_checks(analysis, g, params)
    path = compose_calc_sheet(
        trail=[
            [s.model_dump() for s in sizing.trail],
            [s.model_dump() for s in analysis.trail],
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
    assert [s["id"] for s in doc["sections"]] == ["design_basis", "loading", "section_checks"]
    step_ids = {s["step_id"] for s in doc["trail"]}
    for line in next(s for s in doc["sections"] if s["id"] == "section_checks")["lines"]:
        assert line["status"] in {"PASS", "FAIL"}
        assert line["trail_ref"] in step_ids  # every check.trail_ref resolves


# --- type summary --------------------------------------------------------------


def test_type_summary_has_the_exact_flexure_summary_shape():
    params = _slab()
    g = size_deck(params).geometry
    analysis = analyse_deck(params, g)
    checks = run_deck_checks(analysis, g, params)
    summary = type_summary(
        params=params, geometry=g, analysis=analysis,
        checks=list(checks.checks), verdict="recommended_for_approval",
    )
    assert set(summary) == {
        "kind", "design_moment_knm", "required_depth_mm", "provided_depth_mm",
        "flexure_ok", "design_shear_kn", "shear_stress_mpa", "permissible_shear_mpa",
        "shear_ok", "steel_area_mm2", "min_steel_mm2", "verdict",
    }
    assert summary["kind"] == "flexure_summary"
    assert summary["flexure_ok"] is True and summary["shear_ok"] is True
    assert summary["required_depth_mm"] <= summary["provided_depth_mm"]
