"""Closed-form rigid-frame analysis — solver exactness, statics closure, envelopes.

Solver assertions are against independently hand-derived slope-deflection
results for the symmetric closed rectangular frame (derivations in
tests/validation/test_v3_worked_example.py). Unit tests fake the loading
interface; the real one runs in tests/validation/.
"""

import time

import pytest

from domain.culvert import AnalysisResult, CulvertParams, FrameModel
from engine import size_culvert
from engine.analysis import analyse_frame, build_frame_model, solve_closed_frame
from engine.loads import frame_centreline_dimensions

CANONICAL = {"clear_span_m": 4.0, "clear_height_m": 3.0, "cushion_m": 2.5}
STATIC_RTOL = 1e-3  # 0.1 % closure requirement


class FakeLoadingStandard:
    """Pinned p2-loading-tables interface, faked for unit isolation."""

    citation = "FAKE 25t Loading-2008 table (unit-test stub, ACS n/a)"

    def __init__(self, bm_kn: float = 1000.0, shear_kn: float = 1300.0, cda_value: float = 0.25):
        self._bm = bm_kn
        self._shear = shear_kn
        self._cda = cda_value
        self.cda_calls: list[tuple[float, float]] = []

    def eudl_bm_kn(self, loaded_length_m: float) -> float:
        return self._bm

    def eudl_shear_kn(self, loaded_length_m: float) -> float:
        return self._shear

    def cda(self, loaded_length_m: float, cushion_m: float = 0.0) -> float:
        self.cda_calls.append((loaded_length_m, cushion_m))
        return self._cda


def _square_frame(side_m: float = 3.3, thickness_m: float = 0.3) -> FrameModel:
    i = thickness_m**3 / 12
    return FrameModel(
        span_centreline_m=side_m,
        height_centreline_m=side_m,
        strip_width_m=1.0,
        top_slab_thickness_mm=thickness_m * 1000,
        bottom_slab_thickness_mm=thickness_m * 1000,
        wall_thickness_mm=thickness_m * 1000,
        i_top_m4=i,
        i_bottom_m4=i,
        i_wall_m4=i,
        modulus_note="ratios only",
        boundary_note="test frame",
        sign_convention="tension-inside positive",
    )


def _analyse_canonical(fake=None):
    params = CulvertParams(**CANONICAL)
    geometry = size_culvert(params).geometry
    return params, geometry, analyse_frame(
        params, geometry, loading_standard=fake or FakeLoadingStandard()
    )


def _member(forces, name):
    return next(m for m in forces.members if m.member == name)


def _combined_loads(result, combo):
    """Reconstruct the combined member loads of a combination from the load cases."""
    by_name = {c.name: c for c in result.load_cases}
    w_top = sum(f * by_name[n].top_slab_udl_kn_m2 for n, f in combo.case_factors.items())
    w_bot = sum(f * by_name[n].bottom_slab_net_udl_kn_m2 for n, f in combo.case_factors.items())
    p_top = sum(f * by_name[n].wall_pressure_top_kn_m2 for n, f in combo.case_factors.items())
    p_bot = sum(f * by_name[n].wall_pressure_bottom_kn_m2 for n, f in combo.case_factors.items())
    return w_top, w_bot, p_top, p_bot


# --- exact solver vs hand-derived closed-frame results ----------------------


def test_vertical_load_pair_on_equal_square_frame_matches_wl2_over_24_and_12():
    frame = _square_frame()
    w, length = 100.0, 3.3

    solution = solve_closed_frame(frame, w_top_kn_m2=w, w_bottom_kn_m2=w,
                                  p_wall_top_kn_m2=0.0, p_wall_bottom_kn_m2=0.0)

    wl2 = w * length**2
    assert solution.m_top_corner_knm == pytest.approx(-wl2 / 24, rel=1e-9)
    assert solution.m_bottom_corner_knm == pytest.approx(-wl2 / 24, rel=1e-9)
    assert _member(solution, "top_slab").midspan_moment_knm == pytest.approx(wl2 / 12, rel=1e-9)
    assert _member(solution, "bottom_slab").midspan_moment_knm == pytest.approx(wl2 / 12, rel=1e-9)
    # fixed-end sanity: corner magnitude below the fully-fixed wL^2/12 < wL^2/8 bound
    assert abs(solution.m_top_corner_knm) < wl2 / 8


