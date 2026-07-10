"""Component Registry package.

Importing this package populates the registry: every component module is
imported here so its module-level `register()` call runs exactly once at
process start. Add a new component = add one import line below (and the module
directory). Nothing else changes.
"""

# Importing each component module runs its `register(...)` at import time.
from components import culvert  # noqa: F401  (box_culvert — component #1)

# Component #2 (rcc_cantilever_retaining_wall) self-registers when its package
# lands; import it here in that slice:
try:  # pragma: no cover - the retaining_wall package is added by a sibling slice
    from components import retaining_wall  # noqa: F401
except ImportError:
    pass
