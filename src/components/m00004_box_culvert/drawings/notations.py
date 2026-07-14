"""Notations glossary.

A legend mapping each reinforcement mark to its member/face, taken verbatim from
``reinforcement.MARK_NOTATION`` (the single source shared with the section and the
bar-shape table).
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
from components.m00004_box_culvert.reinforcement import BAR_MARKS, MARK_NOTATION


def build(geometry=None, params=None) -> Drawing:  # noqa: ARG001 - uniform API
    s = 60.0
    doc = new_doc(s)
    msp = doc.modelspace()

    col_mark = 0.0
    col_note = 5.0 * s
    total_w = 60.0 * s
    row_h = 2.6 * s
    n_rows = len(BAR_MARKS) + 1
    top = 0.0

    polyline(msp, [(0.0, top - n_rows * row_h), (total_w, top - n_rows * row_h),
                   (total_w, top), (0.0, top)], layer=LAYER_OUTLINE)
    for r in range(1, n_rows):
        line(msp, (0.0, top - r * row_h), (total_w, top - r * row_h), layer=LAYER_OUTLINE)
    line(msp, (col_note, top), (col_note, top - n_rows * row_h), layer=LAYER_OUTLINE)

    text(msp, "MARK", (col_mark + 0.4 * s, top - row_h + 0.8 * s), 0.8 * s, layer=LAYER_TEXT)
    text(msp, "MEMBER / FACE (NOTATION)", (col_note + 0.4 * s, top - row_h + 0.8 * s), 0.8 * s,
         layer=LAYER_TEXT)

    for ri, mark in enumerate(BAR_MARKS, start=1):
        y = top - (ri + 1) * row_h
        text(msp, mark, (col_mark + 0.4 * s, y + 0.8 * s), 0.8 * s, layer=LAYER_TEXT)
        text(msp, MARK_NOTATION[mark], (col_note + 0.4 * s, y + 0.8 * s), 0.65 * s, layer=LAYER_TEXT)

    add_title_and_caption(msp, "NOTATIONS", s, subtitle="a1..h REINFORCEMENT LEGEND")
    return doc
