"""3D solid — valid non-empty GLB, STEP written, verified volume."""

from pathlib import Path

import pytest

from components.pier_abutment.model3d import (
    analytic_concrete_volume_m3,
    build_substructure_solid,
    generate_solid,
)
from components.pier_abutment.params import PierAbutmentParams
from components.pier_abutment.sizing import size_substructure

PARAMS = PierAbutmentParams(
    pier_height_m=9.0, superstructure_reaction_kn=5000.0,
    safe_bearing_capacity_kn_m2=300.0, component_kind="pier",
)


@pytest.fixture
def geometry():
    return size_substructure(PARAMS).geometry


def test_solid_volume_matches_the_closed_form(geometry):
    solid = build_substructure_solid(geometry)
    assert solid.volume == pytest.approx(analytic_concrete_volume_m3(geometry), rel=1e-3)
    box = solid.bounding_box().size
    assert box.X == pytest.approx(geometry.footing_length_mm / 1000.0, abs=1e-3)
    assert box.Y == pytest.approx(geometry.footing_width_mm / 1000.0, abs=1e-3)
    assert box.Z == pytest.approx(geometry.total_height_mm / 1000.0, abs=1e-3)


def test_glb_is_a_valid_non_empty_binary_gltf_and_step_is_written(geometry, tmp_path: Path):
    paths = generate_solid(geometry, tmp_path)
    assert set(paths) == {"model_glb", "model_step"}
    glb = paths["model_glb"].read_bytes()
    assert glb[:4] == b"glTF"  # binary glTF magic
    assert len(glb) > 500
    step = paths["model_step"].read_text(encoding="utf-8", errors="replace")
    assert step.startswith("ISO-10303-21")


def test_solid_builds_for_an_abutment(tmp_path: Path):
    params = PierAbutmentParams(
        pier_height_m=7.0, superstructure_reaction_kn=4000.0,
        safe_bearing_capacity_kn_m2=250.0, component_kind="abutment",
    )
    geometry = size_substructure(params).geometry
    solid = build_substructure_solid(geometry)
    assert solid.volume > 0
