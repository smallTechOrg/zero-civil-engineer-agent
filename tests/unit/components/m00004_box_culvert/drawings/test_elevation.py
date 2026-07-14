"""Sectional Elevation at X-Y: HFL line + bed-slope callout present, file emitted."""

from components.m00004_box_culvert.drawings import elevation

from .conftest import save_and_read, texts


def test_elevation_emits_and_reopens_with_hfl_and_bed_slope(geometry, params, tmp_path):
    doc = save_and_read(elevation.build(geometry, params), tmp_path, "elevation")
    labels = texts(doc)
    # HFL line (on the HFL layer) + its label
    hfl_lines = [e for e in doc.modelspace().query("LINE") if e.dxf.layer == "HFL"]
    assert hfl_lines, "elevation must draw an HFL line"
    assert any("HFL" in t for t in labels)
    # bed slope callout "1 in <bed_slope_run>"
    assert any(f"1 in {geometry.bed_slope_run:g}" in t for t in labels)
    # PROVISIONAL caption on every drawing
    assert any("PROVISIONAL" in t for t in labels)


def test_elevation_formation_width_is_dimensioned(geometry, params, tmp_path):
    doc = save_and_read(elevation.build(geometry, params), tmp_path, "elevation")
    measures = [round(float(d.get_measurement()), 1) for d in doc.modelspace().query("DIMENSION")]
    assert any(abs(m - geometry.formation_width_mm) <= 1.0 for m in measures)
