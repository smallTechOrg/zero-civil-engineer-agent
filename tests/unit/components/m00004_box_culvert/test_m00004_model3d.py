"""3D solid: model.glb + model.step non-empty; volume matches the closed form."""

from components.m00004_box_culvert.model3d import (
    analytic_concrete_volume_m3,
    build_solid,
    model3d,
)
from components.m00004_box_culvert.params import M00004Params
from components.m00004_box_culvert.sizing import size


def _geometry():
    return size(M00004Params(clear_span_m=4.0, clear_height_m=4.0, cushion_m=2.0)).geometry


def test_solid_volume_matches_closed_form():
    geometry = _geometry()
    solid = build_solid(geometry)
    expected = analytic_concrete_volume_m3(geometry)
    assert expected > 0
    assert abs(solid.volume - expected) <= 1e-3 * expected  # self-check tolerance


def test_exports_non_empty_glb_and_step(tmp_path):
    paths = model3d(_geometry(), tmp_path)
    assert set(paths) == {"model_glb", "model_step"}
    glb = paths["model_glb"].read_bytes()
    step = paths["model_step"].read_bytes()
    assert glb[:4] == b"glTF"              # binary glTF magic
    assert len(glb) > 0 and len(step) > 0
    assert b"ISO-10303" in step[:400]      # STEP header


def test_solid_bounding_box_spans_the_full_structure():
    geometry = _geometry()
    solid = build_solid(geometry)
    size_bb = solid.bounding_box().size
    # Y spans barrel + wing/apron + curtain beyond both ends
    full_len = (
        geometry.barrel_length_mm
        + 2.0 * (geometry.apron_len_mm + geometry.curtain_thickness_mm)
    ) / 1000.0
    assert size_bb.Y >= full_len - 1e-3
