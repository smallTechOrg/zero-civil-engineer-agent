"""Diagram 3 - Plan.

Promotes the Phase-1 part-plan: barrel opening; wing/return walls splaying at the
embankment ``side_slope_h_per_v`` along both ends; aprons; curtain & drop walls;
and ``weep_hole_dia_mm`` PVC weep holes at ``weep_hole_spacing_mm`` c/c along the
barrel. Plan axes: X = barrel length (0..L), Y = transverse width centred on 0.
"""

from __future__ import annotations

from ezdxf.document import Drawing
from ezdxf.enums import TextEntityAlignment

from components.m00004_box_culvert.drawings import (
    LAYER_HIDDEN,
    LAYER_WEEP,
    add_title_and_caption,
    circle,
    dim,
    new_doc,
    polyline,
    scale_for,
    text,
)


def build(geometry, params=None) -> Drawing:  # noqa: ARG001 - params kept for a uniform API
    g = geometry
    length = g.barrel_length_mm
    w = g.outer_width_mm
    cls = g.clear_span_mm
    wing = g.wing_len_mm
    apron = g.apron_len_mm
    slope = g.side_slope_h_per_v
    splay = wing * min(slope, 4.0) / max(slope, 1.0)  # transverse splay of the wing tip

    s = scale_for(length + 2.0 * wing, w * 2.0)
    doc = new_doc(s)
    msp = doc.modelspace()

    # barrel outer band + clear opening (dashed) through the barrel
    polyline(msp, [(0.0, -w / 2.0), (length, -w / 2.0), (length, w / 2.0), (0.0, w / 2.0)])
    polyline(msp, [(0.0, -cls / 2.0), (length, -cls / 2.0), (length, cls / 2.0), (0.0, cls / 2.0)],
             layer=LAYER_HIDDEN)

    # wing/return walls splaying outward along the embankment slope, both ends
    for end_x, direction in ((0.0, -1.0), (length, 1.0)):
        tip_x = end_x + direction * wing
        for side in (1.0, -1.0):
            polyline(
                msp,
                [
                    (end_x, side * w / 2.0),
                    (tip_x, side * (w / 2.0 + splay)),
                    (tip_x, side * (cls / 2.0 + splay)),
                    (end_x, side * cls / 2.0),
                ],
            )
        # apron floor beyond each end (centre band)
        apron_x = end_x + direction * apron
        polyline(msp, [(end_x, -cls / 2.0), (apron_x, -cls / 2.0), (apron_x, cls / 2.0), (end_x, cls / 2.0)],
                 layer=LAYER_HIDDEN)
        # curtain / drop wall transverse band at each end
        cx = end_x + direction * g.curtain_thickness_mm
        polyline(msp, [(end_x, -w / 2.0), (cx, -w / 2.0), (cx, w / 2.0), (end_x, w / 2.0)])

    # weep holes @ weep_hole_spacing_mm c/c along both side walls of the barrel
    spacing = g.weep_hole_spacing_mm
    radius = g.weep_hole_dia_mm / 2.0
    count = max(1, int(length // spacing))
    for i in range(1, count):
        x = i * spacing
        if x >= length:
            break
        circle(msp, (x, cls / 2.0), radius, layer=LAYER_WEEP)
        circle(msp, (x, -cls / 2.0), radius, layer=LAYER_WEEP)
    text(msp, f"{g.weep_hole_dia_mm:g}Ø PVC WEEP HOLES @ {spacing:g} c/c",
         (length / 2.0, w / 2.0 + splay + 1.5 * s), 0.8 * s, TextEntityAlignment.MIDDLE_CENTER)

    dim(msp, base=(length / 2.0, -w / 2.0 - splay - 4.0 * s), p1=(0.0, -w / 2.0), p2=(length, -w / 2.0))

    add_title_and_caption(msp, "PLAN", s, subtitle=f"CONFIG {g.config_id}  (N.T.S.)")
    return doc
