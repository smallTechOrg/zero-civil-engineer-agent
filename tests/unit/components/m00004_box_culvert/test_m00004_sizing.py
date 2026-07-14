"""Geometry derivation + PROVISIONAL provenance from sizing.size."""

import pytest

from components.m00004_box_culvert.params import ExposureCondition, M00004Params
from components.m00004_box_culvert.sizing import resolve_concrete_grade, size
from domain.culvert import ConcreteGrade


def _params(**kw):
    base = {"clear_span_m": 4.0, "clear_height_m": 4.0, "cushion_m": 2.0}
    base.update(kw)
    return M00004Params(**base)


def test_geometry_outer_dims_and_barrel_length():
    result = size(_params())
    g = result.geometry
    assert g.config_id == "F2_4x4"
    assert g.thickness_mm == 500          # 50 cm PROVISIONAL catalogue thickness
    assert g.haunch_mm == 450
    assert g.clear_span_mm == 4000
    assert g.clear_height_mm == 4000
    assert g.outer_width_mm == 5000       # 4000 + 2*500
    assert g.outer_height_mm == 5000
    # barrel = 6850 + 2*(2000 + 5000)*2 = 34850
    assert g.barrel_length_mm == pytest.approx(34850.0)
    assert g.provisional_flags == []


def test_bar_schedule_copied_from_selected_config():
    g = size(_params()).geometry
    assert set(g.bar_schedule) == {
        "a1", "a2", "b", "c", "d", "e", "f1", "f2", "g1", "g2", "g3", "h"
    }
    assert g.bar_schedule["a1"] == {"dia_mm": 16, "spacing_mm": 150}


def test_appendage_constants_recorded_as_provisional_assumptions():
    result = size(_params())
    fields = {a.field for a in result.assumptions}
    for f in ("config_id", "thickness_mm", "haunch_mm", "bar_schedule",
              "wing_len_mm", "apron_len_mm", "curtain_depth_mm"):
        assert f in fields
    # every catalogue/appendage assumption carries the PROVISIONAL verify tag
    for a in result.assumptions:
        if a.field in {"config_id", "thickness_mm", "haunch_mm", "bar_schedule",
                       "wing_len_mm", "apron_len_mm", "apron_thickness_mm",
                       "curtain_thickness_mm", "curtain_depth_mm"}:
            assert "PROVISIONAL" in a.note


def test_calc_trail_is_recorded_with_s_ids():
    result = size(_params())
    assert result.trail
    assert all(step.step_id.startswith("S") for step in result.trail)


def test_out_of_catalogue_flags_flow_into_geometry_and_warnings():
    result = size(_params(clear_span_m=7.0, clear_height_m=7.0, cushion_m=3.0, surcharge_kn_m2=10.0))
    g = result.geometry
    assert g.config_id == "F2_6x6"
    assert len(g.provisional_flags) >= 3          # fill + box + surcharge (+ nearest)
    assert result.warnings == g.provisional_flags  # surfaced to the UI


# --------------------------------------------------------------------------- Phase-2: material derivation


def test_resolve_concrete_grade_defaults_to_m35():
    # None grade + non-very-severe exposure + in-range box -> M35 (typical).
    assert resolve_concrete_grade(_params()) is ConcreteGrade.M35
    assert resolve_concrete_grade(_params(exposure=ExposureCondition.MODERATE)) is ConcreteGrade.M35


def test_resolve_concrete_grade_very_severe_gives_m40():
    assert (
        resolve_concrete_grade(_params(exposure=ExposureCondition.VERY_SEVERE))
        is ConcreteGrade.M40
    )


def test_resolve_concrete_grade_explicit_override_wins():
    # An explicit grade always wins, even under very_severe exposure.
    p = _params(concrete_grade=ConcreteGrade.M25, exposure=ExposureCondition.VERY_SEVERE)
    assert resolve_concrete_grade(p) is ConcreteGrade.M25


def test_below_one_metre_m30_branch_is_documented_unreachable():
    # ge=1.0 validation means the <1 m -> M30 branch cannot be reached with valid
    # params; the smallest valid box still resolves to M35.
    assert resolve_concrete_grade(_params(clear_span_m=1.0, clear_height_m=1.0)) is ConcreteGrade.M35


def test_new_geometry_fields_populated_for_span4_height4_fill2():
    g = size(_params()).geometry
    assert g.concrete_grade_resolved == "M35"
    assert g.cushion_mm == pytest.approx(2000.0)          # 2.0 m x 1000
    assert g.formation_width_mm == pytest.approx(6850.0)  # 6.85 m x 1000
    assert g.side_slope_h_per_v == pytest.approx(2.0)     # echo of the param
    # constant-backed fields
    assert g.wearing_course_thickness_mm == 150.0
    assert g.pcc_thickness_mm == 150.0
    assert g.stone_pitching_thickness_mm == 300.0
    assert g.base_course_thickness_mm == 150.0
    assert g.bed_slope_run == 100.0
    assert g.weep_hole_dia_mm == 75.0
    assert g.weep_hole_spacing_mm == 1000.0
    assert g.drop_wall_depth_mm == 1500.0
    # derived (PROVISIONAL) fields
    assert g.hfl_above_bed_mm == pytest.approx(0.75 * 4000.0)          # factor x clear height
    assert g.return_wall_base_width_mm == pytest.approx(0.5 * 5000.0)  # factor x outer height
    assert g.return_wall_top_width_mm == pytest.approx(g.thickness_mm)


def test_very_severe_exposure_flows_resolved_grade_into_geometry():
    g = size(_params(exposure=ExposureCondition.VERY_SEVERE)).geometry
    assert g.concrete_grade_resolved == "M40"


def test_derived_values_recorded_as_provisional_assumptions():
    result = size(_params(exposure=ExposureCondition.VERY_SEVERE))
    by_field = {a.field: a for a in result.assumptions}
    for field in ("concrete_grade_resolved", "hfl_above_bed_mm",
                  "return_wall_base_width_mm", "drop_wall_depth_mm"):
        assert field in by_field
    # derived (non-user) values carry the PROVISIONAL tag
    for field in ("hfl_above_bed_mm", "return_wall_base_width_mm", "drop_wall_depth_mm"):
        assert "PROVISIONAL" in by_field[field].note
    # derived grade (None input) is a preset PROVISIONAL choice
    assert by_field["concrete_grade_resolved"].source == "preset"
    assert "PROVISIONAL" in by_field["concrete_grade_resolved"].note


def test_explicit_grade_assumption_marked_user_source():
    result = size(_params(concrete_grade=ConcreteGrade.M30))
    by_field = {a.field: a for a in result.assumptions}
    assert by_field["concrete_grade_resolved"].source == "user"
    assert by_field["concrete_grade_resolved"].value == "M30"


def test_concrete_grade_m40_is_additive_enum_member():
    # The shared enum gained M40 additively for the very-severe branch.
    assert ConcreteGrade.M40.value == "M40"
    assert {g.value for g in ConcreteGrade} == {"M25", "M30", "M35", "M40"}
