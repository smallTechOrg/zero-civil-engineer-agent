"""3D solid — valid non-empty GLB, STEP written, verified volume."""

from pathlib import Path

import pytest

from components.plate_girder.model3d import (
    analytic_steel_volume_m3,
    build_girder_solid,
    generate_solid,
)
from components.plate_girder.params import PlateGirderGeometry, PlateGirderParams
from components.plate_girder.sizing import size_girder

PARAMS = PlateGirderParams(span_m=18.0)


@pytest.fixture
def geometry() -> PlateGirderGeometry:
    return size_girder(PARAMS).geometry


def test_solid_volume_matches_the_closed_form(geometry):
    solid = build_girder_solid(geometry)
    assert solid.volume == pytest.approx(analytic_steel_volume_m3(geometry), rel=1e-3)
    box = solid.bounding_box().size
    assert box.X == pytest.approx(geometry.flange_width_mm / 1000.0, abs=1e-3)
    assert box.Z == pytest.approx(geometry.overall_depth_mm / 1000.0, abs=1e-3)
    assert box.Y == pytest.approx(geometry.span_mm / 1000.0, abs=1e-3)


def test_glb_is_a_valid_non_empty_binary_gltf_and_step_is_written(geometry, tmp_path: Path):
    paths = generate_solid(geometry, tmp_path)
    assert set(paths) == {"model_glb", "model_step"}
    glb = paths["model_glb"].read_bytes()
    assert glb[:4] == b"glTF"  # binary glTF magic
    assert len(glb) > 500
    step = paths["model_step"].read_text(encoding="utf-8", errors="replace")
    assert step.startswith("ISO-10303-21")


def test_solid_builds_for_a_deep_long_span_girder(tmp_path: Path):
    geometry = size_girder(PlateGirderParams(span_m=40.0)).geometry
    solid = build_girder_solid(geometry)
    assert solid.volume > 0
