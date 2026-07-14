"""Diagram 5 - Typical Details at A & B.

Reinforcement-placement details at a top-slab / wall / haunch corner: weep holes
(``weep_hole_dia_mm`` PVC @ ``weep_hole_spacing_mm`` c/c) + earth retainer + skin
reinforcement + main reinforcement + distributors in the top/bottom slabs +
haunch bars. All from geometry.
"""

from __future__ import annotations

from ezdxf.document import Drawing
from ezdxf.enums import TextEntityAlignment

from components.m00004_box_culvert.drawings import (
    LAYER_BARS,
    LAYER_WEEP,
    add_title_and_caption,
    circle,
    line,
    new_doc,
    polyline,
    scale_for,
    text,
)


def _detail(msp, g, s, *, ox0: float, label: str) -> None:
    """One corner detail (top-slab + side-wall + haunch) at horizontal offset ox0."""
    t = g.thickness_mm
    b = g.haunch_mm
    span = min(g.clear_span_mm, 2400.0) / 2.0
    ht = min(g.clear_height_mm, 2400.0) / 2.0

    def P(x, y):
        return (x + ox0, y)

    # concrete corner: top slab meeting the side wall with a 45-degree haunch
    polyline(msp, [P(0.0, ht + t), P(span + t, ht + t), P(span + t, -ht),
                   P(span, -ht), P(span, ht), P(0.0, ht)])
    # haunch fillet
    line(msp, P(span, ht), P(span - b, ht), layer=LAYER_BARS)
    polyline(msp, [P(span, ht - b), P(span - b, ht)], close=False)

    cover = 50.0
    # main reinforcement (top slab, transverse) + distributor (dots)
    line(msp, P(cover, ht + t - cover), P(span + t - cover, ht + t - cover), layer=LAYER_BARS)
    line(msp, P(cover, ht + cover), P(span, ht + cover), layer=LAYER_BARS)
    for i in range(4):
        circle(msp, P(cover + i * span / 4.0, ht + t / 2.0), 8.0, layer=LAYER_BARS)
    # skin reinforcement on the wall outer face + earth retainer
    line(msp, P(span + t - cover, ht + t), P(span + t - cover, -ht + cover), layer=LAYER_BARS)
    # haunch bars (diagonal)
    line(msp, P(span - b, ht), P(span, ht - b), layer=LAYER_BARS)

    # weep hole through the wall
    circle(msp, P(span + t / 2.0, 0.0), g.weep_hole_dia_mm / 2.0, layer=LAYER_WEEP)
    text(msp, f"{g.weep_hole_dia_mm:g}Ø PVC WEEP @ {g.weep_hole_spacing_mm:g} c/c",
         P(span + t + 0.5 * s, 0.0), 0.6 * s, layer=LAYER_WEEP)
    text(msp, "EARTH RETAINER + SKIN REINF.", P(span + t + 0.5 * s, ht), 0.6 * s, layer=LAYER_BARS)
    text(msp, "MAIN + DISTRIBUTORS + HAUNCH BARS", P(0.0, ht + t + 1.0 * s), 0.6 * s)
    text(msp, label, P(span / 2.0, -ht - 1.5 * s), 0.9 * s, TextEntityAlignment.MIDDLE_CENTER)


def build(geometry, params=None) -> Drawing:  # noqa: ARG001 - params kept for a uniform API
    g = geometry
    s = scale_for(g.clear_span_mm, g.clear_height_mm)
    doc = new_doc(s)
    msp = doc.modelspace()

    span = min(g.clear_span_mm, 2400.0) / 2.0 + g.thickness_mm
    _detail(msp, g, s, ox0=0.0, label="DETAIL AT A (TOP SLAB)")
    _detail(msp, g, s, ox0=span + 8.0 * s, label="DETAIL AT B (BOTTOM SLAB)")

    add_title_and_caption(msp, "TYPICAL DETAILS AT A & B", s, subtitle="(N.T.S.)")
    return doc
