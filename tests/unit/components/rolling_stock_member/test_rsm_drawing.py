"""Fabrication drawing — ezdxf round-trip, weld symbol on WELD layer, styled SVG."""

from pathlib import Path

import ezdxf
import pytest

from components.rolling_stock_member.drawing import (
    LAYER_WELD,
    InvalidGeometryError,
    generate_ga,
)
from components.rolling_stock_member.params import (
    RollingStockMemberGeometry,
    RollingStockMemberParams,
)
from components.rolling_stock_member.sizing import size_member

PARAMS = RollingStockMemberParams(member_length_m=6.0)


@pytest.fixture
def geometry() -> RollingStockMemberGeometry:
    return size_member(PARAMS).geometry


def test_ga_dxf_round_trips_cleanly_with_principal_dimensions(geometry, tmp_path: Path):
    paths = generate_ga(PARAMS, geometry, tmp_path, run_id="draw-test")
    assert set(paths) == {"ga_dxf", "ga_svg"}
    assert paths["ga_dxf"].is_file()

    doc = ezdxf.readfile(paths["ga_dxf"])
    assert not doc.audit().has_errors
    measurements = [round(float(d.get_measurement()), 1) for d in doc.modelspace().query("DIMENSION")]
    assert any(abs(m - geometry.member_length_mm) <= 1.0 for m in measurements), "member length missing"
    assert any(abs(m - geometry.overall_depth_mm) <= 1.0 for m in measurements), "overall depth missing"
    assert any(abs(m - geometry.flange_width_mm) <= 1.0 for m in measurements), "flange width missing"
    assert any(abs(m - geometry.web_depth_mm) <= 1.0 for m in measurements), "web depth missing"


def test_ga_carries_a_weld_symbol_on_the_weld_layer(geometry, tmp_path: Path):
    paths = generate_ga(PARAMS, geometry, tmp_path, run_id="weld-test")
    doc = ezdxf.readfile(paths["ga_dxf"])
    assert LAYER_WELD in doc.layers
    weld_entities = [e for e in doc.modelspace() if e.dxf.layer == LAYER_WELD]
    kinds = {e.dxftype() for e in weld_entities}
    # The fillet-weld triangle (LWPOLYLINE), the leader/reference/arrow lines,
    # and the leg-size text must all be present on the WELD layer.
    assert "LWPOLYLINE" in kinds, "fillet-weld triangle missing on WELD layer"
    assert "LINE" in kinds, "leader/reference line missing on WELD layer"
    assert "TEXT" in kinds, "weld size/annotation text missing on WELD layer"
    # The leg-size text shows the designed weld size.
    weld_texts = [e.dxf.text for e in weld_entities if e.dxftype() == "TEXT"]
    assert any(f"{geometry.weld_size_mm:g}" == t for t in weld_texts), weld_texts


def test_ga_svg_is_non_empty_and_well_formed(geometry, tmp_path: Path):
    paths = generate_ga(PARAMS, geometry, tmp_path, run_id="draw-test")
    svg = paths["ga_svg"].read_text(encoding="utf-8")
    assert svg.strip().startswith("<")
    assert "<svg" in svg and "</svg>" in svg
    assert len(svg) > 2000  # a real rendered sheet, not a stub


def test_ga_drawing_handles_a_headstock(tmp_path: Path):
    params = RollingStockMemberParams(member_length_m=2.4, member_kind="headstock")
    geometry = size_member(params).geometry
    paths = generate_ga(params, geometry, tmp_path, run_id="headstock")
    assert not ezdxf.readfile(paths["ga_dxf"]).audit().has_errors


def test_invalid_geometry_is_rejected(tmp_path: Path):
    bad = RollingStockMemberGeometry(
        member_length_mm=200.0, member_kind="sole_bar", web_depth_mm=300.0,
        web_thickness_mm=10.0, flange_width_mm=150.0, flange_thickness_mm=12.0,
        overall_depth_mm=324.0, weld_size_mm=8.0,
    )  # overall depth not less than the member length
    with pytest.raises(InvalidGeometryError):
        generate_ga(PARAMS, bad, tmp_path, run_id="bad")
