"""Diagram 2 - Cross Section of R.C.C. Box.

The Phase-1 GA section (hatched concrete ring: outer rectangle + inner haunched
octagon, with dimension chains) refactored into its own module, WITH the a1..h
reinforcement bars drawn in position - the deterministic layout from
``reinforcement.bar_layout`` (reused unchanged). Geometry/behaviour of the
concrete section is equivalent to the Phase-1 ``drawing._draw_section``.
"""

from __future__ import annotations

from ezdxf.document import Drawing
from ezdxf.enums import TextEntityAlignment

from components.m00004_box_culvert.drawings import (
    CAVEAT,
    LAYER_BARS,
    LAYER_HATCH,
    add_title_and_caption,
    dim,
    line,
    new_doc,
    octagon,
    polyline,
    scale_for,
    text,
)
from components.m00004_box_culvert.reinforcement import BAR_MARKS, bar_layout


def build(geometry, params=None) -> Drawing:  # noqa: ARG001 - params kept for a uniform API
    g = geometry
    s = scale_for(g.outer_width_mm, g.outer_height_mm)
    doc = new_doc(s)
    msp = doc.modelspace()

    hs = g.clear_span_mm / 2.0
    hh = g.clear_height_mm / 2.0
    ox = g.outer_width_mm / 2.0
    oy = g.outer_height_mm / 2.0
    outer = [(-ox, -oy), (ox, -oy), (ox, oy), (-ox, oy)]
    inner = octagon(g)

    # hatched concrete ring: outer boundary with the opening as an island
    hatch = msp.add_hatch(dxfattribs={"layer": LAYER_HATCH})
    hatch.set_pattern_fill("ANSI31", scale=max(1.0, 0.4 * s))
    hatch.paths.add_polyline_path(outer, is_closed=True, flags=1)  # external
    hatch.paths.add_polyline_path(inner, is_closed=True, flags=0)  # hole
    polyline(msp, outer)
    polyline(msp, inner)

    # a1..h reinforcement in position (deterministic layout, reused from reinforcement.py)
    marks = bar_layout(g)
    for mark in BAR_MARKS:
        bm = marks[mark]
        for run in bm.polylines:
            polyline(msp, run, layer=LAYER_BARS, close=False)
        for cx, cy in bm.dots:
            msp.add_circle((cx, cy), max(6.0, 0.12 * s), dxfattribs={"layer": LAYER_BARS})
        bar = g.bar_schedule.get(mark, {})
        dia = int(bar.get("dia_mm", 0))
        spacing = int(bar.get("spacing_mm", 0))
        lx, ly = bm.leader
        text(msp, f"{mark}:{dia}Ø@{spacing}", (lx, ly), 0.55 * s, layer=LAYER_BARS)

    off1 = 3.0 * s
    off2 = 7.0 * s
    off3 = 11.0 * s
    dim(msp, base=(0.0, -oy - off2), p1=(-hs, -oy), p2=(hs, -oy))
    dim(msp, base=(0.0, -oy - off3), p1=(-ox, -oy), p2=(ox, -oy))
    dim(msp, base=(-ox - off2, 0.0), p1=(-ox, -hh), p2=(-ox, hh), angle=90)
    dim(msp, base=(-ox - off3, 0.0), p1=(-ox, -oy), p2=(-ox, oy), angle=90)
    dim(msp, base=(ox + off1, (hh + oy) / 2.0), p1=(ox, hh), p2=(ox, oy), angle=90)
    text(msp, f"HAUNCH {g.haunch_mm:g} x {g.haunch_mm:g}", (hs - g.haunch_mm, hh + 1.2 * s), 0.8 * s)
    text(msp, f"CONFIG {g.config_id}  -  {CAVEAT}", (0.0, oy + off2 + 0.6 * s),
         0.7 * s, TextEntityAlignment.MIDDLE_CENTER)

    add_title_and_caption(msp, "CROSS SECTION OF R.C.C. BOX", s,
                          subtitle="a1..h REINFORCEMENT IN POSITION (N.T.S.)")
    return doc
