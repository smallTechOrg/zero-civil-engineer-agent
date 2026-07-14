"""3D artefact generator — M00004Geometry -> fused model + genuinely-3D parts.

Reimplements the RDSO pilot's parametric box-culvert geometry with build123d
(NOT cadquery — cadquery is not a repo dependency): the RCC barrel (outer prism
minus the haunched clear opening) plus the standard appendages — return/wing
walls, apron floor and curtain/drop walls — with a barrel length derived from the
embankment cross-section.

Two families of artefacts, from ONE shared geometry source (the `_*_solid`
helpers below — the fused model and every part reuse them, so the closed-form
sub-volumes and the built solids can never drift):

* Phase-1 (unchanged, backward-compatible) — the fused solid exported as
  `model.glb` (viewer) + `model.step` (single fused solid).
* Phase-2 parts — four genuinely-3D STEP artefacts, EACH self-verifying its own
  closed-form sub-volume before export:
    - `assembly.step`    — the full assembly as a multi-body build123d Compound
                           (distinct from the fused `model.step`); basis = total.
    - `box.step`         — barrel only (outer prism − haunched opening); barrel term.
    - `curtain_wall.step`— the two curtain/drop walls; curtains term.
    - `return_wall.step` — the four wing/return-wall bands; walls term.

Model space (metres), centred at the origin on all three axes:
* X = outer width (across the barrel), Y = barrel length (along the track axis),
  Z = outer height. Bed level (top of the bottom slab) is z = -Hz/2 + thickness.

    from components.m00004_box_culvert.model3d import model3d
    paths = model3d(geometry, out_dir)
    # -> {"model_glb", "model_step", "assembly_step", "box_step",
    #     "curtain_wall_step", "return_wall_step"}  (all Path)
"""

from __future__ import annotations

from pathlib import Path

