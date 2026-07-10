"""3D artefact generator — validated BoxGeometry -> model.glb + model.step.

Public contract (pinned — the graph slice imports exactly this):

    from model3d import generate_solid

    paths = generate_solid(geometry, out_dir)
    # builds the parametric solid, writes out_dir/"model.glb" (binary glTF)
    # and out_dir/"model.step", creating out_dir if missing
    # returns {"model_glb": Path, "model_step": Path}
    # raises InvalidGeometryError / SolidVerificationError (both ValueError
    # subclasses) on impossible geometry, ModelExportError if a writer fails

Failure policy: this module fails LOUDLY. Treating a 3D failure as non-fatal
(warning event, run continues, 2D artefacts stand) is the graph's job
(spec/agent.md model3d node) — never this module's.
"""

from pathlib import Path

from build123d import Unit, export_gltf, export_step

from domain.culvert import BoxGeometry
from model3d.solid import build_culvert_solid

MODEL_GLB_NAME = "model.glb"
MODEL_STEP_NAME = "model.step"


class ModelExportError(RuntimeError):
    """Raised when a build123d exporter reports failure for an artefact."""


def generate_solid(geometry: BoxGeometry, out_dir: Path) -> dict[str, Path]:
    """Build the culvert solid and export it as model.glb + model.step."""
    solid = build_culvert_solid(geometry)  # validates input, verifies output

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    glb_path = out_dir / MODEL_GLB_NAME
    if not export_gltf(solid, glb_path, unit=Unit.M, binary=True):
        raise ModelExportError(f"build123d failed to export binary glTF to {glb_path}")
    step_path = out_dir / MODEL_STEP_NAME
    if not export_step(solid, step_path, unit=Unit.M):
        raise ModelExportError(f"build123d failed to export STEP to {step_path}")
    return {"model_glb": glb_path, "model_step": step_path}
