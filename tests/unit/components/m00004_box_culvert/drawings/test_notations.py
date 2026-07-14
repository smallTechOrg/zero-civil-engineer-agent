"""Notations glossary: every mark mapped to its member/face (MARK_NOTATION)."""

from components.m00004_box_culvert.drawings import notations
from components.m00004_box_culvert.reinforcement import BAR_MARKS, MARK_NOTATION

from .conftest import save_and_read, texts


def test_notations_maps_every_mark(geometry, params, tmp_path):
    doc = save_and_read(notations.build(geometry, params), tmp_path, "notations")
    labels = texts(doc)
    for mark in BAR_MARKS:
        assert mark in labels, f"notations glossary missing mark {mark}"
    # at least one member/face description from the shared notation source
    assert any(MARK_NOTATION["a1"] in t for t in labels)


def test_notations_is_provisional(geometry, params, tmp_path):
    doc = save_and_read(notations.build(geometry, params), tmp_path, "notations")
    assert any("PROVISIONAL" in t for t in texts(doc))
