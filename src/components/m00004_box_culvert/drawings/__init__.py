"""Per-diagram ezdxf authoring for the RDSO/M-00004 standard box culvert.

Deliverable 1 of Phase 2: one DXF + one SVG *per diagram* (never one combined
sheet). Each sibling module authors its OWN ezdxf ``Drawing`` from
``M00004Geometry`` values only (never LLM CAD) via the shared ``build(geometry,
params) -> Drawing`` contract, and every drawing carries the PROVISIONAL /
NOT-FOR-CONSTRUCTION caption. The aggregator (``..drawing``) owns saving each doc
to ``<kind>.dxf`` and rendering ``<kind>.svg`` through ``drawing.svg_render``.

This module holds ONLY the shared authoring helpers (layers, dimstyle, text,
polyline, linear dimension, the concrete octagon, and the title/caption band) so
the ten diagram modules stay small and consistent with the Phase-1 GA
(``..drawing``) conventions.
"""

from __future__ import annotations

import ezdxf
from ezdxf import bbox
from ezdxf.document import Drawing
from ezdxf.enums import TextEntityAlignment
from ezdxf.layouts import Modelspace

# --- layers (superset of the Phase-1 GA layers plus reinforcement/detail layers) ---
LAYER_OUTLINE = "OUTLINE"
LAYER_DIM = "DIM"
LAYER_TEXT = "TEXT"
LAYER_HATCH = "HATCH"
LAYER_HIDDEN = "HIDDEN"
LAYER_SHEET = "SHEET"
LAYER_BARS = "BARS"
LAYER_WEEP = "WEEP"
LAYER_HFL = "HFL"
DIMSTYLE = "M4"

_LAYERS = (
    (LAYER_OUTLINE, 7, None, 50),
    (LAYER_DIM, 1, None, 18),
    (LAYER_TEXT, 7, None, 25),
    (LAYER_HATCH, 8, None, 13),
    (LAYER_HIDDEN, 8, "DASHED", 18),
    (LAYER_SHEET, 7, None, 35),
    (LAYER_BARS, 2, None, 25),
    (LAYER_WEEP, 4, None, 18),
    (LAYER_HFL, 5, None, 18),
)

# PROVISIONAL / NOT-FOR-CONSTRUCTION caption carried by EVERY per-diagram drawing.
CAVEAT = "PROVISIONAL - NOT FOR CONSTRUCTION - verify every value against RDSO/M-00004"

Point = tuple[float, float]


def scale_for(*sizes: float) -> float:
    """A drawing scale unit ``s`` from the largest characteristic size (mm)."""
    return max(50.0, max(sizes) / 40.0)


def new_doc(s: float) -> Drawing:
    """A fresh R2010 mm document with the shared layers + the ``M4`` dimstyle."""
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 4  # mm
    doc.header["$MEASUREMENT"] = 1
    doc.header["$LTSCALE"] = round(1.5 * s, 1)
    for name, color, linetype, lineweight in _LAYERS:
        attribs = {"color": color, "lineweight": lineweight}
        if linetype:
            attribs["linetype"] = linetype
        doc.layers.add(name, **attribs)
    _add_dimstyle(doc, s)
    return doc


def _add_dimstyle(doc: Drawing, s: float) -> None:
    style = doc.dimstyles.duplicate_entry("EZDXF", DIMSTYLE)
    style.dxf.dimlfac = 1.0
    style.dxf.dimtxt = s
    style.dxf.dimasz = round(0.75 * s, 1)
    style.dxf.dimexe = round(0.5 * s, 1)
    style.dxf.dimexo = round(0.35 * s, 1)
    style.dxf.dimgap = round(0.25 * s, 1)
    style.dxf.dimdec = 0
    style.dxf.dimtad = 1


def text(
    msp: Modelspace,
    content: str,
    at: Point,
    height: float,
    align: TextEntityAlignment = TextEntityAlignment.LEFT,
    *,
    layer: str = LAYER_TEXT,
    rotation: float = 0.0,
) -> None:
    entity = msp.add_text(content, height=height, dxfattribs={"layer": layer, "rotation": rotation})
    entity.set_placement(at, align=align)


def polyline(msp: Modelspace, points: list[Point], *, layer: str = LAYER_OUTLINE, close: bool = True) -> None:
    msp.add_lwpolyline(points, close=close, dxfattribs={"layer": layer})


def line(msp: Modelspace, p1: Point, p2: Point, *, layer: str = LAYER_OUTLINE) -> None:
    msp.add_line(p1, p2, dxfattribs={"layer": layer})


def circle(msp: Modelspace, center: Point, radius: float, *, layer: str = LAYER_WEEP) -> None:
    msp.add_circle(center, radius, dxfattribs={"layer": layer})


def dim(msp: Modelspace, *, base: Point, p1: Point, p2: Point, angle: float = 0.0) -> None:
    dimension = msp.add_linear_dim(
        base=base, p1=p1, p2=p2, angle=angle,
        dimstyle=DIMSTYLE, dxfattribs={"layer": LAYER_DIM},
    )
    dimension.render()


def octagon(geometry, *, cx: float = 0.0, cy: float = 0.0) -> list[Point]:
    """The inner haunched opening (four 45-degree haunches) centred at (cx, cy)."""
    hs = geometry.clear_span_mm / 2.0
    hh = geometry.clear_height_mm / 2.0
    b = geometry.haunch_mm
    return [
        (cx - (hs - b), cy + hh), (cx + hs - b, cy + hh), (cx + hs, cy + hh - b), (cx + hs, cy - (hh - b)),
        (cx + hs - b, cy - hh), (cx - (hs - b), cy - hh), (cx - hs, cy - (hh - b)), (cx - hs, cy + hh - b),
    ]


def add_title_and_caption(
    msp: Modelspace, title: str, s: float, *, subtitle: str | None = None
) -> None:
    """Centre a title above the drawn content and the PROVISIONAL caption below it.

    Called last by each diagram module so the title/caption straddle the actual
    content extents (dimensions and callouts included).
    """
    box = bbox.extents(msp)
    cx = (box.extmin.x + box.extmax.x) / 2.0
    top = box.extmax.y + 2.0 * s
    text(msp, title, (cx, top + 1.6 * s), 1.2 * s, TextEntityAlignment.MIDDLE_CENTER)
    if subtitle:
        text(msp, subtitle, (cx, top + 0.3 * s), 0.75 * s, TextEntityAlignment.MIDDLE_CENTER)
    bottom = box.extmin.y - 2.0 * s
    text(msp, CAVEAT, (cx, bottom), 0.8 * s, TextEntityAlignment.MIDDLE_CENTER)
