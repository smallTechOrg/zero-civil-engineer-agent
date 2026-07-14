"""M-00004 PDF drawing sheet — hand-built parametric reportlab template.

One A3 landscape page (never LLM-generated) with six sections:
1. Cross-section (main view): outer concrete rectangle + inner octagon (four
   45-degree haunches), hatched concrete, ALL a1..h bars drawn in position with
   `mark : dia @ spacing` leader tags, and dimension chains.
2. Part-plan view: barrel length + return/wing walls + apron + curtain walls.
3. Reinforcement schedule table (Mark | Bar dia | Spacing | Member/face | Notation).
4. Notations glossary.
5. NOTES block (grade, cover, ALL DIMENSIONS IN mm, PROVISIONAL / NOT-FOR-CONSTRUCTION).
6. Title block (bottom-right) with the bold PROVISIONAL / NOT-FOR-CONSTRUCTION strip.

Every catalogue-derived value carries a PROVISIONAL marking. `generate_sheet`
writes `m00004_sheet.pdf` and returns its Path.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfgen import canvas

from components.base import coerce
from components.m00004_box_culvert.params import CLEAR_COVER_MM, M00004Geometry, M00004Params
from components.m00004_box_culvert.reinforcement import BAR_MARKS, bar_layout

SHEET_FILENAME = "m00004_sheet.pdf"

_PAGE_W, _PAGE_H = landscape(A3)  # points
_MARGIN = 24.0
_INK = HexColor("#1a1a1a")
_CONCRETE = HexColor("#d7dade")
_BAR = HexColor("#b02a37")
_DIM = HexColor("#0a58ca")
_PROV = HexColor("#a01010")
_HAUNCH = HexColor("#198754")

_VERIFY = "PROVISIONAL - verify against RDSO/M-00004"
_NFC = "NOT FOR CONSTRUCTION"


def generate_sheet(
    params: M00004Params,
    geometry: M00004Geometry,
    out_dir: Path,
    run_id: str | None = None,
    *,
    drawing_date: dt.date | None = None,
) -> Path:
    """Render the M-00004 sheet to ``out_dir/m00004_sheet.pdf``; return its Path."""
    params = coerce(M00004Params, params)
    geometry = coerce(M00004Geometry, geometry)
    drawing_date = drawing_date or dt.date.today()

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / SHEET_FILENAME

    c = canvas.Canvas(str(path), pagesize=(_PAGE_W, _PAGE_H))
    c.setTitle("RDSO/M-00004 Standard Single Box Culvert - GA & Reinforcement (PROVISIONAL)")

    _outer_border(c)
    # Left half: section (top) + part-plan (bottom). Right half: tables/notes/title.
    mid_x = _MARGIN + (_PAGE_W - 2 * _MARGIN) * 0.55
    _draw_section(c, geometry, x0=_MARGIN + 8, y0=_PAGE_H * 0.42,
                  x1=mid_x - 8, y1=_PAGE_H - _MARGIN - 20)
    _draw_plan(c, geometry, x0=_MARGIN + 8, y0=_MARGIN + 96,
               x1=mid_x - 8, y1=_PAGE_H * 0.40)
    _draw_schedule(c, geometry, x0=mid_x + 10, y0=_PAGE_H * 0.55,
                   x1=_PAGE_W - _MARGIN - 8, y1=_PAGE_H - _MARGIN - 20)
    _draw_notations(c, x0=mid_x + 10, y0=_PAGE_H * 0.30,
                    x1=_PAGE_W - _MARGIN - 8, y1=_PAGE_H * 0.53)
    _draw_notes(c, params, x0=mid_x + 10, y0=_MARGIN + 96,
                x1=_PAGE_W - _MARGIN - 8, y1=_PAGE_H * 0.285)
    _draw_title_block(c, params, geometry, run_id, drawing_date,
                      x0=_MARGIN + 8, y0=_MARGIN + 8, x1=_PAGE_W - _MARGIN - 8, y1=_MARGIN + 92)

    c.showPage()
    c.save()
    return path


# --------------------------------------------------------------------------- frame helpers
def _outer_border(c: canvas.Canvas) -> None:
    c.setStrokeColor(_INK)
    c.setLineWidth(1.4)
    c.rect(_MARGIN, _MARGIN, _PAGE_W - 2 * _MARGIN, _PAGE_H - 2 * _MARGIN)


def _panel(c: canvas.Canvas, title: str, x0, y0, x1, y1, *, prov: bool = False) -> None:
    c.setStrokeColor(_INK)
    c.setLineWidth(0.8)
    c.rect(x0, y0, x1 - x0, y1 - y0)
    c.setFillColor(_PROV if prov else _INK)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(x0 + 5, y1 - 12, title)
    c.setFillColor(_INK)


# --------------------------------------------------------------------------- (1) cross-section
def _draw_section(c: canvas.Canvas, g: M00004Geometry, *, x0, y0, x1, y1) -> None:
    _panel(c, "1. CROSS-SECTION (a1..h IN POSITION)  -  " + _VERIFY, x0, y0, x1, y1, prov=True)

    ox = g.outer_width_mm / 2.0
    oy = g.outer_height_mm / 2.0
    # scale model-mm -> page-pt, leaving a margin for dims + leader tags
    avail_w = (x1 - x0) - 90.0
    avail_h = (y1 - y0) - 70.0
    scale = min(avail_w / g.outer_width_mm, avail_h / g.outer_height_mm)
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0 - 6.0

    def P(mx, my):
        return (cx + mx * scale, cy + my * scale)

    # concrete ring: fill outer rect, then white opening octagon
    hs = g.clear_span_mm / 2.0
    hh = g.clear_height_mm / 2.0
    b = g.haunch_mm
    outer = [P(-ox, -oy), P(ox, -oy), P(ox, oy), P(-ox, oy)]
    oct_pts = [
        P(-(hs - b), hh), P(hs - b, hh), P(hs, hh - b), P(hs, -(hh - b)),
        P(hs - b, -hh), P(-(hs - b), -hh), P(-hs, -(hh - b)), P(-hs, hh - b),
    ]
    c.setFillColor(_CONCRETE)
    c.setStrokeColor(_INK)
    c.setLineWidth(1.2)
    _fill_poly(c, outer, stroke=1, fill=1)
    _hatch_rect(c, P(-ox, -oy), P(ox, oy), step=7.0)
    c.setFillColorRGB(1, 1, 1)
    _fill_poly(c, oct_pts, stroke=1, fill=1)

    # bars in position
    marks = bar_layout(g)
    c.setStrokeColor(_BAR)
    c.setFillColor(_BAR)
    for mark in BAR_MARKS:
        bm = marks[mark]
        c.setLineWidth(1.6)
        for line in bm.polylines:
            pts = [P(px, py) for px, py in line]
            c.setLineWidth(1.6)
            path = c.beginPath()
            path.moveTo(*pts[0])
            for pt in pts[1:]:
                path.lineTo(*pt)
            c.drawPath(path, stroke=1, fill=0)
        for px, py in bm.dots:
            dx, dy = P(px, py)
            c.circle(dx, dy, 1.6, stroke=0, fill=1)

    # leader tags: mark : dia @ spacing (all twelve)
    _draw_leaders(c, g, marks, P, ox, oy, scale)

    # dimension chains
    c.setStrokeColor(_DIM)
    c.setFillColor(_DIM)
    c.setFont("Helvetica", 6.5)
    _hdim(c, P(-hs, -oy), P(hs, -oy), dy=-14, text=f"clear span {g.clear_span_mm:g}")
    _hdim(c, P(-ox, -oy), P(ox, -oy), dy=-26, text=f"overall {g.outer_width_mm:g}")
    _vdim(c, P(-ox, -hh), P(-ox, hh), dx=-16, text=f"clear height {g.clear_height_mm:g}")
    _vdim(c, P(ox, hh), P(ox, oy), dx=14, text=f"t {g.thickness_mm:g}")
    c.setFillColor(_HAUNCH)
    c.setFont("Helvetica-Oblique", 6.5)
    hx, hy = P(hs - b / 2.0, hh - b / 2.0)
    c.drawString(hx + 3, hy + 3, f"haunch {g.haunch_mm:g}x{g.haunch_mm:g}")
    c.setFillColor(_INK)


def _draw_leaders(c, g, marks, P, ox, oy, scale) -> None:
    c.setFont("Helvetica-Bold", 6.2)
    for mark in BAR_MARKS:
        bm = marks[mark]
        bar = g.bar_schedule.get(mark, {})
        dia = int(bar.get("dia_mm", 0))
        spacing = int(bar.get("spacing_mm", 0))
        tag = f"{mark} : {dia}Ø @ {spacing}"
        lx, ly = bm.leader
        ax, ay = P(lx, ly)
        # place the tag just outside the box on the nearer side
        side = 1 if lx >= 0 else -1
        tx = ax + side * 10
        c.setStrokeColor(_BAR)
        c.setLineWidth(0.4)
        c.line(ax, ay, tx, ay)
        c.setFillColor(_BAR)
        if side >= 0:
            c.drawString(tx + 1, ay - 2, tag)
        else:
            c.drawRightString(tx - 1, ay - 2, tag)
    c.setFillColor(_INK)


# --------------------------------------------------------------------------- (2) part-plan
def _draw_plan(c: canvas.Canvas, g: M00004Geometry, *, x0, y0, x1, y1) -> None:
    _panel(c, "2. PART-PLAN (barrel + wing walls + apron + curtain)", x0, y0, x1, y1)

    length = g.barrel_length_mm
    wing = g.wing_len_mm
    apron = g.apron_len_mm
    curtain = g.curtain_thickness_mm
    total_len = length + 2.0 * (apron + curtain)
    w = g.outer_width_mm
    cls = g.clear_span_mm

    avail_w = (x1 - x0) - 40.0
    avail_h = (y1 - y0) - 46.0
    scale = min(avail_w / total_len, avail_h / w)
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0 - 4.0

    def P(mx, my):  # mx measured from barrel start (0..length), my transverse (centred)
        return (cx + (mx - length / 2.0) * scale, cy + my * scale)

    def rect(mx0, mx1, my0, my1, *, fill=0, dash=False):
        pts = [P(mx0, my0), P(mx1, my0), P(mx1, my1), P(mx0, my1)]
        c.setDash(3, 2) if dash else c.setDash()
        _fill_poly(c, pts, stroke=1, fill=fill)
        c.setDash()

    c.setStrokeColor(_INK)
    c.setFillColor(_CONCRETE)
    c.setLineWidth(0.9)
    rect(0, length, -w / 2.0, w / 2.0, fill=1)
    # clear opening through the barrel
    c.setFillColorRGB(1, 1, 1)
    rect(0, length, -cls / 2.0, cls / 2.0, fill=1, dash=True)
    # wing walls
    c.setFillColor(_CONCRETE)
    for mx0, mx1 in ((-wing, 0.0), (length, length + wing)):
        rect(mx0, mx1, cls / 2.0, w / 2.0, fill=1)
        rect(mx0, mx1, -w / 2.0, -cls / 2.0, fill=1)
    # apron floor + curtain walls (dashed - below bed)
    for mx0, mx1 in ((-apron, 0.0), (length, length + apron)):
        rect(mx0, mx1, -cls / 2.0, cls / 2.0, dash=True)
    for mx0, mx1 in ((-apron - curtain, -apron), (length + apron, length + apron + curtain)):
        rect(mx0, mx1, -w / 2.0, w / 2.0, fill=0, dash=True)

    c.setStrokeColor(_DIM)
    c.setFillColor(_DIM)
    c.setFont("Helvetica", 6.5)
    _hdim(c, P(0, -w / 2.0), P(length, -w / 2.0), dy=-14, text=f"barrel {g.barrel_length_mm:g}")
    c.setFillColor(_INK)


# --------------------------------------------------------------------------- (3) schedule
def _draw_schedule(c: canvas.Canvas, g: M00004Geometry, *, x0, y0, x1, y1) -> None:
    _panel(c, "3. REINFORCEMENT SCHEDULE (" + _VERIFY + ")", x0, y0, x1, y1, prov=True)
    from components.m00004_box_culvert.reinforcement import MARK_NOTATION

    cols = [x0 + 6, x0 + 46, x0 + 104, x0 + 168, x1 - 6]
    headers = ["Mark", "Bar dia", "Spacing", "Member / face"]
    top = y1 - 24
    c.setFont("Helvetica-Bold", 6.8)
    c.setFillColor(_INK)
    for i, h in enumerate(headers):
        c.drawString(cols[i] + 1, top, h)
    c.setLineWidth(0.4)
    c.line(x0 + 4, top - 3, x1 - 4, top - 3)

    row_h = (top - 3 - (y0 + 8)) / (len(BAR_MARKS) + 0.2)
    c.setFont("Helvetica", 6.4)
    for idx, mark in enumerate(BAR_MARKS):
        yy = top - 6 - (idx + 1) * row_h + row_h * 0.35
        bar = g.bar_schedule.get(mark, {})
        dia = int(bar.get("dia_mm", 0))
        spacing = int(bar.get("spacing_mm", 0))
        c.setFillColor(_BAR)
        c.setFont("Helvetica-Bold", 6.6)
        c.drawString(cols[0] + 1, yy, mark)
        c.setFillColor(_INK)
        c.setFont("Helvetica", 6.4)
        c.drawString(cols[1] + 1, yy, f"{dia}Ø")
        c.drawString(cols[2] + 1, yy, f"{spacing} c/c")
        c.drawString(cols[3] + 1, yy, _clip(MARK_NOTATION[mark], 34))


# --------------------------------------------------------------------------- (4) notations
def _draw_notations(c: canvas.Canvas, *, x0, y0, x1, y1) -> None:
    _panel(c, "4. NOTATIONS", x0, y0, x1, y1)
    from components.m00004_box_culvert.reinforcement import MARK_NOTATION

    c.setFont("Helvetica", 6.3)
    c.setFillColor(_INK)
    top = y1 - 22
    line_h = (top - (y0 + 6)) / (len(BAR_MARKS) + 0.5)
    for idx, mark in enumerate(BAR_MARKS):
        yy = top - idx * line_h
        c.setFillColor(_BAR)
        c.setFont("Helvetica-Bold", 6.3)
        c.drawString(x0 + 6, yy, f"{mark}")
        c.setFillColor(_INK)
        c.setFont("Helvetica", 6.3)
        c.drawString(x0 + 26, yy, _clip(MARK_NOTATION[mark], 62))


# --------------------------------------------------------------------------- (5) notes
def _draw_notes(c: canvas.Canvas, params: M00004Params, *, x0, y0, x1, y1) -> None:
    _panel(c, "5. NOTES", x0, y0, x1, y1)
    notes = [
        "1. ALL DIMENSIONS IN mm UNLESS NOTED.",
        f"2. CONCRETE {params.concrete_grade.value}; REINFORCEMENT {params.steel_grade.value}.",
        f"3. CLEAR COVER TO REINFORCEMENT {CLEAR_COVER_MM:g} mm (assumed).",
        "4. LAP / DEVELOPMENT LENGTHS PER IRS CONCRETE BRIDGE CODE.",
        "5. HAUNCHES 45 DEG AT ALL FOUR INNER CORNERS.",
        "6. Thickness, haunch and the a1..h schedule are REPRODUCED from the",
        "   RDSO/M-00004 standard config - PROVISIONAL, verify every value.",
        f"7. {_NFC}. This is a standard reproduction, not an independent design.",
    ]
    c.setFont("Helvetica", 6.4)
    top = y1 - 22
    for idx, line in enumerate(notes):
        c.setFillColor(_PROV if idx >= 5 else _INK)
        c.drawString(x0 + 6, top - idx * 10.5, line)
    c.setFillColor(_INK)


# --------------------------------------------------------------------------- (6) title block
def _draw_title_block(
    c: canvas.Canvas, params: M00004Params, g: M00004Geometry,
    run_id: str | None, drawing_date: dt.date, *, x0, y0, x1, y1,
) -> None:
    c.setStrokeColor(_INK)
    c.setLineWidth(1.0)
    c.rect(x0, y0, x1 - x0, y1 - y0)
    # PROVISIONAL strip
    strip_h = 16.0
    c.setFillColor(_PROV)
    c.rect(x0, y1 - strip_h, x1 - x0, strip_h, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawCentredString((x0 + x1) / 2.0, y1 - strip_h + 4.5,
                        f"PROVISIONAL  -  {_NFC}  -  verify every value against RDSO/M-00004")

    c.setFillColor(_INK)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(x0 + 8, y1 - strip_h - 14,
                 "RDSO/M-00004 STANDARD SINGLE BOX CULVERT - GA & REINFORCEMENT")
    c.setFont("Helvetica", 7.5)
    lines = [
        f"Entered box: {params.clear_span_m:g} x {params.clear_height_m:g} m, fill {params.cushion_m:g} m"
        f"   |   Selected config: {g.config_id}",
        f"Materials: {params.concrete_grade.value} concrete / {params.steel_grade.value} steel"
        f"   |   t {g.thickness_mm:g} mm, haunch {g.haunch_mm:g} mm, barrel {g.barrel_length_mm:g} mm",
        f"Scale: N.T.S.   |   Date: {drawing_date.isoformat()}   |   Run: {run_id or '-'}   |   Sheet 1 of 1",
    ]
    for idx, line in enumerate(lines):
        c.drawString(x0 + 8, y1 - strip_h - 28 - idx * 11, line)
    if g.provisional_flags:
        c.setFillColor(_PROV)
        c.setFont("Helvetica-Oblique", 6.4)
        c.drawString(x0 + 8, y0 + 6, _clip("PROVISIONAL: " + "; ".join(g.provisional_flags), 150))
        c.setFillColor(_INK)


# --------------------------------------------------------------------------- primitives
def _fill_poly(c: canvas.Canvas, pts, *, stroke: int, fill: int) -> None:
    path = c.beginPath()
    path.moveTo(*pts[0])
    for pt in pts[1:]:
        path.lineTo(*pt)
    path.close()
    c.drawPath(path, stroke=stroke, fill=fill)


def _hatch_rect(c: canvas.Canvas, p0, p1, *, step: float) -> None:
    """45-degree concrete hatch clipped to the rectangle p0..p1."""
    x0, y0 = p0
    x1, y1 = p1
    c.saveState()
    path = c.beginPath()
    path.rect(x0, y0, x1 - x0, y1 - y0)
    c.clipPath(path, stroke=0, fill=0)
    c.setStrokeColor(HexColor("#9aa0a6"))
    c.setLineWidth(0.3)
    x = x0 - (y1 - y0)
    while x < x1:
        c.line(x, y0, x + (y1 - y0), y1)
        x += step
    c.restoreState()


def _hdim(c: canvas.Canvas, p1, p2, *, dy: float, text: str) -> None:
    x1, y1 = p1
    x2, y2 = p2
    yy = min(y1, y2) + dy
    c.setLineWidth(0.4)
    c.line(x1, yy, x2, yy)
    c.line(x1, yy, x1, y1)
    c.line(x2, yy, x2, y2)
    c.drawCentredString((x1 + x2) / 2.0, yy + 2, text)


def _vdim(c: canvas.Canvas, p1, p2, *, dx: float, text: str) -> None:
    x1, y1 = p1
    x2, y2 = p2
    xx = min(x1, x2) + dx if dx < 0 else max(x1, x2) + dx
    c.setLineWidth(0.4)
    c.line(xx, y1, xx, y2)
    c.line(xx, y1, x1, y1)
    c.line(xx, y2, x2, y2)
    c.saveState()
    c.translate(xx - 2, (y1 + y2) / 2.0)
    c.rotate(90)
    c.drawCentredString(0, 2, text)
    c.restoreState()


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"
