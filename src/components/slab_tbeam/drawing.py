"""GA drawing generator — hand-validated parametric ezdxf template.

    from components.slab_tbeam.drawing import generate_ga
    paths = generate_ga(params, geometry, out_dir, run_id=run_id)
    # writes out_dir/"ga.dxf" and out_dir/"ga.svg"
    # returns {"ga_dxf": Path, "ga_svg": Path}

Every dimension value comes from `SlabTbeamGeometry` — the same source the calc
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

from components.slab_tbeam.params import SlabTbeamGeometry, SlabTbeamParams
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
DIMSTYLE_ST = "ST"

_LAYERS = (
    (LAYER_OUTLINE, 7, None, 50),
    (LAYER_DIM, 1, None, 18),
    (LAYER_TEXT, 7, None, 25),
    (LAYER_HATCH, 8, None, 13),
    (LAYER_CL, 4, "CENTER", 15),
    (LAYER_HIDDEN, 8, "DASHED", 18),
    (LAYER_SHEET, 7, None, 35),
)

PROJECT_TITLE = "RCC SLAB / T-BEAM DECK - GENERAL ARRANGEMENT"
LOADING_NOTE = "DESIGN & PROOF CHECK PER IRS CBC / IS 456 / IR BRIDGE RULES (25t LOADING-2008)"


class InvalidGeometryError(ValueError):
    """Raised when the deck geometry is impossible or internally inconsistent."""


Point = tuple[float, float]


def _validate(geometry: SlabTbeamGeometry) -> None:
    for name, value in (
        ("span", geometry.span_mm),
        ("overall depth", geometry.overall_depth_mm),
        ("slab depth", geometry.slab_depth_mm),
        ("deck width", geometry.deck_width_mm),
    ):
        if value <= 0:
            raise InvalidGeometryError(f"{name} must be positive, got {value:g} mm")
    if geometry.overall_depth_mm >= geometry.span_mm:
        raise InvalidGeometryError(
            f"overall depth {geometry.overall_depth_mm:g} mm is not less than the span "
            f"{geometry.span_mm:g} mm"
        )
    if geometry.deck_type == "t_beam":
        for name, value in (("rib width", geometry.rib_width_mm), ("rib depth", geometry.rib_depth_mm)):
            if value <= 0:
                raise InvalidGeometryError(f"{name} must be positive for a T-beam, got {value:g} mm")
        expected = geometry.slab_depth_mm + geometry.rib_depth_mm
        if abs(geometry.overall_depth_mm - expected) > 1.0:
            raise InvalidGeometryError(
                f"overall depth {geometry.overall_depth_mm:g} mm != slab + rib "
                f"{expected:g} mm"
            )
    elif abs(geometry.overall_depth_mm - geometry.slab_depth_mm) > 1.0:
        raise InvalidGeometryError(
            f"solid slab overall depth {geometry.overall_depth_mm:g} mm must equal the "
            f"slab depth {geometry.slab_depth_mm:g} mm"
        )


def generate_ga(
    params: SlabTbeamParams,
    geometry: SlabTbeamGeometry,
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
    params: SlabTbeamParams,
    geometry: SlabTbeamGeometry,
    run_id: str | None,
    drawing_date: dt.date,
) -> Drawing:
    span = geometry.span_mm
    overall = geometry.overall_depth_mm
    deck = geometry.deck_width_mm
    t = max(50.0, max(span, deck, overall) / 45.0)

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
    _draw_elevation(msp, geometry, t, base_y=-(overall + 14.0 * t))
    _draw_frame_and_title(msp, geometry, params, run_id, drawing_date, t)
    return doc


def _add_dimstyle(doc: Drawing, t: float) -> None:
    style = doc.dimstyles.duplicate_entry("EZDXF", DIMSTYLE_ST)
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
        dimstyle=DIMSTYLE_ST, dxfattribs={"layer": LAYER_DIM},
    )
    dimension.render()


def _draw_section(msp: Modelspace, g: SlabTbeamGeometry, t: float) -> None:
    """SECTION A-A — the deck cross-section (transverse) with dimension chains."""
    deck = g.deck_width_mm
    overall = g.overall_depth_mm
    hatch_scale = max(1.0, 0.4 * t)
    off1 = 3.0 * t
    off2 = 7.0 * t

    if g.deck_type == "solid_slab":
        slab_pts = [(0.0, 0.0), (deck, 0.0), (deck, overall), (0.0, overall)]
        _outline(msp, slab_pts)
        _hatch(msp, slab_pts, hatch_scale)
    else:
        rib_depth = g.rib_depth_mm
        slab = g.slab_depth_mm
        rib_w = g.rib_width_mm
        n = g.number_of_girders
        spacing = deck / n
        flange_pts = [(0.0, rib_depth), (deck, rib_depth), (deck, overall), (0.0, overall)]
        _outline(msp, flange_pts)
        _hatch(msp, flange_pts, hatch_scale)
        for i in range(n):
            xc = spacing * (i + 0.5)
            rib_pts = [
                (xc - rib_w / 2.0, 0.0), (xc + rib_w / 2.0, 0.0),
                (xc + rib_w / 2.0, rib_depth), (xc - rib_w / 2.0, rib_depth),
            ]
            _outline(msp, rib_pts)
            _hatch(msp, rib_pts, hatch_scale)
        # slab depth (flange) on the right
        _dim(msp, base=(deck + off1, overall - slab / 2.0),
             p1=(deck, rib_depth), p2=(deck, overall), angle=90)
        # rib width on the first rib
        xc0 = spacing * 0.5
        _dim(msp, base=(xc0, overall + off1), p1=(xc0 - rib_w / 2.0, rib_depth), p2=(xc0 + rib_w / 2.0, rib_depth))

    # overall depth (principal) — left
    _dim(msp, base=(-off2, overall / 2.0), p1=(0.0, 0.0), p2=(0.0, overall), angle=90)
    # deck width — bottom
    _dim(msp, base=(deck / 2.0, -off2), p1=(0.0, 0.0), p2=(deck, 0.0))

    _text(msp, "SECTION A-A  (SCALE: N.T.S.)", (deck / 2.0, overall + off2 + 2.5 * t),
          1.1 * t, TextEntityAlignment.MIDDLE_CENTER)


def _draw_elevation(msp: Modelspace, g: SlabTbeamGeometry, t: float, base_y: float) -> None:
    """ELEVATION — the simply-supported deck over its span."""
    span = g.span_mm
    overall = g.overall_depth_mm
    y0 = base_y
    y1 = base_y + overall
    _outline(msp, [(0.0, y0), (span, y0), (span, y1), (0.0, y1)])
    # bearing marks at the supports
    bh = 1.5 * t
    for x in (0.0, span):
        msp.add_lwpolyline(
            [(x - bh, y0 - bh), (x + bh, y0 - bh), (x, y0)],
            close=True, dxfattribs={"layer": LAYER_OUTLINE},
        )
    # span (principal) — bottom
    _dim(msp, base=(span / 2.0, y0 - 6.0 * t), p1=(0.0, y0), p2=(span, y0))
    # overall depth — right
    _dim(msp, base=(span + 4.0 * t, y0 + overall / 2.0), p1=(span, y0), p2=(span, y1), angle=90)
    _text(msp, "ELEVATION  (SCALE: N.T.S.)", (span / 2.0, y1 + 1.5 * t),
          1.0 * t, TextEntityAlignment.MIDDLE_CENTER)


def _draw_frame_and_title(
    msp: Modelspace, g: SlabTbeamGeometry, params: SlabTbeamParams,
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
    deck_label = "SOLID RCC SLAB" if g.deck_type == "solid_slab" else "RCC T-BEAM DECK"
    title_w = min(xmax - xmin, 52.0 * t)
    x0 = xmax - title_w
    rows = [
        (PROJECT_TITLE, 0.9 * t),
        (
            f"{deck_label}   SPAN {g.span_mm:g} x OVERALL DEPTH {g.overall_depth_mm:g}  "
            "(ALL DIMENSIONS IN mm)",
            0.7 * t,
        ),
        (
            f"{params.concrete_grade.value} / {params.steel_grade.value}   "
            f"DECK WIDTH {g.deck_width_mm:g} mm   {params.gauge.value} {params.loading_standard.value}",
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
