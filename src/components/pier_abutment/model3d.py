"""3D artefact generator — PierAbutmentGeometry -> model.glb + model.step.

    from components.pier_abutment.model3d import generate_solid
    paths = generate_solid(geometry, out_dir)
    # returns {"model_glb": Path, "model_step": Path}

Model space (metres): X = footing length (longitudinal), Y = footing width
(transverse), Z = height (founding level at z = 0, bearing level at z = H). The
solid is a footing block + a pier/stem block + a cap block, all centred on the
pier axis and stacked. Fixed parametric build123d template — never generated CAD.
The solid verifies its own volume against the closed-form solid volume before
export.
"""

from __future__ import annotations

from pathlib import Path

from build123d import Box, Pos, Unit, export_gltf, export_step

from components.base import coerce
from components.pier_abutment.params import PierAbutmentGeometry

MODEL_GLB_NAME = "model.glb"
MODEL_STEP_NAME = "model.step"
MM_PER_M = 1000.0

_VERIFY_VOLUME_REL_TOL = 1e-3


class ModelExportError(RuntimeError):
    """Raised when a build123d exporter reports failure for an artefact."""


class SolidVerificationError(ValueError):
    """Raised when the built solid disagrees with the closed-form geometry."""


def analytic_concrete_volume_m3(geometry: PierAbutmentGeometry) -> float:
    b = geometry.footing_length_mm / MM_PER_M
    lw = geometry.footing_width_mm / MM_PER_M
    df = geometry.footing_thickness_mm / MM_PER_M
    pw = geometry.pier_width_mm / MM_PER_M
    pl = geometry.pier_length_mm / MM_PER_M
    cw = geometry.cap_width_mm / MM_PER_M
    cl = geometry.cap_length_mm / MM_PER_M
    ct = geometry.cap_thickness_mm / MM_PER_M
    h = geometry.total_height_mm / MM_PER_M
    shaft_h = h - df - ct
    return b * lw * df + pw * pl * shaft_h + cw * cl * ct


def build_substructure_solid(geometry: PierAbutmentGeometry):
    """Footing block + pier/stem block + cap block, stacked on the pier axis."""
    geometry = coerce(PierAbutmentGeometry, geometry)
    b = geometry.footing_length_mm / MM_PER_M
    lw = geometry.footing_width_mm / MM_PER_M
    df = geometry.footing_thickness_mm / MM_PER_M
    pw = geometry.pier_width_mm / MM_PER_M
    pl = geometry.pier_length_mm / MM_PER_M
    cw = geometry.cap_width_mm / MM_PER_M
    cl = geometry.cap_length_mm / MM_PER_M
    ct = geometry.cap_thickness_mm / MM_PER_M
    h = geometry.total_height_mm / MM_PER_M
    shaft_h = h - df - ct

    footing = Pos(0.0, 0.0, df / 2.0) * Box(b, lw, df)
    shaft = Pos(0.0, 0.0, df + shaft_h / 2.0) * Box(pw, pl, shaft_h)
    cap = Pos(0.0, 0.0, df + shaft_h + ct / 2.0) * Box(cw, cl, ct)
    solid = footing + shaft + cap

    _verify(solid, geometry)
    return solid


def _verify(solid, geometry: PierAbutmentGeometry) -> None:
    expected = analytic_concrete_volume_m3(geometry)
    if abs(solid.volume - expected) > _VERIFY_VOLUME_REL_TOL * expected:
        raise SolidVerificationError(
            f"solid volume {solid.volume:.6f} m^3 disagrees with the closed-form "
            f"concrete volume {expected:.6f} m^3 - refusing to export"
        )


def generate_solid(geometry: PierAbutmentGeometry, out_dir: Path) -> dict[str, Path]:
    """Build the substructure solid and export it as model.glb + model.step."""
    solid = build_substructure_solid(geometry)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    glb_path = out_dir / MODEL_GLB_NAME
    if not export_gltf(solid, glb_path, unit=Unit.M, binary=True):
        raise ModelExportError(f"build123d failed to export binary glTF to {glb_path}")
    step_path = out_dir / MODEL_STEP_NAME
    if not export_step(solid, step_path, unit=Unit.M):
        raise ModelExportError(f"build123d failed to export STEP to {step_path}")
    return {"model_glb": glb_path, "model_step": step_path}
