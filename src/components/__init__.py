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

# Civil breadth (Expansion Phase 2): three new component packages self-register
# on import. They MUST be imported BEFORE `coming_soon` so their real available
# modules win over any leftover preview stub for the same type_id (register() is
# keyed by type_id and last-writer-wins).
try:  # pragma: no cover - the plate_girder package is added by a sibling slice
    from components import plate_girder  # noqa: F401
except ImportError:
    pass

try:  # pragma: no cover - the slab_tbeam package is added by a sibling slice
    from components import slab_tbeam  # noqa: F401
except ImportError:
    pass

try:  # pragma: no cover - the pier_abutment package is added by a sibling slice
    from components import pier_abutment  # noqa: F401
except ImportError:
    pass

# Roadmap ("coming soon") preview stubs — registered AFTER the available civil
# components so the available cards sort ahead of the greyed previews in the
# gallery. Metadata-only; never dispatched to (see components/coming_soon.py).
from components import coming_soon  # noqa: F401  (registers the 3 mechanical stubs)
