"""Load-case builder — DL/FILL/SIDL/LL+CDA/EP/LL-surcharge/WATER per IRS practice.

Unit tests use a FAKE LoadingStandard (pinned interface shape) so this file
never depends on the concurrently-built `engine.loading` slice; the real
interface is exercised in tests/validation/.
"""

import math

import pytest

from domain.culvert import CulvertParams
from engine import size_culvert
from engine.loads import (
    BALLAST_DEPTH_M,
    DISPERSAL_SLOPE_H_PER_V,
    GAMMA_BALLAST_KN_M3,
    GAMMA_CONCRETE_KN_M3,
    GAMMA_WATER_KN_M3,
    LL_SURCHARGE_FORMATION_KN_M2,
    MIN_LOADED_LENGTH_M,
    SLEEPER_LENGTH_M,
    TRACK_PWAY_KN_PER_M,
    build_load_cases,
    dispersed_loaded_length_m,
    frame_centreline_dimensions,
    lateral_distribution_width_m,
)

CANONICAL = {"clear_span_m": 4.0, "clear_height_m": 3.0, "cushion_m": 2.5}


class FakeLoadingStandard:
    """Pinned p2-loading-tables interface, faked for unit isolation."""

    citation = "FAKE 25t Loading-2008 table (unit-test stub, ACS n/a)"

    def __init__(self, bm_kn: float = 1000.0, shear_kn: float = 1300.0, cda_value: float = 0.25):
        self._bm = bm_kn
        self._shear = shear_kn
        self._cda = cda_value
        self.cda_calls: list[tuple[float, float]] = []
        self.bm_calls: list[float] = []

    def eudl_bm_kn(self, loaded_length_m: float) -> float:
        self.bm_calls.append(loaded_length_m)
        return self._bm

    def eudl_shear_kn(self, loaded_length_m: float) -> float:
        return self._shear

    def cda(self, loaded_length_m: float, cushion_m: float = 0.0) -> float:
        self.cda_calls.append((loaded_length_m, cushion_m))
        return self._cda


def _canonical_build(fake=None):
    params = CulvertParams(**CANONICAL)
    geometry = size_culvert(params).geometry
    fake = fake or FakeLoadingStandard()
    return params, geometry, fake, build_load_cases(params, geometry, loading_standard=fake)


def _case(build, name):
    matches = [c for c in build.cases if c.name == name]
    assert matches, f"load case {name!r} missing from {[c.name for c in build.cases]}"
    return matches[0]


# --- geometry helpers -------------------------------------------------------


def test_frame_centreline_dimensions_are_clear_opening_plus_half_members():
    _, geometry, _, _ = _canonical_build()

    span_c, height_c = frame_centreline_dimensions(geometry)

    assert span_c == pytest.approx(4.0 + 0.35)  # clear span + wall thickness
    assert height_c == pytest.approx(3.0 + (0.4 + 0.4) / 2)  # + (t_top + t_bot)/2


def test_dispersed_loaded_length_adds_slope_times_depth_each_side():
    # depth = cushion + ballast; extension = 2 * 0.5H:1V * depth
    length = dispersed_loaded_length_m(4.35, 2.5)

    assert length == pytest.approx(4.35 + 2 * DISPERSAL_SLOPE_H_PER_V * (2.5 + BALLAST_DEPTH_M))


def test_dispersed_loaded_length_never_below_the_table_minimum():
    assert dispersed_loaded_length_m(0.2, 0.0) == MIN_LOADED_LENGTH_M


def test_lateral_width_at_zero_cushion_stays_positive_and_sensible():
    width = lateral_distribution_width_m(0.0, barrel_length_m=22.05)

    assert width == pytest.approx(SLEEPER_LENGTH_M + 2 * DISPERSAL_SLOPE_H_PER_V * BALLAST_DEPTH_M)
    assert width > 0


def test_lateral_width_is_capped_by_the_barrel_length():
    assert lateral_distribution_width_m(10.0, barrel_length_m=5.0) == 5.0


# --- dead load / fill / SIDL ------------------------------------------------


