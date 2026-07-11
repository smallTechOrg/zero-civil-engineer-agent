"""3D artefact generator — SlabTbeamGeometry -> model.glb + model.step.

    from components.slab_tbeam.model3d import generate_solid
    paths = generate_solid(geometry, out_dir)
    # returns {"model_glb": Path, "model_step": Path}

Model space (metres): X = span, Y = deck width, Z = depth (soffit at z = 0, top of
deck at z = overall_depth). Fixed parametric build123d template — never generated
CAD. The solid verifies its own volume against the closed-form deck volume before
export.
"""

from __future__ import annotations

from pathlib import Path

from build123d import Box, Part, Pos, Unit, export_gltf, export_step

from components.base import coerce
from components.slab_tbeam.params import SlabTbeamGeometry

MODEL_GLB_NAME = "model.glb"
MODEL_STEP_NAME = "model.step"
MM_PER_M = 1000.0

_VERIFY_VOLUME_REL_TOL = 1e-3


class ModelExportError(RuntimeError):
    """Raised when a build123d exporter reports failure for an artefact."""


class SolidVerificationError(ValueError):
    """Raised when the built solid disagrees with the closed-form geometry."""


def analytic_concrete_volume_m3(geometry: SlabTbeamGeometry) -> float:
    span = geometry.span_mm / MM_PER_M
    deck = geometry.deck_width_mm / MM_PER_M
    overall = geometry.overall_depth_mm / MM_PER_M
    if geometry.deck_type == "solid_slab":
        return span * deck * overall
    slab = geometry.slab_depth_mm / MM_PER_M
    rib_w = geometry.rib_width_mm / MM_PER_M
    rib_d = geometry.rib_depth_mm / MM_PER_M
    n = geometry.number_of_girders
    return span * deck * slab + n * (span * rib_w * rib_d)


def build_deck_solid(geometry: SlabTbeamGeometry) -> Part:
    """Deck slab (+ optional ribs), soffit at z = 0, centred on the Y axis."""
    geometry = coerce(SlabTbeamGeometry, geometry)
    span = geometry.span_mm / MM_PER_M
    deck = geometry.deck_width_mm / MM_PER_M
    overall = geometry.overall_depth_mm / MM_PER_M

    if geometry.deck_type == "solid_slab":
        solid = Pos(0.0, 0.0, overall / 2.0) * Box(span, deck, overall)
        _verify(solid, geometry)
        return solid

    slab = geometry.slab_depth_mm / MM_PER_M
    rib_w = geometry.rib_width_mm / MM_PER_M
    rib_d = geometry.rib_depth_mm / MM_PER_M
    n = geometry.number_of_girders
    spacing = deck / n

    # Flange (deck slab) at the top.
    solid = Pos(0.0, 0.0, overall - slab / 2.0) * Box(span, deck, slab)
    # Ribs below the flange, centred across the deck width.
    for i in range(n):
        yc = -deck / 2.0 + spacing * (i + 0.5)
        solid = solid + Pos(0.0, yc, rib_d / 2.0) * Box(span, rib_w, rib_d)

    _verify(solid, geometry)
    return solid


def _verify(solid: Part, geometry: SlabTbeamGeometry) -> None:
    expected = analytic_concrete_volume_m3(geometry)
    if abs(solid.volume - expected) > _VERIFY_VOLUME_REL_TOL * expected:
        raise SolidVerificationError(
            f"solid volume {solid.volume:.6f} m^3 disagrees with the closed-form "
            f"deck volume {expected:.6f} m^3 - refusing to export"
        )


def generate_solid(geometry: SlabTbeamGeometry, out_dir: Path) -> dict[str, Path]:
    """Build the deck solid and export it as model.glb + model.step."""
    solid = build_deck_solid(geometry)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    glb_path = out_dir / MODEL_GLB_NAME
    if not export_gltf(solid, glb_path, unit=Unit.M, binary=True):
        raise ModelExportError(f"build123d failed to export binary glTF to {glb_path}")
    step_path = out_dir / MODEL_STEP_NAME
    if not export_step(solid, step_path, unit=Unit.M):
        raise ModelExportError(f"build123d failed to export STEP to {step_path}")
    return {"model_glb": glb_path, "model_step": step_path}
