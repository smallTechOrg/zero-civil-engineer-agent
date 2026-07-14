"""B x B Haunch table.

The haunch ``B x B`` schedule against the box size for the selected standard
config: box clear opening + overall size vs the 45-degree haunch leg
``haunch_mm``. All values from ``M00004Geometry``.
"""

from __future__ import annotations

from ezdxf.document import Drawing

from components.m00004_box_culvert.drawings import (
    LAYER_OUTLINE,
    LAYER_TEXT,
    add_title_and_caption,
    line,
    new_doc,
    polyline,
    text,
)


def build(geometry, params=None) -> Drawing:  # noqa: ARG001 - uniform API
    g = geometry
    s = 60.0
    doc = new_doc(s)
    msp = doc.modelspace()

    headers = ["CONFIG", "CLEAR SPAN x HEIGHT", "OVERALL", "THICKNESS", "HAUNCH B x B"]
    row = [
        g.config_id,
        f"{g.clear_span_mm:g} x {g.clear_height_mm:g}",
        f"{g.outer_width_mm:g} x {g.outer_height_mm:g}",
        f"{g.thickness_mm:g}",
        f"{g.haunch_mm:g} x {g.haunch_mm:g}",
    ]
    cols = [0.0, 10.0 * s, 26.0 * s, 42.0 * s, 52.0 * s, 64.0 * s]
    row_h = 3.0 * s
    total_w = cols[-1]
    top = 0.0
    n_rows = 2

    polyline(msp, [(0.0, top - n_rows * row_h), (total_w, top - n_rows * row_h),
                   (total_w, top), (0.0, top)], layer=LAYER_OUTLINE)
    line(msp, (0.0, top - row_h), (total_w, top - row_h), layer=LAYER_OUTLINE)
    for x in cols[1:-1]:
        line(msp, (x, top), (x, top - n_rows * row_h), layer=LAYER_OUTLINE)

    for ci, head in enumerate(headers):
        text(msp, head, (cols[ci] + 0.4 * s, top - row_h + 0.9 * s), 0.75 * s, layer=LAYER_TEXT)
    for ci, value in enumerate(row):
        text(msp, value, (cols[ci] + 0.4 * s, top - 2.0 * row_h + 0.9 * s), 0.75 * s, layer=LAYER_TEXT)

    add_title_and_caption(msp, "B x B HAUNCH TABLE", s, subtitle="HAUNCH vs BOX SIZE")
    return doc
