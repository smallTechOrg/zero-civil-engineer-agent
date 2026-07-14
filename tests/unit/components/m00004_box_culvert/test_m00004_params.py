"""M00004Params / M00004Geometry validation + ranges."""

import pytest
from pydantic import ValidationError

from components.m00004_box_culvert.params import (
    CRITICAL_FIELDS,
    ExposureCondition,
    M00004Geometry,
    M00004Params,
)


def test_critical_fields_declared():
    assert CRITICAL_FIELDS == ("clear_span_m", "clear_height_m", "cushion_m")


def test_minimal_valid_params_apply_standard_defaults():
    p = M00004Params(clear_span_m=4.0, clear_height_m=4.0, cushion_m=2.0)
    assert p.surcharge_kn_m2 == 0.0
    assert p.formation_width_m == pytest.approx(6.85)
    assert p.side_slope_h_per_v == pytest.approx(2.0)
    # Phase-2 material defaults: grade derives (None), steel Fe415, exposure severe.
    assert p.concrete_grade is None
    assert p.steel_grade.value == "Fe415"
    assert p.exposure is ExposureCondition.SEVERE


def test_explicit_concrete_grade_and_exposure_accepted():
    from domain.culvert import ConcreteGrade

    p = M00004Params(
        clear_span_m=4.0, clear_height_m=4.0, cushion_m=2.0,
        concrete_grade=ConcreteGrade.M40, exposure=ExposureCondition.VERY_SEVERE,
    )
    assert p.concrete_grade is ConcreteGrade.M40
    assert p.exposure is ExposureCondition.VERY_SEVERE


def test_exposure_enum_members():
    assert ExposureCondition.MODERATE.value == "moderate"
    assert ExposureCondition.SEVERE.value == "severe"
    assert ExposureCondition.VERY_SEVERE.value == "very_severe"


def test_missing_critical_field_is_rejected():
    with pytest.raises(ValidationError):
        M00004Params(clear_span_m=4.0, clear_height_m=4.0)


@pytest.mark.parametrize(
    "field,value",
    [
        ("clear_span_m", 0.5),   # < 1.0 hard min
        ("clear_span_m", 8.5),   # > 8.0 hard max
        ("clear_height_m", 0.9),
        ("cushion_m", -0.1),
        ("cushion_m", 6.5),      # > 6.0 hard max
        ("surcharge_kn_m2", 60.0),
    ],
)
def test_out_of_range_values_rejected(field, value):
    kwargs = {"clear_span_m": 4.0, "clear_height_m": 4.0, "cushion_m": 2.0}
    kwargs[field] = value
    with pytest.raises(ValidationError):
        M00004Params(**kwargs)


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        M00004Params(clear_span_m=4.0, clear_height_m=4.0, cushion_m=2.0, bogus=1)


def test_geometry_model_round_trips():
    g = M00004Geometry(
        clear_span_mm=4000, clear_height_mm=4000, thickness_mm=500, haunch_mm=450,
        outer_width_mm=5000, outer_height_mm=5000, barrel_length_mm=34850,
        config_id="F2_4x4", bar_schedule={"a1": {"dia_mm": 16, "spacing_mm": 150}},
        concrete_grade_resolved="M35", cushion_mm=2000, formation_width_mm=6850,
        side_slope_h_per_v=2.0, hfl_above_bed_mm=3000, return_wall_base_width_mm=2500,
        return_wall_top_width_mm=500,
    )
    assert g.wing_len_mm == 2500  # PROVISIONAL default appendage constant
    assert g.provisional_flags == []
    # Phase-2 constant-backed defaults populate without being passed.
    assert g.wearing_course_thickness_mm == 150.0
    assert g.pcc_thickness_mm == 150.0
    assert g.stone_pitching_thickness_mm == 300.0
    assert g.base_course_thickness_mm == 150.0
    assert g.bed_slope_run == 100.0
    assert g.weep_hole_dia_mm == 75.0
    assert g.weep_hole_spacing_mm == 1000.0
    assert g.drop_wall_depth_mm == 1500.0
