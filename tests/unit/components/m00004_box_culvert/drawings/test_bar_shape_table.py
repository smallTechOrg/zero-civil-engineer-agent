"""Bar-bending SHAPE table: a row per a1..h mark with shape + cut length."""

from components.m00004_box_culvert.drawings import bar_shape_table
from components.m00004_box_culvert.reinforcement import BAR_MARKS

from .conftest import save_and_read, texts


def test_bar_shape_table_has_a_row_per_mark(geometry, params, tmp_path):
    doc = save_and_read(bar_shape_table.build(geometry, params), tmp_path, "bar_shape_table")
    labels = texts(doc)
    for mark in BAR_MARKS:
        assert mark in labels, f"bar-shape table missing mark {mark}"
    # bent-bar shape sketches are drawn on the BARS layer
    assert [e for e in doc.modelspace() if e.dxf.layer == "BARS"]


def test_bar_shape_table_headers_and_caption(geometry, params, tmp_path):
    doc = save_and_read(bar_shape_table.build(geometry, params), tmp_path, "bar_shape_table")
    labels = texts(doc)
    assert any("LENGTH FORMULA" in t for t in labels)
    assert any("PROVISIONAL" in t for t in labels)
