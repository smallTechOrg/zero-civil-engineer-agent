"""Diagram 4 - Section of Curtain / Drop Wall.

Detail through the curtain + drop wall: ``curtain_thickness_mm`` wide, curtain
extends ``curtain_depth_mm`` below bed, with the drop-wall ``drop_wall_depth_mm``
key deeper below bed, plus vertical + horizontal reinforcement. All from geometry.
"""

from __future__ import annotations

from ezdxf.document import Drawing
from ezdxf.enums import TextEntityAlignment

from components.m00004_box_culvert.drawings import (
    LAYER_BARS,
    LAYER_WEEP,
    add_title_and_caption,
    dim,
    line,
    new_doc,
    polyline,
    scale_for,
    text,
)


def build(geometry, params=None) -> Drawing:  # noqa: ARG001 - params kept for a uniform API
    g = geometry
    t = g.curtain_thickness_mm
    curtain = g.curtain_depth_mm
    drop = g.drop_wall_depth_mm
    hx = t / 2.0

    s = scale_for(t * 3.0, drop * 1.3)
    doc = new_doc(s)
    msp = doc.modelspace()

    # curtain body from bed (y=0) down to -curtain, then drop-wall key to -drop
    polyline(msp, [(-hx, 0.0), (hx, 0.0), (hx, -curtain), (-hx, -curtain)])
    polyline(msp, [(-hx, -curtain), (hx, -curtain), (hx, -drop), (-hx, -drop)])

    # bed level line
    line(msp, (-t, 0.0), (t, 0.0), layer=LAYER_WEEP)
    text(msp, "BED LEVEL", (t + 0.5 * s, 0.0), 0.7 * s)

    # reinforcement: two vertical main bars + horizontal distributors
    cover = 60.0
    for x in (-hx + cover, hx - cover):
        line(msp, (x, -0.3 * curtain), (x, -drop + cover), layer=LAYER_BARS)
    for j in range(1, 6):
        y = -drop + j * (drop - cover) / 6.0
        line(msp, (-hx + cover, y), (hx - cover, y), layer=LAYER_BARS)
    text(msp, "MAIN + DISTRIBUTION REINFORCEMENT", (hx + 0.5 * s, -curtain / 2.0), 0.6 * s, layer=LAYER_BARS)

    # dimensions: thickness, curtain depth, drop-wall key depth
    dim(msp, base=(0.0, 3.0 * s), p1=(-hx, 0.0), p2=(hx, 0.0))
    dim(msp, base=(-hx - 4.0 * s, 0.0), p1=(-hx, 0.0), p2=(-hx, -curtain), angle=90)
    dim(msp, base=(hx + 6.0 * s, 0.0), p1=(hx, 0.0), p2=(hx, -drop), angle=90)
    text(msp, f"CURTAIN {curtain:g}  /  DROP-WALL KEY {drop:g}", (0.0, -drop - 1.2 * s),
         0.7 * s, TextEntityAlignment.MIDDLE_CENTER)

    add_title_and_caption(msp, "SECTION OF CURTAIN / DROP WALL", s, subtitle="(N.T.S.)")
    return doc
