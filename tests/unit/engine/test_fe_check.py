"""Fixture V4 — independent FE cross-check agrees with the closed form within ±5%.

MARKED AS FIXTURE V4 (spec/capabilities/irs-engine.md, shared with
spec/capabilities/proof-check.md item 11): every test named ``test_v4_*`` is
part of the named validation fixture the Phase 2 gate runs. The FE model here
is anaStruct 1.7.0, rebuilt ONLY from ``AnalysisResult.load_cases`` +
``frame_model`` — never from the closed-form solver's internals — so agreement
is a genuine independent check, not a restatement.

Runs through the REAL 25t Loading-2008 tables (``engine.loading``) — no fakes:
V4 must certify the same numbers the production pipeline produces.

Headless discipline: ``engine.fe_check`` selects the matplotlib Agg backend at
module top, before any pyplot import — these tests must pass with no display
and with ``MPLBACKEND`` unset.
"""

import time
from pathlib import Path

import pytest

from domain.culvert import CulvertParams
from engine import size_culvert
from engine.analysis import analyse_frame
from engine.fe_check import (
    ELEMENTS_PER_MEMBER,
    FeComparison,
    ForceComparison,
    _comparison_row,
    cross_check,
)

CANONICAL = {"clear_span_m": 4.0, "clear_height_m": 3.0, "cushion_m": 2.5}
V4_TOL_PCT = 5.0  # ±5 % per the V4 fixture contract


def _run_cross_check(out_dir: Path, **param_overrides):
    params = CulvertParams(**{**CANONICAL, **param_overrides})
    geometry = size_culvert(params).geometry
    analysis = analyse_frame(params, geometry)
    fe = cross_check(params, geometry, analysis, out_dir)
    return params, geometry, analysis, fe


@pytest.fixture(scope="module")
def canonical(tmp_path_factory):
    """One canonical 4/3/2.5 cross-check shared by the read-only assertions."""
    out_dir = tmp_path_factory.mktemp("fe_canonical")
    params, geometry, analysis, fe = _run_cross_check(out_dir)
    return params, geometry, analysis, out_dir, fe


# --- V4 core: agreement, self-equilibration, sign convention ------------------


def test_v4_canonical_case_agrees_within_five_percent(canonical):
    _, _, _, _, fe = canonical

    assert isinstance(fe, FeComparison)
    assert fe.tolerance_pct == V4_TOL_PCT
    assert fe.within_tolerance is True
    assert 0.0 <= fe.agreement_pct <= V4_TOL_PCT
    # the achieved figure, printed for the gate log (visible with -s / on failure)
    print(f"\nV4 canonical 4/3/2.5 achieved FE agreement: {fe.agreement_pct:.4f}% "
          f"(governing: {fe.governing})")
    for row in fe.comparisons:
        if row.included:
            assert row.diff_pct is not None
            assert row.diff_pct <= V4_TOL_PCT, (
                f"{row.combination}/{row.member}/{row.section} {row.quantity}: "
                f"cf={row.closed_form:.3f} fe={row.fe:.3f} diff={row.diff_pct:.2f}%"
            )


def test_v4_every_combination_member_and_section_is_compared(canonical):
    _, _, analysis, _, fe = canonical

    combination_names = {c.name for c in analysis.combinations}
    assert set(fe.combinations_checked) == combination_names
    # 3 members x (3 moment sections + 2 shear sections) per combination
    assert len(fe.comparisons) == len(combination_names) * 3 * 5
    for member in ("top_slab", "bottom_slab", "wall"):
        sections = {
            (r.section, r.quantity) for r in fe.comparisons if r.member == member
        }
        assert sections == {
            ("start", "moment"), ("midspan", "moment"), ("end", "moment"),
            ("start", "shear"), ("end", "shear"),
        }
    # the comparison is real: closed-form and FE values are actual numbers
    significant = [r for r in fe.comparisons if r.included]
    assert len(significant) >= 40
    assert any(abs(r.closed_form) > 50 for r in significant)


def test_v4_fe_model_is_self_equilibrated_reactions_vanish(canonical):
    _, _, _, _, fe = canonical

    # the minimal supports exist only to remove rigid-body modes: the load set
    # (incl. the uniform base reaction) must balance itself like-for-like
    assert fe.reaction_residual_kn < 0.01
    assert any("self-equilibrated" in note for note in fe.notes)


def test_v4_sign_convention_maps_tension_inside_positive(canonical):
    _, _, _, _, fe = canonical

    # gravity-dominated case: slab midspans sag (tension inside, +), corners
    # hog (tension outside, -) — the FE values must reproduce the DIRECTION,
    # not just the magnitude (this is the sign-convention mapping proof)
    box_empty = next(n for n in fe.combinations_checked if "Box empty" in n)
    rows = {
        (r.member, r.section, r.quantity): r
        for r in fe.comparisons
        if r.combination == box_empty
    }
    assert rows[("top_slab", "midspan", "moment")].fe > 0
    assert rows[("bottom_slab", "midspan", "moment")].fe > 0
    assert rows[("top_slab", "start", "moment")].fe < 0
    assert rows[("bottom_slab", "start", "moment")].fe < 0
    # every significant moment agrees in sign with the closed form
    for row in fe.comparisons:
        if row.quantity == "moment" and row.included and abs(row.closed_form) > 5.0:
            assert row.fe * row.closed_form > 0, (
                f"sign flip at {row.combination}/{row.member}/{row.section}: "
                f"cf={row.closed_form:.3f} fe={row.fe:.3f}"
            )
    # left/right wall mapped through opposite sign factors must coincide
    assert fe.wall_symmetry_residual < 1e-6


