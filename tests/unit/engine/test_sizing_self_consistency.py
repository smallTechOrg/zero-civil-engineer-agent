"""Check-governed sizing — the agent's own sized design passes its own checks.

Phase-2 audit fix: the RDSO family heuristic alone ignores fill load, so at
4 m cushion the 4x3 box's own design failed its own IRS CBC checks (and the
span-5 family point was marginally over in bottom-slab shear, tau 0.601 vs
0.60). `size_culvert` now runs a bounded analyse -> check -> bump-50mm loop on
the AUTO-sized members until the design passes. This file is the property
sweep: EVERY auto-sized design across the valid domain passes ALL of its own
IRS CBC checks — plus the trail/assumption provenance of each bump, the
canonical no-bump guarantee, determinism, the loop bound, and the pathological
override edge. Deterministic — no LLM, no network, no DB.
"""

import re
import time

import pytest

from domain.culvert import CalcStep, CulvertParams
from engine import size_culvert
from engine.analysis import analyse_frame
from engine.checks import CheckResult, ChecksOutput, run_checks

# Representative grid: spans 1-8 m step 1 x cushions 0/2.5/4/6/8/10 on a
# 3 m-height box, plus the three V2 RDSO family points.
SWEEP_HEIGHT_M = 3.0
SWEEP_SPANS_M = (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0)
SWEEP_CUSHIONS_M = (0.0, 2.5, 4.0, 6.0, 8.0, 10.0)
V2_FAMILY_POINTS = ((4.0, 3.0, 2.5), (3.0, 3.0, 2.0), (5.0, 4.0, 3.0))

SWEEP_GRID = [
    (span, SWEEP_HEIGHT_M, cushion)
    for span in SWEEP_SPANS_M
    for cushion in SWEEP_CUSHIONS_M
] + list(V2_FAMILY_POINTS)

BUMP_STEP_PATTERN = re.compile(r"governed by (flexure|shear) check")


def _size_and_check(span: float, height: float, cushion: float):
    params = CulvertParams(clear_span_m=span, clear_height_m=height, cushion_m=cushion)
    sizing = size_culvert(params)
    checks = run_checks(analyse_frame(params, sizing.geometry), sizing.geometry, params)
    return sizing, checks


def _bump_steps(sizing) -> list[CalcStep]:
    return [s for s in sizing.trail if BUMP_STEP_PATTERN.search(s.description)]


def _thicknesses(sizing) -> tuple[float, float, float]:
    g = sizing.geometry
    return (g.top_slab_thickness_mm, g.bottom_slab_thickness_mm, g.wall_thickness_mm)


# --- the property: self-consistency across the valid domain --------------------


@pytest.mark.parametrize(("span", "height", "cushion"), SWEEP_GRID)
def test_auto_sized_design_passes_all_of_its_own_checks(span, height, cushion):
    sizing, checks = _size_and_check(span, height, cushion)

    failures = [
        f"{c.member}/{c.kind}: {c.computed} vs {c.limit}"
        for c in checks
        if c.status != "PASS"
    ]
    assert failures == [], f"({span}, {height}, {cushion}) sized {_thicknesses(sizing)}: {failures}"


def test_canonical_sizing_is_unchanged_and_needs_no_bump():
    """4/3/2.5 already passes at the heuristic 400/400/350 — the loop must not touch it."""
    sizing, checks = _size_and_check(4.0, 3.0, 2.5)

    assert _thicknesses(sizing) == (400.0, 400.0, 350.0)
    assert _bump_steps(sizing) == []
    assert all(c.status == "PASS" for c in checks)
    for assumption in sizing.assumptions:
        if assumption.field.endswith("_thickness_mm"):
            assert "check-governed" in assumption.note


# --- the two audit cases, exactly ----------------------------------------------


def test_fill_4m_bumps_both_slabs_to_450_with_cited_bump_steps():
    """Cushion 4.0 on the 4x3 box — the scripted Phase-1 refinement must go green."""
    sizing, checks = _size_and_check(4.0, 3.0, 4.0)

    assert _thicknesses(sizing) == (450.0, 450.0, 350.0)
    assert all(c.status == "PASS" for c in checks)
    assert sizing.warnings == []  # no overrides -> bumps are silent-by-design

    bump_steps = _bump_steps(sizing)
    assert len(bump_steps) == 2
    descriptions = sorted(s.description for s in bump_steps)
    assert descriptions[0].startswith("Bottom slab governed by")
    assert descriptions[1].startswith("Top slab governed by flexure check")
    for step in bump_steps:
        assert "at 4 m fill: 400 → 450 mm" in step.description
        assert "IRS Concrete Bridge Code" in step.citation
        assert step.value == 450.0
        assert step.unit == "mm"
        assert step.inputs["previous_mm"] == 400.0
        assert step.inputs["governing_check"] in ("flexure", "shear")

    by_field = {a.field: a for a in sizing.assumptions}
    for field in ("top_slab_thickness_mm", "bottom_slab_thickness_mm"):
        assert by_field[field].value == 450.0  # the FINAL value, not the heuristic
        assert "check-governed" in by_field[field].note
    assert by_field["wall_thickness_mm"].value == 350.0


