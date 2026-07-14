"""Return Wall: tapering profile (base width -> top width) both dimensioned."""

from components.m00004_box_culvert.drawings import return_wall

from .conftest import save_and_read, texts


def test_return_wall_shows_the_taper(geometry, params, tmp_path):
    doc = save_and_read(return_wall.build(geometry, params), tmp_path, "return_wall")
    measures = [round(float(d.get_measurement()), 1) for d in doc.modelspace().query("DIMENSION")]
    # taper => base width and top width are distinct and BOTH dimensioned
    assert geometry.return_wall_base_width_mm != geometry.return_wall_top_width_mm
    assert any(abs(m - geometry.return_wall_base_width_mm) <= 1.0 for m in measures)
    assert any(abs(m - geometry.return_wall_top_width_mm) <= 1.0 for m in measures)


def test_return_wall_profile_is_trapezoidal(geometry, params, tmp_path):
    doc = save_and_read(return_wall.build(geometry, params), tmp_path, "return_wall")
    outlines = [e for e in doc.modelspace().query("LWPOLYLINE") if e.dxf.layer == "OUTLINE"]
    assert outlines, "return wall must draw its tapering profile"
    xs = {round(x, 1) for e in outlines for x, *_ in e.get_points()}
    # a genuine taper spans at least the base width and the (smaller) top width
    assert max(xs) >= geometry.return_wall_base_width_mm - 1.0


def test_return_wall_is_provisional(geometry, params, tmp_path):
    doc = save_and_read(return_wall.build(geometry, params), tmp_path, "return_wall")
    assert any("PROVISIONAL" in t for t in texts(doc))
