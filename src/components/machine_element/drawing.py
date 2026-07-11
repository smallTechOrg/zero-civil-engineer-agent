"""Detail-drawing generator — hand-validated parametric ezdxf template.

    from components.machine_element.drawing import generate_ga
    paths = generate_ga(params, geometry, out_dir, run_id=run_id)
    # writes out_dir/"ga.dxf" and out_dir/"ga.svg"
    # returns {"ga_dxf": Path, "ga_svg": Path}

Two element kinds are drawn from the SAME `MachineElementGeometry`:

* **shaft** — a stepped-shaft elevation + mid cross-section, dimensioned, with
  GD&T annotation: a diameter/tolerance callout (⌀d h7), a surface-finish symbol
  (Ra) and a datum feature symbol (a filled triangle + a datum-letter box).
* **welded_joint** — the hub-on-plate detail, dimensioned, with a diameter GD&T
  callout AND a fillet-weld SYMBOL on a dedicated `WELD` layer (arrow + reference
  line + fillet triangle + leg-size text).

Every dimension value comes from the geometry — the same source the calc uses — so
calc-vs-drawing consistency is structural. The SVG is rendered by the shared ezdxf
SVGBackend (`drawing.svg_render.render_svg`) from the very document written to
ga.dxf. HAND-WRITTEN parametric template — never LLM CAD.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import ezdxf
from ezdxf.document import Drawing
from ezdxf.enums import TextEntityAlignment
from ezdxf.layouts import Modelspace

from components.machine_element.params import MachineElementGeometry, MachineElementParams
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
LAYER_GDT = "GDT"    # GD&T: tolerance callouts, surface finish, datum symbols
LAYER_WELD = "WELD"  # welding symbols
DIMSTYLE_ME = "ME"

_LAYERS = (
    (LAYER_OUTLINE, 7, None, 50),
    (LAYER_DIM, 1, None, 18),
    (LAYER_TEXT, 7, None, 25),
    (LAYER_HATCH, 8, None, 13),
    (LAYER_CL, 4, "CENTER", 15),
    (LAYER_HIDDEN, 8, "DASHED", 18),
    (LAYER_SHEET, 7, None, 35),
    (LAYER_GDT, 3, None, 25),
    (LAYER_WELD, 2, None, 25),
)

PROJECT_TITLE = "MACHINE ELEMENT - DETAIL DRAWING"
BASIS_NOTE = "DESIGN & PROOF CHECK PER STANDARD MACHINE-DESIGN PRACTICE (SHIGLEY / PSG / DESIGN DATA BOOK) / IS 816 (WELD)"

Point = tuple[float, float]


class InvalidGeometryError(ValueError):
    """Raised when the element geometry is impossible or internally inconsistent."""


def _validate(geometry: MachineElementGeometry) -> None:
    if geometry.element_kind == "welded_joint":
        for name, value in (
            ("hub diameter", geometry.hub_diameter_mm),
            ("weld size", geometry.weld_size_mm),
            ("plate thickness", geometry.plate_thickness_mm),
            ("plate size", geometry.length_mm),
        ):
            if value <= 0:
                raise InvalidGeometryError(f"{name} must be positive, got {value:g} mm")
        if geometry.weld_size_mm >= geometry.hub_diameter_mm:
            raise InvalidGeometryError(
                f"weld leg {geometry.weld_size_mm:g} mm is not smaller than the hub "
                f"diameter {geometry.hub_diameter_mm:g} mm"
            )
        return
    for name, value in (
        ("diameter", geometry.diameter_mm),
        ("length", geometry.length_mm),
        ("journal diameter", geometry.step_diameter_mm),
        ("journal length", geometry.step_length_mm),
    ):
        if value <= 0:
            raise InvalidGeometryError(f"{name} must be positive, got {value:g} mm")
    if geometry.step_diameter_mm >= geometry.diameter_mm:
        raise InvalidGeometryError(
            f"journal diameter {geometry.step_diameter_mm:g} mm is not smaller than the "
            f"major diameter {geometry.diameter_mm:g} mm"
        )
    if 2.0 * geometry.step_length_mm >= geometry.length_mm:
        raise InvalidGeometryError(
            f"two journals ({2 * geometry.step_length_mm:g} mm) do not fit within the "
            f"overall length {geometry.length_mm:g} mm"
        )


def generate_ga(
    params: MachineElementParams,
    geometry: MachineElementGeometry,
    out_dir: Path,
    run_id: str | None = None,
    *,
    drawing_date: dt.date | None = None,
) -> dict[str, Path]:
    """Generate the detail sheet as ga.dxf + ga.svg inside ``out_dir``."""
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
    params: MachineElementParams,
    geometry: MachineElementGeometry,
    run_id: str | None,
    drawing_date: dt.date,
) -> Drawing:
    if geometry.element_kind == "welded_joint":
        span = max(geometry.hub_diameter_mm, geometry.length_mm)
    else:
        span = max(geometry.length_mm, geometry.diameter_mm)
    t = max(2.0, span / 40.0)

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
    if geometry.element_kind == "welded_joint":
        _draw_weld_detail(msp, geometry, t)
    else:
        _draw_shaft_detail(msp, geometry, t)
    _draw_frame_and_title(msp, geometry, params, run_id, drawing_date, t)
    return doc


def _add_dimstyle(doc: Drawing, t: float) -> None:
    style = doc.dimstyles.duplicate_entry("EZDXF", DIMSTYLE_ME)
    style.dxf.dimlfac = 1.0
    style.dxf.dimtxt = t
    style.dxf.dimasz = round(0.75 * t, 1)
    style.dxf.dimexe = round(0.5 * t, 1)
    style.dxf.dimexo = round(0.35 * t, 1)
    style.dxf.dimgap = round(0.25 * t, 1)
    style.dxf.dimdec = 0
    style.dxf.dimtad = 1


# --------------------------------------------------------------------------- primitives
def _text(msp: Modelspace, content: str, at: Point, height: float,
          layer: str = LAYER_TEXT,
          align: TextEntityAlignment = TextEntityAlignment.LEFT) -> None:
    entity = msp.add_text(content, height=height, dxfattribs={"layer": layer})
    entity.set_placement(at, align=align)


def _outline(msp: Modelspace, points: list[Point], layer: str = LAYER_OUTLINE) -> None:
    msp.add_lwpolyline(points, close=True, dxfattribs={"layer": layer})


def _hatch(msp: Modelspace, points: list[Point], scale: float) -> None:
    hatch = msp.add_hatch(dxfattribs={"layer": LAYER_HATCH})
    hatch.set_pattern_fill("ANSI31", scale=scale)
    hatch.paths.add_polyline_path(points, is_closed=True)


def _dim(msp: Modelspace, *, base: Point, p1: Point, p2: Point, angle: float = 0.0) -> None:
    dimension = msp.add_linear_dim(
        base=base, p1=p1, p2=p2, angle=angle,
        dimstyle=DIMSTYLE_ME, dxfattribs={"layer": LAYER_DIM},
    )
    dimension.render()


def _solid_triangle(msp: Modelspace, a: Point, b: Point, c: Point, layer: str) -> None:
    msp.add_solid([a, b, c, c], dxfattribs={"layer": layer})


# --------------------------------------------------------------------------- GD&T annotations
def _gdt_diameter_callout(msp: Modelspace, *, at: Point, diameter: float, tol: str, t: float) -> None:
    """A diameter/tolerance callout (⌀d <tol>) with a short leader — GD&T."""
    leader_end = (at[0] - 3.0 * t, at[1] + 3.0 * t)
    msp.add_line(at, leader_end, dxfattribs={"layer": LAYER_GDT})
    _solid_triangle(msp, at, (at[0] - 0.6 * t, at[1] + 0.4 * t),
                    (at[0] - 0.4 * t, at[1] + 0.7 * t), LAYER_GDT)
    _text(msp, f"%%c{diameter:g} {tol}", (leader_end[0] - 0.3 * t, leader_end[1] + 0.3 * t),
          1.0 * t, layer=LAYER_GDT)


def _surface_finish(msp: Modelspace, *, at: Point, ra: str, t: float) -> None:
    """A machining surface-finish (√) symbol with the Ra value — GD&T."""
    x, y = at
    msp.add_lwpolyline(
        [(x, y), (x + 0.7 * t, y - 1.2 * t), (x + 1.4 * t, y + 1.4 * t), (x + 3.2 * t, y + 1.4 * t)],
        dxfattribs={"layer": LAYER_GDT},
    )
    _text(msp, ra, (x + 1.7 * t, y + 1.7 * t), 0.9 * t, layer=LAYER_GDT)


def _datum_symbol(msp: Modelspace, *, at: Point, letter: str, t: float) -> None:
    """A datum feature symbol — a filled triangle + a boxed datum letter — GD&T."""
    x, y = at
    _solid_triangle(msp, (x, y), (x - 0.7 * t, y - 1.1 * t), (x + 0.7 * t, y - 1.1 * t), LAYER_GDT)
    msp.add_line((x, y - 1.1 * t), (x, y - 2.2 * t), dxfattribs={"layer": LAYER_GDT})
    box = [(x - 1.1 * t, y - 2.2 * t), (x + 1.1 * t, y - 2.2 * t),
           (x + 1.1 * t, y - 4.4 * t), (x - 1.1 * t, y - 4.4 * t)]
    _outline(msp, box, layer=LAYER_GDT)
    _text(msp, letter, (x, y - 3.3 * t), 1.2 * t, layer=LAYER_GDT,
          align=TextEntityAlignment.MIDDLE_CENTER)


# --------------------------------------------------------------------------- weld symbol
def _fillet_weld_symbol(msp: Modelspace, *, weld_at: Point, leg_mm: float, t: float) -> None:
    """A fillet-weld symbol: arrow (leader + arrowhead) + reference line + fillet
    triangle + leg-size text, all on the WELD layer (welding-symbol convention)."""
    wx, wy = weld_at
    knee = (wx + 5.0 * t, wy + 6.0 * t)
    ref_end = (knee[0] + 12.0 * t, knee[1])
    # arrow leader
    msp.add_line(weld_at, knee, dxfattribs={"layer": LAYER_WELD})
    # arrowhead (filled) pointing at the weld
    msp.add_solid(
        [weld_at, (wx + 1.2 * t, wy + 1.4 * t), (wx + 1.7 * t, wy + 0.6 * t), (wx + 1.7 * t, wy + 0.6 * t)],
        dxfattribs={"layer": LAYER_WELD},
    )
    # horizontal reference line
    msp.add_line(knee, ref_end, dxfattribs={"layer": LAYER_WELD})
    # fillet-weld triangle sitting on the reference line
    tx = knee[0] + 3.0 * t
    _outline(
        msp,
        [(tx, knee[1]), (tx, knee[1] + 2.2 * t), (tx + 2.2 * t, knee[1])],
        layer=LAYER_WELD,
    )
    # leg-size text to the left of the triangle
    _text(msp, f"{leg_mm:g}", (tx - 2.0 * t, knee[1] + 0.4 * t), 1.1 * t, layer=LAYER_WELD)


# --------------------------------------------------------------------------- shaft detail
def _draw_shaft_detail(msp: Modelspace, g: MachineElementGeometry, t: float) -> None:
    """Stepped-shaft elevation + mid cross-section, dimensioned, with GD&T."""
    d = g.diameter_mm
    dj = g.step_diameter_mm
    lj = g.step_length_mm
    length = g.length_mm
    lc = length - 2.0 * lj
    hatch_scale = max(1.0, 0.4 * t)

    # centreline
    msp.add_line((-3.0 * t, 0.0), (length + 3.0 * t, 0.0), dxfattribs={"layer": LAYER_CL})

    # stepped profile outline (symmetric about the axis)
    top = [
        (0.0, dj / 2.0), (lj, dj / 2.0), (lj, d / 2.0), (lj + lc, d / 2.0),
        (lj + lc, dj / 2.0), (length, dj / 2.0),
    ]
    bottom = [(x, -y) for x, y in reversed(top)]
    _outline(msp, top + bottom)

    # shoulder fillet arcs (stress-concentration feature) at the two upper shoulders
    r = g.fillet_radius_mm
    if r > 0:
        msp.add_arc(center=(lj + r, d / 2.0 - r), radius=r, start_angle=90, end_angle=180,
                    dxfattribs={"layer": LAYER_OUTLINE})
        msp.add_arc(center=(lj + lc - r, d / 2.0 - r), radius=r, start_angle=0, end_angle=90,
                    dxfattribs={"layer": LAYER_OUTLINE})

    # keyway (keyseat) on the central top surface
    if g.keyway_width_mm > 0:
        kx1 = lj + 0.2 * lc
        kx2 = lj + 0.8 * lc
        kd = g.keyway_depth_mm
        _outline(msp, [(kx1, d / 2.0), (kx2, d / 2.0), (kx2, d / 2.0 - kd), (kx1, d / 2.0 - kd)])

    # dimensions
    off1 = 4.0 * t
    off2 = 9.0 * t
    _dim(msp, base=(length / 2.0, -(d / 2.0 + off2)), p1=(0.0, -dj / 2.0), p2=(length, -dj / 2.0))
    _dim(msp, base=(-off1, 0.0), p1=(0.0, -dj / 2.0), p2=(0.0, dj / 2.0), angle=90)
    _dim(msp, base=(lj + lc / 2.0, d / 2.0 + off1), p1=(lj + lc / 2.0, -d / 2.0),
         p2=(lj + lc / 2.0, d / 2.0), angle=90)

    # GD&T on the elevation
    _gdt_diameter_callout(msp, at=(lj + 0.35 * lc, d / 2.0), diameter=d, tol="h7", t=t)
    _surface_finish(msp, at=(lj + 0.55 * lc, d / 2.0 + 0.2 * t), ra="Ra 1.6", t=t)
    _text(msp, f"FILLET R{r:g} ALL SHOULDERS", (0.0, -(d / 2.0 + off2 + 2.0 * t)), 0.9 * t,
          layer=LAYER_GDT)

    _text(msp, "SHAFT ELEVATION  (SCALE: N.T.S.)", (length / 2.0, d / 2.0 + off2 + 2.5 * t),
          1.1 * t, layer=LAYER_TEXT, align=TextEntityAlignment.MIDDLE_CENTER)

    # --- mid cross-section (a circle of diameter d with the keyway) ---
    cx = length / 2.0
    cy = -(d / 2.0 + off2 + 12.0 * t)
    msp.add_circle((cx, cy), d / 2.0, dxfattribs={"layer": LAYER_OUTLINE})
    _hatch(msp, _circle_points(cx, cy, d / 2.0), hatch_scale)
    if g.keyway_width_mm > 0:
        kw = g.keyway_width_mm
        kd = g.keyway_depth_mm
        _outline(msp, [
            (cx - kw / 2.0, cy + d / 2.0), (cx + kw / 2.0, cy + d / 2.0),
            (cx + kw / 2.0, cy + d / 2.0 - kd), (cx - kw / 2.0, cy + d / 2.0 - kd),
        ])
    msp.add_line((cx - d / 2.0 - 2.0 * t, cy), (cx + d / 2.0 + 2.0 * t, cy),
                 dxfattribs={"layer": LAYER_CL})
    msp.add_line((cx, cy - d / 2.0 - 2.0 * t), (cx, cy + d / 2.0 + 2.0 * t),
                 dxfattribs={"layer": LAYER_CL})
    _dim(msp, base=(cx, cy - d / 2.0 - off1), p1=(cx - d / 2.0, cy - d / 2.0),
         p2=(cx + d / 2.0, cy - d / 2.0))
    _datum_symbol(msp, at=(cx + d / 2.0, cy - d / 2.0 - 0.5 * t), letter="A", t=t)
    _text(msp, "SECTION A-A  (SCALE: N.T.S.)", (cx, cy - d / 2.0 - off2),
          1.1 * t, layer=LAYER_TEXT, align=TextEntityAlignment.MIDDLE_CENTER)


def _circle_points(cx: float, cy: float, radius: float, segments: int = 48) -> list[Point]:
    import math

    return [
        (cx + radius * math.cos(2.0 * math.pi * i / segments),
         cy + radius * math.sin(2.0 * math.pi * i / segments))
        for i in range(segments)
    ]


# --------------------------------------------------------------------------- weld detail
def _draw_weld_detail(msp: Modelspace, g: MachineElementGeometry, t: float) -> None:
    """Hub-on-plate welded detail, dimensioned, with a diameter GD&T callout and a
    fillet-weld SYMBOL."""
    d = g.hub_diameter_mm
    lp = g.length_mm            # plate size
    tp = g.plate_thickness_mm
    hub_h = d                   # representative hub height
    hatch_scale = max(1.0, 0.4 * t)

    # backing plate (top face at y = 0)
    plate = [(-lp / 2.0, 0.0), (lp / 2.0, 0.0), (lp / 2.0, -tp), (-lp / 2.0, -tp)]
    _outline(msp, plate)
    _hatch(msp, plate, hatch_scale)

    # hub (side view — a rectangle standing on the plate) + centreline
    hub = [(-d / 2.0, 0.0), (d / 2.0, 0.0), (d / 2.0, hub_h), (-d / 2.0, hub_h)]
    _outline(msp, hub)
    _hatch(msp, hub, hatch_scale)
    msp.add_line((0.0, -tp - 2.0 * t), (0.0, hub_h + 3.0 * t), dxfattribs={"layer": LAYER_CL})

    # fillet-weld fillets drawn at the two hub-to-plate toes (triangular fillets)
    s = g.weld_size_mm
    _outline(msp, [(-d / 2.0, 0.0), (-d / 2.0 - s, 0.0), (-d / 2.0, s)])
    _outline(msp, [(d / 2.0, 0.0), (d / 2.0 + s, 0.0), (d / 2.0, s)])

    # dimensions
    off1 = 4.0 * t
    off2 = 9.0 * t
    _dim(msp, base=(0.0, hub_h + off2), p1=(-d / 2.0, hub_h), p2=(d / 2.0, hub_h), angle=0)
    _dim(msp, base=(0.0, -tp - off2), p1=(-lp / 2.0, -tp), p2=(lp / 2.0, -tp), angle=0)
    _dim(msp, base=(-lp / 2.0 - off1, -tp / 2.0), p1=(-lp / 2.0, -tp), p2=(-lp / 2.0, 0.0), angle=90)

    # GD&T diameter callout on the hub
    _gdt_diameter_callout(msp, at=(0.0, hub_h), diameter=d, tol="H8", t=t)

    # fillet-weld symbol pointing at the right-hand weld toe
    _fillet_weld_symbol(msp, weld_at=(d / 2.0 + s, 0.0), leg_mm=s, t=t)

    _text(msp, "WELDED HUB DETAIL  (SCALE: N.T.S.)", (0.0, -tp - off2 - 3.0 * t),
          1.1 * t, layer=LAYER_TEXT, align=TextEntityAlignment.MIDDLE_CENTER)


# --------------------------------------------------------------------------- frame + title
def _draw_frame_and_title(
    msp: Modelspace, g: MachineElementGeometry, params: MachineElementParams,
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
    title_w = min(xmax - xmin, 60.0 * t)
    x0 = xmax - title_w
    if g.element_kind == "welded_joint":
        geo_row = (
            f"HUB DIA {g.hub_diameter_mm:g}   FILLET WELD LEG {g.weld_size_mm:g} "
            f"(THROAT {g.weld_throat_mm:g})   PLATE {g.plate_thickness_mm:g}   (ALL DIMS IN mm)"
        )
    else:
        geo_row = (
            f"DIA {g.diameter_mm:g} x LENGTH {g.length_mm:g}   JOURNAL DIA {g.step_diameter_mm:g}   "
            f"KEYWAY {g.keyway_width_mm:g} x {g.keyway_depth_mm:g}   (ALL DIMS IN mm)"
        )
    rows = [
        (PROJECT_TITLE + f"  -  {g.element_kind.upper()}", 0.9 * t),
        (geo_row, 0.7 * t),
        (f"MATERIAL {params.material_grade}   FoS {params.required_factor_of_safety:g}   BASIS: {BASIS_NOTE}", 0.7 * t),
        (f"RUN: {run_id or '-'}   DATE: {drawing_date.isoformat()}", 0.7 * t),
        ("FOR DEMONSTRATION - NOT FOR MANUFACTURE   SCALE: N.T.S.   SHEET 1 OF 1", 0.7 * t),
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
