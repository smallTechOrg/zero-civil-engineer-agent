"""M-00004 composed GA sheet — valid PDF laying out the diagrams already on disk.

`compose` reads the per-diagram DXFs written by `drawing.draw` (its read
dependency), arranges them into the GA layout, and returns both the composed
`m00004_ga_sheet.pdf` and the `m00004_bundle.zip`. It must produce a valid PDF,
degrade gracefully when a diagram DXF is missing, and never depend on
import-time state.
"""

import zipfile

import pytest

from components.m00004_box_culvert import compose as compose_mod
from components.m00004_box_culvert.compose import GA_SHEET_FILENAME, compose
from components.m00004_box_culvert.drawing import draw
from components.m00004_box_culvert.params import M00004Params
from components.m00004_box_culvert.sizing import size


@pytest.fixture
def built_out_dir(tmp_path):
    """A populated run directory: real diagram DXFs + the params/geometry pair."""
    params = M00004Params(clear_span_m=4.0, clear_height_m=4.0, cushion_m=2.0)
    geometry = size(params).geometry
    draw(params, geometry, tmp_path, run_id="t-compose")
    return params, geometry, tmp_path


def test_compose_returns_both_artefacts(built_out_dir):
    params, geometry, out_dir = built_out_dir

    result = compose(params, geometry, out_dir, run_id="t-compose")

    assert set(result) == {"m00004_ga_sheet", "m00004_bundle"}
    assert result["m00004_ga_sheet"].name == GA_SHEET_FILENAME
    assert result["m00004_bundle"].name == "m00004_bundle.zip"


def test_composed_sheet_is_valid_non_empty_pdf(built_out_dir):
    params, geometry, out_dir = built_out_dir

    result = compose(params, geometry, out_dir, run_id="t-compose")

    pdf = result["m00004_ga_sheet"]
    data = pdf.read_bytes()
    assert data.startswith(b"%PDF-")          # PDF magic
    assert data.rstrip().endswith(b"%%EOF")
    assert len(data) > 5000                    # a real multi-panel sheet, not a stub


def test_composed_bundle_is_valid_zip_with_diagram_dxfs(built_out_dir):
    params, geometry, out_dir = built_out_dir

    result = compose(params, geometry, out_dir, run_id="t-compose")

    zip_path = result["m00004_bundle"]
    assert zipfile.is_zipfile(zip_path)
    with zipfile.ZipFile(zip_path) as archive:
        members = set(archive.namelist())
    # the ten per-diagram DXFs + the Phase-1 GA DXF are all present
    for expected in (
        "ga.dxf",
        "elevation.dxf",
        "cross_section.dxf",
        "plan.dxf",
        "curtain_wall.dxf",
        "typical_details.dxf",
        "return_wall.dxf",
        "bar_shape_table.dxf",
        "notations.dxf",
        "notes.dxf",
        "haunch_table.dxf",
    ):
        assert expected in members


def test_compose_degrades_when_a_diagram_dxf_is_missing(built_out_dir):
    params, geometry, out_dir = built_out_dir
    # simulate a diagram that failed to render upstream
    (out_dir / "curtain_wall.dxf").unlink()

    result = compose(params, geometry, out_dir, run_id="t-compose")

    # the sheet still builds and is a valid PDF (missing panel drawn as a stub)
    data = result["m00004_ga_sheet"].read_bytes()
    assert data.startswith(b"%PDF-")
    assert len(data) > 5000


def test_compose_accepts_dict_inputs(built_out_dir):
    """compose coerces mapping inputs (no import-time state, robust to plain dicts)."""
    params, geometry, out_dir = built_out_dir

    result = compose(
        params.model_dump(), geometry.model_dump(), out_dir, run_id="t-compose"
    )

    assert result["m00004_ga_sheet"].read_bytes().startswith(b"%PDF-")


def test_compose_uses_agg_backend():
    """The module must force the non-interactive Agg backend for headless servers."""
    import matplotlib

    assert matplotlib.get_backend().lower() == "agg"
    # the module exposes the resolved concrete grade path via geometry, not params
    assert compose_mod.GA_SHEET_FILENAME == "m00004_ga_sheet.pdf"
