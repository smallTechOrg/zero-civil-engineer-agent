"""Reinforcement-for-Box bar-bending SHAPE table.

For each of the twelve a1..h marks: a bent-bar SHAPE sketch + a cutting-length
formula and value (distinct from the dia@spacing schedule shown elsewhere).
Reuses ``reinforcement.BAR_MARKS``/``MARK_NOTATION`` and the geometry
``bar_schedule``. Every length is derived from ``M00004Geometry`` only.
"""

from __future__ import annotations

from ezdxf.document import Drawing
from ezdxf.enums import TextEntityAlignment

from components.m00004_box_culvert.drawings import (
    LAYER_BARS,
    LAYER_OUTLINE,
    LAYER_TEXT,
    add_title_and_caption,
    line,
    new_doc,
    polyline,
    text,
)
from components.m00004_box_culvert.params import CLEAR_COVER_MM
from components.m00004_box_culvert.reinforcement import BAR_MARKS, MARK_NOTATION

# Shape kind per mark: how the bent bar is sketched in the SHAPE column.
_SHAPE_KIND = {
    "a1": "U", "a2": "U", "b": "straight", "c": "L", "d": "L", "e": "straight",
    "f1": "U", "f2": "U", "g1": "diag", "g2": "diag", "g3": "L", "h": "straight",
}


def _lengths(g) -> dict[str, tuple[float, str]]:
    """Cutting length (mm) + its formula string per mark, from geometry only."""
    ow = g.outer_width_mm
    oh = g.outer_height_mm
    barrel = g.barrel_length_mm
    b = g.haunch_mm
    c = CLEAR_COVER_MM
    transverse = ow - 2.0 * c + 2.0 * (oh / 8.0)
    longitudinal = barrel - 2.0 * c
    vertical = oh - 2.0 * c + 2.0 * (ow / 8.0)
    haunch = 1.414 * b + 2.0 * 9.0 * 12.0  # diagonal leg + nominal hooks
    return {
        "a1": (transverse, "outer_width - 2*cover + 2 bends"),
        "a2": (transverse, "outer_width - 2*cover + 2 bends"),
        "b": (longitudinal, "barrel - 2*cover"),
        "c": (vertical, "outer_height - 2*cover + 2 bends"),
        "d": (vertical, "outer_height - 2*cover + 2 bends"),
        "e": (longitudinal, "barrel - 2*cover"),
        "f1": (transverse, "outer_width - 2*cover + 2 bends"),
        "f2": (transverse, "outer_width - 2*cover + 2 bends"),
        "g1": (haunch, "1.414*haunch + hooks"),
        "g2": (haunch, "1.414*haunch + hooks"),
        "g3": (haunch, "1.414*haunch + hooks"),
        "h": (longitudinal, "barrel - 2*cover"),
    }


def _shape_sketch(msp, kind: str, x0: float, y0: float, w: float, h: float) -> None:
    if kind == "straight":
        line(msp, (x0, y0 + h / 2.0), (x0 + w, y0 + h / 2.0), layer=LAYER_BARS)
    elif kind == "L":
        polyline(msp, [(x0, y0 + h), (x0, y0), (x0 + w, y0)], layer=LAYER_BARS, close=False)
    elif kind == "U":
        polyline(msp, [(x0, y0 + h), (x0, y0), (x0 + w, y0), (x0 + w, y0 + h)],
                 layer=LAYER_BARS, close=False)
    elif kind == "diag":
        line(msp, (x0, y0), (x0 + w, y0 + h), layer=LAYER_BARS)


def build(geometry, params=None) -> Drawing:  # noqa: ARG001 - params kept for a uniform API
    g = geometry
    s = 60.0
    doc = new_doc(s)
    msp = doc.modelspace()

    lengths = _lengths(g)
    # column x-boundaries (mm) and a fixed row height
    cols = [0.0, 6.0 * s, 16.0 * s, 30.0 * s, 46.0 * s, 60.0 * s]
    headers = ["MARK", "SHAPE", "dia@spc", "LENGTH FORMULA", "CUT LEN (mm)"]
    row_h = 3.0 * s
    n_rows = len(BAR_MARKS) + 1
    total_w = cols[-1]
    top = 0.0

    # outer frame + row lines + column lines
    polyline(msp, [(0.0, top - n_rows * row_h), (total_w, top - n_rows * row_h),
                   (total_w, top), (0.0, top)], layer=LAYER_OUTLINE)
    for r in range(1, n_rows):
        y = top - r * row_h
        line(msp, (0.0, y), (total_w, y), layer=LAYER_OUTLINE)
    for x in cols[1:-1]:
        line(msp, (x, top), (x, top - n_rows * row_h), layer=LAYER_OUTLINE)

    for ci, head in enumerate(headers):
        text(msp, head, (cols[ci] + 0.4 * s, top - row_h + 0.9 * s), 0.8 * s, layer=LAYER_TEXT)

    for ri, mark in enumerate(BAR_MARKS, start=1):
        y = top - (ri + 1) * row_h
        bar = g.bar_schedule.get(mark, {})
        dia = int(bar.get("dia_mm", 0))
        spc = int(bar.get("spacing_mm", 0))
        cut, formula = lengths[mark]
        text(msp, mark, (cols[0] + 0.4 * s, y + 0.9 * s), 0.8 * s, layer=LAYER_TEXT)
        _shape_sketch(msp, _SHAPE_KIND[mark], cols[1] + 1.0 * s, y + 0.6 * s, 7.0 * s, 1.6 * s)
        text(msp, f"{dia}Ø@{spc}", (cols[2] + 0.4 * s, y + 0.9 * s), 0.7 * s, layer=LAYER_TEXT)
        text(msp, formula, (cols[3] + 0.4 * s, y + 0.9 * s), 0.6 * s, layer=LAYER_TEXT)
        text(msp, f"{cut:.0f}", (cols[4] + 0.4 * s, y + 0.9 * s), 0.7 * s, layer=LAYER_TEXT)

    _ = MARK_NOTATION  # imported for provenance / cross-reference with notations.py
    add_title_and_caption(msp, "REINFORCEMENT FOR BOX - BAR-BENDING SHAPE TABLE", s,
                          subtitle=f"CONFIG {g.config_id}")
    return doc
