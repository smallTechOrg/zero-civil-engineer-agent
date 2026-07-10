"""Session-scoped canonical 3D artefacts shared across the model3d test files."""

from pathlib import Path

import pytest

from m3d_test_helpers import CANONICAL, sized


@pytest.fixture(scope="session")
def canonical_geometry():
    return sized(*CANONICAL)


@pytest.fixture(scope="session")
def canonical_paths(canonical_geometry, tmp_path_factory) -> dict[str, Path]:
    from model3d import generate_solid

    return generate_solid(canonical_geometry, tmp_path_factory.mktemp("model3d-canonical"))
