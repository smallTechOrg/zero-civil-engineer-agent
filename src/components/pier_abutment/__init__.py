"""Pier & abutment substructure component package (Expansion Phase 2).

Importing this package runs the module-level `register(PierAbutmentComponent())`
in `module.py`, adding the component to the registry at process start (and
graduating the `pier_abutment` roadmap stub to an available component).
"""

from components.pier_abutment import module  # noqa: F401  (self-registers)
