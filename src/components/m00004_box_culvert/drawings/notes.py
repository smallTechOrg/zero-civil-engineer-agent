"""Notes block.

Standard RDSO/M-00004 notes: concrete grade (``concrete_grade_resolved``) + steel
grade, clear cover, wearing course, PCC, stone pitching, bed slope, "ALL
DIMENSIONS IN mm", and the bold PROVISIONAL / NOT-FOR-CONSTRUCTION caption. Every
value comes from ``M00004Geometry`` (grade) / ``M00004Params`` (steel).
"""

from __future__ import annotations

from ezdxf.document import Drawing
from ezdxf.enums import TextEntityAlignment

from components.m00004_box_culvert.drawings import (
    LAYER_OUTLINE,
    LAYER_TEXT,
    add_title_and_caption,
    new_doc,
    polyline,
    text,
)
from components.m00004_box_culvert.params import CLEAR_COVER_MM


def _note_lines(geometry, steel_grade: str) -> list[str]:
    g = geometry
    return [
        f"1. CONCRETE GRADE {g.concrete_grade_resolved}; REINFORCEMENT STEEL {steel_grade} "
        "(PROVISIONAL - verify against RDSO/M-00004).",
        f"2. CLEAR COVER TO REINFORCEMENT = {CLEAR_COVER_MM:g} mm.",
        f"3. WEARING COURSE = {g.wearing_course_thickness_mm:g} mm ON THE TOP SLAB / FORMATION.",
        f"4. PCC LEVELLING COURSE = {g.pcc_thickness_mm:g} mm UNDER THE BOX.",
        f"5. STONE PITCHING = {g.stone_pitching_thickness_mm:g} mm w/ CEMENT GROUTING ON THE "
        f"SLOPES; BASE COURSE = {g.base_course_thickness_mm:g} mm.",
        f"6. BED SLOPE 1 in {g.bed_slope_run:g}; HFL = {g.hfl_above_bed_mm:g} mm ABOVE BED.",
        f"7. {g.weep_hole_dia_mm:g}Ø PVC WEEP HOLES @ {g.weep_hole_spacing_mm:g} mm c/c.",
        "8. ALL DIMENSIONS IN mm UNLESS NOTED OTHERWISE.",
        "9. THIS IS A STANDARD REPRODUCTION - EVERY CATALOGUE VALUE IS PROVISIONAL.",
        "10. PROVISIONAL - NOT FOR CONSTRUCTION.",
    ]


def build(geometry, params=None) -> Drawing:
    steel_grade = params.steel_grade.value if params is not None else "Fe415"
    s = 60.0
    doc = new_doc(s)
    msp = doc.modelspace()

    lines = _note_lines(geometry, steel_grade)
    row_h = 2.4 * s
    total_w = 60.0 * s
    top = 0.0
    height = (len(lines) + 1) * row_h
    polyline(msp, [(0.0, top - height), (total_w, top - height), (total_w, top), (0.0, top)],
             layer=LAYER_OUTLINE)
    text(msp, "NOTES", (0.6 * s, top - row_h + 0.7 * s), 1.0 * s, layer=LAYER_TEXT)
    for i, note in enumerate(lines, start=1):
        y = top - (i + 1) * row_h + 0.6 * s
        text(msp, note, (0.6 * s, y), 0.7 * s, layer=LAYER_TEXT)

    add_title_and_caption(msp, "NOTES", s,
                          subtitle="PROVISIONAL - NOT FOR CONSTRUCTION")
    # a bold centred restatement of the caveat inside the block
    text(msp, "PROVISIONAL - NOT FOR CONSTRUCTION", (total_w / 2.0, top - height - 1.2 * s),
         0.9 * s, TextEntityAlignment.MIDDLE_CENTER)
    return doc
