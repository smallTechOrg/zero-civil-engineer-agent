"""Section of Curtain / Drop Wall: curtain + drop-wall key depths dimensioned."""

from components.m00004_box_culvert.drawings import curtain_wall

from .conftest import save_and_read, texts


def test_curtain_wall_depths_dimensioned(geometry, params, tmp_path):
    doc = save_and_read(curtain_wall.build(geometry, params), tmp_path, "curtain_wall")
    measures = [round(float(d.get_measurement()), 1) for d in doc.modelspace().query("DIMENSION")]
    assert any(abs(m - geometry.curtain_depth_mm) <= 1.0 for m in measures)
    assert any(abs(m - geometry.drop_wall_depth_mm) <= 1.0 for m in measures)


def test_curtain_wall_has_reinforcement_and_caption(geometry, params, tmp_path):
    doc = save_and_read(curtain_wall.build(geometry, params), tmp_path, "curtain_wall")
    assert [e for e in doc.modelspace() if e.dxf.layer == "BARS"]
    assert any("PROVISIONAL" in t for t in texts(doc))
