"""Typical Details at A & B: weep holes + reinforcement placement labels present."""

from components.m00004_box_culvert.drawings import typical_details

from .conftest import save_and_read, texts


def test_typical_details_weep_and_reinforcement(geometry, params, tmp_path):
    doc = save_and_read(typical_details.build(geometry, params), tmp_path, "typical_details")
    weeps = [e for e in doc.modelspace().query("CIRCLE") if e.dxf.layer == "WEEP"]
    assert weeps, "typical details must show PVC weep holes"
    labels = texts(doc)
    assert any("WEEP" in t for t in labels)
    assert any("MAIN" in t and "HAUNCH" in t for t in labels)
    assert any("EARTH RETAINER" in t for t in labels)
    assert any("PROVISIONAL" in t for t in labels)


def test_typical_details_has_two_labelled_details(geometry, params, tmp_path):
    doc = save_and_read(typical_details.build(geometry, params), tmp_path, "typical_details")
    labels = texts(doc)
    assert any("DETAIL AT A" in t for t in labels)
    assert any("DETAIL AT B" in t for t in labels)
