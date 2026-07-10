"""GA drawing — ezdxf round-trip, principal dimensions, styled SVG."""

from pathlib import Path

import ezdxf
import pytest

from components.slab_tbeam.drawing import InvalidGeometryError, generate_ga
from components.slab_tbeam.params import SlabTbeamGeometry, SlabTbeamParams
from components.slab_tbeam.sizing import size_deck


def _geo(params: SlabTbeamParams) -> SlabTbeamGeometry:
    return size_deck(params).geometry


def test_solid_slab_ga_round_trips_with_span_and_depth_dimensions(tmp_path: Path):
    params = SlabTbeamParams(span_m=6.0, deck_type="solid_slab")
    g = _geo(params)
    paths = generate_ga(params, g, tmp_path, run_id="draw-test")
    assert set(paths) == {"ga_dxf", "ga_svg"}
    assert paths["ga_dxf"].is_file()

    doc = ezdxf.readfile(paths["ga_dxf"])
    assert not doc.audit().has_errors
    measurements = [round(float(d.get_measurement()), 1) for d in doc.modelspace().query("DIMENSION")]
    assert any(abs(m - g.span_mm) <= 1.0 for m in measurements), "span dimension missing"
    assert any(abs(m - g.overall_depth_mm) <= 1.0 for m in measurements), "overall depth missing"


def test_t_beam_ga_round_trips_cleanly_and_dimensions_the_ribs(tmp_path: Path):
    params = SlabTbeamParams(span_m=12.0, deck_type="t_beam", number_of_girders=3)
    g = _geo(params)
    paths = generate_ga(params, g, tmp_path, run_id="tbeam")
    doc = ezdxf.readfile(paths["ga_dxf"])
    assert not doc.audit().has_errors
    measurements = [round(float(d.get_measurement()), 1) for d in doc.modelspace().query("DIMENSION")]
    assert any(abs(m - g.span_mm) <= 1.0 for m in measurements)
    assert any(abs(m - g.overall_depth_mm) <= 1.0 for m in measurements)
    assert any(abs(m - g.rib_width_mm) <= 1.0 for m in measurements)


def test_ga_svg_is_non_empty_and_well_formed(tmp_path: Path):
    params = SlabTbeamParams(span_m=8.0, deck_type="solid_slab")
    g = _geo(params)
    paths = generate_ga(params, g, tmp_path, run_id="svg")
    svg = paths["ga_svg"].read_text(encoding="utf-8")
    assert svg.strip().startswith("<")
    assert "<svg" in svg and "</svg>" in svg
    assert len(svg) > 2000  # a real rendered sheet, not a stub


def test_invalid_geometry_is_rejected(tmp_path: Path):
    bad = SlabTbeamGeometry(
        span_mm=6000.0, deck_type="solid_slab", overall_depth_mm=7000.0,  # deeper than span
        slab_depth_mm=7000.0, flange_width_mm=5000.0, number_of_girders=1,
        girder_spacing_mm=5000.0, deck_width_mm=5000.0,
    )
    params = SlabTbeamParams(span_m=6.0, deck_type="solid_slab")
    with pytest.raises(InvalidGeometryError):
        generate_ga(params, bad, tmp_path, run_id="bad")
