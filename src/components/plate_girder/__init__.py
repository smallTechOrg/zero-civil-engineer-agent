"""Welded steel plate-girder component package.

Importing this package runs the module-level `register(PlateGirderComponent())`
in `module.py`, adding the component to the registry at process start.
"""

from components.plate_girder import module  # noqa: F401  (self-registers)