from build123d import (
    Box,
    Compound,
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
ASSEMBLY_STEP_NAME = "assembly.step"
BOX_STEP_NAME = "box.step"
CURTAIN_WALL_STEP_NAME = "curtain_wall.step"
RETURN_WALL_STEP_NAME = "return_wall.step"
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


# --------------------------------------------------------------------------- closed-form sub-volumes
# The total = barrel + walls + aprons + curtains. Each part self-verifies against
# its own term (the assembly against the total) before it is allowed to export.


def _barrel_volume_m3(d: dict[str, float]) -> float:
    """Outer prism minus the octagonal (haunched) clear opening, x barrel length."""
    void_area = d["cls"] * d["ch"] - 2.0 * d["b"] ** 2
    return (d["wx"] * d["hz"] - void_area) * d["length"]


def _walls_volume_m3(d: dict[str, float]) -> float:
    """Four wing/return-wall bands = 2 sides x 2 ends."""
    return 4.0 * d["t"] * d["hz"] * d["wing"]


def _aprons_volume_m3(d: dict[str, float]) -> float:
    """Two apron floor slabs (centre band, below bed) beyond each end."""
    return 2.0 * d["cls"] * d["apron_t"] * d["apron"]


def _curtains_volume_m3(d: dict[str, float]) -> float:
    """Two full-width curtain/drop walls dropped below bed beyond the aprons."""
    return 2.0 * d["wx"] * d["curtain_dep"] * d["curtain_t"]


def analytic_concrete_volume_m3(geometry: M00004Geometry) -> float:
    """Closed-form total concrete volume = barrel + wing walls + apron + curtains."""
    d = _dims_m(geometry)
    return (
        _barrel_volume_m3(d)
        + _walls_volume_m3(d)
        + _aprons_volume_m3(d)
        + _curtains_volume_m3(d)
    )


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


# --------------------------------------------------------------------------- shared geometry (ONE source)
# The fused solid AND every STEP part are built from these helpers — no duplicated
# or inconsistent math between the two families.


def _barrel_solid(d: dict[str, float]) -> Part:
    """Barrel = outer prism − extruded haunched (octagonal) clear opening."""
    wx, hz, length = d["wx"], d["hz"], d["length"]
    half_len = length / 2.0
    outer = _abox(-wx / 2.0, wx / 2.0, -half_len, half_len, -hz / 2.0, hz / 2.0)
    void = extrude(
        Plane.XZ * make_face(Polyline(*_octagon_profile(d), close=True)),
        amount=half_len + _VOID_END_OVERRUN_M,
        both=True,
    )
    return outer - void


def _wall_solids(d: dict[str, float]) -> list[Part]:
    """The four return/wing-wall bands (side-wall continuations beyond each end)."""
    wx, hz, cls, length, wing = d["wx"], d["hz"], d["cls"], d["length"], d["wing"]
    half_len = length / 2.0
    parts: list[Part] = []
    for y0, y1 in ((-half_len - wing, -half_len), (half_len, half_len + wing)):
        parts.append(_abox(-wx / 2.0, -cls / 2.0, y0, y1, -hz / 2.0, hz / 2.0))
        parts.append(_abox(cls / 2.0, wx / 2.0, y0, y1, -hz / 2.0, hz / 2.0))
    return parts


def _apron_solids(d: dict[str, float]) -> list[Part]:
    """The two apron floor slabs (centre band, below bed) beyond each end."""
    cls, length, apron, apron_t = d["cls"], d["length"], d["apron"], d["apron_t"]
    hz, t = d["hz"], d["t"]
    half_len = length / 2.0
    bed = -hz / 2.0 + t
    parts: list[Part] = []
    for y0, y1 in ((-half_len - apron, -half_len), (half_len, half_len + apron)):
        parts.append(_abox(-cls / 2.0, cls / 2.0, y0, y1, bed - apron_t, bed))
    return parts


def _curtain_solids(d: dict[str, float]) -> list[Part]:
    """The two full-width curtain/drop walls dropped below bed beyond the aprons."""
    wx, length, apron = d["wx"], d["length"], d["apron"]
    ct, curtain_dep = d["curtain_t"], d["curtain_dep"]
    hz, t = d["hz"], d["t"]
    half_len = length / 2.0
    bed = -hz / 2.0 + t
    parts: list[Part] = []
    for y0, y1 in (
        (-half_len - apron - ct, -half_len - apron),
        (half_len + apron, half_len + apron + ct),
    ):
        parts.append(_abox(-wx / 2.0, wx / 2.0, y0, y1, bed - curtain_dep, bed))
    return parts


def build_solid(geometry: M00004Geometry) -> Part:
    """Fused Phase-1 solid: barrel + return/wing walls + apron + curtain walls."""
    geometry = coerce(M00004Geometry, geometry)
    d = _dims_m(geometry)
    solid = _barrel_solid(d)
    for part in (*_wall_solids(d), *_apron_solids(d), *_curtain_solids(d)):
        solid = solid + part
    _verify(solid, geometry)
    return solid


def _verify(solid: Part, geometry: M00004Geometry) -> None:
    """Backward-compatible fused-solid check against the closed-form total."""
    _verify_volume(solid, analytic_concrete_volume_m3(geometry), "fused model")


def _verify_volume(solid: Part | Compound, expected: float, label: str) -> None:
    """Refuse to export a solid whose volume disagrees with its closed form."""
    actual = solid.volume
    if abs(actual - expected) > _VERIFY_VOLUME_REL_TOL * expected:
        raise SolidVerificationError(
            f"{label} volume {actual:.6f} m^3 disagrees with the closed-form "
            f"value {expected:.6f} m^3 - refusing to export"
        )


def _export_step_part(shape: Part | Compound, path: Path) -> Path:
    if not export_step(shape, path, unit=Unit.M):
        raise ModelExportError(f"build123d failed to export STEP to {path}")
    return path


def model3d(geometry: M00004Geometry, out_dir: Path) -> dict[str, Path]:
    """Export the fused model (glb + step) PLUS the four volume-verified STEP parts.

    Returns the six artefact paths keyed by kind: `model_glb`, `model_step`,
    `assembly_step`, `box_step`, `curtain_wall_step`, `return_wall_step`.
    """
    geometry = coerce(M00004Geometry, geometry)
    d = _dims_m(geometry)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- Phase-1 fused solid (unchanged, backward-compatible) ---
    fused = build_solid(geometry)
    glb_path = out_dir / MODEL_GLB_NAME
    if not export_gltf(fused, glb_path, unit=Unit.M, binary=True):
        raise ModelExportError(f"build123d failed to export binary glTF to {glb_path}")
    step_path = out_dir / MODEL_STEP_NAME
    if not export_step(fused, step_path, unit=Unit.M):
        raise ModelExportError(f"build123d failed to export STEP to {step_path}")

    # --- Phase-2 genuinely-3D parts, each verified against its own sub-volume ---
    barrel = _barrel_solid(d)
    _verify_volume(barrel, _barrel_volume_m3(d), "box")
    box_path = _export_step_part(barrel, out_dir / BOX_STEP_NAME)

    curtain_wall = Compound(children=_curtain_solids(d))
    _verify_volume(curtain_wall, _curtains_volume_m3(d), "curtain wall")
    curtain_wall_path = _export_step_part(curtain_wall, out_dir / CURTAIN_WALL_STEP_NAME)

    return_wall = Compound(children=_wall_solids(d))
    _verify_volume(return_wall, _walls_volume_m3(d), "return wall")
    return_wall_path = _export_step_part(return_wall, out_dir / RETURN_WALL_STEP_NAME)

    # Full assembly as a genuine multi-body Compound (distinct from the fused
    # model.step): barrel + 4 wall bands + 2 aprons + 2 curtain walls.
    assembly = Compound(
        children=[
            _barrel_solid(d),
            *_wall_solids(d),
            *_apron_solids(d),
            *_curtain_solids(d),
        ]
    )
    _verify_volume(assembly, analytic_concrete_volume_m3(geometry), "assembly")
    assembly_path = _export_step_part(assembly, out_dir / ASSEMBLY_STEP_NAME)

    return {
        "model_glb": glb_path,
        "model_step": step_path,
        "assembly_step": assembly_path,
        "box_step": box_path,
        "curtain_wall_step": curtain_wall_path,
        "return_wall_step": return_wall_path,
    }
