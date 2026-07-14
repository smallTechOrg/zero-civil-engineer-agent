"""The M-00004 PDF sheet is a valid, non-empty application/pdf."""

from components.m00004_box_culvert.params import M00004Params
from components.m00004_box_culvert.pdfsheet import SHEET_FILENAME, generate_sheet
from components.m00004_box_culvert.sizing import size


def test_pdf_sheet_is_valid_and_non_empty(tmp_path):
    params = M00004Params(clear_span_m=4.0, clear_height_m=4.0, cushion_m=2.0)
    geometry = size(params).geometry
    path = generate_sheet(params, geometry, tmp_path, run_id="t-0001")

    assert path.name == SHEET_FILENAME
    data = path.read_bytes()
    assert data.startswith(b"%PDF")          # valid PDF magic
    assert data.rstrip().endswith(b"%%EOF")
    assert len(data) > 3000                  # a real hand-built sheet, not a stub


def test_pdf_sheet_renders_out_of_catalogue_provisional_case(tmp_path):
    # 7x7 fill 3 surcharge 10 -> 6x6 config with multiple PROVISIONAL flags
    params = M00004Params(
        clear_span_m=7.0, clear_height_m=7.0, cushion_m=3.0, surcharge_kn_m2=10.0
    )
    geometry = size(params).geometry
    assert geometry.provisional_flags  # the sheet must render the flagged case without error
    path = generate_sheet(params, geometry, tmp_path, run_id="t-0002")
    assert path.read_bytes().startswith(b"%PDF")
