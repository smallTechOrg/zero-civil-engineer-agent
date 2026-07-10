"""IRS Concrete Bridge Code member checks (Phase 2, spec/capabilities/irs-engine.md).

Covers: the pinned `run_checks` row shape (spec/api.md `checks[]`), the
working-stress engineering content against independent re-derivations, the
under-design hard case through the REAL sizing -> analysis -> checks chain,
edge and error paths, and fixture V2 (RDSO B-10152/R family cross-check).
Deterministic — no LLM, no network, no DB.
"""

import math
import time

import pytest

from domain.culvert import CulvertParams
from engine import size_culvert
from engine.analysis import analyse_frame
from engine.checks import (
    ASSUMED_BAR_DIA_MM,
    CONCRETE_PERMISSIBLE,
    MIN_CLEAR_COVER_MM,
    MIN_STEEL_PCT_GROSS,
    STEEL_PERMISSIBLE,
    VERIFY_BANNER,
    CheckResult,
    ChecksOutput,
    run_checks,
    run_member_checks,
)
from engine.loading.t25_2008 import VERIFY_BANNER as LOADING_VERIFY_BANNER

CANONICAL = {"clear_span_m": 4.0, "clear_height_m": 3.0, "cushion_m": 2.5}
MEMBERS = ("top_slab", "bottom_slab", "wall")
PER_MEMBER_KINDS = ("flexure", "shear", "min_steel", "crack")

# Forbidden-code tokens built by concatenation so this file itself never greps
# as a violation of the IRS-only citation rule.
FORBIDDEN_CODE_TOKENS = ("IS " + "456", "IS " + "800", "IR" + "C:", "IR" + "C ")


def _run(**overrides):
    params = CulvertParams(**{**CANONICAL, **overrides})
    sizing = size_culvert(params)
    analysis = analyse_frame(params, sizing.geometry)
    return params, sizing, analysis


@pytest.fixture(scope="module")
def canonical_run():
    return _run()


@pytest.fixture(scope="module")
def canonical_output(canonical_run) -> ChecksOutput:
    params, sizing, analysis = canonical_run
    return run_member_checks(analysis, sizing.geometry, params)


@pytest.fixture(scope="module")
def under_design_run():
    """The demo money-shot: canonical box with a deliberately thin 200 mm top slab."""
    return _run(top_slab_thickness_mm=200)


# --- pinned api.md row shape --------------------------------------------------


def test_run_checks_returns_the_pinned_api_row_shape(canonical_run):
    params, sizing, analysis = canonical_run

    checks = run_checks(analysis, sizing.geometry, params)

    assert checks and all(isinstance(c, CheckResult) for c in checks)
    for check in checks:
        assert check.clause.strip()
        assert check.requirement.strip()
        assert check.computed.strip()
        assert check.limit.strip()
        assert check.status in ("PASS", "FAIL")
        assert check.member
        assert check.kind
        assert check.trail_ref
        assert check.severity_hint


def test_every_check_cites_the_irs_concrete_bridge_code_with_acs_level(canonical_output):
    for check in canonical_output.checks:
        assert "IRS Concrete Bridge Code" in check.clause
        assert "ACS" in check.clause


def test_no_forbidden_code_citations_in_any_check_field(canonical_output):
    for check in canonical_output.checks:
        blob = " ".join((check.clause, check.requirement, check.computed, check.limit))
        for token in FORBIDDEN_CODE_TOKENS:
            assert token not in blob, f"forbidden citation {token!r} in {check.kind}"


def test_checks_cover_flexure_shear_min_steel_crack_per_member_plus_cover(canonical_output):
    kinds_by_member = {m: {c.kind for c in canonical_output.checks if c.member == m} for m in MEMBERS}

    for member in MEMBERS:
        assert set(PER_MEMBER_KINDS) <= kinds_by_member[member], member
    cover_rows = [c for c in canonical_output.checks if c.kind == "cover"]
    assert len(cover_rows) == 1


# --- engineering content vs independent re-derivation -------------------------


def _expected_working_stress_constants(params):
    """Independent second derivation of the balanced working-stress constants."""
    sigma_cbc = CONCRETE_PERMISSIBLE[params.concrete_grade].sigma_cbc_n_mm2
    sigma_st = STEEL_PERMISSIBLE[params.steel_grade].sigma_st_n_mm2
    m = 280.0 / (3.0 * sigma_cbc)
    k = m * sigma_cbc / (m * sigma_cbc + sigma_st)
    j = 1.0 - k / 3.0
    q = 0.5 * sigma_cbc * k * j
    return sigma_cbc, sigma_st, m, k, j, q


def _step_value(output: ChecksOutput, description_fragment: str) -> float:
    matches = [s for s in output.trail if description_fragment in s.description]
    assert matches, f"no check trail step matches {description_fragment!r}"
    return matches[0].value


