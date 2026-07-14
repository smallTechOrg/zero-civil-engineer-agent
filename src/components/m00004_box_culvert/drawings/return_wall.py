"""Diagram 6 - Return Wall (section / elevation).

Tapering profile from ``return_wall_base_width_mm`` at the base to
``return_wall_top_width_mm`` (= ``thickness_mm``) at the top, over the return-wall
height (the outer box height), with vertical main reinforcement following the
battered face. Base width and top width are both dimensioned. From geometry.
"""

from __future__ import annotations

from ezdxf.document import Drawing
from ezdxf.enums import TextEntityAlignment

from components.m00004_box_culvert.drawings import (
    LAYER_BARS,
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
    base_w = g.return_wall_base_width_mm
    top_w = g.return_wall_top_width_mm
    height = g.outer_height_mm

    s = scale_for(base_w * 2.0, height * 1.2)
    doc = new_doc(s)
    msp = doc.modelspace()

    # tapering profile: vertical earth face on the left, battered face on the right
    profile = [
        (0.0, 0.0),
        (base_w, 0.0),
        (top_w, height),
        (0.0, height),
    ]
    polyline(msp, profile)

    # vertical main reinforcement following each face
    cover = 60.0
    line(msp, (cover, cover), (cover, height - cover), layer=LAYER_BARS)
    line(msp, (base_w - cover, cover), (top_w - cover, height - cover), layer=LAYER_BARS)
    for j in range(1, 5):
        y = j * height / 5.0
        x_face = base_w + (top_w - base_w) * (y / height)
        line(msp, (cover, y), (x_face - cover, y), layer=LAYER_BARS)
    text(msp, "MAIN + DISTRIBUTION REINFORCEMENT", (base_w + 0.5 * s, height / 2.0), 0.6 * s, layer=LAYER_BARS)

    # dimensions: base width, top width, height
    dim(msp, base=(base_w / 2.0, -3.0 * s), p1=(0.0, 0.0), p2=(base_w, 0.0))
    dim(msp, base=(top_w / 2.0, height + 3.0 * s), p1=(0.0, height), p2=(top_w, height))
    dim(msp, base=(-4.0 * s, 0.0), p1=(0.0, 0.0), p2=(0.0, height), angle=90)
    text(msp, f"TAPER {base_w:g} -> {top_w:g}", (base_w + 0.5 * s, 1.0 * s), 0.7 * s,
         TextEntityAlignment.LEFT)

    add_title_and_caption(msp, "RETURN WALL", s, subtitle="(N.T.S.)")
    return doc
