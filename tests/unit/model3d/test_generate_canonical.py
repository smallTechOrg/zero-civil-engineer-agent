"""generate_solid on the canonical 4 x 3 x 2.5 culvert — files, formats, speed."""

import time

from m3d_test_helpers import glb_header, glb_json_chunk

GLB_MIN_BYTES = 2048
STEP_MIN_BYTES = 10240  # spec/capabilities/model-3d.md: STEP is non-trivial (> 10 KB)
RUNTIME_BUDGET_S = 5.0


def test_returns_pinned_artifact_paths_with_fixed_names(canonical_paths):
    assert set(canonical_paths) == {"model_glb", "model_step"}
    assert canonical_paths["model_glb"].name == "model.glb"
    assert canonical_paths["model_step"].name == "model.step"
    assert canonical_paths["model_glb"].is_file()
    assert canonical_paths["model_step"].is_file()


def test_creates_missing_out_dir(canonical_geometry, tmp_path):
    from model3d import generate_solid

    out_dir = tmp_path / "artifacts" / "run-3d-0001"
    assert not out_dir.exists()

    paths = generate_solid(canonical_geometry, out_dir)

    assert out_dir.is_dir()
    assert paths["model_glb"].parent == out_dir
    assert paths["model_step"].parent == out_dir


def test_glb_is_binary_gltf_with_magic_and_size(canonical_paths):
    raw = canonical_paths["model_glb"].read_bytes()

    assert len(raw) > GLB_MIN_BYTES
    magic, version, total_length = glb_header(raw)
    assert magic == b"glTF"
    assert version == 2
    assert total_length == len(raw)


def test_glb_json_chunk_parses_with_meshes(canonical_paths):
    doc = glb_json_chunk(canonical_paths["model_glb"].read_bytes())

    assert doc["asset"]["version"] == "2.0"
    assert doc["meshes"]
    assert doc["accessors"]


def test_step_has_iso_10303_21_header_and_size(canonical_paths):
    raw = canonical_paths["model_step"].read_bytes()

    assert len(raw) > STEP_MIN_BYTES
    text = raw.decode("utf-8", errors="replace")
    assert text.startswith("ISO-10303-21")
    assert "END-ISO-10303-21" in text


def test_generate_completes_under_five_seconds(canonical_geometry, tmp_path):
    from model3d import generate_solid

    start = time.perf_counter()
    generate_solid(canonical_geometry, tmp_path / "timed")
    assert time.perf_counter() - start < RUNTIME_BUDGET_S
