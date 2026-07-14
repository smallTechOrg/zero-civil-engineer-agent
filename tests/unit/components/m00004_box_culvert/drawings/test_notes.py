"""Notes block: grades, cover, units and the PROVISIONAL / NOT-FOR-CONSTRUCTION caveat."""

from components.m00004_box_culvert.drawings import notes

from .conftest import save_and_read, texts


def test_notes_carry_grades_units_and_caveat(geometry, params, tmp_path):
    doc = save_and_read(notes.build(geometry, params), tmp_path, "notes")
    blob = "\n".join(texts(doc))
    assert geometry.concrete_grade_resolved in blob  # resolved concrete grade (single source)
    assert params.steel_grade.value in blob
    assert "ALL DIMENSIONS IN mm" in blob
    assert "NOT FOR CONSTRUCTION" in blob
    assert "PROVISIONAL" in blob


def test_notes_reference_wearing_pcc_pitching_bed_slope(geometry, params, tmp_path):
    doc = save_and_read(notes.build(geometry, params), tmp_path, "notes")
    blob = "\n".join(texts(doc))
    assert "WEARING COURSE" in blob
    assert "PCC" in blob
    assert "STONE PITCHING" in blob
    assert f"1 in {geometry.bed_slope_run:g}" in blob
