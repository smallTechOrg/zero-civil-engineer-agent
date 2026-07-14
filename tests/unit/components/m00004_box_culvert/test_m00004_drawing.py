"""GA aggregator: ga.dxf reopens with ezdxf and the read-back dimensions match;
ga.svg + m00004_sheet.pdf are produced; and the ten per-diagram DXF+SVG pairs are
emitted alongside (byte-behaviour of the Phase-1 GA preserved)."""

import ezdxf

from components.m00004_box_culvert.drawing import _draw_diagrams, draw
from components.m00004_box_culvert.params import M00004Params
from components.m00004_box_culvert.sizing import size

_DIAGRAM_KINDS = (
    "elevation", "cross_section", "plan", "curtain_wall", "typical_details",
    "return_wall", "bar_shape_table", "notations", "notes", "haunch_table",
)
_DIAGRAM_KEYS = {f"{kind}_{ext}" for kind in _DIAGRAM_KINDS for ext in ("dxf", "svg")}
_PHASE1_KEYS = {"ga_dxf", "ga_svg", "m00004_sheet"}


def _run(tmp_path):
    params = M00004Params(clear_span_m=4.0, clear_height_m=4.0, cushion_m=2.0)
    geometry = size(params).geometry
    return params, geometry, draw(params, geometry, tmp_path, run_id="t-0001")


def test_draw_returns_phase1_keys_plus_ten_diagram_pairs(tmp_path):
    _, _, paths = _run(tmp_path)
    assert set(paths) == _PHASE1_KEYS | _DIAGRAM_KEYS
    for p in paths.values():
        assert p.exists() and p.stat().st_size > 0


def test_ga_dxf_reopens_and_dimensions_read_back(tmp_path):
    _, geometry, paths = _run(tmp_path)
    doc = ezdxf.readfile(paths["ga_dxf"])
    measurements = [
        round(float(d.get_measurement()), 1) for d in doc.modelspace().query("DIMENSION")
    ]
    assert measurements
    # clear span + clear height + barrel length read back within 1 mm
    assert any(abs(m - geometry.clear_span_mm) <= 1.0 for m in measurements)
    assert any(abs(m - geometry.clear_height_mm) <= 1.0 for m in measurements)
    assert any(abs(m - geometry.barrel_length_mm) <= 1.0 for m in measurements)


def test_ga_svg_is_non_empty_svg(tmp_path):
    _, _, paths = _run(tmp_path)
    svg = paths["ga_svg"].read_text(encoding="utf-8")
    assert svg.strip().startswith("<") and "svg" in svg
    assert "PROVISIONAL" in svg  # NOT-FOR-CONSTRUCTION caveat is searchable in the SVG text layer


def test_draw_diagrams_emits_all_ten_pairs_with_provisional_svg(tmp_path):
    """The aggregator's per-diagram portion: ten DXF+SVG pairs, each openable and
    each SVG carrying the PROVISIONAL caption (independent of the PDF-sheet path)."""
    params = M00004Params(clear_span_m=4.0, clear_height_m=4.0, cushion_m=2.0)
    geometry = size(params).geometry
    pairs = _draw_diagrams(params, geometry, tmp_path)
    assert set(pairs) == _DIAGRAM_KEYS
    for kind in _DIAGRAM_KINDS:
        dxf = pairs[f"{kind}_dxf"]
        svg = pairs[f"{kind}_svg"]
        assert dxf.name == f"{kind}.dxf" and svg.name == f"{kind}.svg"
        ezdxf.readfile(dxf)  # reopens without error
        assert "PROVISIONAL" in svg.read_text(encoding="utf-8")
