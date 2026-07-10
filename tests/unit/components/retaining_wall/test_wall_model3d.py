"""3D solid — valid non-empty GLB, STEP written, verified volume."""

from pathlib import Path

import pytest

from components.retaining_wall.model3d import (
    analytic_concrete_volume_m3,
    build_wall_solid,
    generate_solid,
)
from components.retaining_wall.params import RetainingWallGeometry
from components.retaining_wall.sizing import size_wall
from components.retaining_wall.params import RetainingWallParams

PARAMS = RetainingWallParams(
    retained_height_m=5.0, safe_bearing_capacity_kn_m2=200.0, backfill_friction_angle_deg=30.0
)


@pytest.fixture
def geometry() -> RetainingWallGeometry:
    return size_wall(PARAMS).geometry


def test_solid_volume_matches_the_closed_form(geometry):
    solid = build_wall_solid(geometry)
    assert solid.volume == pytest.approx(analytic_concrete_volume_m3(geometry), rel=1e-3)
    box = solid.bounding_box().size
    assert box.X == pytest.approx(geometry.base_width_mm / 1000.0, abs=1e-3)
    # Height spans the base underside (or key bottom) to the top of the stem.
    assert box.Z == pytest.approx(
        (geometry.total_height_mm + geometry.key_depth_mm) / 1000.0, abs=1e-3
    )


def test_glb_is_a_valid_non_empty_binary_gltf_and_step_is_written(geometry, tmp_path: Path):
    paths = generate_solid(geometry, tmp_path)
    assert set(paths) == {"model_glb", "model_step"}
    glb = paths["model_glb"].read_bytes()
    assert glb[:4] == b"glTF"  # binary glTF magic
    assert len(glb) > 500
    step = paths["model_step"].read_text(encoding="utf-8", errors="replace")
    assert step.startswith("ISO-10303-21")


def test_solid_builds_without_a_key(tmp_path: Path):
    params = RetainingWallParams(
        retained_height_m=2.0, safe_bearing_capacity_kn_m2=300.0, backfill_friction_angle_deg=35.0,
        track_surcharge=False,
    )
    geometry = size_wall(params).geometry
    solid = build_wall_solid(geometry)
    assert solid.volume > 0
