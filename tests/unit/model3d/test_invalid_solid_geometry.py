"""Impossible BoxGeometry must raise loudly before any file is written."""

import pytest

from domain.culvert import BoxGeometry


def consistent_geometry(**overrides) -> BoxGeometry:
    """A hand-consistent canonical-sized box; overrides introduce the defect."""
    values = dict(
        clear_span_m=4.0,
        clear_height_m=3.0,
        cushion_m=2.5,
        top_slab_thickness_mm=400.0,
        bottom_slab_thickness_mm=400.0,
        wall_thickness_mm=400.0,
        haunch_mm=150.0,
        external_width_m=4.8,
        external_height_m=3.8,
        barrel_length_m=15.0,
    )
    values.update(overrides)
    return BoxGeometry(**values)


def test_invalid_geometry_error_is_a_value_error():
    from model3d import InvalidGeometryError

    assert issubclass(InvalidGeometryError, ValueError)


def test_zero_span_raises_with_clear_message(tmp_path):
    from model3d import InvalidGeometryError, generate_solid

    with pytest.raises(InvalidGeometryError, match="clear span"):
        generate_solid(consistent_geometry(clear_span_m=0.0), tmp_path)


def test_haunch_too_large_to_fit_raises(tmp_path):
    from model3d import InvalidGeometryError, generate_solid

    # 2 x 1600 mm legs meet across the 3000 mm clear height.
    with pytest.raises(InvalidGeometryError, match="haunch"):
        generate_solid(consistent_geometry(haunch_mm=1600.0), tmp_path)


def test_negative_barrel_length_raises(tmp_path):
    from model3d import InvalidGeometryError, generate_solid

    with pytest.raises(InvalidGeometryError, match="barrel length"):
        generate_solid(consistent_geometry(barrel_length_m=-15.0), tmp_path)


def test_inconsistent_external_width_raises(tmp_path):
    from model3d import InvalidGeometryError, generate_solid

    with pytest.raises(InvalidGeometryError, match="inconsistent"):
        generate_solid(consistent_geometry(external_width_m=5.4), tmp_path)


def test_no_files_written_when_geometry_invalid(tmp_path):
    from model3d import generate_solid

    out_dir = tmp_path / "never-created"

    with pytest.raises(ValueError):
        generate_solid(consistent_geometry(clear_span_m=0.0), out_dir)

    assert not out_dir.exists()
