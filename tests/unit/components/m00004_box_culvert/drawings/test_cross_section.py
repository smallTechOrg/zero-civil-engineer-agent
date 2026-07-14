"""Cross Section of R.C.C. Box: a1..h bars drawn in position + dimensions read back."""

from components.m00004_box_culvert.drawings import cross_section
from components.m00004_box_culvert.reinforcement import BAR_MARKS

from .conftest import save_and_read, texts


def test_cross_section_draws_the_a1_h_bars(geometry, params, tmp_path):
    doc = save_and_read(cross_section.build(geometry, params), tmp_path, "cross_section")
    msp = doc.modelspace()
    bar_entities = [e for e in msp if e.dxf.layer == "BARS"]
    assert bar_entities, "cross-section must draw reinforcement on the BARS layer"
    labels = texts(doc)
    # every mark carries a leader tag "<mark>:..."
    for mark in BAR_MARKS:
        assert any(t.startswith(f"{mark}:") for t in labels), f"missing bar tag for {mark}"


def test_cross_section_dimensions_read_back(geometry, params, tmp_path):
    doc = save_and_read(cross_section.build(geometry, params), tmp_path, "cross_section")
    measures = [round(float(d.get_measurement()), 1) for d in doc.modelspace().query("DIMENSION")]
    assert any(abs(m - geometry.clear_span_mm) <= 1.0 for m in measures)
    assert any(abs(m - geometry.clear_height_mm) <= 1.0 for m in measures)


def test_cross_section_carries_provisional_caption(geometry, params, tmp_path):
    doc = save_and_read(cross_section.build(geometry, params), tmp_path, "cross_section")
    assert any("PROVISIONAL" in t for t in texts(doc))
