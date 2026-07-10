"""3D model package — build123d parametric solid -> GLB + STEP.

Public API (pinned — the graph slice imports exactly this):

    from model3d import generate_solid
"""

from model3d.generate import ModelExportError, generate_solid
from model3d.solid import SolidVerificationError, analytic_concrete_volume_m3, build_culvert_solid
from model3d.validation import InvalidGeometryError

__all__ = [
    "InvalidGeometryError",
    "ModelExportError",
    "SolidVerificationError",
    "analytic_concrete_volume_m3",
    "build_culvert_solid",
    "generate_solid",
]