def test_dl_case_is_member_self_weight_at_25_kn_m3():
    _, _, _, build = _canonical_build()
    dl = _case(build, "DL")

    assert dl.top_slab_udl_kn_m2 == pytest.approx(GAMMA_CONCRETE_KN_M3 * 0.400)
    assert dl.bottom_slab_applied_udl_kn_m2 == pytest.approx(GAMMA_CONCRETE_KN_M3 * 0.400)
    assert dl.wall_axial_kn_per_m == pytest.approx(GAMMA_CONCRETE_KN_M3 * 0.350 * 3.4)
    assert dl.wall_pressure_top_kn_m2 == 0.0
    assert dl.wall_pressure_bottom_kn_m2 == 0.0


def test_every_case_closes_vertical_equilibrium_with_uniform_base_reaction():
    _, geometry, _, build = _canonical_build()
    span_c, _ = frame_centreline_dimensions(geometry)

    for case in build.cases:
        total_down = (
            case.top_slab_udl_kn_m2 * span_c
            + 2 * case.wall_axial_kn_per_m
            + case.bottom_slab_applied_udl_kn_m2 * span_c
        )
        assert case.base_reaction_kn_m2 * span_c == pytest.approx(total_down, abs=1e-9)
        assert case.bottom_slab_net_udl_kn_m2 == pytest.approx(
            case.base_reaction_kn_m2 - case.bottom_slab_applied_udl_kn_m2
        )


def test_fill_case_is_soil_unit_weight_times_cushion():
    _, _, _, build = _canonical_build()

    assert _case(build, "FILL").top_slab_udl_kn_m2 == pytest.approx(18.0 * 2.5)


def test_fill_case_is_zero_at_zero_cushion():
    params = CulvertParams(clear_span_m=4.0, clear_height_m=3.0, cushion_m=0.0)
    geometry = size_culvert(params).geometry

    build = build_load_cases(params, geometry, loading_standard=FakeLoadingStandard())

    assert _case(build, "FILL").top_slab_udl_kn_m2 == 0.0


def test_sidl_case_is_ballast_plus_track_dispersed_laterally():
    _, geometry, _, build = _canonical_build()
    sidl = _case(build, "SIDL")

    ballast = BALLAST_DEPTH_M * GAMMA_BALLAST_KN_M3
    width = lateral_distribution_width_m(2.5, geometry.barrel_length_m)
    assert sidl.top_slab_udl_kn_m2 == pytest.approx(ballast + TRACK_PWAY_KN_PER_M / width)


# --- live load + CDA --------------------------------------------------------


def test_ll_case_intensity_is_eudl_with_cda_over_dispersed_area():
    _, geometry, fake, build = _canonical_build()
    ll = _case(build, "LL+CDA")

    span_c, _ = frame_centreline_dimensions(geometry)
    loaded = dispersed_loaded_length_m(span_c, 2.5)
    width = lateral_distribution_width_m(2.5, geometry.barrel_length_m)
    expected = 1000.0 * 1 * (1 + 0.25) / (loaded * width)
    assert ll.top_slab_udl_kn_m2 == pytest.approx(expected)


def test_ll_case_calls_cda_with_the_actual_cushion():
    _, _, fake, _ = _canonical_build()

    assert fake.cda_calls, "cda() was never called"
    loaded_length, cushion = fake.cda_calls[0]
    assert cushion == 2.5
    assert loaded_length == pytest.approx(dispersed_loaded_length_m(4.35, 2.5))


def test_ll_case_at_zero_cushion_completes_with_full_cda_and_positive_widths():
    params = CulvertParams(clear_span_m=4.0, clear_height_m=3.0, cushion_m=0.0)
    geometry = size_culvert(params).geometry
    fake = FakeLoadingStandard()

    build = build_load_cases(params, geometry, loading_standard=fake)

    ll = _case(build, "LL+CDA")
    assert ll.top_slab_udl_kn_m2 > 0
    assert fake.cda_calls[0][1] == 0.0  # CDA asked at zero cushion -> full value
    assert dispersed_loaded_length_m(4.35, 0.0) >= 4.35
    assert lateral_distribution_width_m(0.0, geometry.barrel_length_m) > 0


def test_ll_case_carries_the_loading_table_citation():
    _, _, fake, build = _canonical_build()

    assert any(fake.citation in c for c in _case(build, "LL+CDA").citations)


# --- earth pressure, surcharge, water ---------------------------------------