def test_flexure_required_depth_matches_an_independent_derivation(canonical_run, canonical_output):
    params, sizing, analysis = canonical_run
    *_, q = _expected_working_stress_constants(params)
    env = {(e.member, e.section): e for e in analysis.envelopes}
    # bottom slab governs at midspan (max sagging moment of the design sections)
    moment = max(
        max(abs(env[("bottom_slab", s)].max_moment_knm), abs(env[("bottom_slab", s)].min_moment_knm))
        for s in ("haunch_face", "midspan")
    )
    expected_d_req_mm = 1000.0 * math.sqrt(moment / (q * 1000.0))

    d_req = _step_value(canonical_output, "bottom_slab: required effective depth")

    assert d_req == pytest.approx(expected_d_req_mm, rel=1e-9)


def test_shear_stress_matches_v_over_bd(canonical_run, canonical_output):
    params, sizing, analysis = canonical_run
    env = {(e.member, e.section): e for e in analysis.envelopes}
    d_mm = sizing.geometry.top_slab_thickness_mm - params.clear_cover_mm - ASSUMED_BAR_DIA_MM / 2.0
    expected_tau = env[("top_slab", "haunch_face")].max_abs_shear_kn / d_mm

    tau = _step_value(canonical_output, "top_slab: applied shear stress")

    assert tau == pytest.approx(expected_tau, rel=1e-9)


def test_required_steel_area_uses_sigma_st_and_lever_arm(canonical_run, canonical_output):
    params, sizing, analysis = canonical_run
    _, sigma_st, _, _, j, _ = _expected_working_stress_constants(params)
    moment = _step_value(canonical_output, "wall: design bending moment")
    d_mm = sizing.geometry.wall_thickness_mm - params.clear_cover_mm - ASSUMED_BAR_DIA_MM / 2.0
    expected_as = moment * 1e6 / (sigma_st * j * d_mm)

    as_req = _step_value(canonical_output, "wall: required steel area")

    assert as_req == pytest.approx(expected_as, rel=1e-9)


def test_permissible_stress_tables_are_flagged_for_verification_with_the_shared_banner():
    assert VERIFY_BANNER == LOADING_VERIFY_BANNER
    for row in CONCRETE_PERMISSIBLE.values():
        assert row.needs_verification is True
        assert row.sigma_cbc_n_mm2 > 0
        assert row.tau_c_n_mm2 > 0
    for row in STEEL_PERMISSIBLE.values():
        assert row.needs_verification is True
        assert row.sigma_st_n_mm2 > 0
    assert 0 < MIN_STEEL_PCT_GROSS < 1
    assert MIN_CLEAR_COVER_MM > 0


def test_every_check_trail_step_is_fully_cited(canonical_output):
    assert canonical_output.trail
    for step in canonical_output.trail:
        assert step.citation.strip()
        assert step.formula.strip()
        assert step.unit.strip()


def test_every_check_trail_ref_resolves_into_the_check_trail(canonical_output):
    step_ids = {s.step_id for s in canonical_output.trail}
    assert len(step_ids) == len(canonical_output.trail), "duplicate check step ids"
    for check in canonical_output.checks:
        assert check.trail_ref in step_ids


def test_check_assumptions_state_bar_allowance_and_exposure(canonical_output):
    fields = {a.field for a in canonical_output.assumptions}
    assert "effective_depth_bar_allowance" in fields
    assert "exposure_condition" in fields
    for assumption in canonical_output.assumptions:
        assert assumption.source == "engine_default"
        assert assumption.note.strip()


# --- hard cases ----------------------------------------------------------------


def test_canonical_sized_box_passes_every_check(canonical_output):
    failures = [c for c in canonical_output.checks if c.status != "PASS"]
    assert failures == [], [f"{c.member}/{c.kind}: {c.computed} vs {c.limit}" for c in failures]


def test_under_design_200mm_top_slab_fails_flexure_and_shear_on_the_top_slab(under_design_run):
    params, sizing, analysis = under_design_run
    assert any("thinner than the auto-sized" in w for w in sizing.warnings)

    checks = run_checks(analysis, sizing.geometry, params)

    top_slab_failures = {
        c.kind for c in checks if c.member == "top_slab" and c.status == "FAIL"
    }
    assert {"flexure", "shear"} <= top_slab_failures
    # the failure is localised: the untouched members still pass flexure
    for member in ("bottom_slab", "wall"):
        flexure = next(c for c in checks if c.member == member and c.kind == "flexure")
        assert flexure.status == "PASS"


def test_failed_checks_carry_a_critical_severity_hint(under_design_run):
    params, sizing, analysis = under_design_run

    checks = run_checks(analysis, sizing.geometry, params)

    for check in checks:
        if check.status == "FAIL":
            assert check.severity_hint == "critical"


