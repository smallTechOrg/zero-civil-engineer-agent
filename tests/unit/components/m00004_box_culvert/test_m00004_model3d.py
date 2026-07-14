"""3D solids: fused model.glb + model.step (Phase-1, unchanged) PLUS the four
Phase-2 genuinely-3D STEP parts, each volume-verified against its closed form."""

from build123d import Compound

from components.m00004_box_culvert.model3d import (
    _barrel_solid,
    _barrel_volume_m3,
    _curtain_solids,
    _curtains_volume_m3,
    _dims_m,
    _wall_solids,
    _walls_volume_m3,
    analytic_concrete_volume_m3,
    build_solid,
    model3d,
)
from components.m00004_box_culvert.params import M00004Params
from components.m00004_box_culvert.sizing import size

_TOL = 1e-3  # relative volume self-check tolerance (matches the module)

_STEP_KEYS = ("assembly_step", "box_step", "curtain_wall_step", "return_wall_step")
_ALL_KEYS = {"model_glb", "model_step", *_STEP_KEYS}


def _geometry():
    return size(M00004Params(clear_span_m=4.0, clear_height_m=4.0, cushion_m=2.0)).geometry


# --------------------------------------------------------------------------- Phase-1 (unchanged)


def test_solid_volume_matches_closed_form():
    geometry = _geometry()
    solid = build_solid(geometry)
    expected = analytic_concrete_volume_m3(geometry)
    assert expected > 0
    assert abs(solid.volume - expected) <= _TOL * expected  # self-check tolerance


def test_solid_bounding_box_spans_the_full_structure():
    geometry = _geometry()
    solid = build_solid(geometry)
    size_bb = solid.bounding_box().size
    # Y spans barrel + wing/apron + curtain beyond both ends
    full_len = (
        geometry.barrel_length_mm
        + 2.0 * (geometry.apron_len_mm + geometry.curtain_thickness_mm)
    ) / 1000.0
    assert size_bb.Y >= full_len - 1e-3


# --------------------------------------------------------------------------- closed-form partition


def test_subvolumes_partition_the_total():
    """barrel + walls + aprons + curtains must sum to the closed-form total."""
    geometry = _geometry()
    d = _dims_m(geometry)
    from components.m00004_box_culvert.model3d import _aprons_volume_m3

    total = analytic_concrete_volume_m3(geometry)
    parts_sum = (
        _barrel_volume_m3(d)
        + _walls_volume_m3(d)
        + _aprons_volume_m3(d)
        + _curtains_volume_m3(d)
    )
    assert all(
        v > 0
        for v in (
            _barrel_volume_m3(d),
            _walls_volume_m3(d),
            _aprons_volume_m3(d),
            _curtains_volume_m3(d),
        )
    )
    assert abs(parts_sum - total) <= _TOL * total


# --------------------------------------------------------------------------- built parts vs sub-volume


def test_built_parts_match_their_closed_form_subvolumes():
    """Each built sub-solid's volume equals its own closed-form basis."""
    geometry = _geometry()
    d = _dims_m(geometry)

    barrel = _barrel_solid(d)
    barrel_expected = _barrel_volume_m3(d)
    assert abs(barrel.volume - barrel_expected) <= _TOL * barrel_expected

    return_wall = Compound(children=_wall_solids(d))
    walls_expected = _walls_volume_m3(d)
    assert abs(return_wall.volume - walls_expected) <= _TOL * walls_expected

    curtain_wall = Compound(children=_curtain_solids(d))
    curtains_expected = _curtains_volume_m3(d)
    assert abs(curtain_wall.volume - curtains_expected) <= _TOL * curtains_expected


def test_assembly_compound_is_multibody_and_matches_total():
    """The assembly is a genuine multi-body Compound whose volume = the total."""
    geometry = _geometry()
    d = _dims_m(geometry)
    from components.m00004_box_culvert.model3d import _apron_solids

    assembly = Compound(
        children=[
            _barrel_solid(d),
            *_wall_solids(d),
            *_apron_solids(d),
            *_curtain_solids(d),
        ]
    )
    # 1 barrel + 4 walls + 2 aprons + 2 curtains = 9 distinct bodies
    assert len(assembly.solids()) == 9
    total = analytic_concrete_volume_m3(geometry)
    assert abs(assembly.volume - total) <= _TOL * total


# --------------------------------------------------------------------------- export (six artefacts)


def test_exports_six_artefacts_non_empty(tmp_path):
    paths = model3d(_geometry(), tmp_path)
    assert set(paths) == _ALL_KEYS

    # Phase-1 fused artefacts (unchanged behaviour)
    glb = paths["model_glb"].read_bytes()
    step = paths["model_step"].read_bytes()
    assert glb[:4] == b"glTF"                # binary glTF magic
    assert len(glb) > 0 and len(step) > 0
    assert b"ISO-10303" in step[:400]        # STEP header

    # Phase-2 STEP parts: emitted, non-empty, valid STEP headers
    for key in _STEP_KEYS:
        data = paths[key].read_bytes()
        assert len(data) > 0, f"{key} STEP is empty"
        assert b"ISO-10303" in data[:400], f"{key} lacks a STEP header"


def test_exported_step_parts_have_expected_filenames(tmp_path):
    paths = model3d(_geometry(), tmp_path)
    assert paths["assembly_step"].name == "assembly.step"
    assert paths["box_step"].name == "box.step"
    assert paths["curtain_wall_step"].name == "curtain_wall.step"
    assert paths["return_wall_step"].name == "return_wall.step"
