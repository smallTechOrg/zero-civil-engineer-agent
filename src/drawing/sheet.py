"""Sheet furniture for the GA template — units, metrics, layers, dimension style,
frame, title block and general notes.

All sheet proportions are expressed as multiples of one text height, which
itself scales with the drawing's overall extent — this is what keeps extreme
geometry (1 m x 6 m, 8 m x 1 m, 9 m fill) legible and inside the frame.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import ezdxf
import ezdxf.bbox
from ezdxf.document import Drawing
from ezdxf.entities import Text
from ezdxf.enums import TextEntityAlignment
from ezdxf.layouts import Modelspace

from domain.culvert import BoxGeometry, CulvertParams

LAYER_OUTLINE = "OUTLINE"
LAYER_DIM = "DIM"
LAYER_TEXT = "TEXT"
LAYER_HATCH = "HATCH"
LAYER_CL = "CL"
LAYER_HIDDEN = "HIDDEN"
LAYER_SHEET = "SHEET"
DIMSTYLE_GA = "GA"

# (name, ACI colour, linetype, lineweight in 1/100 mm)
_LAYERS = (
    (LAYER_OUTLINE, 7, None, 50),
    (LAYER_DIM, 1, None, 18),
    (LAYER_TEXT, 7, None, 25),
    (LAYER_HATCH, 8, None, 13),
    (LAYER_CL, 4, "CENTER", 15),
    (LAYER_HIDDEN, 8, "DASHED", 18),
    (LAYER_SHEET, 7, None, 35),
)

# Drawing-standard proportion: text ~ 1/180 of the sheet's larger rough extent.
_TEXT_HEIGHT_RATIO = 1.0 / 180.0
_MIN_TEXT_HEIGHT_MM = 25.0

LOADING_NOTE = "IRS BRIDGE RULES - 25t LOADING-2008 (INCL. ACS)"
PROJECT_TITLE = "SINGLE CELL RCC BOX CULVERT - GENERAL ARRANGEMENT"


@dataclass(frozen=True)
class BoxMM:
    """BoxGeometry converted once to drawing units (mm) — the single value source
    for every coordinate and every dimension defpoint on the sheet."""

    span: float
    height: float
    cushion: float
    t_top: float
    t_bot: float
    t_wall: float
    haunch: float
    w_ext: float
    h_ext: float
    l_barrel: float

    @classmethod
    def from_geometry(cls, geometry: BoxGeometry) -> "BoxMM":
        return cls(
            span=round(geometry.clear_span_m * 1000.0, 3),
            height=round(geometry.clear_height_m * 1000.0, 3),
            cushion=round(geometry.cushion_m * 1000.0, 3),
            t_top=round(geometry.top_slab_thickness_mm, 3),
            t_bot=round(geometry.bottom_slab_thickness_mm, 3),
            t_wall=round(geometry.wall_thickness_mm, 3),
            haunch=round(geometry.haunch_mm, 3),
            w_ext=round(geometry.external_width_m * 1000.0, 3),
            h_ext=round(geometry.external_height_m * 1000.0, 3),
            l_barrel=round(geometry.barrel_length_m * 1000.0, 3),
        )


@dataclass(frozen=True)
class SheetMetrics:
    """One text height drives every offset, gap and block size on the sheet."""

    text_h: float

    @classmethod
    def for_box(cls, box: BoxMM) -> "SheetMetrics":
        rough_width = box.l_barrel + box.w_ext
        rough_height = box.h_ext + box.cushion + box.w_ext
        text_h = max(
            _MIN_TEXT_HEIGHT_MM, max(rough_width, rough_height) * _TEXT_HEIGHT_RATIO
        )
        return cls(text_h=round(text_h, 1))

    @property
    def dim_off1(self) -> float:
        return 4.0 * self.text_h

    @property
    def dim_off2(self) -> float:
        return 8.0 * self.text_h

    @property
    def view_gap(self) -> float:
        return 16.0 * self.text_h

    @property
    def frame_margin(self) -> float:
        return 4.0 * self.text_h

    @property
    def title_w(self) -> float:
        return 46.0 * self.text_h

    @property
    def title_h(self) -> float:
        return 10.0 * self.text_h


def new_sheet_doc(metrics: SheetMetrics) -> Drawing:
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 4  # millimetres
    doc.header["$MEASUREMENT"] = 1  # metric
    # CENTER's dash cycle is 2.0 drawing units — scale it to ~3 text heights.
    doc.header["$LTSCALE"] = round(1.5 * metrics.text_h, 1)
    for name, color, linetype, lineweight in _LAYERS:
        attribs = {"color": color, "lineweight": lineweight}
        if linetype:
            attribs["linetype"] = linetype
        doc.layers.add(name, **attribs)
    _add_ga_dimstyle(doc, metrics)
    return doc


def _add_ga_dimstyle(doc: Drawing, metrics: SheetMetrics) -> None:
    t = metrics.text_h
    style = doc.dimstyles.duplicate_entry("EZDXF", DIMSTYLE_GA)
    # The EZDXF base style carries dimlfac=100 (metres shown as cm); this sheet
    # draws in mm and must print the measured value verbatim.
    style.dxf.dimlfac = 1.0
    style.dxf.dimtxt = t
    style.dxf.dimasz = round(0.75 * t, 1)
    style.dxf.dimexe = round(0.5 * t, 1)
    style.dxf.dimexo = round(0.35 * t, 1)
    style.dxf.dimgap = round(0.25 * t, 1)
    style.dxf.dimdec = 0  # whole millimetres on the sheet
    style.dxf.dimtad = 1  # text above the dimension line


def add_text(
    msp: Modelspace,
    content: str,
    *,
    at: tuple[float, float],
    height: float,
    layer: str = LAYER_TEXT,
    align: TextEntityAlignment = TextEntityAlignment.LEFT,
    rotation: float = 0.0,
) -> Text:
    entity = msp.add_text(
        content, height=height, rotation=rotation, dxfattribs={"layer": layer}
    )
    entity.set_placement(at, align=align)
    return entity


def general_notes_lines(params: CulvertParams, box: BoxMM) -> list[str]:
    haunch_note = (
        f"7. HAUNCHES {box.haunch:g} x {box.haunch:g} AT ALL INSIDE CORNERS."
        if box.haunch > 0
        else "7. NO HAUNCHES PROVIDED."
    )
    return [
        "1. ALL DIMENSIONS ARE IN MILLIMETRES UNLESS NOTED OTHERWISE.",
        f"2. CONCRETE GRADE: {params.concrete_grade.value}.",
        f"3. REINFORCEMENT STEEL GRADE: {params.steel_grade.value}.",
        f"4. CLEAR COVER TO REINFORCEMENT: {params.clear_cover_mm:g} mm.",
        f"5. LOADING STANDARD: {LOADING_NOTE}.",
        "6. DESIGN AND PROOF CHECK PER IRS CONCRETE BRIDGE CODE (CBC).",
        haunch_note,
        f"8. FILL OVER TOP SLAB (CUSHION): {box.cushion:g} mm TO FORMATION LEVEL.",
        "9. GENERAL ARRANGEMENT ONLY - REINFORCEMENT DETAILING NOT INCLUDED.",
    ]


def draw_general_notes(
    msp: Modelspace,
    metrics: SheetMetrics,
    params: CulvertParams,
    box: BoxMM,
    origin: tuple[float, float],
) -> None:
    t = metrics.text_h
    x, y = origin
    add_text(msp, "GENERAL NOTES", at=(x, y), height=0.9 * t)
    for index, line in enumerate(general_notes_lines(params, box), start=1):
        add_text(msp, line, at=(x, y - index * 1.8 * t), height=0.7 * t)


def draw_frame_and_title_block(
    msp: Modelspace,
    metrics: SheetMetrics,
    box: BoxMM,
    run_id: str | None,
    drawing_date: dt.date,
) -> None:
    """Drawn LAST: the frame wraps everything already on the sheet plus a
    dedicated bottom band for the title block, so no content can fall outside."""
    content = ezdxf.bbox.extents(msp)
    margin = metrics.frame_margin
    xmin = content.extmin.x - margin
    xmax = content.extmax.x + margin
    ymax = content.extmax.y + margin
    ymin = content.extmin.y - margin - metrics.title_h
    msp.add_lwpolyline(
        [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)],
        close=True,
        dxfattribs={"layer": LAYER_SHEET},
    )
    _draw_title_block(msp, metrics, box, run_id, drawing_date, x_right=xmax, y_bottom=ymin)


def _draw_title_block(
    msp: Modelspace,
    metrics: SheetMetrics,
    box: BoxMM,
    run_id: str | None,
    drawing_date: dt.date,
    *,
    x_right: float,
    y_bottom: float,
) -> None:
    t = metrics.text_h
    x0 = x_right - metrics.title_w
    rows = [
        (PROJECT_TITLE, 0.9 * t),
        (
            f"CLEAR SPAN {box.span:g} x CLEAR HEIGHT {box.height:g} x "
            f"CUSHION {box.cushion:g}  (ALL DIMENSIONS IN mm)",
            0.7 * t,
        ),
        (f"LOADING: {LOADING_NOTE}", 0.7 * t),
        (f"RUN: {run_id or '-'}   DATE: {drawing_date.isoformat()}", 0.7 * t),
        (
            "FOR DEMONSTRATION - NOT FOR CONSTRUCTION   SCALE: N.T.S.   SHEET 1 OF 1",
            0.7 * t,
        ),
    ]
    row_h = metrics.title_h / len(rows)
    msp.add_lwpolyline(
        [
            (x0, y_bottom),
            (x_right, y_bottom),
            (x_right, y_bottom + metrics.title_h),
            (x0, y_bottom + metrics.title_h),
        ],
        close=True,
        dxfattribs={"layer": LAYER_SHEET},
    )
    for index in range(1, len(rows)):
        y = y_bottom + index * row_h
        msp.add_line((x0, y), (x_right, y), dxfattribs={"layer": LAYER_SHEET})
    for index, (content_text, height) in enumerate(rows):
        row_top = y_bottom + metrics.title_h - index * row_h
        add_text(
            msp,
            content_text,
            at=(x0 + 0.8 * t, row_top - row_h + 0.55 * t),
            height=height,
        )
