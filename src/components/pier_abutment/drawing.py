"""GA drawing generator — hand-validated parametric ezdxf template.

    from components.pier_abutment.drawing import generate_ga
    paths = generate_ga(params, geometry, out_dir, run_id=run_id)
    # writes out_dir/"ga.dxf" and out_dir/"ga.svg"
    # returns {"ga_dxf": Path, "ga_svg": Path}

Draws a longitudinal ELEVATION (footing + pier/stem + cap), a transverse SECTION,
and a FOUNDATION PLAN with an RDSO-style title block. Every dimension value comes
from `PierAbutmentGeometry` — the same source the calc uses — so calc-vs-drawing
consistency is structural. The SVG is rendered by the shared ezdxf SVGBackend
(`drawing.svg_render.render_svg`) from the very document written to ga.dxf.
HAND-WRITTEN parametric template — never LLM CAD.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import ezdxf
from ezdxf.document import Drawing
from ezdxf.enums import TextEntityAlignment
from ezdxf.layouts import Modelspace

from components.pier_abutment.params import PierAbutmentGeometry, PierAbutmentParams
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
DIMSTYLE_PA = "PA"

_LAYERS = (
    (LAYER_OUTLINE, 7, None, 50),
    (LAYER_DIM, 1, None, 18),
    (LAYER_TEXT, 7, None, 25),
    (LAYER_HATCH, 8, None, 13),
    (LAYER_CL, 4, "CENTER", 15),
    (LAYER_HIDDEN, 8, "DASHED", 18),
    (LAYER_SHEET, 7, None, 35),
)

PROJECT_TITLE = "PIER / ABUTMENT SUBSTRUCTURE - GENERAL ARRANGEMENT"
LOADING_NOTE = "DESIGN & PROOF CHECK PER IRS BRIDGE SUBSTRUCTURE & FOUNDATION CODE / IRS BRIDGE RULES"


class InvalidGeometryError(ValueError):
    """Raised when the substructure geometry is impossible or internally inconsistent."""


Point = tuple[float, float]


def _validate(geometry: PierAbutmentGeometry) -> None:
    for name, value in (
        ("total height", geometry.total_height_mm),
        ("pier width", geometry.pier_width_mm),
        ("pier length", geometry.pier_length_mm),
        ("cap thickness", geometry.cap_thickness_mm),
        ("cap width", geometry.cap_width_mm),
        ("footing length", geometry.footing_length_mm),
        ("footing width", geometry.footing_width_mm),
        ("footing thickness", geometry.footing_thickness_mm),
    ):
        if value <= 0:
            raise InvalidGeometryError(f"{name} must be positive, got {value:g} mm")
    shaft = geometry.total_height_mm - geometry.footing_thickness_mm - geometry.cap_thickness_mm
    if shaft <= 0:
        raise InvalidGeometryError(
            f"footing {geometry.footing_thickness_mm:g} mm + cap {geometry.cap_thickness_mm:g} mm "
            f"leave no positive pier shaft within the total height {geometry.total_height_mm:g} mm"
        )
    if geometry.footing_length_mm < geometry.pier_width_mm - 1.0:
        raise InvalidGeometryError(
            f"footing length {geometry.footing_length_mm:g} mm is narrower than the pier "
            f"width {geometry.pier_width_mm:g} mm"
        )
    if geometry.footing_width_mm < geometry.pier_length_mm - 1.0:
        raise InvalidGeometryError(
            f"footing width {geometry.footing_width_mm:g} mm is narrower than the pier "
            f"length {geometry.pier_length_mm:g} mm"
        )


def generate_ga(
    params: PierAbutmentParams,
    geometry: PierAbutmentGeometry,
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
    params: PierAbutmentParams,
    geometry: PierAbutmentGeometry,
    run_id: str | None,
    drawing_date: dt.date,
) -> Drawing:
    b = geometry.footing_length_mm
    h = geometry.total_height_mm
    t = max(50.0, max(b, h) / 40.0)

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
    _draw_plan(msp, geometry, t, plan_top_y=-(7.0 * t))
    _draw_frame_and_title(msp, geometry, params, run_id, drawing_date, t)
    return doc


def _add_dimstyle(doc: Drawing, t: float) -> None:
    style = doc.dimstyles.duplicate_entry("EZDXF", DIMSTYLE_PA)
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
        dimstyle=DIMSTYLE_PA, dxfattribs={"layer": LAYER_DIM},
    )
    dimension.render()


def _draw_elevation(msp: Modelspace, g: PierAbutmentGeometry, t: float) -> None:
    """ELEVATION — the longitudinal profile: footing, pier/stem, cap."""
    b = g.footing_length_mm
    h = g.total_height_mm
    df = g.footing_thickness_mm
    ct = g.cap_thickness_mm
    pw = g.pier_width_mm
    cw = g.cap_width_mm
    shaft_top = h - ct
    hatch_scale = max(1.0, 0.4 * t)

    x_pier0 = (b - pw) / 2.0
    x_pier1 = (b + pw) / 2.0
    x_cap0 = (b - cw) / 2.0
    x_cap1 = (b + cw) / 2.0

    # footing
    footing_pts = [(0.0, 0.0), (b, 0.0), (b, df), (0.0, df)]
    _outline(msp, footing_pts)
    _hatch(msp, footing_pts, hatch_scale)
    # pier / stem
    pier_pts = [(x_pier0, df), (x_pier1, df), (x_pier1, shaft_top), (x_pier0, shaft_top)]
    _outline(msp, pier_pts)
    _hatch(msp, pier_pts, hatch_scale)
    # cap
    cap_pts = [(x_cap0, shaft_top), (x_cap1, shaft_top), (x_cap1, h), (x_cap0, h)]
    _outline(msp, cap_pts)
    _hatch(msp, cap_pts, hatch_scale)

    # centre line
    msp.add_line((b / 2.0, -1.5 * t), (b / 2.0, h + 2.0 * t), dxfattribs={"layer": LAYER_CL})

    off1 = 3.0 * t
    off2 = 7.0 * t
    # total height (principal) — left
    _dim(msp, base=(-off2, h / 2.0), p1=(0.0, 0.0), p2=(0.0, h), angle=90)
    # footing thickness — right
    _dim(msp, base=(b + off1, df / 2.0), p1=(b, 0.0), p2=(b, df), angle=90)
    # cap thickness — right
    _dim(msp, base=(b + off1, (shaft_top + h) / 2.0), p1=(b, shaft_top), p2=(b, h), angle=90)
    # footing length B (principal) — bottom
    _dim(msp, base=(b / 2.0, -off2), p1=(0.0, 0.0), p2=(b, 0.0))
    # pier width — top
    _dim(msp, base=(b / 2.0, h + off1), p1=(x_pier0, shaft_top), p2=(x_pier1, shaft_top))
    # cap width — top, higher
    _dim(msp, base=(b / 2.0, h + off2), p1=(x_cap0, h), p2=(x_cap1, h))

    _text(msp, "ELEVATION  (SCALE: N.T.S.)", (b / 2.0, h + off2 + 2.5 * t),
          1.1 * t, TextEntityAlignment.MIDDLE_CENTER)


def _draw_plan(msp: Modelspace, g: PierAbutmentGeometry, t: float, plan_top_y: float) -> None:
    """FOUNDATION PLAN — the spread footing (B x L) with the pier footprint dashed."""
    b = g.footing_length_mm  # longitudinal
    lw = g.footing_width_mm  # transverse
    pw = g.pier_width_mm
    pl = g.pier_length_mm
    y1 = plan_top_y
    y0 = plan_top_y - lw
    _outline(msp, [(0.0, y0), (b, y0), (b, y1), (0.0, y1)])
    # pier footprint (dashed)
    px0 = (b - pw) / 2.0
    px1 = (b + pw) / 2.0
    py0 = y1 - (lw + pl) / 2.0
    py1 = y1 - (lw - pl) / 2.0
    for pts in ([(px0, py0), (px1, py0)], [(px1, py0), (px1, py1)],
                [(px1, py1), (px0, py1)], [(px0, py1), (px0, py0)]):
        msp.add_line(pts[0], pts[1], dxfattribs={"layer": LAYER_HIDDEN})
    # footing length (longitudinal) — bottom
    _dim(msp, base=(b / 2.0, y0 - 3.0 * t), p1=(0.0, y0), p2=(b, y0))
    # footing width (transverse) — right
    _dim(msp, base=(b + 3.0 * t, (y0 + y1) / 2.0), p1=(b, y0), p2=(b, y1), angle=90)
    _text(msp, "FOUNDATION PLAN  (SCALE: N.T.S.)", (b / 2.0, y1 + 1.0 * t),
          0.9 * t, TextEntityAlignment.LEFT)


def _draw_frame_and_title(
    msp: Modelspace, g: PierAbutmentGeometry, params: PierAbutmentParams,
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
    kind = g.component_kind.upper()
    rows = [
        (PROJECT_TITLE, 0.9 * t),
        (
            f"{kind}  HEIGHT {g.total_height_mm:g} x FOOTING {g.footing_length_mm:g} x "
            f"{g.footing_width_mm:g}  (ALL DIMENSIONS IN mm)",
            0.7 * t,
        ),
        (
            f"{params.concrete_grade.value} / {params.steel_grade.value}   "
            f"SBC {params.safe_bearing_capacity_kn_m2:g} kN/m2   REACTION "
            f"{params.superstructure_reaction_kn:g} kN",
            0.7 * t,
        ),
        (f"LOADING: {LOADING_NOTE}", 0.6 * t),
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
