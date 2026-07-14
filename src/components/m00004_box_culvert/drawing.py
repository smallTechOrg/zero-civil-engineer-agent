"""GA drawing generator for the M-00004 standard box culvert.

Hand-validated parametric ezdxf template (never LLM CAD): a dimensioned concrete
cross-section (outer rectangle + inner octagon with four 45-degree haunches,
hatched) and a part-plan (barrel + return/wing walls + apron), with an RDSO-style
title block carrying the PROVISIONAL / NOT-FOR-CONSTRUCTION caveat. The SVG is
rendered by the shared ezdxf SVGBackend (`drawing.svg_render.render_svg`) from the
very document written to ga.dxf. `draw` also produces the M-00004 PDF sheet.

Every dimension value comes from `M00004Geometry` — the same source the PDF sheet
and 3D solid use — so calc-vs-drawing consistency is structural.

    from components.m00004_box_culvert.drawing import draw
    paths = draw(params, geometry, out_dir, run_id)
    # -> {"ga_dxf", "ga_svg", "m00004_sheet", <ten <kind>_dxf/_svg pairs>}

Phase 2 turns this module into an AGGREGATOR: it still authors the combined
Phase-1 GA (`ga.dxf` = section + plan + title, byte-behaviour preserved) and the
PDF sheet, AND additionally drives the ten per-diagram modules under `drawings/`
(one `<kind>.dxf` + `<kind>.svg` each), saving + rendering them in one place.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import ezdxf
from ezdxf.document import Drawing
from ezdxf.enums import TextEntityAlignment
from ezdxf.layouts import Modelspace

from components.m00004_box_culvert import pdfsheet
from components.m00004_box_culvert.drawings import (
    bar_shape_table,
    cross_section,
    curtain_wall,
    elevation,
    haunch_table,
    notations,
    notes,
    plan,
    return_wall,
    typical_details,
)
from components.m00004_box_culvert.params import M00004Geometry, M00004Params
from drawing.svg_render import render_svg

# kind -> diagram module (each exposes ``build(geometry, params) -> Drawing``).
# The kind is the artefact key stem AND the on-disk filename stem (kind.dxf/kind.svg).
_DIAGRAM_MODULES = (
    ("elevation", elevation),
    ("cross_section", cross_section),
    ("plan", plan),
    ("curtain_wall", curtain_wall),
    ("typical_details", typical_details),
    ("return_wall", return_wall),
    ("bar_shape_table", bar_shape_table),
    ("notations", notations),
    ("notes", notes),
    ("haunch_table", haunch_table),
)

GA_DXF_NAME = "ga.dxf"
GA_SVG_NAME = "ga.svg"

LAYER_OUTLINE = "OUTLINE"
LAYER_DIM = "DIM"
LAYER_TEXT = "TEXT"
LAYER_HATCH = "HATCH"
LAYER_HIDDEN = "HIDDEN"
LAYER_SHEET = "SHEET"
DIMSTYLE = "M4"

_LAYERS = (
    (LAYER_OUTLINE, 7, None, 50),
    (LAYER_DIM, 1, None, 18),
    (LAYER_TEXT, 7, None, 25),
    (LAYER_HATCH, 8, None, 13),
    (LAYER_HIDDEN, 8, "DASHED", 18),
    (LAYER_SHEET, 7, None, 35),
)

PROJECT_TITLE = "RDSO/M-00004 STANDARD SINGLE BOX CULVERT - GENERAL ARRANGEMENT & REINFORCEMENT"
CAVEAT = "PROVISIONAL - NOT FOR CONSTRUCTION - verify every value against RDSO/M-00004"

Point = tuple[float, float]


class InvalidGeometryError(ValueError):
    """Raised when the box geometry is impossible or internally inconsistent."""


def _validate(geometry: M00004Geometry) -> None:
    for name, value in (
        ("clear span", geometry.clear_span_mm),
        ("clear height", geometry.clear_height_mm),
        ("thickness", geometry.thickness_mm),
        ("outer width", geometry.outer_width_mm),
        ("outer height", geometry.outer_height_mm),
        ("barrel length", geometry.barrel_length_mm),
    ):
        if value <= 0:
            raise InvalidGeometryError(f"{name} must be positive, got {value:g} mm")
    if geometry.haunch_mm < 0:
        raise InvalidGeometryError(f"haunch must be non-negative, got {geometry.haunch_mm:g} mm")
    if 2.0 * geometry.haunch_mm >= min(geometry.clear_span_mm, geometry.clear_height_mm):
        raise InvalidGeometryError("haunch legs overlap the clear opening")


def draw(
    params: M00004Params,
    geometry: M00004Geometry,
    out_dir: Path,
    run_id: str | None = None,
    *,
    drawing_date: dt.date | None = None,
) -> dict[str, Path]:
    """Generate ga.dxf + ga.svg + m00004_sheet.pdf inside ``out_dir``."""
    params = _coerce_params(params)
    geometry = _coerce_geometry(geometry)
    _validate(geometry)
    drawing_date = drawing_date or dt.date.today()

    doc = _build_sheet(params, geometry, run_id, drawing_date)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dxf_path = out_dir / GA_DXF_NAME
    doc.saveas(dxf_path)
    svg_path = out_dir / GA_SVG_NAME
    svg_path.write_text(render_svg(doc), encoding="utf-8")

    pdf_path = pdfsheet.generate_sheet(
        params, geometry, out_dir, run_id=run_id, drawing_date=drawing_date
    )
    result: dict[str, Path] = {"ga_dxf": dxf_path, "ga_svg": svg_path, "m00004_sheet": pdf_path}
    result.update(_draw_diagrams(params, geometry, out_dir))
    return result


def _draw_diagrams(
    params: M00004Params, geometry: M00004Geometry, out_dir: Path
) -> dict[str, Path]:
    """Author, save and render the ten per-diagram DXF+SVG pairs.

    Each diagram module builds its own ezdxf ``Drawing`` from geometry; saving to
    ``<kind>.dxf`` and rendering ``<kind>.svg`` (shared SVG backend) happen here so
    on-disk naming stays in one place. Returns ``{<kind>_dxf, <kind>_svg -> Path}``.
    """
    pairs: dict[str, Path] = {}
    for kind, module in _DIAGRAM_MODULES:
        doc = module.build(geometry, params)
        dxf_path = out_dir / f"{kind}.dxf"
        doc.saveas(dxf_path)
        svg_path = out_dir / f"{kind}.svg"
        svg_path.write_text(render_svg(doc), encoding="utf-8")
        pairs[f"{kind}_dxf"] = dxf_path
        pairs[f"{kind}_svg"] = svg_path
    return pairs


def _coerce_params(params) -> M00004Params:
    from components.base import coerce

    return coerce(M00004Params, params)


def _coerce_geometry(geometry) -> M00004Geometry:
    from components.base import coerce

    return coerce(M00004Geometry, geometry)


def _build_sheet(
    params: M00004Params, geometry: M00004Geometry, run_id: str | None, drawing_date: dt.date
) -> Drawing:
    s = max(50.0, max(geometry.outer_width_mm, geometry.outer_height_mm) / 40.0)
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

    msp = doc.modelspace()
    _draw_section(msp, geometry, s)
    plan_top_y = -(geometry.outer_height_mm / 2.0) - 14.0 * s
    _draw_plan(msp, geometry, s, plan_top_y)
    _draw_frame_and_title(msp, params, geometry, run_id, drawing_date, s)
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


def _text(msp: Modelspace, content: str, at: Point, height: float,
          align: TextEntityAlignment = TextEntityAlignment.LEFT) -> None:
    entity = msp.add_text(content, height=height, dxfattribs={"layer": LAYER_TEXT})
    entity.set_placement(at, align=align)


def _polyline(msp: Modelspace, points: list[Point], *, layer: str = LAYER_OUTLINE) -> None:
    msp.add_lwpolyline(points, close=True, dxfattribs={"layer": layer})


def _dim(msp: Modelspace, *, base: Point, p1: Point, p2: Point, angle: float = 0.0) -> None:
    dimension = msp.add_linear_dim(
        base=base, p1=p1, p2=p2, angle=angle,
        dimstyle=DIMSTYLE, dxfattribs={"layer": LAYER_DIM},
    )
    dimension.render()


def _octagon(geometry: M00004Geometry) -> list[Point]:
    hs = geometry.clear_span_mm / 2.0
    hh = geometry.clear_height_mm / 2.0
    b = geometry.haunch_mm
    return [
        (-(hs - b), hh), (hs - b, hh), (hs, hh - b), (hs, -(hh - b)),
        (hs - b, -hh), (-(hs - b), -hh), (-hs, -(hh - b)), (-hs, hh - b),
    ]


def _draw_section(msp: Modelspace, g: M00004Geometry, s: float) -> None:
    """SECTION A-A — the concrete cross-section with dimension chains."""
    hs = g.clear_span_mm / 2.0
    hh = g.clear_height_mm / 2.0
    ox = g.outer_width_mm / 2.0
    oy = g.outer_height_mm / 2.0
    outer = [(-ox, -oy), (ox, -oy), (ox, oy), (-ox, oy)]
    inner = _octagon(g)

    # hatched concrete ring: outer boundary with the opening as an island
    hatch = msp.add_hatch(dxfattribs={"layer": LAYER_HATCH})
    hatch.set_pattern_fill("ANSI31", scale=max(1.0, 0.4 * s))
    hatch.paths.add_polyline_path(outer, is_closed=True, flags=1)  # external
    hatch.paths.add_polyline_path(inner, is_closed=True, flags=0)  # hole
    _polyline(msp, outer)
    _polyline(msp, inner)

    off1 = 3.0 * s
    off2 = 7.0 * s
    off3 = 11.0 * s
    # clear span (principal) — bottom
    _dim(msp, base=(0.0, -oy - off2), p1=(-hs, -oy), p2=(hs, -oy))
    # overall width — bottom, lower row
    _dim(msp, base=(0.0, -oy - off3), p1=(-ox, -oy), p2=(ox, -oy))
    # clear height (principal) — left
    _dim(msp, base=(-ox - off2, 0.0), p1=(-ox, -hh), p2=(-ox, hh), angle=90)
    # overall height — left, outer row
    _dim(msp, base=(-ox - off3, 0.0), p1=(-ox, -oy), p2=(-ox, oy), angle=90)
    # slab thickness — right, at the top slab
    _dim(msp, base=(ox + off1, (hh + oy) / 2.0), p1=(ox, hh), p2=(ox, oy), angle=90)
    # haunch leg — callout text near the top-right haunch
    _text(msp, f"HAUNCH {g.haunch_mm:g} x {g.haunch_mm:g}", (hs - g.haunch_mm, hh + 1.2 * s), 0.8 * s)
    _text(msp, "SECTION A-A  (SCALE: N.T.S.)", (0.0, oy + off2 + 2.0 * s),
          1.1 * s, TextEntityAlignment.MIDDLE_CENTER)
    _text(msp, f"CONFIG {g.config_id}  -  {CAVEAT}", (0.0, oy + off2 + 0.6 * s),
          0.7 * s, TextEntityAlignment.MIDDLE_CENTER)


def _draw_plan(msp: Modelspace, g: M00004Geometry, s: float, plan_top_y: float) -> None:
    """PART-PLAN — barrel length with return/wing walls + apron, dimensioned.

    Plan axes: X = barrel length (0..L), Y = transverse width centred on 0.
    """
    length = g.barrel_length_mm
    w = g.outer_width_mm
    cls = g.clear_span_mm
    wing = g.wing_len_mm
    apron = g.apron_len_mm
    y_mid = plan_top_y - w / 2.0

    def band(x0, x1, y0, y1, *, layer=LAYER_OUTLINE):
        _polyline(msp, [(x0, y_mid + y0), (x1, y_mid + y0), (x1, y_mid + y1), (x0, y_mid + y1)], layer=layer)

    # barrel outer + clear opening (dashed) through the barrel
    band(0.0, length, -w / 2.0, w / 2.0)
    band(0.0, length, -cls / 2.0, cls / 2.0, layer=LAYER_HIDDEN)
    # return / wing walls (continuations of the side-wall bands beyond each end)
    for x0, x1 in ((-wing, 0.0), (length, length + wing)):
        band(x0, x1, cls / 2.0, w / 2.0)
        band(x0, x1, -w / 2.0, -cls / 2.0)
    # apron floor (centre band) beyond each end
    for x0, x1 in ((-apron, 0.0), (length, length + apron)):
        band(x0, x1, -cls / 2.0, cls / 2.0, layer=LAYER_HIDDEN)

    _dim(msp, base=(length / 2.0, y_mid - w / 2.0 - 3.0 * s), p1=(0.0, y_mid - w / 2.0),
         p2=(length, y_mid - w / 2.0))
    _text(msp, "PART-PLAN  (SCALE: N.T.S.)", (length / 2.0, plan_top_y + 1.0 * s),
          0.9 * s, TextEntityAlignment.MIDDLE_CENTER)


def _draw_frame_and_title(
    msp: Modelspace, params: M00004Params, g: M00004Geometry,
    run_id: str | None, drawing_date: dt.date, s: float,
) -> None:
    content = ezdxf.bbox.extents(msp)
    margin = 4.0 * s
    title_h = 11.0 * s
    xmin = content.extmin.x - margin
    xmax = content.extmax.x + margin
    ymax = content.extmax.y + margin
    ymin = content.extmin.y - margin - title_h
    _polyline(msp, [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)], layer=LAYER_SHEET)

    title_w = min(xmax - xmin, 58.0 * s)
    x0 = xmax - title_w
    rows = [
        (PROJECT_TITLE, 0.85 * s),
        (
            f"ENTERED {params.clear_span_m:g} x {params.clear_height_m:g} m, FILL "
            f"{params.cushion_m:g} m   CONFIG {g.config_id}   (ALL DIMENSIONS IN mm)",
            0.7 * s,
        ),
        (
            f"{g.concrete_grade_resolved} / {params.steel_grade.value}   t {g.thickness_mm:g}   "
            f"HAUNCH {g.haunch_mm:g}   BARREL {g.barrel_length_mm:g}",
            0.7 * s,
        ),
        (f"RUN: {run_id or '-'}   DATE: {drawing_date.isoformat()}   SCALE: N.T.S.   SHEET 1 OF 1", 0.7 * s),
        (CAVEAT, 0.75 * s),
    ]
    row_h = title_h / len(rows)
    _polyline(msp, [(x0, ymin), (xmax, ymin), (xmax, ymin + title_h), (x0, ymin + title_h)], layer=LAYER_SHEET)
    for index in range(1, len(rows)):
        y = ymin + index * row_h
        msp.add_line((x0, y), (xmax, y), dxfattribs={"layer": LAYER_SHEET})
    for index, (text_row, height) in enumerate(rows):
        row_top = ymin + title_h - index * row_h
        _text(msp, text_row, (x0 + 0.8 * s, row_top - row_h + 0.5 * s), height)
