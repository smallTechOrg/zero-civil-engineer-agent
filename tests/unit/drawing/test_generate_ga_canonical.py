"""Canonical 4/3/2.5 case — file outputs, DXF structure, layers, notes, title block."""

import inspect
from pathlib import Path

from ga_test_helpers import CANONICAL_RUN_ID, all_text_of, sized

EXPECTED_LAYERS = {"OUTLINE", "DIM", "TEXT", "HATCH", "CL", "HIDDEN", "SHEET"}


def test_pinned_public_signature_matches_the_contract():
    from drawing.ga import generate_ga

    signature = inspect.signature(generate_ga)
    names = list(signature.parameters)

    assert names[:4] == ["geometry", "params", "out_dir", "run_id"]
    assert signature.parameters["run_id"].default is None


def test_writes_both_fixed_name_artifacts_and_returns_their_paths(canonical_paths):
    assert set(canonical_paths) == {"ga_dxf", "ga_svg"}
    assert canonical_paths["ga_dxf"].name == "ga.dxf"
    assert canonical_paths["ga_svg"].name == "ga.svg"
    assert canonical_paths["ga_dxf"].is_file()
    assert canonical_paths["ga_svg"].is_file()
    assert canonical_paths["ga_dxf"].stat().st_size > 5 * 1024


def test_dxf_round_trips_and_audits_clean(canonical_doc):
    auditor = canonical_doc.audit()

    assert len(auditor.errors) == 0


def test_dxf_contains_more_than_eight_rendered_dimensions(canonical_doc):
    dimensions = canonical_doc.modelspace().query("DIMENSION")

    assert len(dimensions) > 8
    for dim in dimensions:
        block_name = dim.dxf.get("geometry", None)
        assert block_name and block_name in canonical_doc.blocks, (
            "dimension has no rendered geometry block - dim.render() was not called"
        )


def test_dxf_declares_the_conventional_layers(canonical_doc):
    layer_names = {layer.dxf.name for layer in canonical_doc.layers}

    assert EXPECTED_LAYERS <= layer_names
    assert canonical_doc.layers.get("CL").dxf.linetype == "CENTER"


def test_concrete_is_hatched_and_centrelines_drawn(canonical_doc):
    msp = canonical_doc.modelspace()

    hatches = msp.query("HATCH[layer=='HATCH']")
    centrelines = msp.query("LINE[layer=='CL']")
    assert len(hatches) >= 1
    assert len(centrelines) >= 2


def test_title_block_names_project_run_loading_and_demo_tag(canonical_doc):
    text = all_text_of(canonical_doc)

    assert "BOX CULVERT" in text
    assert "GENERAL ARRANGEMENT" in text
    assert CANONICAL_RUN_ID in text
    assert "25t LOADING-2008" in text
    assert "FOR DEMONSTRATION" in text


def test_general_notes_state_materials_cover_units_and_loading(canonical_doc):
    text = all_text_of(canonical_doc)

    assert "GENERAL NOTES" in text
    assert "M30" in text
    assert "Fe500" in text
    assert "COVER" in text
    assert "MILLIMETRES" in text
    assert "INCL. ACS" in text


def test_all_three_views_are_titled_with_a_scale_note(canonical_doc):
    text = all_text_of(canonical_doc)

    assert "PLAN" in text
    assert "SECTION A-A" in text
    assert "SECTION B-B" in text
    assert "N.T.S." in text


def test_out_dir_is_created_when_missing_and_run_id_is_optional(tmp_path):
    from drawing.ga import generate_ga

    params, geometry = sized(4.0, 3.0, 2.5)
    nested = tmp_path / "artifacts" / "some-run-id"

    paths = generate_ga(geometry, params, nested)

    assert nested.is_dir()
    assert paths["ga_dxf"].is_file()
    assert paths["ga_svg"].is_file()
    assert isinstance(paths["ga_dxf"], Path)
