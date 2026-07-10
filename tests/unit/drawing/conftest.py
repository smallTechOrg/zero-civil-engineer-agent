"""Session-scoped canonical GA artefacts shared across the drawing test files."""

from pathlib import Path

import ezdxf
import pytest

from ga_test_helpers import CANONICAL, CANONICAL_RUN_ID, sized


@pytest.fixture(scope="session")
def canonical_paths(tmp_path_factory) -> dict[str, Path]:
    from drawing.ga import generate_ga

    params, geometry = sized(*CANONICAL)
    out_dir = tmp_path_factory.mktemp("ga-canonical")
    return generate_ga(geometry, params, out_dir, run_id=CANONICAL_RUN_ID)


@pytest.fixture(scope="session")
def canonical_doc(canonical_paths):
    return ezdxf.readfile(canonical_paths["ga_dxf"])


@pytest.fixture(scope="session")
def canonical_svg(canonical_paths) -> str:
    return Path(canonical_paths["ga_svg"]).read_text(encoding="utf-8")
