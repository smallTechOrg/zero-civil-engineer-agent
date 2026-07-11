"""Fabrication drawing generator — hand-validated parametric ezdxf template.

    from components.structural_steel_member.drawing import generate_ga
    paths = generate_ga(params, geometry, out_dir, run_id=run_id)
    # writes out_dir/"ga.dxf" and out_dir/"ga.svg"
    # returns {"ga_dxf": Path, "ga_svg": Path}

Every dimension value comes from `SteelMemberGeometry` — the same source the calc
uses — so calc-vs-drawing consistency is structural. The base fillet-weld is
annotated with a proper AWS/ISO-style **weld symbol** (leader/arrow line +
horizontal reference line + fillet-weld triangle + weld-size text + weld-all-round
circle) on a dedicated ``WELD`` layer, plus a basic GD&T flatness/datum callout on
the base plate. The SVG is rendered by the shared ezdxf SVGBackend
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

from components.structural_steel_member.params import (
    SteelMemberGeometry,
    SteelMemberParams,
)
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
LAYER_WELD = "WELD"
LAYER_GDT = "GDT"
DIMSTYLE_SSM = "SSM"

_LAYERS = (
    (LAYER_OUTLINE, 7, None, 50),
    (LAYER_DIM, 1, None, 18),
    (LAYER_TEXT, 7, None, 25),
    (LAYER_HATCH, 8, None, 13),
    (LAYER_CL, 4, "CENTER", 15),
    (LAYER_HIDDEN, 8, "DASHED", 18),
    (LAYER_SHEET, 7, None, 35),
    (LAYER_WELD, 3, None, 25),
    (LAYER_GDT, 6, None, 20),
)

PROJECT_TITLE = "FABRICATED STRUCTURAL STEEL MEMBER - GENERAL ARRANGEMENT"
LOADING_NOTE = "DESIGN & PROOF CHECK PER IS 800 (WORKING STRESS) / IS 816 (FILLET WELDS)"
_MEMBER_TITLES = {
    "bracket": "WELDED STEEL BRACKET",
    "gantry_post": "WELDED STEEL GANTRY POST",
    "ohe_mast": "WELDED STEEL OHE MAST",
}

Point = tuple[float, float]


class InvalidGeometryError(ValueError):
    """Raised when the member geometry is impossible or internally inconsistent."""


def _validate(geometry: SteelMemberGeometry) -> None:
    for name, value in (
        ("length", geometry.cantilever_length_mm),
        ("web depth", geometry.web_depth_mm),
        ("web thickness", geometry.web_thickness_mm),
        ("flange width", geometry.flange_width_mm),
        ("flange thickness", geometry.flange_thickness_mm),
        ("overall depth", geometry.overall_depth_mm),
        ("weld size", geometry.weld_size_mm),
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
    if geometry.overall_depth_mm >= geometry.cantilever_length_mm:
        raise InvalidGeometryError(
            f"overall depth {geometry.overall_depth_mm:g} mm is not less than the "
            f"cantilever length {geometry.cantilever_length_mm:g} mm"
        )


def generate_ga(
    params: SteelMemberParams,
    geometry: SteelMemberGeometry,
    out_dir: Path,
    run_id: str | None = None,
    *,
    drawing_date: dt.date | None = None,
) -> dict[str, Path]:
    """Generate the fabrication sheet as ga.dxf + ga.svg inside ``out_dir``."""
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
    params: SteelMemberParams,
    geometry: SteelMemberGeometry,
    run_id: str | None,
    drawing_date: dt.date,
) -> Drawing:
    length = geometry.cantilever_length_mm
    overall = geometry.overall_depth_mm
    t = max(30.0, max(length, overall) / 40.0)

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
    _draw_weld_symbol(msp, geometry, t)
    _draw_gdt_callout(msp, geometry, t)
    _draw_section(
        msp, geometry, t, section_cx=length / 2.0, section_base_y=-(overall + 18.0 * t)
    )
    _draw_frame_and_title(msp, geometry, params, run_id, drawing_date, t)
    return doc


def _add_dimstyle(doc: Drawing, t: float) -> None:
    style = doc.dimstyles.duplicate_entry("EZDXF", DIMSTYLE_SSM)
    style.dxf.dimlfac = 1.0
    style.dxf.dimtxt = t
    style.dxf.dimasz = round(0.75 * t, 1)
    style.dxf.dimexe = round(0.5 * t, 1)
    style.dxf.dimexo = round(0.35 * t, 1)
    style.dxf.dimgap = round(0.25 * t, 1)
    style.dxf.dimdec = 0
    style.dxf.dimtad = 1


def _text(msp: Modelspace, content: str, at: Point, height: float,
          align: TextEntityAlignment = TextEntityAlignment.LEFT,
          layer: str = LAYER_TEXT) -> None:
    entity = msp.add_text(content, height=height, dxfattribs={"layer": layer})
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
        dimstyle=DIMSTYLE_SSM, dxfattribs={"layer": LAYER_DIM},
    )
    dimension.render()


def _draw_elevation(msp: Modelspace, g: SteelMemberGeometry, t: float) -> None:
    """ELEVATION — the cantilever member along its length, base plate at the left."""
    length = g.cantilever_length_mm
    overall = g.overall_depth_mm
    tf = g.flange_thickness_mm

    # member outline (overall envelope) + flange lines
    _outline(msp, [(0.0, 0.0), (length, 0.0), (length, overall), (0.0, overall)])
    msp.add_line((0.0, tf), (length, tf), dxfattribs={"layer": LAYER_OUTLINE})
    msp.add_line((0.0, overall - tf), (length, overall - tf), dxfattribs={"layer": LAYER_OUTLINE})

    # base plate (the member welds to it at x = 0)
    bp = 2.0 * t
    msp.add_lwpolyline(
        [(-bp, -1.5 * t), (0.0, -1.5 * t), (0.0, overall + 1.5 * t), (-bp, overall + 1.5 * t)],
        close=True, dxfattribs={"layer": LAYER_OUTLINE},
    )

    # member axis centre-line
    msp.add_line((-bp, overall / 2.0), (length + 3.0 * t, overall / 2.0),
                 dxfattribs={"layer": LAYER_CL})

    # tip transverse load arrow (downward at the free end)
    tip_x = length
    msp.add_line((tip_x, overall + 6.0 * t), (tip_x, overall), dxfattribs={"layer": LAYER_DIM})
    _arrowhead(msp, tip=(tip_x, overall), back=(tip_x, overall + 1.5 * t), t=t, layer=LAYER_DIM)
    _text(msp, "P (TRANSVERSE)", (tip_x + 0.6 * t, overall + 5.0 * t), 0.9 * t)
    # axial load arrow (along the axis at the tip)
    msp.add_line((tip_x + 1.0 * t, overall / 2.0), (tip_x + 6.0 * t, overall / 2.0),
                 dxfattribs={"layer": LAYER_DIM})
    _text(msp, "N (AXIAL)", (tip_x + 1.0 * t, overall / 2.0 + 1.0 * t), 0.9 * t)

    off1 = 4.0 * t
    off2 = 9.0 * t
    # length (principal) — bottom
    _dim(msp, base=(length / 2.0, -off2), p1=(0.0, 0.0), p2=(length, 0.0))
    # overall depth — left
    _dim(msp, base=(-off1 - 2.0 * t, overall / 2.0), p1=(0.0, 0.0), p2=(0.0, overall), angle=90)

    _text(msp, "ELEVATION  (SCALE: N.T.S.)", (length / 2.0, overall + 9.0 * t),
          1.1 * t, TextEntityAlignment.MIDDLE_CENTER)


def _arrowhead(msp: Modelspace, *, tip: Point, back: Point, t: float, layer: str) -> None:
    """A small filled triangular arrowhead pointing at ``tip`` from ``back``."""
    dx = tip[0] - back[0]
    dy = tip[1] - back[1]
    length = (dx**2 + dy**2) ** 0.5 or 1.0
    ux, uy = dx / length, dy / length
    px, py = -uy, ux  # perpendicular
    half = 0.35 * t
    b1 = (back[0] + px * half, back[1] + py * half)
    b2 = (back[0] - px * half, back[1] - py * half)
    hatch = msp.add_hatch(dxfattribs={"layer": layer})
    hatch.set_solid_fill()
    hatch.paths.add_polyline_path([tip, b1, b2], is_closed=True)
    msp.add_lwpolyline([tip, b1, b2], close=True, dxfattribs={"layer": layer})


def _draw_weld_symbol(msp: Modelspace, g: SteelMemberGeometry, t: float) -> None:
    """AWS/ISO fillet-weld symbol for the base connection, on the WELD layer.

    leader/arrow line -> the base weld; horizontal reference line; a filled
    fillet-weld triangle; the weld-size text; and a weld-all-round circle.
    """
    overall = g.overall_depth_mm
    # the base weld is at x = 0 (member to base plate); annotate it from above-left.
    weld_point = (0.0, overall * 0.75)
    ref_y = overall + 12.0 * t
    ref_x0 = -6.0 * t
    ref_x1 = 4.0 * t

    # leader / arrow line from the reference line to the weld root
    msp.add_line((ref_x0, ref_y), weld_point, dxfattribs={"layer": LAYER_WELD})
    _arrowhead(msp, tip=weld_point, back=(ref_x0 * 0.5, (ref_y + weld_point[1]) / 2.0),
               t=t, layer=LAYER_WELD)

    # horizontal reference line
    msp.add_line((ref_x0, ref_y), (ref_x1, ref_y), dxfattribs={"layer": LAYER_WELD})

    # weld-all-round circle at the leader / reference junction
    msp.add_circle((ref_x0, ref_y), 0.6 * t, dxfattribs={"layer": LAYER_WELD})

    # fillet-weld triangle sitting on the reference line (vertical leg on the arrow side)
    tri_x = ref_x0 + 1.4 * t
    tri = [(tri_x, ref_y), (tri_x, ref_y + 1.6 * t), (tri_x + 1.6 * t, ref_y)]
    msp.add_lwpolyline(tri, close=True, dxfattribs={"layer": LAYER_WELD})
    hatch = msp.add_hatch(dxfattribs={"layer": LAYER_WELD})
    hatch.set_solid_fill()
    hatch.paths.add_polyline_path(tri, is_closed=True)

    # weld-size text (leg size, mm) to the left of the triangle
    _text(msp, f"{g.weld_size_mm:g}", (tri_x - 1.4 * t, ref_y + 0.2 * t), 1.1 * t,
          TextEntityAlignment.MIDDLE_RIGHT, layer=LAYER_WELD)
    # fillet-weld designator + note on the reference line tail
    _text(msp, "FILLET WELD (IS 816)", (tri_x + 2.2 * t, ref_y + 0.3 * t), 0.8 * t,
          layer=LAYER_WELD)


def _draw_gdt_callout(msp: Modelspace, g: SteelMemberGeometry, t: float) -> None:
    """Basic GD&T-style annotation: a datum triangle + flatness feature-control note
    on the machined base-plate face, on the GDT layer."""
    overall = g.overall_depth_mm
    bp = 2.0 * t
    # datum feature triangle on the base-plate face (datum A)
    base = (-bp, -1.5 * t)
    tri = [base, (base[0] - 0.9 * t, base[1] - 1.4 * t), (base[0] + 0.9 * t, base[1] - 1.4 * t)]
    msp.add_lwpolyline(tri, close=True, dxfattribs={"layer": LAYER_GDT})
    hatch = msp.add_hatch(dxfattribs={"layer": LAYER_GDT})
    hatch.set_solid_fill()
    hatch.paths.add_polyline_path(tri, is_closed=True)
    _text(msp, "A", (base[0], base[1] - 3.0 * t), 0.9 * t,
          TextEntityAlignment.MIDDLE_CENTER, layer=LAYER_GDT)
    # feature-control-frame style flatness callout (bracketed, machined base face)
    _text(
        msp,
        "[ FLATNESS 0.2 | A ]  BASE PLATE FACE MACHINED (GD&T)",
        (-bp, overall + 3.0 * t), 0.8 * t, layer=LAYER_GDT,
    )


def _draw_section(
    msp: Modelspace, g: SteelMemberGeometry, t: float, *, section_cx: float, section_base_y: float
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

    _text(msp, "SECTION AT BASE  (SCALE: N.T.S.)", (cx, y0 + overall + off2),
          1.1 * t, TextEntityAlignment.MIDDLE_CENTER)


def _draw_frame_and_title(
    msp: Modelspace, g: SteelMemberGeometry, params: SteelMemberParams,
    run_id: str | None, drawing_date: dt.date, t: float,
) -> None:
    content = ezdxf.bbox.extents(msp)
    margin = 4.0 * t
    title_h = 11.0 * t
    xmin = content.extmin.x - margin
    xmax = content.extmax.x + margin
    ymax = content.extmax.y + margin
    ymin = content.extmin.y - margin - title_h
    msp.add_lwpolyline(
        [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)],
        close=True, dxfattribs={"layer": LAYER_SHEET},
    )
    title_w = min(xmax - xmin, 54.0 * t)
    x0 = xmax - title_w
    member_title = _MEMBER_TITLES.get(g.member_type, PROJECT_TITLE)
    rows = [
        (f"{PROJECT_TITLE}  ({member_title})", 0.85 * t),
        (
            f"LENGTH {g.cantilever_length_mm:g} x OVERALL DEPTH {g.overall_depth_mm:g}  "
            "(ALL DIMENSIONS IN mm)",
            0.7 * t,
        ),
        (
            f"WEB {g.web_depth_mm:g} x {g.web_thickness_mm:g}   "
            f"FLANGE {g.flange_width_mm:g} x {g.flange_thickness_mm:g}   "
            f"BASE FILLET WELD {g.weld_size_mm:g} mm ALL ROUND",
            0.7 * t,
        ),
        (f"STEEL {params.steel_grade}   {LOADING_NOTE}", 0.7 * t),
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
