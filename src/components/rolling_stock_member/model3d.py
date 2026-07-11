"""3D artefact generator — RollingStockMemberGeometry -> model.glb + model.step.

    from components.rolling_stock_member.model3d import generate_solid
    paths = generate_solid(geometry, out_dir)
    # returns {"model_glb": Path, "model_step": Path}

Model space (metres): X = flange width, Z = overall depth (welded I-section), Y =
member length (member axis). The member is modelled as a doubly-symmetric welded
I-section extruded over its length. Fixed parametric build123d template — never
generated CAD. The solid verifies its own volume against the closed-form section
area x length before export.
"""

from __future__ import annotations

from pathlib import Path

from build123d import Part, Plane, Polyline, Unit, export_gltf, export_step, extrude, make_face

from components.base import coerce
from components.rolling_stock_member.params import RollingStockMemberGeometry

MODEL_GLB_NAME = "model.glb"
MODEL_STEP_NAME = "model.step"
MM_PER_M = 1000.0

_VERIFY_VOLUME_REL_TOL = 1e-3


class ModelExportError(RuntimeError):
    """Raised when a build123d exporter reports failure for an artefact."""


class SolidVerificationError(ValueError):
    """Raised when the built solid disagrees with the closed-form geometry."""


def analytic_steel_volume_m3(geometry: RollingStockMemberGeometry) -> float:
    """Volume of the member = (web area + 2 flange areas) x length, m^3."""
    dw = geometry.web_depth_mm / MM_PER_M
    tw = geometry.web_thickness_mm / MM_PER_M
    bf = geometry.flange_width_mm / MM_PER_M
    tf = geometry.flange_thickness_mm / MM_PER_M
    length = geometry.member_length_mm / MM_PER_M
    section_area = tw * dw + 2.0 * bf * tf
    return section_area * length


def _i_section_points(geometry: RollingStockMemberGeometry) -> list[tuple[float, float]]:
    bf = geometry.flange_width_mm / MM_PER_M
    tf = geometry.flange_thickness_mm / MM_PER_M
    tw = geometry.web_thickness_mm / MM_PER_M
    overall = geometry.overall_depth_mm / MM_PER_M
    hb = bf / 2.0
    hd = overall / 2.0
    hw = tw / 2.0
    return [
        (-hb, -hd), (hb, -hd), (hb, -hd + tf), (hw, -hd + tf),
        (hw, hd - tf), (hb, hd - tf), (hb, hd), (-hb, hd),
        (-hb, hd - tf), (-hw, hd - tf), (-hw, -hd + tf), (-hb, -hd + tf),
    ]


def build_member_solid(geometry: RollingStockMemberGeometry) -> Part:
    """One welded I-section member extruded over its length, centred on the Y axis."""
    geometry = coerce(RollingStockMemberGeometry, geometry)
    length = geometry.member_length_mm / MM_PER_M
    face = make_face(Polyline(*_i_section_points(geometry), close=True))
    solid = extrude(Plane.XZ * face, amount=length / 2.0, both=True)
    _verify(solid, geometry)
    return solid


def _verify(solid: Part, geometry: RollingStockMemberGeometry) -> None:
    expected = analytic_steel_volume_m3(geometry)
    if abs(solid.volume - expected) > _VERIFY_VOLUME_REL_TOL * expected:
        raise SolidVerificationError(
            f"solid volume {solid.volume:.6f} m^3 disagrees with the closed-form "
            f"steel volume {expected:.6f} m^3 - refusing to export"
        )


def generate_solid(geometry: RollingStockMemberGeometry, out_dir: Path) -> dict[str, Path]:
    """Build the member solid and export it as model.glb + model.step."""
    solid = build_member_solid(geometry)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    glb_path = out_dir / MODEL_GLB_NAME
    if not export_gltf(solid, glb_path, unit=Unit.M, binary=True):
        raise ModelExportError(f"build123d failed to export binary glTF to {glb_path}")
    step_path = out_dir / MODEL_STEP_NAME
    if not export_step(solid, step_path, unit=Unit.M):
        raise ModelExportError(f"build123d failed to export STEP to {step_path}")
    return {"model_glb": glb_path, "model_step": step_path}
