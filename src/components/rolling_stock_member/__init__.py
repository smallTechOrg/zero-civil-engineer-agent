"""Fabricated rolling-stock member component package (mechanical domain).

Importing this package runs the module-level `register(RollingStockMemberComponent())`
in `module.py`, adding the component to the registry at process start.
"""

from components.rolling_stock_member import module  # noqa: F401  (self-registers)
