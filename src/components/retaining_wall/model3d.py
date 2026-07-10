"""3D artefact generator — RetainingWallGeometry -> model.glb + model.step.

    from components.retaining_wall.model3d import generate_solid
    paths = generate_solid(geometry, out_dir)
    # returns {"model_glb": Path, "model_step": Path}

Model space (metres): X = base width, Y = 1 m run of wall along the wall axis,
Z = height (base underside at z = 0, top of stem at z = H, shear key below
z = 0). Fixed parametric build123d template — never generated CAD. The solid
verifies its own volume against the closed-form cross-section area before export.
"""

from __future__ import annotations

from pathlib import Path

from build123d import Part, Plane, Polyline, Unit, export_gltf, export_step, extrude, make_face

from components.base import coerce
from components.retaining_wall.params import RetainingWallGeometry

MODEL_GLB_NAME = "model.glb"
MODEL_STEP_NAME = "model.step"
RUN_LENGTH_M = 1.0
MM_PER_M = 1000.0

_VERIFY_VOLUME_REL_TOL = 1e-3


class ModelExportError(RuntimeError):
    """Raised when a build123d exporter reports failure for an artefact."""


class SolidVerificationError(ValueError):
    """Raised when the built solid disagrees with the closed-form geometry."""


def _region(points: list[tuple[float, float]], run: float) -> Part:
    face = make_face(Polyline(*points, close=True))
    return extrude(Plane.XZ * face, amount=run / 2.0, both=True)


def analytic_concrete_volume_m3(geometry: RetainingWallGeometry) -> float:
    b = geometry.base_width_mm / MM_PER_M
    h = geometry.total_height_mm / MM_PER_M
    db = geometry.base_thickness_mm / MM_PER_M
    tsb = geometry.stem_base_thickness_mm / MM_PER_M
    tst = geometry.stem_top_thickness_mm / MM_PER_M
    key = geometry.key_depth_mm / MM_PER_M
    base_area = b * db
    stem_area = 0.5 * (tsb + tst) * (h - db)
    key_area = tsb * key
    return (base_area + stem_area + key_area) * RUN_LENGTH_M


def build_wall_solid(geometry: RetainingWallGeometry) -> Part:
    """Base slab + tapered stem (+ optional shear key), centred on the Y axis."""
    geometry = coerce(RetainingWallGeometry, geometry)
    b = geometry.base_width_mm / MM_PER_M
    h = geometry.total_height_mm / MM_PER_M
    db = geometry.base_thickness_mm / MM_PER_M
    lt = geometry.toe_length_mm / MM_PER_M
    tsb = geometry.stem_base_thickness_mm / MM_PER_M
    tst = geometry.stem_top_thickness_mm / MM_PER_M
    key = geometry.key_depth_mm / MM_PER_M
    x_back = lt + tsb
    delta = tsb - tst
    run = RUN_LENGTH_M

    solid = _region([(0.0, 0.0), (b, 0.0), (b, db), (0.0, db)], run)
    solid = solid + _region(
        [(lt, db), (x_back, db), (x_back, h), (lt + delta, h)], run
    )
    if key > 0:
        solid = solid + _region([(lt, -key), (x_back, -key), (x_back, 0.0), (lt, 0.0)], run)

    _verify(solid, geometry)
    return solid


def _verify(solid: Part, geometry: RetainingWallGeometry) -> None:
    expected = analytic_concrete_volume_m3(geometry)
    if abs(solid.volume - expected) > _VERIFY_VOLUME_REL_TOL * expected:
        raise SolidVerificationError(
            f"solid volume {solid.volume:.6f} m^3 disagrees with the closed-form "
            f"concrete volume {expected:.6f} m^3 - refusing to export"
        )


def generate_solid(geometry: RetainingWallGeometry, out_dir: Path) -> dict[str, Path]:
    """Build the wall solid and export it as model.glb + model.step."""
    solid = build_wall_solid(geometry)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    glb_path = out_dir / MODEL_GLB_NAME
    if not export_gltf(solid, glb_path, unit=Unit.M, binary=True):
        raise ModelExportError(f"build123d failed to export binary glTF to {glb_path}")
    step_path = out_dir / MODEL_STEP_NAME
    if not export_step(solid, step_path, unit=Unit.M):
        raise ModelExportError(f"build123d failed to export STEP to {step_path}")
    return {"model_glb": glb_path, "model_step": step_path}
