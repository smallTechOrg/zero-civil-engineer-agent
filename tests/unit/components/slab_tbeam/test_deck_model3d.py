"""3D solid — valid non-empty GLB, STEP written, verified volume for both decks."""

from pathlib import Path

import pytest

from components.slab_tbeam.model3d import (
    analytic_concrete_volume_m3,
    build_deck_solid,
    generate_solid,
)
from components.slab_tbeam.params import SlabTbeamParams
from components.slab_tbeam.sizing import size_deck


def test_solid_slab_volume_matches_the_closed_form():
    g = size_deck(SlabTbeamParams(span_m=6.0, deck_type="solid_slab")).geometry
    solid = build_deck_solid(g)
    assert solid.volume == pytest.approx(analytic_concrete_volume_m3(g), rel=1e-3)
    box = solid.bounding_box().size
    assert box.X == pytest.approx(g.span_mm / 1000.0, abs=1e-3)
    assert box.Y == pytest.approx(g.deck_width_mm / 1000.0, abs=1e-3)
    assert box.Z == pytest.approx(g.overall_depth_mm / 1000.0, abs=1e-3)


def test_t_beam_volume_matches_the_slab_plus_ribs_closed_form():
    g = size_deck(SlabTbeamParams(span_m=12.0, deck_type="t_beam", number_of_girders=3)).geometry
    solid = build_deck_solid(g)
    expected = analytic_concrete_volume_m3(g)
    assert solid.volume == pytest.approx(expected, rel=1e-3)
    # The T-beam concrete is less than the solid block of the same envelope.
    envelope = g.span_mm / 1000.0 * g.deck_width_mm / 1000.0 * g.overall_depth_mm / 1000.0
    assert expected < envelope


def test_glb_is_a_valid_non_empty_binary_gltf_and_step_is_written(tmp_path: Path):
    g = size_deck(SlabTbeamParams(span_m=10.0, deck_type="t_beam")).geometry
    paths = generate_solid(g, tmp_path)
    assert set(paths) == {"model_glb", "model_step"}
    glb = paths["model_glb"].read_bytes()
    assert glb[:4] == b"glTF"  # binary glTF magic
    assert len(glb) > 500
    step = paths["model_step"].read_text(encoding="utf-8", errors="replace")
    assert step.startswith("ISO-10303-21")
