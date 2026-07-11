"""Fabrication drawing — ezdxf round-trip, principal dimensions, weld symbol, styled SVG."""

from pathlib import Path

import ezdxf
import pytest

from components.structural_steel_member.drawing import (
    LAYER_WELD,
    InvalidGeometryError,
    generate_ga,
)
from components.structural_steel_member.params import SteelMemberGeometry, SteelMemberParams
from components.structural_steel_member.sizing import size_member

PARAMS = SteelMemberParams(cantilever_length_m=6.0, transverse_load_kn=20.0)


@pytest.fixture
def geometry() -> SteelMemberGeometry:
    return size_member(PARAMS).geometry


def test_ga_dxf_round_trips_cleanly_with_principal_dimensions(geometry, tmp_path: Path):
    paths = generate_ga(PARAMS, geometry, tmp_path, run_id="draw-test")
    assert set(paths) == {"ga_dxf", "ga_svg"}
    assert paths["ga_dxf"].is_file()

    doc = ezdxf.readfile(paths["ga_dxf"])
    assert not doc.audit().has_errors
    measurements = [round(float(d.get_measurement()), 1) for d in doc.modelspace().query("DIMENSION")]
    assert any(abs(m - geometry.cantilever_length_mm) <= 1.0 for m in measurements), "length missing"
    assert any(abs(m - geometry.overall_depth_mm) <= 1.0 for m in measurements), "overall depth missing"
    assert any(abs(m - geometry.flange_width_mm) <= 1.0 for m in measurements), "flange width missing"
    assert any(abs(m - geometry.web_depth_mm) <= 1.0 for m in measurements), "web depth missing"


def test_weld_symbol_is_drawn_on_the_weld_layer(geometry, tmp_path: Path):
    """The mandatory fillet-weld symbol: an arrow/reference line, a fillet-weld
    triangle (a 3-vertex closed polyline) and the weld-size text, all on WELD."""
    paths = generate_ga(PARAMS, geometry, tmp_path, run_id="weld-test")
    doc = ezdxf.readfile(paths["ga_dxf"])
    msp = doc.modelspace()

    weld_lines = [e for e in msp.query("LINE") if e.dxf.layer == LAYER_WELD]
    assert len(weld_lines) >= 2, "expected the leader/arrow line and the reference line on WELD"

    weld_triangles = [
        e for e in msp.query("LWPOLYLINE")
        if e.dxf.layer == LAYER_WELD and len(list(e.get_points())) == 3 and e.closed
    ]
    assert weld_triangles, "expected a fillet-weld triangle (3-vertex closed polyline) on WELD"

    weld_texts = [e.dxf.text for e in msp.query("TEXT") if e.dxf.layer == LAYER_WELD]
    assert any(t == f"{geometry.weld_size_mm:g}" for t in weld_texts), (
        f"expected the weld-size text {geometry.weld_size_mm:g} on WELD; got {weld_texts}"
    )
    # A weld-all-round circle marks the fillet as continuous around the profile.
    assert [e for e in msp.query("CIRCLE") if e.dxf.layer == LAYER_WELD]


def test_ga_svg_is_non_empty_and_well_formed(geometry, tmp_path: Path):
    paths = generate_ga(PARAMS, geometry, tmp_path, run_id="draw-test")
    svg = paths["ga_svg"].read_text(encoding="utf-8")
    assert svg.strip().startswith("<")
    assert "<svg" in svg and "</svg>" in svg
    assert len(svg) > 2000  # a real rendered sheet, not a stub
    # the weld-size text is machine-searchable in the SVG text layer
    assert f">{geometry.weld_size_mm:g}<" in svg


def test_ga_drawing_handles_a_bracket_member(tmp_path: Path):
    params = SteelMemberParams(cantilever_length_m=1.2, transverse_load_kn=40.0, member_type="bracket")
    geometry = size_member(params).geometry
    paths = generate_ga(params, geometry, tmp_path, run_id="bracket")
    assert not ezdxf.readfile(paths["ga_dxf"]).audit().has_errors


def test_invalid_geometry_is_rejected(tmp_path: Path):
    bad = SteelMemberGeometry(
        member_type="gantry_post", cantilever_length_mm=500.0, web_depth_mm=2000.0,
        web_thickness_mm=12.0, flange_width_mm=300.0, flange_thickness_mm=20.0,
        overall_depth_mm=2040.0, weld_size_mm=8.0,
    )  # overall depth not less than the length
    with pytest.raises(InvalidGeometryError):
        generate_ga(PARAMS, bad, tmp_path, run_id="bad")
