"""Plan: PVC weep holes at weep_hole_spacing_mm c/c along the barrel side walls."""

from components.m00004_box_culvert.drawings import plan

from .conftest import save_and_read, texts


def test_plan_weep_holes_at_1000_cc(geometry, params, tmp_path):
    doc = save_and_read(plan.build(geometry, params), tmp_path, "plan")
    weeps = [e for e in doc.modelspace().query("CIRCLE") if e.dxf.layer == "WEEP"]
    assert len(weeps) >= 2, "plan must draw PVC weep holes"
    # weep-hole diameter matches geometry
    assert all(abs(2.0 * e.dxf.radius - geometry.weep_hole_dia_mm) <= 1e-6 for e in weeps)
    # consecutive weep holes on one side wall are spaced weep_hole_spacing_mm c/c
    xs = sorted({round(e.dxf.center.x, 3) for e in weeps})
    gaps = {round(b - a, 3) for a, b in zip(xs, xs[1:])}
    assert geometry.weep_hole_spacing_mm in gaps


def test_plan_labels_weep_spacing_and_is_provisional(geometry, params, tmp_path):
    doc = save_and_read(plan.build(geometry, params), tmp_path, "plan")
    labels = texts(doc)
    assert any(f"@ {geometry.weep_hole_spacing_mm:g} c/c" in t for t in labels)
    assert any("PROVISIONAL" in t for t in labels)


def test_plan_barrel_length_is_dimensioned(geometry, params, tmp_path):
    doc = save_and_read(plan.build(geometry, params), tmp_path, "plan")
    measures = [round(float(d.get_measurement()), 1) for d in doc.modelspace().query("DIMENSION")]
    assert any(abs(m - geometry.barrel_length_mm) <= 1.0 for m in measures)