def test_earth_pressure_at_rest_uses_jaky_k0_on_fill_depth():
    _, _, _, build = _canonical_build()
    ep = _case(build, "EP_at_rest")

    k0 = 1 - math.sin(math.radians(30.0))
    depth_top = 2.5 + 0.400 / 2  # cushion + half top slab (centreline node)
    depth_bottom = depth_top + 3.4  # + centreline height
    assert k0 == pytest.approx(0.5)
    assert ep.wall_pressure_top_kn_m2 == pytest.approx(k0 * 18.0 * depth_top)
    assert ep.wall_pressure_bottom_kn_m2 == pytest.approx(k0 * 18.0 * depth_bottom)
    assert ep.top_slab_udl_kn_m2 == 0.0


def test_earth_pressure_active_uses_rankine_ka():
    _, _, _, build = _canonical_build()
    ep = _case(build, "EP_active")

    ka = (1 - math.sin(math.radians(30.0))) / (1 + math.sin(math.radians(30.0)))
    assert ka == pytest.approx(1 / 3)
    assert ep.wall_pressure_top_kn_m2 == pytest.approx(ka * 18.0 * 2.7)
    assert ep.wall_pressure_bottom_kn_m2 == pytest.approx(ka * 18.0 * 6.1)


def test_active_pressure_is_below_at_rest_pressure():
    _, _, _, build = _canonical_build()

    at_rest = _case(build, "EP_at_rest")
    active = _case(build, "EP_active")
    assert active.wall_pressure_bottom_kn_m2 < at_rest.wall_pressure_bottom_kn_m2


def test_ll_surcharge_is_uniform_k_times_equivalent_formation_pressure():
    _, _, _, build = _canonical_build()

    at_rest = _case(build, "LL_surcharge")
    active = _case(build, "LL_surcharge_active")
    assert at_rest.wall_pressure_top_kn_m2 == pytest.approx(0.5 * LL_SURCHARGE_FORMATION_KN_M2)
    assert at_rest.wall_pressure_top_kn_m2 == at_rest.wall_pressure_bottom_kn_m2
    assert active.wall_pressure_top_kn_m2 == pytest.approx(LL_SURCHARGE_FORMATION_KN_M2 / 3)


def test_water_case_pushes_outward_and_has_zero_net_bottom_bending():
    _, _, _, build = _canonical_build()
    water = _case(build, "WATER")

    assert water.wall_pressure_top_kn_m2 == 0.0
    assert water.wall_pressure_bottom_kn_m2 == pytest.approx(-GAMMA_WATER_KN_M3 * 3.0)
    assert water.bottom_slab_applied_udl_kn_m2 == pytest.approx(GAMMA_WATER_KN_M3 * 3.0)
    assert water.bottom_slab_net_udl_kn_m2 == pytest.approx(0.0, abs=1e-9)


# --- combinations, citations, trail, determinism ----------------------------


def test_combinations_cover_box_empty_and_box_full_with_unity_factors():
    _, _, _, build = _canonical_build()

    names = [c.name for c in build.combinations]
    assert any("Box empty" in n for n in names)
    assert any("Box full" in n for n in names)
    case_names = {c.name for c in build.cases}
    for combo in build.combinations:
        assert combo.case_factors, combo.name
        assert set(combo.case_factors) <= case_names
        assert all(f == 1.0 for f in combo.case_factors.values())


def test_combination_set_pairs_ll_with_matching_earth_pressure_variants():
    _, _, _, build = _canonical_build()

    by_name = {c.name: c for c in build.combinations}
    for combo in by_name.values():
        cases = set(combo.case_factors)
        if "EP_at_rest" in cases:
            assert "EP_active" not in cases
        if "LL_surcharge_active" in cases:
            assert "EP_active" in cases


def test_every_case_has_nonempty_citations():
    _, _, _, build = _canonical_build()

    for case in build.cases:
        assert case.citations, case.name
        assert all(c.strip() for c in case.citations)


def test_every_trail_step_is_fully_cited():
    _, _, _, build = _canonical_build()

    assert len(build.trail_steps) >= 20
    for step in build.trail_steps:
        assert step.citation.strip()
        assert step.formula.strip()
        assert step.unit.strip()


def test_rigid_base_uniform_reaction_is_recorded_as_an_assumption():
    _, _, _, build = _canonical_build()

    notes = " ".join(a.note.lower() for a in build.assumptions)
    assert "uniform" in notes and "reaction" in notes


def test_build_is_deterministic_for_identical_inputs():
    _, _, _, first = _canonical_build()
    _, _, _, second = _canonical_build()

    assert first.model_dump() == second.model_dump()
