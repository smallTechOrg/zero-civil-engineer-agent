"""Shared fixtures for the per-diagram (drawings/) unit tests.

Every diagram is built from the same sample config: span 4 m / height 4 m /
fill 2 m. Each test saves the authored ezdxf ``Drawing`` and reopens it via
``ezdxf.readfile`` (the artefact-round-trip the graph relies on).
"""

from __future__ import annotations

from pathlib import Path

import ezdxf
import pytest
from ezdxf.document import Drawing

from components.m00004_box_culvert.params import M00004Params
from components.m00004_box_culvert.sizing import size


@pytest.fixture
def params() -> M00004Params:
    return M00004Params(clear_span_m=4.0, clear_height_m=4.0, cushion_m=2.0)


@pytest.fixture
def geometry(params):
    return size(params).geometry


def save_and_read(doc: Drawing, tmp_path: Path, name: str) -> Drawing:
    """Save ``doc`` to ``<name>.dxf`` and reopen it via ezdxf (asserts emission)."""
    path = tmp_path / f"{name}.dxf"
    doc.saveas(path)
    assert path.exists() and path.stat().st_size > 0
    return ezdxf.readfile(path)


def texts(doc: Drawing) -> list[str]:
    return [t.dxf.text for t in doc.modelspace().query("TEXT")]