def test_uniform_lateral_pressure_on_equal_square_frame_matches_ph2_over_24_and_12():
    frame = _square_frame()
    p, height = 50.0, 3.3

    solution = solve_closed_frame(frame, 0.0, 0.0, p, p)

    ph2 = p * height**2
    assert solution.m_top_corner_knm == pytest.approx(-ph2 / 24, rel=1e-9)
    assert solution.m_bottom_corner_knm == pytest.approx(-ph2 / 24, rel=1e-9)
    assert _member(solution, "wall").midspan_moment_knm == pytest.approx(ph2 / 12, rel=1e-9)


def test_triangular_lateral_pressure_matches_hand_slope_deflection_coefficients():
    # Hand solve (equal square frame, triangle 0 at top -> p at bottom, both walls):
    # M_top = -3 p H^2 / 160, M_bottom = -11 p H^2 / 480.
    frame = _square_frame()
    p, height = 48.0, 3.3

    solution = solve_closed_frame(frame, 0.0, 0.0, 0.0, p)

    ph2 = p * height**2
    assert solution.m_top_corner_knm == pytest.approx(-3 * ph2 / 160, rel=1e-9)
    assert solution.m_bottom_corner_knm == pytest.approx(-11 * ph2 / 480, rel=1e-9)


def test_rigid_walls_drive_slab_corners_to_the_fixed_end_moment():
    frame = _square_frame().model_copy(update={"i_wall_m4": 1e6})
    w, length = 100.0, 3.3

    solution = solve_closed_frame(frame, w, 0.0, 0.0, 0.0)

    assert solution.m_top_corner_knm == pytest.approx(-w * length**2 / 12, rel=1e-3)


def test_flexible_walls_release_the_slab_to_simply_supported():
    frame = _square_frame().model_copy(update={"i_wall_m4": 1e-12})
    w, length = 100.0, 3.3

    solution = solve_closed_frame(frame, w, 0.0, 0.0, 0.0)

    assert solution.m_top_corner_knm == pytest.approx(0.0, abs=1e-6)
    assert _member(solution, "top_slab").midspan_moment_knm == pytest.approx(
        w * length**2 / 8, rel=1e-6
    )


def test_solver_reports_joint_residuals_below_a_tenth_of_a_percent():
    frame = _square_frame()

    solution = solve_closed_frame(frame, 87.3, 55.1, 21.7, 64.9)

    scale = max(abs(solution.m_top_corner_knm), abs(solution.m_bottom_corner_knm), 1.0)
    assert abs(solution.residual_top_knm) < STATIC_RTOL * scale
    assert abs(solution.residual_bottom_knm) < STATIC_RTOL * scale


# --- full analyse_frame: statics closure on every combination ---------------


def test_every_combination_balances_joints_to_within_a_tenth_of_a_percent():
    _, _, result = _analyse_canonical()

    for forces in result.member_forces:
        top, bottom, wall = (
            _member(forces, "top_slab"),
            _member(forces, "bottom_slab"),
            _member(forces, "wall"),
        )
        scale = max(abs(top.end_moment_start_knm), abs(bottom.end_moment_start_knm), 1.0)
        # moment continuity around each corner (design convention: shared value)
        assert abs(top.end_moment_start_knm - wall.end_moment_end_knm) < STATIC_RTOL * scale
        assert abs(bottom.end_moment_start_knm - wall.end_moment_start_knm) < STATIC_RTOL * scale


