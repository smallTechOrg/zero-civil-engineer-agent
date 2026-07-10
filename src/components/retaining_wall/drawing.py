"""GA drawing generator — hand-validated parametric ezdxf template.

    from components.retaining_wall.drawing import generate_ga
    paths = generate_ga(params, geometry, out_dir, run_id=run_id)
    # writes out_dir/"ga.dxf" and out_dir/"ga.svg"
    # returns {"ga_dxf": Path, "ga_svg": Path}

Every dimension value comes from `RetainingWallGeometry` — the same source the
calc uses — so calc-vs-drawing consistency is structural. The SVG is rendered by
the shared ezdxf SVGBackend (`drawing.svg_render.render_svg`) from the very
document written to ga.dxf. HAND-WRITTEN parametric template — never LLM CAD.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import ezdxf
from ezdxf.document import Drawing
from ezdxf.enums import TextEntityAlignment
from ezdxf.layouts import Modelspace

from components.retaining_wall.params import RetainingWallGeometry, RetainingWallParams
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
DIMSTYLE_RW = "RW"

_LAYERS = (
    (LAYER_OUTLINE, 7, None, 50),
    (LAYER_DIM, 1, None, 18),
    (LAYER_TEXT, 7, None, 25),
    (LAYER_HATCH, 8, None, 13),
    (LAYER_CL, 4, "CENTER", 15),
    (LAYER_HIDDEN, 8, "DASHED", 18),
    (LAYER_SHEET, 7, None, 35),
)

PROJECT_TITLE = "RCC CANTILEVER RETAINING WALL - GENERAL ARRANGEMENT"
LOADING_NOTE = "DESIGN & PROOF CHECK PER IRS CBC / IS 456 / IR BRIDGE RULES"


class InvalidGeometryError(ValueError):
    """Raised when the wall geometry is impossible or internally inconsistent."""


Point = tuple[float, float]


def _validate(geometry: RetainingWallGeometry) -> None:
    for name, value in (
        ("total height", geometry.total_height_mm),
        ("base width", geometry.base_width_mm),
        ("base thickness", geometry.base_thickness_mm),
        ("stem base thickness", geometry.stem_base_thickness_mm),
        ("stem top thickness", geometry.stem_top_thickness_mm),
        ("toe length", geometry.toe_length_mm),
        ("heel length", geometry.heel_length_mm),
    ):
        if value <= 0:
            raise InvalidGeometryError(f"{name} must be positive, got {value:g} mm")
    expected_b = geometry.toe_length_mm + geometry.stem_base_thickness_mm + geometry.heel_length_mm
    if abs(geometry.base_width_mm - expected_b) > 1.0:
        raise InvalidGeometryError(
            f"base width {geometry.base_width_mm:g} mm is inconsistent with toe + "
            f"stem base + heel = {expected_b:g} mm"
        )
    if geometry.base_thickness_mm >= geometry.total_height_mm:
        raise InvalidGeometryError(
            f"base thickness {geometry.base_thickness_mm:g} mm is not less than the "
            f"total height {geometry.total_height_mm:g} mm"
        )
    if geometry.stem_top_thickness_mm > geometry.stem_base_thickness_mm + 1.0:
        raise InvalidGeometryError(
            f"stem top {geometry.stem_top_thickness_mm:g} mm exceeds the stem base "
            f"{geometry.stem_base_thickness_mm:g} mm"
        )


def generate_ga(
    params: RetainingWallParams,
    geometry: RetainingWallGeometry,
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
    params: RetainingWallParams,
    geometry: RetainingWallGeometry,
    run_id: str | None,
    drawing_date: dt.date,
) -> Drawing:
    b = geometry.base_width_mm
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
    _draw_section(msp, geometry, t)
    _draw_plan(msp, geometry, t, plan_top_y=-(6.0 * t))
    _draw_frame_and_title(msp, geometry, params, run_id, drawing_date, t)
    return doc


def _add_dimstyle(doc: Drawing, t: float) -> None:
    style = doc.dimstyles.duplicate_entry("EZDXF", DIMSTYLE_RW)
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
        dimstyle=DIMSTYLE_RW, dxfattribs={"layer": LAYER_DIM},
    )
    dimension.render()


def _draw_section(msp: Modelspace, g: RetainingWallGeometry, t: float) -> None:
    """SECTION A-A — the wall cross-section (elevation) with dimension chains."""
    b = g.base_width_mm
    h = g.total_height_mm
    db = g.base_thickness_mm
    lt = g.toe_length_mm
    ts_base = g.stem_base_thickness_mm
    ts_top = g.stem_top_thickness_mm
    key = g.key_depth_mm
    delta = ts_base - ts_top
    x_backface = lt + ts_base
    hatch_scale = max(1.0, 0.4 * t)

    # base slab
    base_pts = [(0.0, 0.0), (b, 0.0), (b, db), (0.0, db)]
    _outline(msp, base_pts)
    _hatch(msp, base_pts, hatch_scale)

    # shear key
    if key > 0:
        key_pts = [(lt, -key), (lt + ts_base, -key), (lt + ts_base, 0.0), (lt, 0.0)]
        _outline(msp, key_pts)
        _hatch(msp, key_pts, hatch_scale)

    # stem (vertical back face at x_backface, battered front face)
    stem_pts = [(lt, db), (x_backface, db), (x_backface, h), (lt + delta, h)]
    _outline(msp, stem_pts)
    _hatch(msp, stem_pts, hatch_scale)

    # backfill surface line (over the heel) + ground line in front (toe)
    msp.add_line((x_backface, h), (b, h), dxfattribs={"layer": LAYER_HIDDEN})
    msp.add_line((0.0, db), (lt, db), dxfattribs={"layer": LAYER_HIDDEN})

    # dimensions
    off1 = 3.0 * t
    off2 = 7.0 * t
    # total height (principal) — left
    _dim(msp, base=(-off2, h / 2.0), p1=(0.0, 0.0), p2=(0.0, h), angle=90)
    # base thickness — right, low
    _dim(msp, base=(b + off1, db / 2.0), p1=(b, 0.0), p2=(b, db), angle=90)
    # base width (principal) — bottom
    _dim(msp, base=(b / 2.0, -off2 - (key if key else 0.0)), p1=(0.0, 0.0), p2=(b, 0.0))
    # toe / heel — bottom, higher row
    _dim(msp, base=(lt / 2.0, -off1 - (key if key else 0.0)), p1=(0.0, 0.0), p2=(lt, 0.0))
    _dim(msp, base=((x_backface + b) / 2.0, -off1 - (key if key else 0.0)),
         p1=(x_backface, 0.0), p2=(b, 0.0))
    # stem base thickness — measured at the base (front-bottom to vertical back)
    _dim(msp, base=(x_backface - ts_base / 2.0, h + off1),
         p1=(lt, db), p2=(x_backface, db))
    # stem top thickness — measured at the top (front-top to vertical back)
    _dim(msp, base=(x_backface - ts_top / 2.0, h + off2),
         p1=(lt + delta, h), p2=(x_backface, h))
    # key depth — right of key
    if key > 0:
        _dim(msp, base=(lt + ts_base + off1, -key / 2.0), p1=(lt + ts_base, -key),
             p2=(lt + ts_base, 0.0), angle=90)

    _text(msp, "SECTION A-A  (SCALE: N.T.S.)", (b / 2.0, h + off2 + 2.5 * t),
          1.1 * t, TextEntityAlignment.MIDDLE_CENTER)


def _draw_plan(msp: Modelspace, g: RetainingWallGeometry, t: float, plan_top_y: float) -> None:
    """PLAN — a 1 m run of the base with the stem footprint (dashed)."""
    b = g.base_width_mm
    run = 1000.0
    lt = g.toe_length_mm
    ts_base = g.stem_base_thickness_mm
    y0 = plan_top_y - run
    y1 = plan_top_y
    _outline(msp, [(0.0, y0), (b, y0), (b, y1), (0.0, y1)])
    for x in (lt, lt + ts_base):
        msp.add_line((x, y0), (x, y1), dxfattribs={"layer": LAYER_HIDDEN})
    _dim(msp, base=(b / 2.0, y0 - 3.0 * t), p1=(0.0, y0), p2=(b, y0))
    _text(msp, "PLAN - 1 m RUN  (SCALE: N.T.S.)", (b / 2.0, y1 + 1.0 * t),
          0.9 * t, TextEntityAlignment.LEFT)


def _draw_frame_and_title(
    msp: Modelspace, g: RetainingWallGeometry, params: RetainingWallParams,
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
            f"RETAINED HEIGHT {g.total_height_mm:g} x BASE WIDTH {g.base_width_mm:g}  "
            "(ALL DIMENSIONS IN mm)",
            0.7 * t,
        ),
        (
            f"{params.concrete_grade.value} / {params.steel_grade.value}   "
            f"SBC {params.safe_bearing_capacity_kn_m2:g} kN/m2   phi {params.backfill_friction_angle_deg:g} deg",
            0.7 * t,
        ),
        (f"LOADING: {LOADING_NOTE}", 0.7 * t),
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
