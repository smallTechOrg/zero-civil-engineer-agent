"""GA drawing — ezdxf round-trip, principal dimensions, styled SVG."""

from pathlib import Path

import ezdxf
import pytest

from components.retaining_wall.drawing import InvalidGeometryError, generate_ga
from components.retaining_wall.params import RetainingWallGeometry, RetainingWallParams
from components.retaining_wall.sizing import size_wall

PARAMS = RetainingWallParams(
    retained_height_m=5.0, safe_bearing_capacity_kn_m2=200.0, backfill_friction_angle_deg=30.0
)


@pytest.fixture
def geometry() -> RetainingWallGeometry:
    return size_wall(PARAMS).geometry


def test_ga_dxf_round_trips_cleanly_with_principal_dimensions(geometry, tmp_path: Path):
    paths = generate_ga(PARAMS, geometry, tmp_path, run_id="draw-test")
    assert set(paths) == {"ga_dxf", "ga_svg"}
    assert paths["ga_dxf"].is_file()

    doc = ezdxf.readfile(paths["ga_dxf"])
    assert not doc.audit().has_errors
    measurements = [round(float(d.get_measurement()), 1) for d in doc.modelspace().query("DIMENSION")]
    assert any(abs(m - geometry.total_height_mm) <= 1.0 for m in measurements), "retained height missing"
    assert any(abs(m - geometry.base_width_mm) <= 1.0 for m in measurements), "base width missing"
    # Stem base thickness is drawn (not confused with the top thickness).
    assert any(abs(m - geometry.stem_base_thickness_mm) <= 1.0 for m in measurements)


def test_ga_svg_is_non_empty_and_well_formed(geometry, tmp_path: Path):
    paths = generate_ga(PARAMS, geometry, tmp_path, run_id="draw-test")
    svg = paths["ga_svg"].read_text(encoding="utf-8")
    assert svg.strip().startswith("<")
    assert "<svg" in svg and "</svg>" in svg
    assert len(svg) > 2000  # a real rendered sheet, not a stub


def test_ga_drawing_handles_a_wall_with_a_shear_key(tmp_path: Path):
    # Track surcharge on a weak soil forces a shear key — the key must draw too.
    params = RetainingWallParams(
        retained_height_m=6.0, safe_bearing_capacity_kn_m2=120.0, backfill_friction_angle_deg=28.0
    )
    geometry = size_wall(params).geometry
    assert geometry.key_depth_mm > 0
    paths = generate_ga(params, geometry, tmp_path, run_id="key")
    assert not ezdxf.readfile(paths["ga_dxf"]).audit().has_errors


def test_invalid_geometry_is_rejected(tmp_path: Path):
    bad = RetainingWallGeometry(
        stem_top_thickness_mm=200.0, stem_base_thickness_mm=400.0, base_thickness_mm=6000.0,
        toe_length_mm=900.0, heel_length_mm=1600.0, base_width_mm=2900.0,
        total_height_mm=5000.0, key_depth_mm=0.0,  # base thicker than total height
    )
    with pytest.raises(InvalidGeometryError):
        generate_ga(PARAMS, bad, tmp_path, run_id="bad")
