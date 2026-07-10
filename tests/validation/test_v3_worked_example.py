"""Fixture V3 — published railway box-culvert worked example (irs-engine.md).

SOURCE (named per the fixture contract): IRICEN course-material lineage —
"Design of Box Culverts / Bridges" course notes, IRICEN Pune, single-cell RCC
box worked example (equal-member square box, unit-strip closed-frame moment
coefficients for (i) the balanced vertical load pair, (ii) uniform lateral
pressure and (iii) triangular earth pressure), as tabulated in the IRICEN
notes and in Reynolds & Steedman closed-rectangular-frame tables.

TRANSCRIPTION HONESTY (same discipline as the loading-table slice): the
expected values below were INDEPENDENTLY RE-DERIVED by hand slope-deflection
in this file's comments — they are the classical coefficients the IRICEN
worked example reproduces. Verify the numbers against the printed source
before demo day.

Hand derivation (equal square frame, side L, all members EI, symmetric loads;
theta_A = top-corner rotation, theta_B = bottom-corner rotation, s = 2EI/L):

  joint A:  3*s*theta_A + s*theta_B = -(FEM_A_slab + FEM_A_wall)
  joint B:  s*theta_A + 3*s*theta_B = -(FEM_B_slab + FEM_B_wall)

  (i)  vertical pair (w down on top, w up on bottom):
       theta_B = -theta_A  ->  M_corner = -w*L^2/24, slab midspans = +w*L^2/12
  (ii) uniform lateral p on both walls:
       theta_B = -theta_A  ->  M_corner = -p*H^2/24, wall midheight = +p*H^2/12
  (iii) triangular lateral, 0 at top -> p at bottom (FEM p*H^2/30 top, p*H^2/20
       bottom):  8*s*theta_A = -3*p*H^2/20  ->  M_top = -3*p*H^2/160,
       M_bottom = -11*p*H^2/480
  (iv) DL of the example box (0.3 m members, gamma_c = 25 kN/m^3, L = 3.3 m):
       top w = 7.5, bottom net = 22.5 up  ==  pair(7.5) + bottom-only(15 up);
       bottom-only q (mirror of top-only):  M_bottom = -5*q*L^2/96,
       M_top = +q*L^2/96, bottom mid = +7*q*L^2/96, top mid = +q*L^2/96
       ->  M_top = -1.7016, M_bottom = -11.9109, top mid = +8.5078,
           bottom mid = +18.7172 kN*m/m.

Tolerance: +/-5 % per the V3 fixture contract.
"""

import time

import pytest

from domain.culvert import BoxGeometry, CulvertParams
from engine.analysis import analyse_frame, build_frame_model, solve_closed_frame

V3_TOL = 0.05  # +/-5 % per spec/capabilities/irs-engine.md

WORKED_EXAMPLE_PARAMS = CulvertParams(
    clear_span_m=3.0,
    clear_height_m=3.0,
    cushion_m=2.5,
    top_slab_thickness_mm=300,
    bottom_slab_thickness_mm=300,
    wall_thickness_mm=300,
)
WORKED_EXAMPLE_GEOMETRY = BoxGeometry(
    clear_span_m=3.0,
    clear_height_m=3.0,
    cushion_m=2.5,
    top_slab_thickness_mm=300,
    bottom_slab_thickness_mm=300,
    wall_thickness_mm=300,
    haunch_mm=150,
    external_width_m=3.6,
    external_height_m=3.6,
    barrel_length_m=31.25,  # 6.85 + 2*2.0*(2.5+3.6)
)


def _frame():
    return build_frame_model(WORKED_EXAMPLE_PARAMS, WORKED_EXAMPLE_GEOMETRY)


def _member(solution, name):
    return next(m for m in solution.members if m.member == name)


# --- worked-example load cases against the published coefficients -----------


def test_v3_vertical_load_pair_case_matches_published_coefficients():
    w, length = 100.0, 3.3

    solution = solve_closed_frame(_frame(), w, w, 0.0, 0.0)

    wl2 = w * length**2  # 1089
    assert solution.m_top_corner_knm == pytest.approx(-wl2 / 24, rel=V3_TOL)  # -45.375
    assert solution.m_bottom_corner_knm == pytest.approx(-wl2 / 24, rel=V3_TOL)
    assert _member(solution, "top_slab").midspan_moment_knm == pytest.approx(
        wl2 / 12, rel=V3_TOL
    )  # +90.75
    assert _member(solution, "bottom_slab").midspan_moment_knm == pytest.approx(
        wl2 / 12, rel=V3_TOL
    )


