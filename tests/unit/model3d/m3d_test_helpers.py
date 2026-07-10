"""Shared helpers for the 3D-model template tests — engine-sized geometry,
the closed-form concrete volume, and raw GLB (binary glTF) parsing."""

import json
import struct

from domain.culvert import BoxGeometry, CulvertParams
from engine import size_culvert

CANONICAL = (4.0, 3.0, 2.5)  # clear span, clear height, cushion (m)

MM_PER_M = 1000.0


def sized(span: float, height: float, cushion: float, **overrides) -> BoxGeometry:
    """Engine-sized BoxGeometry for a span/height/cushion triple."""
    params = CulvertParams(
        clear_span_m=span, clear_height_m=height, cushion_m=cushion, **overrides
    )
    return size_culvert(params).geometry


def analytic_concrete_volume_m3(geometry: BoxGeometry) -> float:
    """(outer area - haunched void area) x barrel length, all in metres.

    Each 45-degree haunch fills a corner triangle of leg^2 / 2, so the void
    cross-section is clear_span x clear_height - 4 x haunch^2 / 2.
    """
    haunch_m = geometry.haunch_mm / MM_PER_M
    void_area_m2 = geometry.clear_span_m * geometry.clear_height_m - 2.0 * haunch_m**2
    concrete_area_m2 = geometry.external_width_m * geometry.external_height_m - void_area_m2
    return concrete_area_m2 * geometry.barrel_length_m


def glb_header(raw: bytes) -> tuple[bytes, int, int]:
    """(magic, version, total_length) from the 12-byte GLB header."""
    return struct.unpack_from("<4sII", raw, 0)


def glb_json_chunk(raw: bytes) -> dict:
    """The parsed JSON chunk (chunk 0) of a GLB payload."""
    chunk_length, chunk_type = struct.unpack_from("<I4s", raw, 12)
    assert chunk_type == b"JSON", f"first GLB chunk must be JSON, got {chunk_type!r}"
    return json.loads(raw[20 : 20 + chunk_length])


def glb_mesh_extents_m(doc: dict) -> tuple[float, float, float]:
    """Combined POSITION-accessor extents over all mesh primitives, metres.

    Mesh space (before OCCT's Z-up -> Y-up scene rotation node) uses the
    model axis mapping: X = external width, Y = barrel length, Z = height.
    """
    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    for mesh in doc["meshes"]:
        for primitive in mesh["primitives"]:
            accessor = doc["accessors"][primitive["attributes"]["POSITION"]]
            for axis in range(3):
                lo[axis] = min(lo[axis], accessor["min"][axis])
                hi[axis] = max(hi[axis], accessor["max"][axis])
    return (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])
