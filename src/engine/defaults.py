"""Auto-sizing rules and citations for the Phase-1 sizing subset.

Every constant here names its source — sizing.py contains no magic numbers.
Proportions follow the RDSO B-10152/R standard-drawing family for single-cell
RCC box culverts under 25t Loading-2008; Phase 2's V2 fixture cross-checks the
sized thicknesses against that family within +/-10%.
"""

import math

# RDSO B-10152/R family proportion: slab thickness ~ clear span / 10.
SLAB_SPAN_DIVISOR = 10.0
# RDSO B-10152/R family proportion: wall thickness ~ governing clear opening / 12
# (the larger of span and height governs — earth pressure on tall walls, frame
# action on wide boxes).
WALL_OPENING_DIVISOR = 12.0
# RDSO family floor — no member of a railway box goes below 300 mm.
MIN_MEMBER_THICKNESS_MM = 300.0
# Constructible increment used on RDSO standard sheets.
THICKNESS_ROUND_STEP_MM = 50.0

CITATION_RDSO_FAMILY = (
    "RDSO B-10152/R standard-drawing family proportions — single-cell RCC box, 25t Loading-2008"
)
CITATION_BRIDGE_MANUAL = (
    "Indian Railways Bridge Manual — embankment profile at culvert crossings "
    "(barrel spans the full embankment width at the box base)"
)
CITATION_USER_INPUT = (
    "User design requirement — validated against the RDSO B-10152/R single-cell family range"
)
CITATION_BOX_GEOMETRY = (
    "RDSO B-10152/R GA convention — external dimension = clear opening + member thicknesses"
)


def round_up_to_step(value_mm: float, step_mm: float = THICKNESS_ROUND_STEP_MM) -> float:
    """Round up to the next constructible increment (guarding float wobble at exact multiples)."""
    ratio = round(value_mm / step_mm, 9)
    return math.ceil(ratio) * step_mm


def auto_slab_thickness_mm(clear_span_m: float) -> float:
    """Slab thickness = max(clear span / 10, 300 mm), rounded up to 50 mm."""
    return round_up_to_step(max(clear_span_m * 1000.0 / SLAB_SPAN_DIVISOR, MIN_MEMBER_THICKNESS_MM))


def auto_wall_thickness_mm(clear_span_m: float, clear_height_m: float) -> float:
    """Wall thickness = max(governing opening / 12, 300 mm), rounded up to 50 mm."""
    governing_opening_m = max(clear_span_m, clear_height_m)
    return round_up_to_step(
        max(governing_opening_m * 1000.0 / WALL_OPENING_DIVISOR, MIN_MEMBER_THICKNESS_MM)
    )
