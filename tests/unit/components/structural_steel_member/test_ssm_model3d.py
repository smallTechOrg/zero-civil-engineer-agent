"""3D solid — valid non-empty GLB, STEP written, verified volume."""

from pathlib import Path

import pytest

from components.structural_steel_member.model3d import (
    analytic_steel_volume_m3,
    build_member_solid,
    generate_solid,
)
from components.structural_steel_member.params import SteelMemberParams
from components.structural_steel_member.sizing import size_member

PARAMS = SteelMemberParams(cantilever_length_m=4.0, transverse_load_kn=30.0)


@pytest.fixture
def geometry():
    return size_member(PARAMS).geometry


def test_solid_volume_matches_the_closed_form(geometry):
    solid = build_member_solid(geometry)
    assert solid.volume == pytest.approx(analytic_steel_volume_m3(geometry), rel=1e-3)
    box = solid.bounding_box().size
    assert box.X == pytest.approx(geometry.flange_width_mm / 1000.0, abs=1e-3)
    assert box.Z == pytest.approx(geometry.overall_depth_mm / 1000.0, abs=1e-3)
    assert box.Y == pytest.approx(geometry.cantilever_length_mm / 1000.0, abs=1e-3)


def test_glb_is_a_valid_non_empty_binary_gltf_and_step_is_written(geometry, tmp_path: Path):
    paths = generate_solid(geometry, tmp_path)
    assert set(paths) == {"model_glb", "model_step"}
    glb = paths["model_glb"].read_bytes()
    assert glb[:4] == b"glTF"  # binary glTF magic
    assert len(glb) > 500
    step = paths["model_step"].read_text(encoding="utf-8", errors="replace")
    assert step.startswith("ISO-10303-21")


def test_solid_builds_for_a_deep_long_member(tmp_path: Path):
    geometry = size_member(
        SteelMemberParams(cantilever_length_m=8.0, transverse_load_kn=40.0)
    ).geometry
    solid = build_member_solid(geometry)
    assert solid.volume > 0
