"""Deterministic a1..h bar layout."""

from components.m00004_box_culvert.reinforcement import BAR_MARKS, bar_layout
from components.m00004_box_culvert.sizing import size
from components.m00004_box_culvert.params import M00004Params


def _geometry():
    return size(M00004Params(clear_span_m=4.0, clear_height_m=4.0, cushion_m=2.0)).geometry


def test_all_twelve_marks_returned_with_positions():
    marks = bar_layout(_geometry())
    assert set(marks) == set(BAR_MARKS)
    assert len(marks) == 12
    for mark in BAR_MARKS:
        bm = marks[mark]
        # every mark has at least one drawable position (polyline or dot) + a leader
        assert bm.polylines or bm.dots
        assert isinstance(bm.leader, tuple) and len(bm.leader) == 2
        assert bm.notation  # member/face description for the notations glossary


def test_positions_lie_within_the_outer_section():
    g = _geometry()
    ox = g.outer_width_mm / 2.0
    oy = g.outer_height_mm / 2.0
    marks = bar_layout(g)
    tol = 5.0
    for bm in marks.values():
        pts = [p for line in bm.polylines for p in line] + list(bm.dots)
        for x, y in pts:
            assert -ox - tol <= x <= ox + tol
            assert -oy - tol <= y <= oy + tol


def test_top_and_bottom_slab_bars_are_on_opposite_faces():
    marks = bar_layout(_geometry())
    a1_y = marks["a1"].polylines[0][0][1]   # top-slab inner face main
    f1_y = marks["f1"].polylines[0][0][1]   # bottom-slab inner face main
    assert a1_y > 0 > f1_y