def test_span5_family_point_bottom_slab_governed_by_shear():
    """5/4/3: bottom-slab shear was marginally over (tau 0.601 vs 0.60) — one bump."""
    sizing, checks = _size_and_check(5.0, 4.0, 3.0)

    assert _thicknesses(sizing) == (500.0, 550.0, 450.0)
    assert all(c.status == "PASS" for c in checks)
    bump_steps = _bump_steps(sizing)
    assert len(bump_steps) == 1
    assert bump_steps[0].description.startswith("Bottom slab governed by shear check")
    assert "500 → 550 mm" in bump_steps[0].description


def test_deep_fill_8m_converges_to_a_much_heavier_section():
    sizing, checks = _size_and_check(4.0, 3.0, 8.0)

    assert _thicknesses(sizing) == (650.0, 700.0, 400.0)
    assert all(c.status == "PASS" for c in checks)


# --- geometry consistency, determinism, performance -----------------------------


def test_external_dimensions_and_barrel_follow_the_check_governed_sizes():
    sizing, _ = _size_and_check(4.0, 3.0, 4.0)
    g = sizing.geometry

    assert g.external_width_m == 4.7  # 4.0 + 2 * 0.35
    assert g.external_height_m == 3.9  # 3.0 + 0.45 + 0.45 (post-bump)
    assert g.barrel_length_m == 38.45  # 6.85 + 2 * 2.0 * (4.0 + 3.9)


def test_bumped_sizing_is_deterministic_byte_identical():
    params = CulvertParams(clear_span_m=4.0, clear_height_m=3.0, cushion_m=4.0)

    first = size_culvert(params)
    second = size_culvert(params)

    assert first.model_dump_json() == second.model_dump_json()


def test_worst_valid_corner_sizes_within_the_two_second_budget():
    params = CulvertParams(clear_span_m=8.0, clear_height_m=6.0, cushion_m=10.0)

    started = time.perf_counter()
    sizing = size_culvert(params)
    elapsed = time.perf_counter() - started

    assert elapsed < 2.0, f"check-governed sizing took {elapsed:.2f}s"
    checks = run_checks(analyse_frame(params, sizing.geometry), sizing.geometry, params)
    assert all(c.status == "PASS" for c in checks)


# --- edge and error paths --------------------------------------------------------


def test_override_below_the_cover_allowance_still_sizes_without_bumps():
    """A 55 mm override leaves no effective depth (d <= 0): the in-loop checks
    cannot run, so sizing keeps the heuristic sizes and the graph's check step
    raises the same loud error downstream — exactly the pre-fix behaviour."""
    params = CulvertParams(
        clear_span_m=4.0, clear_height_m=3.0, cushion_m=2.5, top_slab_thickness_mm=55.0
    )

    sizing = size_culvert(params)

    assert sizing.geometry.top_slab_thickness_mm == 55.0  # override honoured
    assert sizing.geometry.bottom_slab_thickness_mm == 400.0  # heuristic, unbumped
    assert sizing.geometry.wall_thickness_mm == 350.0
    assert _bump_steps(sizing) == []
    with pytest.raises(ValueError, match="effective depth"):
        run_checks(analyse_frame(params, sizing.geometry), sizing.geometry, params)


def test_loop_bound_raises_a_clear_error_when_checks_can_never_pass(monkeypatch):
    """Unreachable for valid inputs (worst valid corner converges in 41 passes;
    the bound is 60) — forced here by stubbing the check run to always FAIL."""
    import engine.sizing as sizing_module

    always_fail = ChecksOutput(
        checks=[
            CheckResult(
                clause="IRS Concrete Bridge Code (stub)",
                requirement="stub",
                computed="stub",
                limit="stub",
                status="FAIL",
                member="top_slab",
                kind="flexure",
                trail_ref="K01",
                severity_hint="critical",
            )
        ],
        trail=[
            CalcStep(
                step_id="K01",
                description="stub d_req",
                formula="stub",
                inputs={"stub": 1},
                value=10_000.0,
                unit="mm",
                citation="IRS Concrete Bridge Code (stub)",
            )
        ],
        assumptions=[],
    )
    monkeypatch.setattr(sizing_module, "analyse_frame", lambda params, geometry: None)
    monkeypatch.setattr(
        sizing_module, "run_member_checks", lambda analysis, geometry, params: always_fail
    )

    with pytest.raises(ValueError, match="did not converge"):
        size_culvert(CulvertParams(clear_span_m=4.0, clear_height_m=3.0, cushion_m=2.5))