def test_v3_uniform_lateral_pressure_case_matches_published_coefficients():
    p, height = 50.0, 3.3

    solution = solve_closed_frame(_frame(), 0.0, 0.0, p, p)

    ph2 = p * height**2  # 544.5
    assert solution.m_top_corner_knm == pytest.approx(-ph2 / 24, rel=V3_TOL)  # -22.6875
    assert _member(solution, "wall").midspan_moment_knm == pytest.approx(
        ph2 / 12, rel=V3_TOL
    )  # +45.375


def test_v3_triangular_earth_pressure_case_matches_published_coefficients():
    p, height = 48.0, 3.3

    solution = solve_closed_frame(_frame(), 0.0, 0.0, 0.0, p)

    ph2 = p * height**2  # 522.72
    assert solution.m_top_corner_knm == pytest.approx(-3 * ph2 / 160, rel=V3_TOL)  # -9.801
    assert solution.m_bottom_corner_knm == pytest.approx(-11 * ph2 / 480, rel=V3_TOL)  # -11.979


# --- full path through the REAL loading interface ----------------------------


def test_v3_dl_case_through_the_full_engine_matches_hand_values():
    pytest.importorskip(
        "engine.loading", reason="p2-loading-tables slice not landed yet — rerun at gate"
    )

    result = analyse_frame(WORKED_EXAMPLE_PARAMS, WORKED_EXAMPLE_GEOMETRY)

    dl = next(c for c in result.load_cases if c.name == "DL")
    assert dl.top_slab_udl_kn_m2 == pytest.approx(7.5, rel=V3_TOL)
    assert dl.bottom_slab_net_udl_kn_m2 == pytest.approx(22.5, rel=V3_TOL)

    solution = solve_closed_frame(
        result.frame_model,
        dl.top_slab_udl_kn_m2,
        dl.bottom_slab_net_udl_kn_m2,
        dl.wall_pressure_top_kn_m2,
        dl.wall_pressure_bottom_kn_m2,
    )
    assert solution.m_top_corner_knm == pytest.approx(-1.7016, rel=V3_TOL)
    assert solution.m_bottom_corner_knm == pytest.approx(-11.9109, rel=V3_TOL)
    assert _member(solution, "top_slab").midspan_moment_knm == pytest.approx(8.5078, rel=V3_TOL)
    assert _member(solution, "bottom_slab").midspan_moment_knm == pytest.approx(
        18.7172, rel=V3_TOL
    )


def test_v3_live_load_values_flow_from_the_real_25t_tables_with_citation():
    loading = pytest.importorskip(
        "engine.loading", reason="p2-loading-tables slice not landed yet — rerun at gate"
    )

    result = analyse_frame(WORKED_EXAMPLE_PARAMS, WORKED_EXAMPLE_GEOMETRY)

    ll = next(c for c in result.load_cases if c.name == "LL+CDA")
    assert ll.top_slab_udl_kn_m2 > 0
    std = loading.get_loading_standard("25t-2008")
    assert any(std.citation in c for c in ll.citations)
    assert any(std.citation in s.citation for s in result.trail)


def test_v3_zero_cushion_hard_case_with_real_tables_completes():
    pytest.importorskip(
        "engine.loading", reason="p2-loading-tables slice not landed yet — rerun at gate"
    )
    params = CulvertParams(clear_span_m=4.0, clear_height_m=3.0, cushion_m=0.0)
    geometry = BoxGeometry(
        clear_span_m=4.0,
        clear_height_m=3.0,
        cushion_m=0.0,
        top_slab_thickness_mm=400,
        bottom_slab_thickness_mm=400,
        wall_thickness_mm=350,
        haunch_mm=150,
        external_width_m=4.7,
        external_height_m=3.8,
        barrel_length_m=22.05,
    )

    result = analyse_frame(params, geometry)

    ll = next(c for c in result.load_cases if c.name == "LL+CDA")
    assert ll.top_slab_udl_kn_m2 > 0
    assert result.envelopes


def test_v3_canonical_analysis_with_real_tables_runs_under_two_seconds():
    pytest.importorskip(
        "engine.loading", reason="p2-loading-tables slice not landed yet — rerun at gate"
    )
    params = CulvertParams(clear_span_m=4.0, clear_height_m=3.0, cushion_m=2.5)
    geometry = BoxGeometry(
        clear_span_m=4.0,
        clear_height_m=3.0,
        cushion_m=2.5,
        top_slab_thickness_mm=400,
        bottom_slab_thickness_mm=400,
        wall_thickness_mm=350,
        haunch_mm=150,
        external_width_m=4.7,
        external_height_m=3.8,
        barrel_length_m=32.05,
    )

    started = time.perf_counter()
    analyse_frame(params, geometry)
    elapsed = time.perf_counter() - started

    assert elapsed < 2.0, f"analyse_frame took {elapsed:.2f}s"
