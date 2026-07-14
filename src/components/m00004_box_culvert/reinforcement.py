"""Deterministic reinforcement-bar layout for the M-00004 standard box section.

WHERE each of the twelve marks a1..h goes is deterministic geometry from the
standard single-cell box cross-section (no annexure needed); the dia @ spacing
NUMBERS come from the selected config's `bars` map (see catalog.json). This
module returns only the positions — the PDF sheet combines them with the numbers
for rendering.

Section coordinate frame (millimetres, origin at the box centroid):
* x = width  (+x to the right), y = height (+y up)
* inner opening: x in [-hs, hs], y in [-hh, hh]  (hs, hh = half clear span/height)
* outer face:    x in [-ox, ox], y in [-oy, oy]  (ox, oy = half outer width/height)
* top slab  : y in [ hh,  oy];  bottom slab: y in [-oy, -hh]
* side walls: x in [ hs,  ox]  and  x in [-ox, -hs]

Positions use a nominal clear cover (50 mm assumption). Each mark carries one or
more `polylines` (bar runs drawn as lines) and/or `dots` (bars seen end-on),
plus a `leader` anchor for its `mark : dia @ spacing` tag.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from components.m00004_box_culvert.params import CLEAR_COVER_MM
from components.m00004_box_culvert.params import M00004Geometry

Point = tuple[float, float]
_ROOT2_INV = 0.70710678

# Bar marks in canonical (schedule) order.
BAR_MARKS = ("a1", "a2", "b", "c", "d", "e", "f1", "f2", "g1", "g2", "g3", "h")

# Human-readable member / face description per mark (the notations glossary).
MARK_NOTATION: dict[str, str] = {
    "a1": "Top slab - bottom (inner) face main, transverse",
    "a2": "Top slab - top (outer) face main, transverse",
    "b": "Top slab - distribution, longitudinal",
    "c": "Side wall - main vertical, earth (outer) face",
    "d": "Side wall - main vertical, inner face",
    "e": "Side wall - horizontal distribution",
    "f1": "Bottom slab - top (inner) face main, transverse",
    "f2": "Bottom slab - bottom (outer) face main, transverse",
    "g1": "Top haunch corner bars (diagonal)",
    "g2": "Bottom haunch corner bars (diagonal)",
    "g3": "Corner / link bars",
    "h": "Bottom slab - distribution, longitudinal",
}


@dataclass
class BarMark:
    """The drawable layout of one reinforcement mark in the section frame."""

    mark: str
    notation: str
    polylines: list[list[Point]] = field(default_factory=list)
    dots: list[Point] = field(default_factory=list)
    leader: Point = (0.0, 0.0)


def _dot_row(x0: float, x1: float, y: float, count: int = 5) -> list[Point]:
    if count <= 1:
        return [((x0 + x1) / 2.0, y)]
    step = (x1 - x0) / (count - 1)
    return [(x0 + i * step, y) for i in range(count)]


def _dot_col(y0: float, y1: float, x: float, count: int = 5) -> list[Point]:
    if count <= 1:
        return [(x, (y0 + y1) / 2.0)]
    step = (y1 - y0) / (count - 1)
    return [(x, y0 + i * step) for i in range(count)]


def bar_layout(geometry: M00004Geometry, cover_mm: float = CLEAR_COVER_MM) -> dict[str, BarMark]:
    """Return the deterministic layout for all twelve marks, keyed by mark id."""
    c = cover_mm
    hs = geometry.clear_span_mm / 2.0
    hh = geometry.clear_height_mm / 2.0
    ox = geometry.outer_width_mm / 2.0
    oy = geometry.outer_height_mm / 2.0
    t = geometry.thickness_mm
    b = geometry.haunch_mm
    d = _ROOT2_INV * c

    marks: dict[str, BarMark] = {}

    def add(mark: str, **kw) -> None:
        marks[mark] = BarMark(mark=mark, notation=MARK_NOTATION[mark], **kw)

    # a1 - top slab inner (soffit) face main, transverse
    add("a1", polylines=[[(-(hs - c), hh + c), (hs - c, hh + c)]], leader=(hs - c, hh + c))
    # a2 - top slab outer (top) face main, transverse
    add("a2", polylines=[[(-(ox - c), oy - c), (ox - c, oy - c)]], leader=(ox - c, oy - c))
    # b - top slab distribution (longitudinal), seen end-on
    add("b", dots=_dot_row(-(hs - c), hs - c, (hh + oy) / 2.0), leader=(-(hs - c), (hh + oy) / 2.0))
    # c - side wall outer (earth) face vertical main, both walls
    add(
        "c",
        polylines=[
            [(ox - c, -(oy - c)), (ox - c, oy - c)],
            [(-(ox - c), -(oy - c)), (-(ox - c), oy - c)],
        ],
        leader=(ox - c, oy - c),
    )
    # d - side wall inner face vertical main, both walls
    add(
        "d",
        polylines=[
            [(hs + c, -(hh - c)), (hs + c, hh - c)],
            [(-(hs + c), -(hh - c)), (-(hs + c), hh - c)],
        ],
        leader=(hs + c, -(hh - c)),
    )
    # e - side wall horizontal distribution, both walls (seen end-on at mid-thickness)
    add(
        "e",
        dots=_dot_col(-(hh - c), hh - c, hs + t / 2.0) + _dot_col(-(hh - c), hh - c, -(hs + t / 2.0)),
        leader=(hs + t / 2.0, hh - c),
    )
    # f1 - bottom slab inner (top) face main, transverse
    add("f1", polylines=[[(-(hs - c), -(hh + c)), (hs - c, -(hh + c))]], leader=(hs - c, -(hh + c)))
    # f2 - bottom slab outer (bottom) face main, transverse
    add("f2", polylines=[[(-(ox - c), -(oy - c)), (ox - c, -(oy - c))]], leader=(ox - c, -(oy - c)))
    # g1 - top haunch corner bars (diagonal), both top corners
    add(
        "g1",
        polylines=[
            [(hs - b + d, hh + d), (hs + d, hh - b + d)],
            [(-(hs - b) - d, hh + d), (-hs - d, hh - b + d)],
        ],
        leader=(hs + d, hh - b + d),
    )
    # g2 - bottom haunch corner bars (diagonal), both bottom corners
    add(
        "g2",
        polylines=[
            [(hs - b + d, -(hh + d)), (hs + d, -(hh - b) - d)],
            [(-(hs - b) - d, -(hh + d)), (-hs - d, -(hh - b) - d)],
        ],
        leader=(hs + d, -(hh - b) - d),
    )
    # g3 - corner / link bars tying the haunch bars (all four inner corners)
    add(
        "g3",
        dots=[
            (hs - b / 2.0, hh - b / 2.0),
            (-(hs - b / 2.0), hh - b / 2.0),
            (hs - b / 2.0, -(hh - b / 2.0)),
            (-(hs - b / 2.0), -(hh - b / 2.0)),
        ],
        leader=(-(hs - b / 2.0), -(hh - b / 2.0)),
    )
    # h - bottom slab distribution (longitudinal), seen end-on
    add("h", dots=_dot_row(-(hs - c), hs - c, -(hh + oy) / 2.0), leader=(-(hs - c), -(hh + oy) / 2.0))

    return marks