def test_every_load_case_and_combination_closes_vertical_equilibrium():
    _, geometry, result = _analyse_canonical()
    span_c, _ = frame_centreline_dimensions(geometry)

    for case in result.load_cases:
        total_down = (
            case.top_slab_udl_kn_m2 * span_c
            + 2 * case.wall_axial_kn_per_m
            + case.bottom_slab_applied_udl_kn_m2 * span_c
        )
        assert case.base_reaction_kn_m2 * span_c == pytest.approx(total_down, abs=1e-9)


def test_symmetric_loading_gives_symmetric_slab_moments_and_antisymmetric_shears():
    _, _, result = _analyse_canonical()

    for forces in result.member_forces:
        for name in ("top_slab", "bottom_slab"):
            member = _member(forces, name)
            assert member.end_moment_start_knm == pytest.approx(member.end_moment_end_knm)
            assert member.end_shear_start_kn == pytest.approx(-member.end_shear_end_kn)


def test_slab_midspan_minus_corner_equals_the_simply_supported_wl2_over_8():
    _, geometry, result = _analyse_canonical()
    span_c, _ = frame_centreline_dimensions(geometry)
    combos = {c.name: c for c in result.combinations}

    for forces in result.member_forces:
        w_top, w_bot, _, _ = _combined_loads(result, combos[forces.combination])
        top, bottom = _member(forces, "top_slab"), _member(forces, "bottom_slab")
        assert top.midspan_moment_knm - top.end_moment_start_knm == pytest.approx(
            w_top * span_c**2 / 8, rel=1e-9
        )
        assert bottom.midspan_moment_knm - bottom.end_moment_start_knm == pytest.approx(
            w_bot * span_c**2 / 8, rel=1e-9
        )


def test_slab_end_shears_equal_half_the_combined_udl_times_span():
    _, geometry, result = _analyse_canonical()
    span_c, _ = frame_centreline_dimensions(geometry)
    combos = {c.name: c for c in result.combinations}

    for forces in result.member_forces:
        w_top, _, _, _ = _combined_loads(result, combos[forces.combination])
        top = _member(forces, "top_slab")
        assert top.end_shear_start_kn == pytest.approx(w_top * span_c / 2, rel=1e-9)


def test_gravity_dominated_case_has_tension_inside_at_midspans_and_outside_at_corners():
    _, _, result = _analyse_canonical()

    box_empty = next(f for f in result.member_forces if "Box empty" in f.combination)
    assert _member(box_empty, "top_slab").midspan_moment_knm > 0
    assert _member(box_empty, "bottom_slab").midspan_moment_knm > 0
    assert _member(box_empty, "top_slab").end_moment_start_knm < 0
    assert _member(box_empty, "bottom_slab").end_moment_start_knm < 0


# --- envelopes ---------------------------------------------------------------


def test_envelope_extremes_match_a_manual_scan_of_the_member_forces():
    _, _, result = _analyse_canonical()

    checks = [
        ("top_slab", "midspan", lambda m: m.midspan_moment_knm),
        ("top_slab", "end", lambda m: m.end_moment_start_knm),
        ("bottom_slab", "midspan", lambda m: m.midspan_moment_knm),
        ("wall", "bottom_end", lambda m: m.end_moment_start_knm),
        ("wall", "top_end", lambda m: m.end_moment_end_knm),
    ]
    for member_name, section_name, getter in checks:
        env = next(
            e for e in result.envelopes if e.member == member_name and e.section == section_name
        )
        values = [getter(_member(f, member_name)) for f in result.member_forces]
        assert env.max_moment_knm == pytest.approx(max(values), rel=1e-9)
        assert env.min_moment_knm == pytest.approx(min(values), rel=1e-9)


def test_envelope_governing_combinations_are_real_combination_names():
    _, _, result = _analyse_canonical()

    combo_names = {c.name for c in result.combinations}
    for env in result.envelopes:
        assert env.max_moment_combination in combo_names
        assert env.min_moment_combination in combo_names
        assert env.max_shear_combination in combo_names
        assert env.max_abs_shear_kn >= 0


