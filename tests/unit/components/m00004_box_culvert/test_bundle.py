"""M-00004 ZIP bundle — gathers every per-diagram DXF + STEP part on disk.

The bundle must be a valid, flat zip that contains exactly the DXF/STEP files
present in ``out_dir`` and must build robustly when the (non-fatal) 3D step left
no STEP files behind.
"""

import zipfile

from components.m00004_box_culvert.bundle import BUNDLE_FILENAME, build_bundle


def _touch(path, content=b"x"):
    path.write_bytes(content)


def test_bundle_contains_every_dxf_and_step(tmp_path):
    # a representative spread of the on-disk artefacts a real run leaves behind
    for name in ("ga.dxf", "elevation.dxf", "cross_section.dxf", "plan.dxf"):
        _touch(tmp_path / name)
    for name in ("model.step", "assembly.step", "box.step"):
        _touch(tmp_path / name)
    # a non-artefact file that must NOT be swept into the bundle
    _touch(tmp_path / "ga.svg")
    _touch(tmp_path / "m00004_sheet.pdf")

    zip_path = build_bundle(tmp_path)

    assert zip_path.name == BUNDLE_FILENAME
    assert zip_path.is_file()
    assert zipfile.is_zipfile(zip_path)

    with zipfile.ZipFile(zip_path) as archive:
        members = set(archive.namelist())
        assert archive.testzip() is None  # every member is intact

    assert members == {
        "ga.dxf",
        "elevation.dxf",
        "cross_section.dxf",
        "plan.dxf",
        "model.step",
        "assembly.step",
        "box.step",
    }
    # the SVG + PDF are deliberately excluded
    assert "ga.svg" not in members
    assert "m00004_sheet.pdf" not in members


def test_bundle_builds_with_dxfs_only_when_step_absent(tmp_path):
    # mirrors a run where the non-fatal 3D step produced no STEP files
    for name in ("ga.dxf", "notes.dxf", "haunch_table.dxf"):
        _touch(tmp_path / name)

    zip_path = build_bundle(tmp_path)

    assert zipfile.is_zipfile(zip_path)
    with zipfile.ZipFile(zip_path) as archive:
        members = set(archive.namelist())
    assert members == {"ga.dxf", "notes.dxf", "haunch_table.dxf"}
    assert not any(m.endswith(".step") for m in members)


def test_bundle_builds_even_when_nothing_present(tmp_path):
    # pathological: no artefacts on disk yet -> still a valid (empty) zip, no raise
    zip_path = build_bundle(tmp_path)

    assert zip_path.is_file()
    assert zipfile.is_zipfile(zip_path)
    with zipfile.ZipFile(zip_path) as archive:
        assert archive.namelist() == []


def test_bundle_creates_missing_out_dir(tmp_path):
    nested = tmp_path / "runs" / "abc"
    zip_path = build_bundle(nested)

    assert zip_path.parent == nested
    assert zip_path.is_file()
