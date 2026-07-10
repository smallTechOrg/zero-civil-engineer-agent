"""Impossible/invalid geometry fails loudly with a clear message — nothing is drawn."""

import pytest

from domain.culvert import BoxGeometry
from ga_test_helpers import sized


def valid_geometry(**overrides) -> BoxGeometry:
    _, geometry = sized(4.0, 3.0, 2.5)
    return geometry.model_copy(update=overrides)


def generate_into(tmp_path, geometry):
    from drawing.ga import generate_ga

    params, _ = sized(4.0, 3.0, 2.5)
    return generate_ga(geometry, params, tmp_path / "out")


def test_invalid_geometry_error_is_a_value_error():
    from drawing import InvalidGeometryError

    assert issubclass(InvalidGeometryError, ValueError)


def test_zero_span_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="span"):
        generate_into(tmp_path, valid_geometry(clear_span_m=0.0))


def test_negative_height_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="height"):
        generate_into(tmp_path, valid_geometry(clear_height_m=-3.0))


def test_negative_cushion_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="cushion"):
        generate_into(tmp_path, valid_geometry(cushion_m=-0.5))


def test_zero_wall_thickness_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="wall"):
        generate_into(tmp_path, valid_geometry(wall_thickness_mm=0.0))


def test_wall_thicker_than_half_the_span_is_rejected(tmp_path):
    geometry = valid_geometry(wall_thickness_mm=2100.0, external_width_m=8.2)

    with pytest.raises(ValueError, match="wall"):
        generate_into(tmp_path, geometry)


def test_haunches_that_close_the_opening_are_rejected(tmp_path):
    _, geometry = sized(8.0, 1.0, 0.5)

    with pytest.raises(ValueError, match="[Hh]aunch"):
        generate_into(tmp_path, geometry.model_copy(update={"haunch_mm": 600.0}))


def test_external_width_inconsistent_with_members_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="external width"):
        generate_into(tmp_path, valid_geometry(external_width_m=5.5))


def test_external_height_inconsistent_with_members_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="external height"):
        generate_into(tmp_path, valid_geometry(external_height_m=5.0))


def test_zero_barrel_length_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="barrel"):
        generate_into(tmp_path, valid_geometry(barrel_length_m=0.0))


def test_nothing_is_written_when_geometry_is_invalid(tmp_path):
    with pytest.raises(ValueError):
        generate_into(tmp_path, valid_geometry(clear_span_m=-1.0))

    assert not (tmp_path / "out").exists()
