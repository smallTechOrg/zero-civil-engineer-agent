"""Machine-element component package (mechanical domain).

Importing this package runs the module-level `register(MachineElementComponent())`
in `module.py`, adding the component to the registry at process start (replacing
the `machine_element` coming_soon stub).
"""

from components.machine_element import module  # noqa: F401  (self-registers)