def test_v4_governing_quantity_is_a_real_compared_row(canonical):
    _, _, _, _, fe = canonical

    assert any(name in fe.governing for name in fe.combinations_checked)
    assert any(member in fe.governing for member in ("top_slab", "bottom_slab", "wall"))
    assert fe.solver == "anastruct 1.7.0"
    assert fe.elements_per_member == ELEMENTS_PER_MEMBER >= 8


# --- V4 hard cases: agreement is independent of design adequacy ---------------


def test_v4_under_designed_200mm_top_slab_still_agrees(tmp_path):
    # the deliberately thin slab fails the CBC checks (another slice's job) but
    # the FE cross-check must still certify the ANALYSIS to within 5%
    out_dir = tmp_path / "nested" / "fe_thin"  # also proves out_dir creation
    _, geometry, _, fe = _run_cross_check(out_dir, top_slab_thickness_mm=200)

    assert geometry.top_slab_thickness_mm == 200
    assert fe.within_tolerance is True
    assert fe.agreement_pct <= V4_TOL_PCT
    print(f"\nV4 under-designed (200 mm top slab) achieved FE agreement: "
          f"{fe.agreement_pct:.4f}%")
    assert (out_dir / "bmd.svg").is_file()
    assert (out_dir / "sfd.svg").is_file()


def test_v4_zero_cushion_boundary_case_completes_and_agrees(tmp_path):
    _, _, _, fe = _run_cross_check(tmp_path / "fe_zero_cushion", cushion_m=0.0)

    assert fe.within_tolerance is True
    assert fe.agreement_pct <= V4_TOL_PCT


# --- diagrams: real vector SVGs, labelled, no raster ---------------------------


def test_bmd_and_sfd_svgs_are_real_labelled_vector_files(canonical):
    _, _, _, out_dir, fe = canonical

    for filename, unit in (("bmd.svg", "kN·m per m strip"), ("sfd.svg", "kN per m strip")):
        path = out_dir / filename
        assert path.is_file(), f"{filename} was not written"
        content = path.read_text()
        assert "<svg" in content
        assert path.stat().st_size > 2048, f"{filename} suspiciously small"
        assert "<image" not in content, f"{filename} contains a raster blob"
        # labelled: title with units + the independent-FE caption
        assert "Independent FE re-solve" in content
        assert unit in content
        assert fe.diagram_combination in content


def test_diagram_combination_governs_the_envelope(canonical):
    _, _, analysis, _, fe = canonical

    assert fe.diagram_combination in {c.name for c in analysis.combinations}
    governing_envelope = max(
        (max(abs(e.max_moment_knm), abs(e.min_moment_knm)), e) for e in analysis.envelopes
    )[1]
    expected = (
        governing_envelope.max_moment_combination
        if abs(governing_envelope.max_moment_knm) >= abs(governing_envelope.min_moment_knm)
        else governing_envelope.min_moment_combination
    )
    assert fe.diagram_combination == expected


# --- determinism & runtime -----------------------------------------------------


def test_cross_check_is_deterministic_identical_numbers(canonical, tmp_path):
    params, geometry, analysis, _, first = canonical

    second = cross_check(params, geometry, analysis, tmp_path / "fe_again")

    assert second.model_dump() == first.model_dump()


def test_cross_check_completes_in_under_five_seconds(tmp_path):
    params = CulvertParams(**CANONICAL)
    geometry = size_culvert(params).geometry
    analysis = analyse_frame(params, geometry)

    started = time.perf_counter()
    cross_check(params, geometry, analysis, tmp_path / "fe_timed")
    elapsed = time.perf_counter() - started

    assert elapsed < 5.0, f"cross_check took {elapsed:.2f}s"


# --- error paths: inconsistent AnalysisResult fails loudly ----------------------


def test_empty_combinations_raise_a_clear_value_error(canonical, tmp_path):
    params, geometry, analysis, _, _ = canonical
    broken = analysis.model_copy(update={"combinations": [], "member_forces": []})

    with pytest.raises(ValueError, match="no load combinations"):
        cross_check(params, geometry, broken, tmp_path / "fe_broken")


def test_combination_referencing_an_unknown_case_raises(canonical, tmp_path):
    params, geometry, analysis, _, _ = canonical
    broken = analysis.model_copy(deep=True)
    broken.combinations[0].case_factors = {"NO_SUCH_CASE": 1.0}

    with pytest.raises(ValueError, match="NO_SUCH_CASE"):
        cross_check(params, geometry, broken, tmp_path / "fe_broken")


def test_missing_member_forces_for_a_combination_raises(canonical, tmp_path):
    params, geometry, analysis, _, _ = canonical
    broken = analysis.model_copy(update={"member_forces": analysis.member_forces[1:]})

    with pytest.raises(ValueError, match="no member forces"):
        cross_check(params, geometry, broken, tmp_path / "fe_broken")


# --- significance floor (unit level) --------------------------------------------


def test_rows_below_the_significance_floor_are_reported_but_excluded():
    near_zero = _comparison_row("C", "wall", "midspan", "moment", 0.2, 0.9, floor=1.0)
    significant = _comparison_row("C", "wall", "midspan", "moment", 10.0, 10.4, floor=1.0)

    assert isinstance(near_zero, ForceComparison)
    assert near_zero.included is False
    assert near_zero.diff_pct is None  # a 350% "diff" on 0.2 kN*m would be noise
    assert significant.included is True
    assert significant.diff_pct == pytest.approx(4.0)
