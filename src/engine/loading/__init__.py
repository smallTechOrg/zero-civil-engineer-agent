"""Pluggable loading-standard layer — 25t Loading-2008 registered as the POC standard.

Pinned public API (other slices import exactly this):

    from engine.loading import get_loading_standard, LoadingStandard
"""

from engine.loading.base import (
    EudlRow,
    LoadingStandard,
    get_loading_standard,
    register_loading_standard,
    registered_standard_names,
)
from engine.loading.t25_2008 import T25Loading2008

__all__ = [
    "EudlRow",
    "LoadingStandard",
    "T25Loading2008",
    "get_loading_standard",
    "register_loading_standard",
    "registered_standard_names",
]
