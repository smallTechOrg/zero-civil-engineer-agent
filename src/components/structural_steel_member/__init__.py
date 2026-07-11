"""Fabricated structural-steel member component package (mechanical domain).

Importing this package runs the module-level
`register(StructuralSteelMemberComponent())` in `module.py`, adding the component
to the registry at process start (replacing the coming_soon stub of the same
type_id).
"""

from components.structural_steel_member import module  # noqa: F401  (self-registers)
