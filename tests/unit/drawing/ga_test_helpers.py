"""DXF read-back helpers shared by the GA drawing template tests."""

import ezdxf.bbox
from ezdxf.math import BoundingBox2d

from domain.culvert import CulvertParams
from engine import size_culvert

CANONICAL = (4.0, 3.0, 2.5)  # clear span, clear height, cushion (m)
CANONICAL_RUN_ID = "run-ga-0001"


def sized(span: float, height: float, cushion: float, **overrides):
    """CulvertParams + engine-sized BoxGeometry for a span/height/cushion triple."""
    params = CulvertParams(
        clear_span_m=span, clear_height_m=height, cushion_m=cushion, **overrides
    )
    return params, size_culvert(params).geometry


def measurements_of(doc) -> list[float]:
    """Every DIMENSION measurement in the modelspace, in mm."""
    return sorted(
        round(dim.get_measurement(), 3) for dim in doc.modelspace().query("DIMENSION")
    )


def count_close(values: list[float], expected: float, tol: float = 1.0) -> int:
    return sum(1 for v in values if abs(v - expected) <= tol)


def all_text_of(doc) -> str:
    """All TEXT/MTEXT content — modelspace plus rendered dimension geometry blocks."""
    chunks: list[str] = []
    msp = doc.modelspace()
    for entity in msp.query("TEXT"):
        chunks.append(entity.dxf.text)
    for entity in msp.query("MTEXT"):
        chunks.append(entity.plain_text())
    for dim in msp.query("DIMENSION"):
        block_name = dim.dxf.get("geometry", None)
        if not block_name or block_name not in doc.blocks:
            continue
        block = doc.blocks[block_name]
        for entity in block.query("TEXT"):
            chunks.append(entity.dxf.text)
        for entity in block.query("MTEXT"):
            chunks.append(entity.plain_text())
    return "\n".join(chunks)


def dimension_texts_of(doc) -> set[str]:
    """The rendered dimension text strings, straight from the geometry blocks."""
    texts: set[str] = set()
    for dim in doc.modelspace().query("DIMENSION"):
        block_name = dim.dxf.get("geometry", None)
        if not block_name or block_name not in doc.blocks:
            continue
        block = doc.blocks[block_name]
        for entity in block.query("TEXT"):
            texts.add(entity.dxf.text.strip())
        for entity in block.query("MTEXT"):
            texts.add(entity.plain_text().strip())
    return texts


def frame_bbox_of(doc) -> BoundingBox2d:
    """Bounding box of the sheet frame — the largest closed polyline on SHEET."""
    boxes = [
        BoundingBox2d(pline.get_points(format="xy"))
        for pline in doc.modelspace().query("LWPOLYLINE[layer=='SHEET']")
    ]
    assert boxes, "no sheet frame polyline found on layer SHEET"
    return max(boxes, key=lambda b: b.size.x * b.size.y)


def content_bbox_of(doc):
    """Extents of every modelspace entity (frame included)."""
    return ezdxf.bbox.extents(doc.modelspace())
