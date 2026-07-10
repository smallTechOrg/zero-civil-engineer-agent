"""size_culvert geometry — canonical case, extreme-but-valid cases, determinism."""

from domain.culvert import CulvertParams
from engine import SizingResult, size_culvert

CANONICAL = {"clear_span_m": 4.0, "clear_height_m": 3.0, "cushion_m": 2.5}


def test_canonical_case_produces_the_hand_computed_geometry():
    params = CulvertParams(**CANONICAL)

    result = size_culvert(params)
    g = result.geometry

    assert g.clear_span_m == 4.0
    assert g.clear_height_m == 3.0
    assert g.cushion_m == 2.5
    assert g.top_slab_thickness_mm == 400.0  # ceil50(max(4000/10, 300))
    assert g.bottom_slab_thickness_mm == 400.0  # matched to top slab
    assert g.wall_thickness_mm == 350.0  # ceil50(max(4000/12, 300))
    assert g.haunch_mm == 150.0


def test_external_dimensions_equal_clear_opening_plus_member_thicknesses():
    result = size_culvert(CulvertParams(**CANONICAL))
    g = result.geometry

    assert g.external_width_m == round(g.clear_span_m + 2 * g.wall_thickness_mm / 1000, 3)
    assert g.external_height_m == round(
        g.clear_height_m + (g.top_slab_thickness_mm + g.bottom_slab_thickness_mm) / 1000, 3
    )
    assert g.external_width_m == 4.7
    assert g.external_height_m == 3.8


def test_barrel_length_matches_the_embankment_formula_by_hand():
    # L = formation_width + 2 * side_slope * (cushion + external_height)
    #   = 6.85 + 2 * 2.0 * (2.5 + 3.8) = 32.05 m
    result = size_culvert(CulvertParams(**CANONICAL))

    assert result.geometry.barrel_length_m == 32.05


def test_barrel_length_uses_overridden_formation_width_and_side_slope():
    params = CulvertParams(**CANONICAL, formation_width_m=7.0, side_slope_h_per_v=1.5)

    result = size_culvert(params)

    # 7.0 + 2 * 1.5 * (2.5 + 3.8) = 25.9 m
    assert result.geometry.barrel_length_m == 25.9


def test_tall_narrow_box_one_by_six_sizes_without_error():
    params = CulvertParams(clear_span_m=1.0, clear_height_m=6.0, cushion_m=5.0)

    g = size_culvert(params).geometry

    # heuristic start 300/300/500 (height governs the wall); the 5 m fill on the
    # tall box is check-governed up to 450/450/600
    assert g.top_slab_thickness_mm == 450.0
    assert g.bottom_slab_thickness_mm == 450.0
    assert g.wall_thickness_mm == 600.0
    assert g.external_width_m == 2.2
    assert g.external_height_m == 6.9


def test_wide_flat_box_eight_by_one_sizes_without_error():
    params = CulvertParams(clear_span_m=8.0, clear_height_m=1.0, cushion_m=0.5)

    g = size_culvert(params).geometry

    assert g.top_slab_thickness_mm == 800.0
    assert g.bottom_slab_thickness_mm == 800.0
    assert g.wall_thickness_mm == 700.0  # span governs
    assert g.external_width_m == 9.4
    assert g.external_height_m == 2.6


def test_zero_cushion_completes_and_barrel_length_stays_positive():
    params = CulvertParams(clear_span_m=4.0, clear_height_m=3.0, cushion_m=0.0)

    g = size_culvert(params).geometry

    # zero cushion = undispersed live load: slabs check-governed 400 -> 450 mm,
    # so H_ext = 3.9 m and L = 6.85 + 2 * 2.0 * (0.0 + 3.9) = 22.45 m
    assert g.external_height_m == 3.9
    assert g.barrel_length_m == 22.45
    assert g.barrel_length_m > 0


def test_full_valid_range_corners_all_size_without_error():
    corners = [
        (1.0, 1.0, 0.0),
        (8.0, 6.0, 10.0),
        (1.0, 6.0, 10.0),
        (8.0, 1.0, 0.0),
    ]

    for span, height, cushion in corners:
        result = size_culvert(
            CulvertParams(clear_span_m=span, clear_height_m=height, cushion_m=cushion)
        )
        g = result.geometry
        assert g.external_width_m > g.clear_span_m
        assert g.external_height_m > g.clear_height_m
        assert g.barrel_length_m > 0


def test_sizing_is_deterministic_same_params_give_identical_results():
    params = CulvertParams(**CANONICAL)

    first = size_culvert(params)
    second = size_culvert(params)

    assert first.model_dump() == second.model_dump()
    assert first.model_dump_json() == second.model_dump_json()


def test_result_is_a_sizing_result_with_the_pinned_shape():
    result = size_culvert(CulvertParams(**CANONICAL))

    assert isinstance(result, SizingResult)
    assert result.geometry is not None
    assert isinstance(result.assumptions, list)
    assert isinstance(result.trail, list)
    assert isinstance(result.warnings, list)


def test_unusual_but_valid_span_produces_no_sizing_level_warning():
    # Param-level flags (span > 6 m) belong to unusual_value_warnings, not the engine.
    result = size_culvert(CulvertParams(clear_span_m=7.0, clear_height_m=3.0, cushion_m=2.5))

    assert result.warnings == []
