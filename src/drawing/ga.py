"""GA drawing generator — hand-validated parametric ezdxf template.

Public contract (pinned — the graph slice imports exactly this):

    from drawing.ga import generate_ga

    paths = generate_ga(geometry, params, out_dir, run_id=run_id)
    # writes out_dir/"ga.dxf" and out_dir/"ga.svg"
    # returns {"ga_dxf": Path, "ga_svg": Path}
    # raises InvalidGeometryError (a ValueError) on impossible geometry

Every dimension value on the sheet comes from BoxGeometry — the same source
the calc uses — so calc-vs-drawing consistency is structural
(spec/capabilities/ga-drawing.md). The SVG is rendered from the same document
that is written to ga.dxf (fidelity rule, spec/architecture.md).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from ezdxf.document import Drawing

from domain.culvert import BoxGeometry, CulvertParams
from drawing.sheet import (
    BoxMM,
    SheetMetrics,
    draw_frame_and_title_block,
    draw_general_notes,
    new_sheet_doc,
)
from drawing.svg_render import render_svg
from drawing.validation import validate_geometry
from drawing.views import draw_cross_section, draw_longitudinal_section, draw_plan

GA_DXF_NAME = "ga.dxf"
GA_SVG_NAME = "ga.svg"


def generate_ga(
    geometry: BoxGeometry,
    params: CulvertParams,
    out_dir: Path,
    run_id: str | None = None,
    *,
    drawing_date: dt.date | None = None,
) -> dict[str, Path]:
    """Generate the GA sheet as ga.dxf + ga.svg inside ``out_dir``.

    ``drawing_date`` pins the title-block date (defaults to today) so tests
    and regenerations stay deterministic.
    """
    validate_geometry(geometry)
    doc = _build_sheet(geometry, params, run_id, drawing_date or dt.date.today())

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dxf_path = out_dir / GA_DXF_NAME
    doc.saveas(dxf_path)
    svg_path = out_dir / GA_SVG_NAME
    svg_path.write_text(render_svg(doc), encoding="utf-8")
    return {"ga_dxf": dxf_path, "ga_svg": svg_path}


def _build_sheet(
    geometry: BoxGeometry,
    params: CulvertParams,
    run_id: str | None,
    drawing_date: dt.date,
) -> Drawing:
    """Arrange the three views, notes and title block on one auto-sized sheet.

    Layout (all gaps are multiples of the sheet text height, so the
    arrangement scales with the geometry):

        +----------------------------------------------------+
        |  SECTION A-A (longitudinal)      SECTION B-B       |
        |  PLAN (aligned under A-A)        GENERAL NOTES     |
        |                                       TITLE BLOCK  |
        +----------------------------------------------------+
    """
    box = BoxMM.from_geometry(geometry)
    metrics = SheetMetrics.for_box(box)
    doc = new_sheet_doc(metrics)
    msp = doc.modelspace()
    t = metrics.text_h

    plan_origin = (0.0, 0.0)
    # Above the plan: room for the plan's top B-label (4t) and the
    # longitudinal section's own view-title stack below its box (6.5t).
    long_origin = (0.0, box.w_ext + 4.0 * t + metrics.view_gap + 6.5 * t)
    # Right of both wide views: room for the plan's A-label (5.5t) and the
    # cross-section's left-hand dimension columns (11t); top-aligned with
    # the longitudinal section's formation level.
    cross_origin = (
        box.l_barrel + 5.5 * t + metrics.view_gap + 11.0 * t,
        long_origin[1] + box.cushion,
    )
    notes_origin = (
        cross_origin[0] - metrics.dim_off2,
        cross_origin[1] - 16.5 * t,
    )

    draw_plan(msp, box, metrics, plan_origin)
    draw_longitudinal_section(
        msp,
        box,
        metrics,
        long_origin,
        formation_width_mm=round(params.formation_width_m * 1000.0, 3),
    )
    draw_cross_section(msp, box, metrics, cross_origin)
    draw_general_notes(msp, metrics, params, box, notes_origin)
    draw_frame_and_title_block(msp, metrics, box, run_id, drawing_date)
    return doc
