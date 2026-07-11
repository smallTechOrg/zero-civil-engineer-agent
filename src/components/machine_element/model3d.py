"""3D artefact generator — MachineElementGeometry -> model.glb + model.step.

    from components.machine_element.model3d import generate_solid
    paths = generate_solid(geometry, out_dir)
    # returns {"model_glb": Path, "model_step": Path}

Model space (metres), axis Z = the element axis:

* **shaft** — a stepped shaft: a central cylinder (major diameter) with a smaller
  journal cylinder at each end, coaxial on Z. (The keyway is a drawing/GD&T
  feature and is not cut from the nominal solid.)
* **welded_joint** — a backing-plate box with the welded hub cylinder standing on
  it.

Fixed parametric build123d template — never generated CAD. The solid verifies its
own volume against the closed-form volume before export.
"""

from __future__ import annotations

import math
from pathlib import Path

from build123d import Cylinder, Box, Part, Pos, Unit, export_gltf, export_step

from components.base import coerce
from components.machine_element.params import MachineElementGeometry

MODEL_GLB_NAME = "model.glb"
MODEL_STEP_NAME = "model.step"
MM_PER_M = 1000.0

_VERIFY_VOLUME_REL_TOL = 1e-3


class ModelExportError(RuntimeError):
    """Raised when a build123d exporter reports failure for an artefact."""


class SolidVerificationError(ValueError):
    """Raised when the built solid disagrees with the closed-form geometry."""


def analytic_volume_m3(geometry: MachineElementGeometry) -> float:
    """Closed-form solid volume, m^3."""
    geometry = coerce(MachineElementGeometry, geometry)
    if geometry.element_kind == "welded_joint":
        lp = geometry.length_mm / MM_PER_M
        tp = geometry.plate_thickness_mm / MM_PER_M
        d = geometry.hub_diameter_mm / MM_PER_M
        hub_h = d  # representative hub height = hub diameter
        return lp * lp * tp + math.pi / 4.0 * d**2 * hub_h
    d = geometry.diameter_mm / MM_PER_M
    dj = geometry.step_diameter_mm / MM_PER_M
    lj = geometry.step_length_mm / MM_PER_M
    length = geometry.length_mm / MM_PER_M
    central = length - 2.0 * lj
    return math.pi / 4.0 * d**2 * central + 2.0 * (math.pi / 4.0 * dj**2 * lj)


def build_element_solid(geometry: MachineElementGeometry) -> Part:
    """Build the machine-element solid (stepped shaft or welded hub-on-plate)."""
    geometry = coerce(MachineElementGeometry, geometry)
    if geometry.element_kind == "welded_joint":
        solid = _build_weld_solid(geometry)
    else:
        solid = _build_shaft_solid(geometry)
    _verify(solid, geometry)
    return solid


def _build_shaft_solid(geometry: MachineElementGeometry) -> Part:
    d = geometry.diameter_mm / MM_PER_M
    dj = geometry.step_diameter_mm / MM_PER_M
    lj = geometry.step_length_mm / MM_PER_M
    length = geometry.length_mm / MM_PER_M
    central = length - 2.0 * lj

    body = Pos(0.0, 0.0, 0.0) * Cylinder(radius=d / 2.0, height=central)
    left = Pos(0.0, 0.0, -(central / 2.0 + lj / 2.0)) * Cylinder(radius=dj / 2.0, height=lj)
    right = Pos(0.0, 0.0, central / 2.0 + lj / 2.0) * Cylinder(radius=dj / 2.0, height=lj)
    return body + left + right


def _build_weld_solid(geometry: MachineElementGeometry) -> Part:
    lp = geometry.length_mm / MM_PER_M
    tp = geometry.plate_thickness_mm / MM_PER_M
    d = geometry.hub_diameter_mm / MM_PER_M
    hub_h = d

    plate = Pos(0.0, 0.0, -tp / 2.0) * Box(lp, lp, tp)
    hub = Pos(0.0, 0.0, hub_h / 2.0) * Cylinder(radius=d / 2.0, height=hub_h)
    return plate + hub


def _verify(solid: Part, geometry: MachineElementGeometry) -> None:
    expected = analytic_volume_m3(geometry)
    if abs(solid.volume - expected) > _VERIFY_VOLUME_REL_TOL * expected:
        raise SolidVerificationError(
            f"solid volume {solid.volume:.6f} m^3 disagrees with the closed-form "
            f"volume {expected:.6f} m^3 - refusing to export"
        )


def generate_solid(geometry: MachineElementGeometry, out_dir: Path) -> dict[str, Path]:
    """Build the element solid and export it as model.glb + model.step."""
    solid = build_element_solid(geometry)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    glb_path = out_dir / MODEL_GLB_NAME
    if not export_gltf(solid, glb_path, unit=Unit.M, binary=True):
        raise ModelExportError(f"build123d failed to export binary glTF to {glb_path}")
    step_path = out_dir / MODEL_STEP_NAME
    if not export_step(solid, step_path, unit=Unit.M):
        raise ModelExportError(f"build123d failed to export STEP to {step_path}")
    return {"model_glb": glb_path, "model_step": step_path}
