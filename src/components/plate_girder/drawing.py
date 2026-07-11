"""GA drawing generator — hand-validated parametric ezdxf template.

    from components.plate_girder.drawing import generate_ga
    paths = generate_ga(params, geometry, out_dir, run_id=run_id)
    # writes out_dir/"ga.dxf" and out_dir/"ga.svg"
    # returns {"ga_dxf": Path, "ga_svg": Path}

Every dimension value comes from `PlateGirderGeometry` — the same source the calc
uses — so calc-vs-drawing consistency is structural. The SVG is rendered by the
shared ezdxf SVGBackend (`drawing.svg_render.render_svg`) from the very document
written to ga.dxf. HAND-WRITTEN parametric template — never LLM CAD.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import ezdxf
from ezdxf.document import Drawing
from ezdxf.enums import TextEntityAlignment
from ezdxf.layouts import Modelspace

from components.plate_girder.params import PlateGirderGeometry, PlateGirderParams
from drawing.svg_render import render_svg

GA_DXF_NAME = "ga.dxf"
GA_SVG_NAME = "ga.svg"

LAYER_OUTLINE = "OUTLINE"
LAYER_DIM = "DIM"
LAYER_TEXT = "TEXT"
LAYER_HATCH = "HATCH"
LAYER_CL = "CL"
LAYER_HIDDEN = "HIDDEN"
LAYER_SHEET = "SHEET"
DIMSTYLE_PG = "PG"

_LAYERS = (
    (LAYER_OUTLINE, 7, None, 50),
    (LAYER_DIM, 1, None, 18),
    (LAYER_TEXT, 7, None, 25),
    (LAYER_HATCH, 8, None, 13),
    (LAYER_CL, 4, "CENTER", 15),
    (LAYER_HIDDEN, 8, "DASHED", 18),
    (LAYER_SHEET, 7, None, 35),
)

PROJECT_TITLE = "WELDED STEEL PLATE GIRDER - GENERAL ARRANGEMENT"
LOADING_NOTE = "DESIGN & PROOF CHECK PER IRS STEEL BRIDGE CODE / IS 800 / IR BRIDGE RULES"

Point = tuple[float, float]


class InvalidGeometryError(ValueError):
    """Raised when the girder geometry is impossible or internally inconsistent."""


def _validate(geometry: PlateGirderGeometry) -> None:
    for name, value in (
        ("span", geometry.span_mm),
        ("web depth", geometry.web_depth_mm),
        ("web thickness", geometry.web_thickness_mm),
        ("flange width", geometry.flange_width_mm),
        ("flange thickness", geometry.flange_thickness_mm),
        ("overall depth", geometry.overall_depth_mm),
    ):
        if value <= 0:
            raise InvalidGeometryError(f"{name} must be positive, got {value:g} mm")
    expected = geometry.web_depth_mm + 2.0 * geometry.flange_thickness_mm
    if abs(geometry.overall_depth_mm - expected) > 1.0:
        raise InvalidGeometryError(
            f"overall depth {geometry.overall_depth_mm:g} mm is inconsistent with web "
            f"depth + 2 x flange thickness = {expected:g} mm"
        )
    if geometry.flange_width_mm < geometry.web_thickness_mm:
        raise InvalidGeometryError(
            f"flange width {geometry.flange_width_mm:g} mm is narrower than the web "
            f"thickness {geometry.web_thickness_mm:g} mm"
        )
    if geometry.overall_depth_mm >= geometry.span_mm:
        raise InvalidGeometryError(
            f"overall depth {geometry.overall_depth_mm:g} mm is not less than the span "
            f"{geometry.span_mm:g} mm"
        )


def generate_ga(
    params: PlateGirderParams,
    geometry: PlateGirderGeometry,
    out_dir: Path,
    run_id: str | None = None,
    *,
    drawing_date: dt.date | None = None,
) -> dict[str, Path]:
    """Generate the GA sheet as ga.dxf + ga.svg inside ``out_dir``."""
    _validate(geometry)
    doc = _build_sheet(params, geometry, run_id, drawing_date or dt.date.today())

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dxf_path = out_dir / GA_DXF_NAME
    doc.saveas(dxf_path)
    svg_path = out_dir / GA_SVG_NAME
    svg_path.write_text(render_svg(doc), encoding="utf-8")
    return {"ga_dxf": dxf_path, "ga_svg": svg_path}


def _build_sheet(
    params: PlateGirderParams,
    geometry: PlateGirderGeometry,
    run_id: str | None,
    drawing_date: dt.date,
) -> Drawing:
    span = geometry.span_mm
    overall = geometry.overall_depth_mm
    t = max(50.0, max(span, overall) / 40.0)

    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 4  # mm
    doc.header["$MEASUREMENT"] = 1
    doc.header["$LTSCALE"] = round(1.5 * t, 1)
    for name, color, linetype, lineweight in _LAYERS:
        attribs = {"color": color, "lineweight": lineweight}
        if linetype:
            attribs["linetype"] = linetype
        doc.layers.add(name, **attribs)
    _add_dimstyle(doc, t)

    msp = doc.modelspace()
    _draw_elevation(msp, geometry, t)
    _draw_section(msp, geometry, t, section_cx=span / 2.0, section_base_y=-(overall + 16.0 * t))
    _draw_frame_and_title(msp, geometry, params, run_id, drawing_date, t)
    return doc


def _add_dimstyle(doc: Drawing, t: float) -> None:
    style = doc.dimstyles.duplicate_entry("EZDXF", DIMSTYLE_PG)
    style.dxf.dimlfac = 1.0
    style.dxf.dimtxt = t
    style.dxf.dimasz = round(0.75 * t, 1)
    style.dxf.dimexe = round(0.5 * t, 1)
    style.dxf.dimexo = round(0.35 * t, 1)
    style.dxf.dimgap = round(0.25 * t, 1)
    style.dxf.dimdec = 0
    style.dxf.dimtad = 1


def _text(msp: Modelspace, content: str, at: Point, height: float,
          align: TextEntityAlignment = TextEntityAlignment.LEFT) -> None:
    entity = msp.add_text(content, height=height, dxfattribs={"layer": LAYER_TEXT})
    entity.set_placement(at, align=align)


def _outline(msp: Modelspace, points: list[Point]) -> None:
    msp.add_lwpolyline(points, close=True, dxfattribs={"layer": LAYER_OUTLINE})


def _hatch(msp: Modelspace, points: list[Point], scale: float) -> None:
    hatch = msp.add_hatch(dxfattribs={"layer": LAYER_HATCH})
    hatch.set_pattern_fill("ANSI31", scale=scale)
    hatch.paths.add_polyline_path(points, is_closed=True)


def _dim(msp: Modelspace, *, base: Point, p1: Point, p2: Point, angle: float = 0.0) -> None:
    dimension = msp.add_linear_dim(
        base=base, p1=p1, p2=p2, angle=angle,
        dimstyle=DIMSTYLE_PG, dxfattribs={"layer": LAYER_DIM},
    )
    dimension.render()


def _draw_elevation(msp: Modelspace, g: PlateGirderGeometry, t: float) -> None:
    """ELEVATION — the girder over its span, with intermediate stiffeners."""
    span = g.span_mm
    overall = g.overall_depth_mm
    tf = g.flange_thickness_mm
    hatch_scale = max(1.0, 0.4 * t)

    # girder outline (overall envelope) + flange lines
    _outline(msp, [(0.0, 0.0), (span, 0.0), (span, overall), (0.0, overall)])
    msp.add_line((0.0, tf), (span, tf), dxfattribs={"layer": LAYER_OUTLINE})
    msp.add_line((0.0, overall - tf), (span, overall - tf), dxfattribs={"layer": LAYER_OUTLINE})

    # intermediate transverse stiffeners
    spacing = g.stiffener_spacing_mm
    x = spacing
    while x < span - 1e-6:
        msp.add_line((x, tf), (x, overall - tf), dxfattribs={"layer": LAYER_HIDDEN})
        x += spacing

    # bearing centre lines at the supports
    for bx in (0.0, span):
        msp.add_line((bx, -3.0 * t), (bx, overall + 2.0 * t), dxfattribs={"layer": LAYER_CL})

    off1 = 4.0 * t
    off2 = 9.0 * t
    # span (principal) — bottom
    _dim(msp, base=(span / 2.0, -off2), p1=(0.0, 0.0), p2=(span, 0.0))
    # overall depth — left
    _dim(msp, base=(-off1, overall / 2.0), p1=(0.0, 0.0), p2=(0.0, overall), angle=90)

    _text(msp, "ELEVATION  (SCALE: N.T.S.)", (span / 2.0, overall + 3.0 * t),
          1.1 * t, TextEntityAlignment.MIDDLE_CENTER)


def _draw_section(
    msp: Modelspace, g: PlateGirderGeometry, t: float, *, section_cx: float, section_base_y: float
) -> None:
    """SECTION — the welded I cross-section with dimension chains."""
    dw = g.web_depth_mm
    tw = g.web_thickness_mm
    bf = g.flange_width_mm
    tf = g.flange_thickness_mm
    overall = g.overall_depth_mm
    cx = section_cx
    y0 = section_base_y
    hatch_scale = max(1.0, 0.4 * t)

    bottom = [(cx - bf / 2.0, y0), (cx + bf / 2.0, y0), (cx + bf / 2.0, y0 + tf), (cx - bf / 2.0, y0 + tf)]
    web = [(cx - tw / 2.0, y0 + tf), (cx + tw / 2.0, y0 + tf),
           (cx + tw / 2.0, y0 + tf + dw), (cx - tw / 2.0, y0 + tf + dw)]
    top = [(cx - bf / 2.0, y0 + tf + dw), (cx + bf / 2.0, y0 + tf + dw),
           (cx + bf / 2.0, y0 + overall), (cx - bf / 2.0, y0 + overall)]
    for shape in (bottom, web, top):
        _outline(msp, shape)
        _hatch(msp, shape, hatch_scale)

    off1 = 4.0 * t
    off2 = 9.0 * t
    # overall depth — right of the section
    _dim(msp, base=(cx + bf / 2.0 + off2, y0 + overall / 2.0),
         p1=(cx + bf / 2.0, y0), p2=(cx + bf / 2.0, y0 + overall), angle=90)
    # web (clear) depth — right of the section, inner
    _dim(msp, base=(cx + bf / 2.0 + off1, y0 + tf + dw / 2.0),
         p1=(cx + tw / 2.0, y0 + tf), p2=(cx + tw / 2.0, y0 + tf + dw), angle=90)
    # flange width — below the section
    _dim(msp, base=(cx, y0 - off1), p1=(cx - bf / 2.0, y0), p2=(cx + bf / 2.0, y0))
    # flange thickness — left of the section, low
    _dim(msp, base=(cx - bf / 2.0 - off1, y0 + tf / 2.0),
         p1=(cx - bf / 2.0, y0), p2=(cx - bf / 2.0, y0 + tf), angle=90)
    # web thickness — top of the section
    _dim(msp, base=(cx, y0 + overall + off1),
         p1=(cx - tw / 2.0, y0 + overall), p2=(cx + tw / 2.0, y0 + overall))

    _text(msp, "SECTION AT MID-SPAN  (SCALE: N.T.S.)", (cx, y0 + overall + off2),
          1.1 * t, TextEntityAlignment.MIDDLE_CENTER)


def _draw_frame_and_title(
    msp: Modelspace, g: PlateGirderGeometry, params: PlateGirderParams,
    run_id: str | None, drawing_date: dt.date, t: float,
) -> None:
    content = ezdxf.bbox.extents(msp)
    margin = 4.0 * t
    title_h = 10.0 * t
    xmin = content.extmin.x - margin
    xmax = content.extmax.x + margin
    ymax = content.extmax.y + margin
    ymin = content.extmin.y - margin - title_h
    msp.add_lwpolyline(
        [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)],
        close=True, dxfattribs={"layer": LAYER_SHEET},
    )
    title_w = min(xmax - xmin, 52.0 * t)
    x0 = xmax - title_w
    rows = [
        (PROJECT_TITLE, 0.9 * t),
        (
            f"SPAN {g.span_mm:g} x OVERALL DEPTH {g.overall_depth_mm:g}  "
            "(ALL DIMENSIONS IN mm)",
            0.7 * t,
        ),
        (
            f"WEB {g.web_depth_mm:g} x {g.web_thickness_mm:g}   "
            f"FLANGE {g.flange_width_mm:g} x {g.flange_thickness_mm:g}   "
            f"{params.number_of_girders} GIRDERS @ {g.girder_spacing_mm:g} c/c",
            0.7 * t,
        ),
        (f"STEEL {params.steel_grade}   {params.deck_type.upper()}-TYPE   LOADING: {LOADING_NOTE}", 0.7 * t),
        (f"RUN: {run_id or '-'}   DATE: {drawing_date.isoformat()}", 0.7 * t),
        ("FOR DEMONSTRATION - NOT FOR CONSTRUCTION   SCALE: N.T.S.   SHEET 1 OF 1", 0.7 * t),
    ]
    row_h = title_h / len(rows)
    msp.add_lwpolyline(
        [(x0, ymin), (xmax, ymin), (xmax, ymin + title_h), (x0, ymin + title_h)],
        close=True, dxfattribs={"layer": LAYER_SHEET},
    )
    for index in range(1, len(rows)):
        y = ymin + index * row_h
        msp.add_line((x0, y), (xmax, y), dxfattribs={"layer": LAYER_SHEET})
    for index, (text_row, height) in enumerate(rows):
        row_top = ymin + title_h - index * row_h
        _text(msp, text_row, (x0 + 0.8 * t, row_top - row_h + 0.55 * t), height)
