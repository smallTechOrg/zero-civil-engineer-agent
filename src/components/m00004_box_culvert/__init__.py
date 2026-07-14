"""RDSO/M-00004 standard box-culvert component package.

Importing this package runs the module-level
`register(M00004BoxCulvertComponent())` in `module.py`, adding the component to
the registry. (Slice (b) adds this package to `src/components/__init__.py` so it
self-registers at process start; this slice's own tests import
`components.m00004_box_culvert.module` explicitly.)
"""

from components.m00004_box_culvert import module  # noqa: F401  (self-registers)
