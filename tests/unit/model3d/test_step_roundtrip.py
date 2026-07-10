"""The exported STEP re-imports in the same kernel to the same solid.

build123d's STEP reader works in an OCCT millimetre session, so the
re-imported solid comes back scaled x1000 per axis relative to the
metre-unit model space; the assertions convert back to metres.
"""

import pytest

from m3d_test_helpers import analytic_concrete_volume_m3

MM_PER_M = 1000.0
VOLUME_REL_TOL = 1e-3  # 0.1%
BBOX_TOL_M = 0.001  # 1 mm


@pytest.fixture(scope="module")
def reimported_solid(canonical_paths):
    from build123d import import_step

    return import_step(canonical_paths["model_step"])


def test_step_reimports_with_matching_volume(reimported_solid, canonical_geometry):
    volume_m3 = reimported_solid.volume / MM_PER_M**3

    assert volume_m3 == pytest.approx(
        analytic_concrete_volume_m3(canonical_geometry), rel=VOLUME_REL_TOL
    )


def test_step_reimports_with_matching_external_dimensions(reimported_solid, canonical_geometry):
    size = reimported_solid.bounding_box().size

    assert size.X / MM_PER_M == pytest.approx(canonical_geometry.external_width_m, abs=BBOX_TOL_M)
    assert size.Y / MM_PER_M == pytest.approx(canonical_geometry.barrel_length_m, abs=BBOX_TOL_M)
    assert size.Z / MM_PER_M == pytest.approx(canonical_geometry.external_height_m, abs=BBOX_TOL_M)
