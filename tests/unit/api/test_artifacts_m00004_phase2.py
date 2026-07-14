"""Slice (e) — the 26 new M-00004 Phase-2 filenames in the ARTIFACT_FILES whitelist.

Pins the api-side whitelist against the normative capability-doc Phase 2 table
(kind <-> filename <-> mime <-> disposition) and confirms an unknown filename is
still rejected 400 (traversal-proof by construction).
"""

from api.designs import ARTIFACT_FILES

# filename -> (mime, disposition) — normative (capability doc Phase 2 table).
NEW_FILES = {
    "elevation.dxf": ("image/vnd.dxf", "attachment"),
    "elevation.svg": ("image/svg+xml", "inline"),
    "cross_section.dxf": ("image/vnd.dxf", "attachment"),
    "cross_section.svg": ("image/svg+xml", "inline"),
    "plan.dxf": ("image/vnd.dxf", "attachment"),
    "plan.svg": ("image/svg+xml", "inline"),
    "curtain_wall.dxf": ("image/vnd.dxf", "attachment"),
    "curtain_wall.svg": ("image/svg+xml", "inline"),
    "typical_details.dxf": ("image/vnd.dxf", "attachment"),
    "typical_details.svg": ("image/svg+xml", "inline"),
    "return_wall.dxf": ("image/vnd.dxf", "attachment"),
    "return_wall.svg": ("image/svg+xml", "inline"),
    "bar_shape_table.dxf": ("image/vnd.dxf", "attachment"),
    "bar_shape_table.svg": ("image/svg+xml", "inline"),
    "notations.dxf": ("image/vnd.dxf", "attachment"),
    "notations.svg": ("image/svg+xml", "inline"),
    "notes.dxf": ("image/vnd.dxf", "attachment"),
    "notes.svg": ("image/svg+xml", "inline"),
    "haunch_table.dxf": ("image/vnd.dxf", "attachment"),
    "haunch_table.svg": ("image/svg+xml", "inline"),
    "assembly.step": ("application/step", "attachment"),
    "box.step": ("application/step", "attachment"),
    "curtain_wall.step": ("application/step", "attachment"),
    "return_wall.step": ("application/step", "attachment"),
    "m00004_ga_sheet.pdf": ("application/pdf", "inline"),
    "m00004_bundle.zip": ("application/zip", "attachment"),
}


def test_whitelist_has_all_26_new_files_with_correct_mime_and_disposition():
    assert len(NEW_FILES) == 26
    for filename, expected in NEW_FILES.items():
        assert filename in ARTIFACT_FILES, filename
        assert ARTIFACT_FILES[filename] == expected, filename
    # Phase-1 entries untouched.
    assert ARTIFACT_FILES["ga.dxf"] == ("image/vnd.dxf", "attachment")
    assert ARTIFACT_FILES["m00004_sheet.pdf"] == ("application/pdf", "inline")


def test_served_files_use_the_whitelisted_mime_and_disposition(
    api_client, make_session_row, make_run_row, artifacts_dir
):
    session_id = make_session_row()
    run_id = make_run_row(session_id, status="completed")
    run_dir = artifacts_dir / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "elevation.dxf").write_bytes(b"0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n")
    (run_dir / "m00004_ga_sheet.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    (run_dir / "m00004_bundle.zip").write_bytes(b"PK\x03\x04rest")

    r = api_client.get(f"/api/designs/{run_id}/artifacts/elevation.dxf")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/vnd.dxf")
    assert r.headers["content-disposition"] == 'attachment; filename="elevation.dxf"'

    r = api_client.get(f"/api/designs/{run_id}/artifacts/m00004_ga_sheet.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.headers["content-disposition"] == 'inline; filename="m00004_ga_sheet.pdf"'

    r = api_client.get(f"/api/designs/{run_id}/artifacts/m00004_bundle.zip")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/zip")
    assert r.headers["content-disposition"] == 'attachment; filename="m00004_bundle.zip"'


def test_non_whitelisted_filename_still_400(
    api_client, make_session_row, make_run_row, artifacts_dir
):
    session_id = make_session_row()
    run_id = make_run_row(session_id, status="completed")
    (artifacts_dir / run_id).mkdir(parents=True)
    for bad in ("elevation.pdf", "assembly.stp", "m00004_ga_sheet.zip", "notes.txt"):
        r = api_client.get(f"/api/designs/{run_id}/artifacts/{bad}")
        assert r.status_code == 400, bad
        assert r.json()["detail"]["code"] == "INVALID_FILENAME"
