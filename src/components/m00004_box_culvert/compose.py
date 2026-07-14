"""M-00004 review-stage composed GA sheet + downloadable bundle.

`compose(params, geometry, out_dir, run_id)` is the single M-00004-only review
hook (invoked by the graph `review` node inside a non-fatal try/except by the
wiring slice). It is side-effect-free outside ``out_dir`` and depends on NO
import-time state — it reads the per-diagram DXFs already on disk and produces:

* ``m00004_ga_sheet.pdf`` — a composed A1-landscape GA sheet (matplotlib +
  ezdxf's matplotlib backend). The six drawings (elevation, cross-section, plan,
  curtain wall, return wall, typical details) are positioned in the M-00004 GA
  layout, alongside the notations glossary, notes block, bar-bending table,
  haunch table, a material-specs / RDSO title block and a bold
  PROVISIONAL / NOT-FOR-CONSTRUCTION strip. Every rendered material value comes
  from the single geometry/param source (`geometry.concrete_grade_resolved`,
  `params.steel_grade`). A missing per-diagram DXF degrades to a labelled empty
  panel rather than an error.
* ``m00004_bundle.zip`` — via `bundle.build_bundle` (every DXF + STEP on disk).

Returns ``{"m00004_ga_sheet": Path, "m00004_bundle": Path}`` — the exact dict the
wiring slice re-emits as review artefacts.

Headless-safe: matplotlib is forced onto the non-interactive ``Agg`` backend and
every figure is closed after use.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless / server-safe, before pyplot is imported

import ezdxf  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from ezdxf.addons.drawing import Frontend, RenderContext  # noqa: E402
from ezdxf.addons.drawing.config import BackgroundPolicy, Configuration  # noqa: E402
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend  # noqa: E402
from matplotlib.gridspec import GridSpec  # noqa: E402

from components.base import coerce  # noqa: E402
from components.m00004_box_culvert import bundle  # noqa: E402
from components.m00004_box_culvert.params import (  # noqa: E402
    CLEAR_COVER_MM,
    M00004Geometry,
    M00004Params,
)

GA_SHEET_FILENAME = "m00004_ga_sheet.pdf"

_INK = "#1a1a1a"
_PROV_RED = "#a01010"
_NFC = "NOT FOR CONSTRUCTION"
_CAVEAT = "PROVISIONAL  -  NOT FOR CONSTRUCTION  -  verify every value against RDSO/M-00004"

# (dxf stem, panel title, gridspec row-slice, gridspec col-slice).
# Four horizontal bands (each 3 of 12 rows) x three columns (wide 0-6, mid 6-9,
# narrow 9-12). The six drawings sit like the real GA sheet — elevation +
# cross-section across the top, plan across the middle, secondary details along
# the third band — with the four reference tables filling the remaining cells.
_ROWS = 12
_COLS = 12
_PANELS = (
    ("elevation", "1. LONGITUDINAL ELEVATION", slice(0, 3), slice(0, 6)),
    ("cross_section", "2. CROSS-SECTION (a1..h)", slice(0, 3), slice(6, 9)),
    ("notations", "3. NOTATIONS", slice(0, 3), slice(9, 12)),
    ("plan", "4. PART-PLAN", slice(3, 6), slice(0, 6)),
    ("curtain_wall", "5. CURTAIN / DROP WALL", slice(3, 6), slice(6, 9)),
    ("return_wall", "6. RETURN / WING WALL", slice(3, 6), slice(9, 12)),
    ("typical_details", "7. TYPICAL DETAILS", slice(6, 9), slice(0, 6)),
    ("bar_shape_table", "8. BAR-BENDING SCHEDULE", slice(6, 9), slice(6, 9)),
    ("haunch_table", "9. HAUNCH TABLE", slice(6, 9), slice(9, 12)),
    ("notes", "10. NOTES", slice(9, 12), slice(0, 6)),
)
# The material-specs / RDSO title block occupies the final bottom-right block.
_TITLE_ROWS = slice(9, 12)
_TITLE_COLS = slice(6, 12)

# ezdxf render configuration: white paper background so ACI-7 lines resolve to ink.
_RENDER_CFG = Configuration(background_policy=BackgroundPolicy.WHITE)


def compose(
    params: M00004Params,
    geometry: M00004Geometry,
    out_dir: Path,
    run_id: str | None = None,
    *,
    drawing_date: dt.date | None = None,
) -> dict[str, Path]:
    """Produce the composed GA sheet + bundle in ``out_dir``.

    Returns ``{"m00004_ga_sheet": <pdf Path>, "m00004_bundle": <zip Path>}``.
    """
    params = coerce(M00004Params, params)
    geometry = coerce(M00004Geometry, geometry)
    drawing_date = drawing_date or dt.date.today()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ga_sheet = _render_ga_sheet(params, geometry, out_dir, run_id, drawing_date)
    zip_path = bundle.build_bundle(out_dir)
    return {"m00004_ga_sheet": ga_sheet, "m00004_bundle": zip_path}


# --------------------------------------------------------------------------- GA sheet
def _render_ga_sheet(
    params: M00004Params,
    geometry: M00004Geometry,
    out_dir: Path,
    run_id: str | None,
    drawing_date: dt.date,
) -> Path:
    pdf_path = out_dir / GA_SHEET_FILENAME
    fig = plt.figure(figsize=(33.1, 23.4), facecolor="white")  # A1 landscape (inches)
    try:
        gs = GridSpec(
            _ROWS,
            _COLS,
            figure=fig,
            left=0.012,
            right=0.988,
            top=0.925,
            bottom=0.012,
            wspace=0.28,
            hspace=0.6,
        )
        _draw_banner(fig)
        for stem, title, rows, cols in _PANELS:
            ax = fig.add_subplot(gs[rows, cols])
            _render_panel(ax, out_dir / f"{stem}.dxf", title)
        _title_block(
            fig.add_subplot(gs[_TITLE_ROWS, _TITLE_COLS]),
            params,
            geometry,
            run_id,
            drawing_date,
        )
        fig.savefig(pdf_path, format="pdf", facecolor="white")
    finally:
        plt.close(fig)
    return pdf_path


def _draw_banner(fig) -> None:
    """Bold full-width PROVISIONAL / NOT-FOR-CONSTRUCTION strip across the top."""
    fig.text(
        0.5,
        0.987,
        "RDSO/M-00004 STANDARD SINGLE BOX CULVERT  -  GENERAL ARRANGEMENT & REINFORCEMENT",
        ha="center",
        va="center",
        fontsize=20,
        fontweight="bold",
        color=_INK,
    )
    fig.patches.append(
        plt.Rectangle(
            (0.0, 0.948),
            1.0,
            0.022,
            transform=fig.transFigure,
            facecolor=_PROV_RED,
            edgecolor="none",
            zorder=5,
        )
    )
    fig.text(
        0.5,
        0.959,
        _CAVEAT,
        ha="center",
        va="center",
        fontsize=13,
        fontweight="bold",
        color="white",
        zorder=6,
    )


def _render_panel(ax, dxf_path: Path, title: str) -> None:
    """Render one on-disk DXF into ``ax``; degrade to a labelled empty panel."""
    ax.set_title(title, fontsize=11, fontweight="bold", color=_INK, loc="left", pad=4)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_edgecolor(_INK)
        spine.set_linewidth(0.8)

    if not dxf_path.is_file():
        ax.text(
            0.5,
            0.5,
            f"[{dxf_path.stem} unavailable]",
            ha="center",
            va="center",
            fontsize=10,
            color=_PROV_RED,
            transform=ax.transAxes,
        )
        return

    try:
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()
        backend = MatplotlibBackend(ax)
        Frontend(RenderContext(doc), backend, config=_RENDER_CFG).draw_layout(
            msp, finalize=True
        )
        ax.set_facecolor("white")
    except Exception as exc:  # pragma: no cover - defensive; a corrupt DXF must not abort
        ax.text(
            0.5,
            0.5,
            f"[{dxf_path.stem} render error]\n{type(exc).__name__}",
            ha="center",
            va="center",
            fontsize=9,
            color=_PROV_RED,
            transform=ax.transAxes,
        )


def _title_block(
    ax,
    params: M00004Params,
    geometry: M00004Geometry,
    run_id: str | None,
    drawing_date: dt.date,
) -> None:
    """Material specs + RDSO title block panel (single geometry/param source)."""
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_edgecolor(_INK)
        spine.set_linewidth(1.0)
    ax.set_title("11. MATERIALS & TITLE BLOCK", fontsize=11, fontweight="bold",
                 color=_INK, loc="left", pad=4)

    lines = [
        ("STANDARD", "RDSO/M-00004 single-cell box culvert"),
        ("CONFIG", geometry.config_id),
        ("ENTERED", f"{params.clear_span_m:g} x {params.clear_height_m:g} m clear, "
                    f"fill {params.cushion_m:g} m"),
        ("CONCRETE", f"{geometry.concrete_grade_resolved}  (PROVISIONAL)"),
        ("STEEL", params.steel_grade.value),
        ("EXPOSURE", params.exposure.value),
        ("CLEAR COVER", f"{CLEAR_COVER_MM:g} mm (assumed)"),
        ("THICKNESS", f"{geometry.thickness_mm:g} mm"),
        ("HAUNCH", f"{geometry.haunch_mm:g} x {geometry.haunch_mm:g} mm"),
        ("BARREL", f"{geometry.barrel_length_mm:g} mm"),
        ("RUN", run_id or "-"),
        ("DATE", drawing_date.isoformat()),
        ("SCALE", "N.T.S.   |   ALL DIMENSIONS IN mm"),
    ]
    y = 0.90
    step = 0.062
    for label, value in lines:
        ax.text(0.03, y, f"{label}:", fontsize=9, fontweight="bold", color=_INK,
                va="top", transform=ax.transAxes)
        ax.text(0.34, y, str(value), fontsize=9, color=_INK, va="top",
                transform=ax.transAxes)
        y -= step

    ax.text(
        0.5,
        0.03,
        f"PROVISIONAL  -  {_NFC}",
        ha="center",
        va="bottom",
        fontsize=11,
        fontweight="bold",
        color="white",
        bbox={"facecolor": _PROV_RED, "edgecolor": "none", "pad": 4.0},
        transform=ax.transAxes,
    )
