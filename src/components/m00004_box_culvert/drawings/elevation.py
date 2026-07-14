"""Diagram 1 - Sectional Elevation at X-Y (longitudinal, along the waterway).

Box under the embankment: C.L. of track + formation level (``formation_width_mm``);
earth banks at ``side_slope_h_per_v`` (H:V); HFL line at ``hfl_above_bed_mm``; bed
level + bed slope ``1 in bed_slope_run``; ``stone_pitching_thickness_mm`` pitching
with cement grouting; hand-packed boulders; wing/return + drop/curtain walls at
each end; ``base_course_thickness_mm`` base course. All from ``M00004Geometry``.
"""

from __future__ import annotations

from ezdxf.document import Drawing
from ezdxf.enums import TextEntityAlignment

from components.m00004_box_culvert.drawings import (
    LAYER_HFL,
    LAYER_HIDDEN,
    LAYER_TEXT,
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
    ox = g.outer_width_mm / 2.0
    oh = g.outer_height_mm
    fw = g.formation_width_mm
    cushion = g.cushion_mm
    slope = g.side_slope_h_per_v
    fl = oh + cushion  # formation level above bed (y = 0 at bed)
    toe_x = fw / 2.0 + slope * fl  # embankment toe offset from centre-line
    pitch = g.stone_pitching_thickness_mm
    base = g.base_course_thickness_mm

    s = scale_for(2.0 * toe_x, fl * 1.3)
    doc = new_doc(s)
    msp = doc.modelspace()

    # embankment ground line: toe -> formation shoulder -> shoulder -> toe
    ground = [(-toe_x, 0.0), (-fw / 2.0, fl), (fw / 2.0, fl), (toe_x, 0.0)]
    polyline(msp, ground, close=False)
    # formation level line + C.L. of track
    text(msp, "FORMATION LEVEL", (0.0, fl + 0.6 * s), 0.8 * s, TextEntityAlignment.MIDDLE_CENTER)
    line(msp, (0.0, fl + 3.0 * s), (0.0, -g.drop_wall_depth_mm - 2.0 * s), layer=LAYER_HIDDEN)
    text(msp, "C.L. OF TRACK", (0.4 * s, fl + 2.0 * s), 0.7 * s)

    # stone pitching w/ cement grouting - a band parallel to each earth bank
    for sign in (-1.0, 1.0):
        polyline(
            msp,
            [(sign * toe_x, base), (sign * fw / 2.0, fl + pitch)],
            close=False,
        )
    text(
        msp,
        f"STONE PITCHING {pitch:g} w/ CEMENT GROUTING",
        (-fw / 2.0 - 3.0 * s, fl / 2.0),
        0.7 * s,
    )
    text(msp, "HAND-PACKED BOULDERS", (toe_x - 6.0 * s, 1.2 * s), 0.7 * s)

    # base course under the box + apron
    polyline(msp, [(-toe_x, -base), (toe_x, -base), (toe_x, 0.0), (-toe_x, 0.0)])
    text(msp, f"BASE COURSE {base:g}", (0.0, -base - 1.2 * s), 0.7 * s, TextEntityAlignment.MIDDLE_CENTER)

    # the box (outer rectangle + hidden opening) sitting on the bed
    polyline(msp, [(-ox, 0.0), (ox, 0.0), (ox, oh), (-ox, oh)])
    ihs = g.clear_span_mm / 2.0
    polyline(msp, [(-ihs, g.thickness_mm), (ihs, g.thickness_mm),
                   (ihs, g.thickness_mm + g.clear_height_mm), (-ihs, g.thickness_mm + g.clear_height_mm)],
             layer=LAYER_HIDDEN)

    # wing/return + drop/curtain walls at each end (below the bed)
    for sign in (-1.0, 1.0):
        x = sign * ox
        polyline(msp, [(x - sign * g.curtain_thickness_mm, 0.0), (x, 0.0),
                       (x, -g.curtain_depth_mm), (x - sign * g.curtain_thickness_mm, -g.curtain_depth_mm)])
        # drop wall key deeper below bed
        line(msp, (x, -g.curtain_depth_mm), (x, -g.drop_wall_depth_mm))
    text(msp, f"CURTAIN / DROP WALL (KEY {g.drop_wall_depth_mm:g})", (0.0, -g.drop_wall_depth_mm - 1.0 * s),
         0.7 * s, TextEntityAlignment.MIDDLE_CENTER)

    # HFL line across the waterway opening
    hfl = g.hfl_above_bed_mm
    line(msp, (-ihs, g.thickness_mm + hfl), (ihs, g.thickness_mm + hfl), layer=LAYER_HFL)
    text(msp, f"HFL (+{hfl:g})", (ihs + 0.5 * s, g.thickness_mm + hfl), 0.8 * s, layer=LAYER_HFL)

    # bed level + bed slope callout
    line(msp, (-toe_x, 0.0), (toe_x, 0.0), layer=LAYER_WEEP)
    text(msp, f"BED LEVEL - SLOPE 1 in {g.bed_slope_run:g}", (0.0, 0.6 * s), 0.75 * s,
         TextEntityAlignment.MIDDLE_CENTER)

    # dimensions
    dim(msp, base=(0.0, fl + 5.0 * s), p1=(-fw / 2.0, fl), p2=(fw / 2.0, fl))
    dim(msp, base=(-ox - 4.0 * s, 0.0), p1=(-ox, 0.0), p2=(-ox, oh), angle=90)

    add_title_and_caption(msp, "SECTIONAL ELEVATION AT X-Y", s, subtitle=f"CONFIG {g.config_id}  (N.T.S.)")
    return doc
