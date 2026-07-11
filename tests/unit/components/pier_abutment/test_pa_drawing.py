"""GA drawing — ezdxf round-trip, principal dimensions, styled SVG."""

from pathlib import Path

import ezdxf
import pytest

from components.pier_abutment.drawing import InvalidGeometryError, generate_ga
from components.pier_abutment.params import PierAbutmentGeometry, PierAbutmentParams
from components.pier_abutment.sizing import size_substructure

PARAMS = PierAbutmentParams(
    pier_height_m=9.0, superstructure_reaction_kn=5000.0,
    safe_bearing_capacity_kn_m2=300.0, component_kind="abutment",
)


@pytest.fixture
def geometry() -> PierAbutmentGeometry:
    return size_substructure(PARAMS).geometry


def test_ga_dxf_round_trips_cleanly_with_principal_dimensions(geometry, tmp_path: Path):
    paths = generate_ga(PARAMS, geometry, tmp_path, run_id="draw-test")
    assert set(paths) == {"ga_dxf", "ga_svg"}
    assert paths["ga_dxf"].is_file()

    doc = ezdxf.readfile(paths["ga_dxf"])
    assert not doc.audit().has_errors
    measurements = [round(float(d.get_measurement()), 1) for d in doc.modelspace().query("DIMENSION")]
    # The proof-check reads these back: total height + footing width within +/-1 mm.
    assert any(abs(m - geometry.total_height_mm) <= 1.0 for m in measurements), "total height missing"
    assert any(abs(m - geometry.footing_width_mm) <= 1.0 for m in measurements), "footing width missing"
    assert any(abs(m - geometry.footing_length_mm) <= 1.0 for m in measurements), "footing length missing"


def test_ga_svg_is_non_empty_and_well_formed(geometry, tmp_path: Path):
    paths = generate_ga(PARAMS, geometry, tmp_path, run_id="draw-test")
    svg = paths["ga_svg"].read_text(encoding="utf-8")
    assert svg.strip().startswith("<")
    assert "<svg" in svg and "</svg>" in svg
    assert len(svg) > 2000  # a real rendered sheet, not a stub


def test_ga_drawing_handles_a_pier(tmp_path: Path):
    params = PierAbutmentParams(
        pier_height_m=6.0, superstructure_reaction_kn=3000.0,
        safe_bearing_capacity_kn_m2=350.0, component_kind="pier",
    )
    geometry = size_substructure(params).geometry
    paths = generate_ga(params, geometry, tmp_path, run_id="pier")
    assert not ezdxf.readfile(paths["ga_dxf"]).audit().has_errors


def test_invalid_geometry_is_rejected(tmp_path: Path):
    bad = PierAbutmentGeometry(
        total_height_mm=8000.0, component_kind="pier",
        pier_width_mm=1500.0, pier_length_mm=1500.0,
        cap_thickness_mm=5000.0, cap_width_mm=2000.0, cap_length_mm=2000.0,
        footing_length_mm=6000.0, footing_width_mm=6000.0,
        footing_thickness_mm=5000.0,  # footing + cap leave no positive shaft
    )
    with pytest.raises(InvalidGeometryError):
        generate_ga(PARAMS, bad, tmp_path, run_id="bad")
