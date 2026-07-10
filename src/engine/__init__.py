"""Deterministic IRS design engine — Phase 1 exposes the sizing subset.

Public API (pinned — other slices import exactly this):

    from engine import size_culvert, SizingResult
"""

from engine.sizing import SizingResult, size_culvert

__all__ = ["SizingResult", "size_culvert"]
