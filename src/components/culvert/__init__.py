"""Box-culvert component package — component #1.

Importing this package imports `module`, whose module-level `register(...)` call
adds the box culvert to the registry. The module is a thin adapter over the
UNCHANGED `src/engine`, `src/drawing`, `src/model3d`, `src/proofcheck`.
"""

from components.culvert import module  # noqa: F401  (runs register() at import)
from components.culvert.module import BoxCulvertComponent

__all__ = ["BoxCulvertComponent"]
