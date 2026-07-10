"""RCC cantilever retaining-wall component package.

Importing this package runs the module-level `register(RetainingWallComponent())`
in `module.py`, adding the component to the registry at process start.
"""

from components.retaining_wall import module  # noqa: F401  (self-registers)
