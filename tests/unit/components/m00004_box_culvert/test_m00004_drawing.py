"""GA drawing: ga.dxf reopens with ezdxf and the read-back dimensions match;
ga.svg + m00004_sheet.pdf are produced."""

import ezdxf

from components.m00004_box_culvert.drawing import draw
from components.m00004_box_culvert.params import M00004Params
from components.m00004_box_culvert.sizing import size


def _run(tmp_path):
    params = M00004Params(clear_span_m=4.0, clear_height_m=4.0, cushion_m=2.0)
    geometry = size(params).geometry
    return params, geometry, draw(params, geometry, tmp_path, run_id="t-0001")


def test_draw_returns_the_three_keys(tmp_path):
    _, _, paths = _run(tmp_path)
    assert set(paths) == {"ga_dxf", "ga_svg", "m00004_sheet"}
    for p in paths.values():
        assert p.exists() and p.stat().st_size > 0


def test_ga_dxf_reopens_and_dimensions_read_back(tmp_path):
    _, geometry, paths = _run(tmp_path)
    doc = ezdxf.readfile(paths["ga_dxf"])
    measurements = [
        round(float(d.get_measurement()), 1) for d in doc.modelspace().query("DIMENSION")
    ]
    assert measurements
    # clear span + clear height read back within 1 mm
    assert any(abs(m - geometry.clear_span_mm) <= 1.0 for m in measurements)
    assert any(abs(m - geometry.clear_height_mm) <= 1.0 for m in measurements)
    assert any(abs(m - geometry.barrel_length_mm) <= 1.0 for m in measurements)


def test_ga_svg_is_non_empty_svg(tmp_path):
    _, _, paths = _run(tmp_path)
    svg = paths["ga_svg"].read_text(encoding="utf-8")
    assert svg.strip().startswith("<") and "svg" in svg
    assert "PROVISIONAL" in svg  # NOT-FOR-CONSTRUCTION caveat is searchable in the SVG text layer