def test_zero_cushion_edge_case_completes_with_the_full_check_set():
    params, sizing, analysis = _run(cushion_m=0.0)

    checks = run_checks(analysis, sizing.geometry, params)

    kinds_by_member = {m: {c.kind for c in checks if c.member == m} for m in MEMBERS}
    for member in MEMBERS:
        assert set(PER_MEMBER_KINDS) <= kinds_by_member[member]


def test_min_steel_governs_note_for_a_lightly_loaded_member():
    params, sizing, analysis = _run(clear_span_m=1.5, clear_height_m=1.5, cushion_m=0.5)

    checks = run_checks(analysis, sizing.geometry, params)

    wall_min_steel = next(c for c in checks if c.member == "wall" and c.kind == "min_steel")
    assert wall_min_steel.status == "PASS"
    assert "minimum governs" in wall_min_steel.computed


def test_missing_envelope_is_a_loud_error_naming_the_member(canonical_run):
    params, sizing, analysis = canonical_run
    crippled = analysis.model_copy(
        update={"envelopes": [e for e in analysis.envelopes if e.member != "wall"]}
    )

    with pytest.raises(ValueError, match="wall"):
        run_checks(crippled, sizing.geometry, params)


def test_checks_are_deterministic_byte_identical(canonical_run):
    params, sizing, analysis = canonical_run

    first = run_member_checks(analysis, sizing.geometry, params)
    second = run_member_checks(analysis, sizing.geometry, params)

    assert first.model_dump_json() == second.model_dump_json()


def test_sizing_analysis_and_checks_complete_in_under_two_seconds():
    started = time.perf_counter()
    params, sizing, analysis = _run()
    run_checks(analysis, sizing.geometry, params)
    elapsed = time.perf_counter() - started

    assert elapsed < 2.0, f"sizing+analysis+checks took {elapsed:.2f}s"


# ==============================================================================
# Fixture V2 — RDSO B-10152/R family cross-check (spec/capabilities/irs-engine.md)
# ==============================================================================
#
# SOURCE (named per the fixture contract): RDSO Drawing No. B-10152/R —
# standard-drawing family for single-cell RCC box culverts, BG, 25t
# Loading-2008. The family values below are the proportional-rule values the
# family is believed to follow (slab thickness ~ clear span / 10, wall ~
# governing opening / 12, 300 mm floor, 50 mm constructible rounding — the
# same basis already cited in src/engine/defaults.py).
#
# TRANSCRIPTION HONESTY (same discipline as the loading-table slice): these
# family values were NOT read digit-for-digit from the printed B-10152/R
# sheets — verify each against the actual RDSO drawings before demo day
# (IR engineer pre-review required per spec).
#
# CHECK-GOVERNED SIZING (Phase-2 audit fix): size_culvert now bumps auto-sized
# members 50 mm at a time until the design passes its own IRS CBC checks.
# Post-bump sized values against the family:
#   (4.0, 3.0, 2.5) -> 400/400/350 — no bump (exactly the family values)
#   (3.0, 3.0, 2.0) -> 300/300/300 — no bump (exactly the family values)
#   (5.0, 4.0, 3.0) -> 500/550/450 — bottom slab shear-governed 500 -> 550 mm
#                      (tau was 0.601 vs 0.60 permissible); 550 vs the family
#                      500 sits EXACTLY at the +10 % tolerance edge — kept
#                      honest below with <=, not rounded away.
# ==============================================================================

V2_TOLERANCE = 0.10  # +/-10 % per the V2 fixture contract

RDSO_B10152R_FAMILY_MM = {
    # (clear_span_m, clear_height_m, cushion_m): (top slab, bottom slab, wall)
    (4.0, 3.0, 2.5): (400.0, 400.0, 350.0),  # the canonical demo box
    (3.0, 3.0, 2.0): (300.0, 300.0, 300.0),
    (5.0, 4.0, 3.0): (500.0, 500.0, 450.0),
}


@pytest.mark.parametrize("span_height_cushion,family_mm", sorted(RDSO_B10152R_FAMILY_MM.items()))
def test_v2_engine_sized_thicknesses_match_the_rdso_family_within_10_percent(
    span_height_cushion, family_mm
):
    span, height, cushion = span_height_cushion
    params = CulvertParams(clear_span_m=span, clear_height_m=height, cushion_m=cushion)

    geometry = size_culvert(params).geometry

    sized = (
        geometry.top_slab_thickness_mm,
        geometry.bottom_slab_thickness_mm,
        geometry.wall_thickness_mm,
    )
    for sized_mm, family_value_mm in zip(sized, family_mm):
        assert abs(sized_mm - family_value_mm) / family_value_mm <= V2_TOLERANCE, (
            f"{span_height_cushion}: sized {sized_mm} mm vs RDSO family {family_value_mm} mm"
        )


def test_v2_canonical_family_sized_sections_pass_all_member_checks(canonical_output):
    """Self-consistency: the thicknesses our sizing rules produce satisfy our
    own IRS CBC working-stress checks for the canonical family case."""
    assert all(c.status == "PASS" for c in canonical_output.checks)
