"""GA drawing — ezdxf round-trip, principal dimensions, styled SVG."""

from pathlib import Path

import ezdxf
import pytest

from components.plate_girder.drawing import InvalidGeometryError, generate_ga
from components.plate_girder.params import PlateGirderGeometry, PlateGirderParams
from components.plate_girder.sizing import size_girder

PARAMS = PlateGirderParams(span_m=24.0)


@pytest.fixture
def geometry() -> PlateGirderGeometry:
    return size_girder(PARAMS).geometry


def test_ga_dxf_round_trips_cleanly_with_principal_dimensions(geometry, tmp_path: Path):
    paths = generate_ga(PARAMS, geometry, tmp_path, run_id="draw-test")
    assert set(paths) == {"ga_dxf", "ga_svg"}
    assert paths["ga_dxf"].is_file()

    doc = ezdxf.readfile(paths["ga_dxf"])
    assert not doc.audit().has_errors
    measurements = [round(float(d.get_measurement()), 1) for d in doc.modelspace().query("DIMENSION")]
    assert any(abs(m - geometry.span_mm) <= 1.0 for m in measurements), "span missing"
    assert any(abs(m - geometry.overall_depth_mm) <= 1.0 for m in measurements), "overall depth missing"
    assert any(abs(m - geometry.flange_width_mm) <= 1.0 for m in measurements), "flange width missing"
    assert any(abs(m - geometry.web_depth_mm) <= 1.0 for m in measurements), "web depth missing"


def test_ga_svg_is_non_empty_and_well_formed(geometry, tmp_path: Path):
    paths = generate_ga(PARAMS, geometry, tmp_path, run_id="draw-test")
    svg = paths["ga_svg"].read_text(encoding="utf-8")
    assert svg.strip().startswith("<")
    assert "<svg" in svg and "</svg>" in svg
    assert len(svg) > 2000  # a real rendered sheet, not a stub


def test_ga_drawing_handles_a_through_type_girder(tmp_path: Path):
    params = PlateGirderParams(span_m=30.0, deck_type="through", number_of_girders=2)
    geometry = size_girder(params).geometry
    paths = generate_ga(params, geometry, tmp_path, run_id="through")
    assert not ezdxf.readfile(paths["ga_dxf"]).audit().has_errors


def test_invalid_geometry_is_rejected(tmp_path: Path):
    bad = PlateGirderGeometry(
        span_mm=1000.0, web_depth_mm=2000.0, web_thickness_mm=12.0,
        flange_width_mm=500.0, flange_thickness_mm=40.0, overall_depth_mm=2080.0,
        number_of_girders=2, girder_spacing_mm=1800.0, stiffener_spacing_mm=2000.0,
    )  # overall depth not less than the span
    with pytest.raises(InvalidGeometryError):
        generate_ga(PARAMS, bad, tmp_path, run_id="bad")
