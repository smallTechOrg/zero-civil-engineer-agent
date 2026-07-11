"""3D solid — valid non-empty GLB, STEP written, verified volume (both kinds)."""

from pathlib import Path

import pytest

from components.machine_element.model3d import (
    analytic_volume_m3,
    build_element_solid,
    generate_solid,
)
from components.machine_element.params import MachineElementParams
from components.machine_element.sizing import size_element

SHAFT = MachineElementParams(power_kw=20.0, speed_rpm=1000.0)
WELD = MachineElementParams(
    power_kw=100.0, speed_rpm=100.0, element_kind="welded_joint", hub_diameter_mm=120.0
)


def test_shaft_solid_volume_matches_the_closed_form():
    g = size_element(SHAFT).geometry
    solid = build_element_solid(g)
    assert solid.volume == pytest.approx(analytic_volume_m3(g), rel=1e-3)
    box = solid.bounding_box().size
    assert box.X == pytest.approx(g.diameter_mm / 1000.0, abs=1e-3)
    assert box.Y == pytest.approx(g.diameter_mm / 1000.0, abs=1e-3)
    assert box.Z == pytest.approx(g.length_mm / 1000.0, abs=1e-3)


def test_welded_joint_solid_volume_matches_the_closed_form():
    g = size_element(WELD).geometry
    solid = build_element_solid(g)
    assert solid.volume == pytest.approx(analytic_volume_m3(g), rel=1e-3)
    box = solid.bounding_box().size
    assert box.X == pytest.approx(g.length_mm / 1000.0, abs=1e-3)  # plate size governs
    assert box.Z == pytest.approx((g.plate_thickness_mm + g.hub_diameter_mm) / 1000.0, abs=1e-3)


def test_glb_is_a_valid_non_empty_binary_gltf_and_step_is_written(tmp_path: Path):
    g = size_element(SHAFT).geometry
    paths = generate_solid(g, tmp_path)
    assert set(paths) == {"model_glb", "model_step"}
    glb = paths["model_glb"].read_bytes()
    assert glb[:4] == b"glTF"  # binary glTF magic
    assert len(glb) > 500
    step = paths["model_step"].read_text(encoding="utf-8", errors="replace")
    assert step.startswith("ISO-10303-21")


def test_welded_joint_solid_exports(tmp_path: Path):
    g = size_element(WELD).geometry
    paths = generate_solid(g, tmp_path)
    glb = paths["model_glb"].read_bytes()
    assert glb[:4] == b"glTF" and len(glb) > 500