def test_haunch_face_sections_sit_between_corner_and_midspan():
    _, geometry, result = _analyse_canonical()
    span_c, height_c = frame_centreline_dimensions(geometry)

    slab_face = next(
        e for e in result.envelopes if e.member == "top_slab" and e.section == "haunch_face"
    )
    assert 0 < slab_face.position_m <= span_c / 2
    # parabolic slab diagram is monotone corner -> midspan, so face is bounded
    env_by_section = {
        e.section: e for e in result.envelopes if e.member == "top_slab"
    }
    upper = max(env_by_section["end"].max_moment_knm, env_by_section["midspan"].max_moment_knm)
    lower = min(env_by_section["end"].min_moment_knm, env_by_section["midspan"].min_moment_knm)
    assert lower - 1e-9 <= slab_face.max_moment_knm <= upper + 1e-9

    wall_sections = {e.section for e in result.envelopes if e.member == "wall"}
    assert {"bottom_end", "bottom_haunch_face", "midheight", "top_haunch_face", "top_end"} \
        <= wall_sections


# --- result shape, trail, hard cases -----------------------------------------


def test_result_is_a_fully_populated_analysis_result():
    _, _, result = _analyse_canonical()

    assert isinstance(result, AnalysisResult)
    required = {"DL", "FILL", "SIDL", "LL+CDA", "EP_at_rest", "EP_active",
                "LL_surcharge", "LL_surcharge_active", "WATER"}
    assert required <= {c.name for c in result.load_cases}
    assert len(result.combinations) >= 4
    assert len(result.member_forces) == len(result.combinations)
    assert result.frame_model.span_centreline_m == pytest.approx(4.35)
    assert result.frame_model.height_centreline_m == pytest.approx(3.4)
    assert result.frame_model.i_wall_m4 == pytest.approx(0.35**3 / 12)
    assert result.assumptions
    assert result.trail


def test_frame_model_matches_the_geometry_it_was_built_from():
    params = CulvertParams(**CANONICAL)
    geometry = size_culvert(params).geometry

    frame = build_frame_model(params, geometry)

    assert frame.top_slab_thickness_mm == geometry.top_slab_thickness_mm
    assert frame.strip_width_m == 1.0
    assert "tension" in frame.sign_convention.lower()


def test_every_trail_step_is_fully_cited_and_corner_moments_are_in_the_trail():
    _, _, result = _analyse_canonical()

    assert len(result.trail) >= 50
    for step in result.trail:
        assert step.citation.strip()
        assert step.formula.strip()
        assert step.unit.strip()
    trail_values = {round(s.value, 6) for s in result.trail}
    first = result.member_forces[0]
    assert round(_member(first, "top_slab").end_moment_start_knm, 6) in trail_values
    assert round(_member(first, "top_slab").midspan_moment_knm, 6) in trail_values


def test_zero_cushion_hard_case_completes_end_to_end():
    params = CulvertParams(clear_span_m=4.0, clear_height_m=3.0, cushion_m=0.0)
    geometry = size_culvert(params).geometry
    fake = FakeLoadingStandard()

    result = analyse_frame(params, geometry, loading_standard=fake)

    assert isinstance(result, AnalysisResult)
    assert fake.cda_calls[0][1] == 0.0
    ll = next(c for c in result.load_cases if c.name == "LL+CDA")
    assert ll.top_slab_udl_kn_m2 > 0


def test_analysis_is_deterministic_byte_identical():
    _, _, first = _analyse_canonical()
    _, _, second = _analyse_canonical()

    assert first.model_dump_json() == second.model_dump_json()


def test_canonical_analysis_completes_in_under_two_seconds():
    params = CulvertParams(**CANONICAL)
    geometry = size_culvert(params).geometry
    fake = FakeLoadingStandard()

    started = time.perf_counter()
    analyse_frame(params, geometry, loading_standard=fake)
    elapsed = time.perf_counter() - started

    assert elapsed < 2.0, f"analyse_frame took {elapsed:.2f}s"
