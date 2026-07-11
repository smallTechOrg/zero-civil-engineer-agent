"""Detail drawing — ezdxf round-trip, principal dimensions, GD&T + weld symbols, SVG."""

from pathlib import Path

import ezdxf
import pytest

from components.machine_element.drawing import (
    LAYER_GDT,
    LAYER_WELD,
    InvalidGeometryError,
    generate_ga,
)
from components.machine_element.params import MachineElementGeometry, MachineElementParams
from components.machine_element.sizing import size_element

SHAFT = MachineElementParams(power_kw=20.0, speed_rpm=1000.0)
WELD = MachineElementParams(
    power_kw=100.0, speed_rpm=100.0, element_kind="welded_joint", hub_diameter_mm=120.0
)


def _by_layer(msp, layer):
    return list(msp.query(f'*[layer=="{layer}"]'))


def test_shaft_ga_round_trips_with_principal_dimensions_and_gdt(tmp_path: Path):
    g = size_element(SHAFT).geometry
    paths = generate_ga(SHAFT, g, tmp_path, run_id="draw-test")
    assert set(paths) == {"ga_dxf", "ga_svg"}
    assert paths["ga_dxf"].is_file()

    doc = ezdxf.readfile(paths["ga_dxf"])
    assert not doc.audit().has_errors
    msp = doc.modelspace()
    measurements = [round(float(d.get_measurement()), 1) for d in msp.query("DIMENSION")]
    assert any(abs(m - g.diameter_mm) <= 1.0 for m in measurements), "major diameter missing"
    assert any(abs(m - g.length_mm) <= 1.0 for m in measurements), "overall length missing"

    # GD&T annotation entities exist: a diameter/tolerance callout, a surface-finish
    # symbol, a datum feature symbol (filled triangle).
    gdt = _by_layer(msp, LAYER_GDT)
    assert gdt, "no GD&T annotation entities on the GDT layer"
    gdt_types = {e.dxftype() for e in gdt}
    assert "SOLID" in gdt_types, "no filled datum/leader triangle in GD&T"
    assert "LWPOLYLINE" in gdt_types, "no surface-finish / datum-box polyline in GD&T"
    texts = [e.dxf.text for e in msp.query("TEXT") if e.dxf.layer == LAYER_GDT]
    assert any("h7" in t for t in texts), "no diameter/tolerance callout text (⌀d h7)"

    # A plain shaft carries NO weld symbol.
    assert not _by_layer(msp, LAYER_WELD)


def test_shaft_svg_is_non_empty_and_well_formed(tmp_path: Path):
    g = size_element(SHAFT).geometry
    paths = generate_ga(SHAFT, g, tmp_path, run_id="draw-test")
    svg = paths["ga_svg"].read_text(encoding="utf-8")
    assert svg.strip().startswith("<")
    assert "<svg" in svg and "</svg>" in svg
    assert len(svg) > 2000  # a real rendered sheet, not a stub


def test_welded_joint_ga_has_weld_symbol_and_gdt(tmp_path: Path):
    g = size_element(WELD).geometry
    paths = generate_ga(WELD, g, tmp_path, run_id="weld")
    doc = ezdxf.readfile(paths["ga_dxf"])
    assert not doc.audit().has_errors
    msp = doc.modelspace()

    measurements = [round(float(d.get_measurement()), 1) for d in msp.query("DIMENSION")]
    assert any(abs(m - g.hub_diameter_mm) <= 1.0 for m in measurements), "hub diameter missing"
    assert any(abs(m - g.length_mm) <= 1.0 for m in measurements), "plate size missing"

    # Weld symbol: arrow leader + arrowhead + reference line + fillet triangle + size text.
    weld = _by_layer(msp, LAYER_WELD)
    assert weld, "no weld-symbol entities on the WELD layer"
    weld_types = [e.dxftype() for e in weld]
    assert weld_types.count("LINE") >= 2, "weld arrow leader + reference line missing"
    assert "SOLID" in weld_types, "weld arrowhead (filled triangle) missing"
    assert "LWPOLYLINE" in weld_types, "fillet-weld triangle symbol missing"
    weld_texts = [e.dxf.text for e in msp.query("TEXT") if e.dxf.layer == LAYER_WELD]
    assert any(t.strip() == f"{g.weld_size_mm:g}" for t in weld_texts), "weld leg-size text missing"

    # GD&T diameter callout on the hub.
    assert _by_layer(msp, LAYER_GDT)


def test_invalid_shaft_geometry_is_rejected(tmp_path: Path):
    bad = MachineElementGeometry(
        element_kind="shaft", diameter_mm=30.0, length_mm=40.0,
        step_diameter_mm=40.0,  # journal not smaller than the major diameter
        step_length_mm=10.0, fillet_radius_mm=3.0, keyway_width_mm=8.0, keyway_depth_mm=4.0,
        hub_diameter_mm=0.0, weld_size_mm=0.0, weld_throat_mm=0.0, plate_thickness_mm=0.0,
    )
    with pytest.raises(InvalidGeometryError):
        generate_ga(SHAFT, bad, tmp_path, run_id="bad")
