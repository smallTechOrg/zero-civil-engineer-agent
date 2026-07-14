"""CulvertParams validation — field names, defaults, and hard ranges per spec/data.md."""

import pytest
from pydantic import ValidationError

from domain.culvert import (
    ConcreteGrade,
    CulvertParams,
    Gauge,
    LoadingStandard,
    SteelGrade,
)

CRITICALS = {"clear_span_m": 4.0, "clear_height_m": 3.0, "cushion_m": 2.5}


def test_constructs_with_only_the_three_critical_fields():
    params = CulvertParams(**CRITICALS)

    assert params.clear_span_m == 4.0
    assert params.clear_height_m == 3.0
    assert params.cushion_m == 2.5


@pytest.mark.parametrize("missing", ["clear_span_m", "clear_height_m", "cushion_m"])
def test_missing_critical_field_raises_validation_error(missing):
    kwargs = {k: v for k, v in CRITICALS.items() if k != missing}

    with pytest.raises(ValidationError) as exc_info:
        CulvertParams(**kwargs)

    assert missing in str(exc_info.value)


def test_non_critical_defaults_match_data_md():
    params = CulvertParams(**CRITICALS)

    assert params.gauge == Gauge.BG
    assert params.tracks == 1
    assert params.loading_standard == LoadingStandard.T25_2008
    assert params.loading_standard.value == "25t-2008"
    assert params.concrete_grade == ConcreteGrade.M30
    assert params.steel_grade == SteelGrade.FE500
    assert params.clear_cover_mm == 50
    assert params.soil_unit_weight_kn_m3 == 18.0
    assert params.angle_of_friction_deg == 30.0
    assert params.formation_width_m == 6.85
    assert params.side_slope_h_per_v == 2.0
    assert params.haunch_mm == 150


def test_thickness_fields_default_to_none_meaning_auto_size():
    params = CulvertParams(**CRITICALS)

    assert params.top_slab_thickness_mm is None
    assert params.bottom_slab_thickness_mm is None
    assert params.wall_thickness_mm is None


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("clear_span_m", 0.9),
        ("clear_span_m", 8.1),
        ("clear_height_m", 0.9),
        ("clear_height_m", 6.1),
        ("cushion_m", -0.1),
        ("cushion_m", 10.1),
        ("clear_cover_mm", 39),
        ("clear_cover_mm", 76),
        ("soil_unit_weight_kn_m3", 14.9),
        ("soil_unit_weight_kn_m3", 22.1),
        ("angle_of_friction_deg", 24.9),
        ("angle_of_friction_deg", 40.1),
        ("haunch_mm", -1),
        ("haunch_mm", 301),
        ("tracks", 2),
        ("tracks", 0),
        ("formation_width_m", 0),
        ("formation_width_m", -1.0),
        ("side_slope_h_per_v", -0.5),
        ("top_slab_thickness_mm", 0),
        ("bottom_slab_thickness_mm", -50),
        ("wall_thickness_mm", 0),
    ],
)
def test_hard_range_violation_raises_validation_error(field, bad_value):
    kwargs = {**CRITICALS, field: bad_value}

    with pytest.raises(ValidationError):
        CulvertParams(**kwargs)


@pytest.mark.parametrize(
    ("field", "boundary_value"),
    [
        ("clear_span_m", 1.0),
        ("clear_span_m", 8.0),
        ("clear_height_m", 1.0),
        ("clear_height_m", 6.0),
        ("cushion_m", 0.0),
        ("cushion_m", 10.0),
        ("clear_cover_mm", 40),
        ("clear_cover_mm", 75),
        ("haunch_mm", 0),
        ("haunch_mm", 300),
    ],
)
def test_hard_range_boundary_values_are_accepted(field, boundary_value):
    kwargs = {**CRITICALS, field: boundary_value}

    params = CulvertParams(**kwargs)

    assert getattr(params, field) == boundary_value


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("gauge", "MG"),
        ("loading_standard", "32.5t-DFC"),
        ("concrete_grade", "M45"),
        ("steel_grade", "Fe550"),
    ],
)
def test_out_of_scope_enum_value_raises_validation_error(field, bad_value):
    kwargs = {**CRITICALS, field: bad_value}

    with pytest.raises(ValidationError):
        CulvertParams(**kwargs)


def test_enum_fields_accept_their_string_values():
    params = CulvertParams(
        **CRITICALS,
        gauge="BG",
        loading_standard="25t-2008",
        concrete_grade="M25",
        steel_grade="Fe415",
    )

    assert params.concrete_grade == ConcreteGrade.M25
    assert params.steel_grade == SteelGrade.FE415


def test_unknown_extra_field_is_rejected():
    with pytest.raises(ValidationError):
        CulvertParams(**CRITICALS, skew_angle_deg=15.0)


def test_params_round_trip_through_json_dump_and_validate():
    params = CulvertParams(**CRITICALS, top_slab_thickness_mm=450.0)

    restored = CulvertParams.model_validate_json(params.model_dump_json())

    assert restored == params
