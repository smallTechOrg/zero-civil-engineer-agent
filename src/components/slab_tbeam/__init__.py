"""RCC slab / T-beam superstructure deck component package.

Importing this package runs the module-level `register(SlabTbeamComponent())` in
`module.py`, adding the component to the registry at process start.
"""

from components.slab_tbeam import module  # noqa: F401  (self-registers)
