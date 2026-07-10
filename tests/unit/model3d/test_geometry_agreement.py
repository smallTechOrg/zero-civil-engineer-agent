"""The core gate: the solid agrees with the closed-form geometry.

Volume must equal (external_width x external_height - [clear_span x
clear_height - 4 x haunch^2 / 2]) x barrel_length within 0.1%, and the
bounding box must equal the external dimensions within 1 mm.

Axis mapping (documented in src/model3d/solid.py): model units are metres;
X = external width, Y = barrel length, Z = external height.
"""

import pytest

from m3d_test_helpers import CANONICAL, analytic_concrete_volume_m3, glb_json_chunk, glb_mesh_extents_m, sized

VOLUME_REL_TOL = 1e-3  # 0.1%
BBOX_TOL_M = 0.001  # 1 mm

CASES = [
    pytest.param(*CANONICAL, {}, id="canonical_4x3"),
    pytest.param(1.0, 6.0, 2.5, {}, id="extreme_tall_narrow_1x6"),
    pytest.param(8.0, 1.0, 2.5, {}, id="extreme_wide_flat_8x1"),
    pytest.param(*CANONICAL, {"haunch_mm": 0.0}, id="zero_haunch"),
    pytest.param(*CANONICAL, {"haunch_mm": 300.0}, id="max_haunch_300"),
]


@pytest.mark.parametrize(("span", "height", "cushion", "overrides"), CASES)
def test_solid_volume_matches_analytic_concrete_volume(span, height, cushion, overrides):
    from model3d import build_culvert_solid

    geometry = sized(span, height, cushion, **overrides)

    solid = build_culvert_solid(geometry)

    assert solid.volume == pytest.approx(
        analytic_concrete_volume_m3(geometry), rel=VOLUME_REL_TOL
    )


@pytest.mark.parametrize(("span", "height", "cushion", "overrides"), CASES)
def test_bounding_box_matches_external_dimensions(span, height, cushion, overrides):
    from model3d import build_culvert_solid

    geometry = sized(span, height, cushion, **overrides)

    size = build_culvert_solid(geometry).bounding_box().size

    assert size.X == pytest.approx(geometry.external_width_m, abs=BBOX_TOL_M)
    assert size.Y == pytest.approx(geometry.barrel_length_m, abs=BBOX_TOL_M)
    assert size.Z == pytest.approx(geometry.external_height_m, abs=BBOX_TOL_M)


def test_glb_mesh_extents_match_external_dimensions(canonical_paths, canonical_geometry):
    doc = glb_json_chunk(canonical_paths["model_glb"].read_bytes())

    width_m, length_m, height_m = glb_mesh_extents_m(doc)

    assert width_m == pytest.approx(canonical_geometry.external_width_m, abs=BBOX_TOL_M)
    assert length_m == pytest.approx(canonical_geometry.barrel_length_m, abs=BBOX_TOL_M)
    assert height_m == pytest.approx(canonical_geometry.external_height_m, abs=BBOX_TOL_M)
