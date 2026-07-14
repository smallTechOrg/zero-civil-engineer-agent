"""3D artefact generator — M00004Geometry -> model.glb + model.step.

Reimplements the RDSO pilot's parametric box-culvert geometry with build123d
(NOT cadquery — cadquery is not a repo dependency): the RCC barrel (outer prism
minus the haunched clear opening) plus the standard appendages — return/wing
walls, apron floor and curtain/drop walls — with a barrel length derived from the
embankment cross-section. The solid verifies its own volume against the
closed-form concrete volume before export (as the retaining-wall model3d does).

Model space (metres), centred at the origin on all three axes:
* X = outer width (across the barrel), Y = barrel length (along the track axis),
  Z = outer height. Bed level (top of the bottom slab) is z = -Hz/2 + thickness.

    from components.m00004_box_culvert.model3d import model3d
    paths = model3d(geometry, out_dir)   # -> {"model_glb": Path, "model_step": Path}
"""

from __future__ import annotations

from pathlib import Path

from build123d import (
    Box,
    Part,
    Plane,
    Polyline,
    Pos,
    Unit,
    export_gltf,
    export_step,
    extrude,
    make_face,
)

from components.base import coerce
from components.m00004_box_culvert.params import M00004Geometry

MODEL_GLB_NAME = "model.glb"
MODEL_STEP_NAME = "model.step"
MM_PER_M = 1000.0

_VOID_END_OVERRUN_M = 0.02
_VERIFY_VOLUME_REL_TOL = 1e-3


class ModelExportError(RuntimeError):
    """Raised when a build123d exporter reports failure for an artefact."""


class SolidVerificationError(ValueError):
    """Raised when the built solid disagrees with the closed-form geometry."""


def _abox(x0, x1, y0, y1, z0, z1) -> Part:
    """Axis-aligned solid between two corners (metres)."""
    return Pos((x0 + x1) / 2.0, (y0 + y1) / 2.0, (z0 + z1) / 2.0) * Box(
        x1 - x0, y1 - y0, z1 - z0
    )


def _dims_m(geometry: M00004Geometry) -> dict[str, float]:
    return {
        "cls": geometry.clear_span_mm / MM_PER_M,
        "ch": geometry.clear_height_mm / MM_PER_M,
        "t": geometry.thickness_mm / MM_PER_M,
        "b": geometry.haunch_mm / MM_PER_M,
        "wx": geometry.outer_width_mm / MM_PER_M,
        "hz": geometry.outer_height_mm / MM_PER_M,
        "length": geometry.barrel_length_mm / MM_PER_M,
        "wing": geometry.wing_len_mm / MM_PER_M,
        "apron": geometry.apron_len_mm / MM_PER_M,
        "apron_t": geometry.apron_thickness_mm / MM_PER_M,
        "curtain_t": geometry.curtain_thickness_mm / MM_PER_M,
        "curtain_dep": geometry.curtain_depth_mm / MM_PER_M,
    }


def analytic_concrete_volume_m3(geometry: M00004Geometry) -> float:
    """Closed-form total concrete volume = barrel + wing walls + apron + curtains."""
    d = _dims_m(geometry)
    void_area = d["cls"] * d["ch"] - 2.0 * d["b"] ** 2
    barrel = (d["wx"] * d["hz"] - void_area) * d["length"]
    walls = 4.0 * d["t"] * d["hz"] * d["wing"]  # 2 sides x 2 ends
    aprons = 2.0 * d["cls"] * d["apron_t"] * d["apron"]
    curtains = 2.0 * d["wx"] * d["curtain_dep"] * d["curtain_t"]
    return barrel + walls + aprons + curtains


def _octagon_profile(d: dict[str, float]) -> list[tuple[float, float]]:
    """Clear-opening octagon in the XZ plane (local x = width, y = height),
    centred at the origin."""
    hs = d["cls"] / 2.0
    hh = d["ch"] / 2.0
    b = d["b"]
    return [
        (-(hs - b), hh), (hs - b, hh), (hs, hh - b), (hs, -(hh - b)),
        (hs - b, -hh), (-(hs - b), -hh), (-hs, -(hh - b)), (-hs, hh - b),
    ]


def build_solid(geometry: M00004Geometry) -> Part:
    """Barrel (haunched box) + return/wing walls + apron + curtain walls."""
    geometry = coerce(M00004Geometry, geometry)
    d = _dims_m(geometry)
    wx, hz, length, t = d["wx"], d["hz"], d["length"], d["t"]
    cls = d["cls"]
    half_len = length / 2.0
    bed = -hz / 2.0 + t  # top of the bottom slab

    outer = _abox(-wx / 2.0, wx / 2.0, -half_len, half_len, -hz / 2.0, hz / 2.0)
    void = extrude(
        Plane.XZ * make_face(Polyline(*_octagon_profile(d), close=True)),
        amount=half_len + _VOID_END_OVERRUN_M,
        both=True,
    )
    solid = outer - void

    # return / wing walls (continuations of the side-wall bands beyond each end)
    for y0, y1 in ((-half_len - d["wing"], -half_len), (half_len, half_len + d["wing"])):
        solid = solid + _abox(-wx / 2.0, -cls / 2.0, y0, y1, -hz / 2.0, hz / 2.0)
        solid = solid + _abox(cls / 2.0, wx / 2.0, y0, y1, -hz / 2.0, hz / 2.0)

    # apron floor (centre band, below bed) beyond each end
    for y0, y1 in ((-half_len - d["apron"], -half_len), (half_len, half_len + d["apron"])):
        solid = solid + _abox(-cls / 2.0, cls / 2.0, y0, y1, bed - d["apron_t"], bed)

    # curtain / drop walls (full width, dropped below bed) beyond the aprons
    ct = d["curtain_t"]
    for y0, y1 in (
        (-half_len - d["apron"] - ct, -half_len - d["apron"]),
        (half_len + d["apron"], half_len + d["apron"] + ct),
    ):
        solid = solid + _abox(-wx / 2.0, wx / 2.0, y0, y1, bed - d["curtain_dep"], bed)

    _verify(solid, geometry)
    return solid


def _verify(solid: Part, geometry: M00004Geometry) -> None:
    expected = analytic_concrete_volume_m3(geometry)
    if abs(solid.volume - expected) > _VERIFY_VOLUME_REL_TOL * expected:
        raise SolidVerificationError(
            f"solid volume {solid.volume:.6f} m^3 disagrees with the closed-form "
            f"concrete volume {expected:.6f} m^3 - refusing to export"
        )


def model3d(geometry: M00004Geometry, out_dir: Path) -> dict[str, Path]:
    """Build the standard box solid and export it as model.glb + model.step."""
    solid = build_solid(geometry)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    glb_path = out_dir / MODEL_GLB_NAME
    if not export_gltf(solid, glb_path, unit=Unit.M, binary=True):
        raise ModelExportError(f"build123d failed to export binary glTF to {glb_path}")
    step_path = out_dir / MODEL_STEP_NAME
    if not export_step(solid, step_path, unit=Unit.M):
        raise ModelExportError(f"build123d failed to export STEP to {step_path}")
    return {"model_glb": glb_path, "model_step": step_path}
