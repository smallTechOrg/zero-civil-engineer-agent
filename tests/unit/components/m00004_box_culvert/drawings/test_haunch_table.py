"""B x B Haunch table: haunch leg vs box size for the selected config."""

from components.m00004_box_culvert.drawings import haunch_table

from .conftest import save_and_read, texts


def test_haunch_table_lists_haunch_and_box_size(geometry, params, tmp_path):
    doc = save_and_read(haunch_table.build(geometry, params), tmp_path, "haunch_table")
    blob = "\n".join(texts(doc))
    assert geometry.config_id in blob
    assert f"{geometry.haunch_mm:g} x {geometry.haunch_mm:g}" in blob  # B x B haunch
    assert f"{geometry.clear_span_mm:g} x {geometry.clear_height_mm:g}" in blob


def test_haunch_table_is_provisional(geometry, params, tmp_path):
    doc = save_and_read(haunch_table.build(geometry, params), tmp_path, "haunch_table")
    assert any("PROVISIONAL" in t for t in texts(doc))
