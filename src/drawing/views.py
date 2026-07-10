"""The three GA views — cross-section (B-B), longitudinal section (A-A), plan.

Every coordinate and every dimension defpoint is built from BoxMM (the
mm-converted BoxGeometry), so the drawn geometry and the dimension read-back
stay structurally consistent with the calc (spec/capabilities/ga-drawing.md).
"""

from __future__ import annotations

from ezdxf.enums import TextEntityAlignment
from ezdxf.lldxf import const
from ezdxf.layouts import Modelspace

from drawing.sheet import (
    DIMSTYLE_GA,
    LAYER_CL,
    LAYER_DIM,
    LAYER_HATCH,
    LAYER_HIDDEN,
    LAYER_OUTLINE,
    BoxMM,
    SheetMetrics,
    add_text,
)

Point = tuple[float, float]

HATCH_PATTERN = "ANSI31"


def draw_cross_section(
    msp: Modelspace, box: BoxMM, metrics: SheetMetrics, origin: Point
) -> None:
    """SECTION B-B — through the box: clear opening, walls, slabs, haunches."""
    t = metrics.text_h
    w, h = box.w_ext, box.h_ext
    tw, tt, tb, hn = box.t_wall, box.t_top, box.t_bot, box.haunch
    x0, x1 = tw, tw + box.span
    y0, y1 = tb, tb + box.height

    outer = [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)]
    if hn > 0:
        inner = [
            (x0 + hn, y0),
            (x1 - hn, y0),
            (x1, y0 + hn),
            (x1, y1 - hn),
            (x1 - hn, y1),
            (x0 + hn, y1),
            (x0, y1 - hn),
            (x0, y0 + hn),
        ]
    else:
        inner = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

    _outline(msp, _shift_all(origin, outer))
    _outline(msp, _shift_all(origin, inner))
    _hatch(
        msp,
        _shift_all(origin, outer),
        inner=_shift_all(origin, inner),
        scale=max(1.0, 0.2 * t),
    )
    msp.add_line(
        _shift(origin, w / 2, -1.5 * t),
        _shift(origin, w / 2, h + 2.0 * t),
        dxfattribs={"layer": LAYER_CL},
    )

    # Top: wall thickness, then the haunch leg on a staggered row.
    _dim(
        msp,
        base=_shift(origin, tw / 2, h + metrics.dim_off1),
        p1=_shift(origin, 0, h),
        p2=_shift(origin, tw, h),
    )
    if hn > 0:
        _dim(
            msp,
            base=_shift(origin, tw + hn / 2, h + metrics.dim_off2),
            p1=_shift(origin, tw, h),
            p2=_shift(origin, tw + hn, h),
        )
    # Bottom: clear span, then external width.
    _dim(
        msp,
        base=_shift(origin, (x0 + x1) / 2, -metrics.dim_off1),
        p1=_shift(origin, x0, 0),
        p2=_shift(origin, x1, 0),
    )
    _dim(
        msp,
        base=_shift(origin, w / 2, -metrics.dim_off2),
        p1=_shift(origin, 0, 0),
        p2=_shift(origin, w, 0),
    )
    # Left: clear height, then external height.
    _dim(
        msp,
        base=_shift(origin, -metrics.dim_off1, (y0 + y1) / 2),
        p1=_shift(origin, 0, y0),
        p2=_shift(origin, 0, y1),
        angle=90,
    )
    _dim(
        msp,
        base=_shift(origin, -metrics.dim_off2, h / 2),
        p1=_shift(origin, 0, 0),
        p2=_shift(origin, 0, h),
        angle=90,
    )
    # Right: bottom and top slab thicknesses.
    _dim(
        msp,
        base=_shift(origin, w + metrics.dim_off1, tb / 2),
        p1=_shift(origin, w, 0),
        p2=_shift(origin, w, tb),
        angle=90,
    )
    _dim(
        msp,
        base=_shift(origin, w + metrics.dim_off1, h - tt / 2),
        p1=_shift(origin, w, h - tt),
        p2=_shift(origin, w, h),
        angle=90,
    )

    _view_title(
        msp,
        metrics,
        at=_shift(origin, w / 2, -(metrics.dim_off2 + 3.0 * t)),
        title="SECTION B-B",
        subtitle="(CROSS-SECTION)  SCALE: N.T.S.",
    )


def draw_longitudinal_section(
    msp: Modelspace,
    box: BoxMM,
    metrics: SheetMetrics,
    origin: Point,
    formation_width_mm: float,
) -> None:
    """SECTION A-A — along the barrel: box profile, slabs, fill and formation."""
    t = metrics.text_h
    length, h = box.l_barrel, box.h_ext
    tt, tb, cushion = box.t_top, box.t_bot, box.cushion
    formation_level = h + cushion

    _outline(msp, _shift_all(origin, [(0.0, 0.0), (length, 0.0), (length, h), (0.0, h)]))
    msp.add_line(
        _shift(origin, 0, tb), _shift(origin, length, tb), dxfattribs={"layer": LAYER_OUTLINE}
    )
    msp.add_line(
        _shift(origin, 0, h - tt),
        _shift(origin, length, h - tt),
        dxfattribs={"layer": LAYER_OUTLINE},
    )
    band_scale = max(1.0, 0.3 * t)
    _hatch(
        msp,
        _shift_all(origin, [(0.0, h - tt), (length, h - tt), (length, h), (0.0, h)]),
        scale=band_scale,
    )
    _hatch(
        msp,
        _shift_all(origin, [(0.0, 0.0), (length, 0.0), (length, tb), (0.0, tb)]),
        scale=band_scale,
    )

    # Embankment profile: slopes meet the box base exactly at the barrel ends —
    # the geometric reason the barrel is as long as it is.
    xf1 = max(0.0, (length - formation_width_mm) / 2)
    xf2 = min(length, xf1 + formation_width_mm)
    for start, end in (
        ((0.0, 0.0), (xf1, formation_level)),
        ((xf1, formation_level), (xf2, formation_level)),
        ((xf2, formation_level), (length, 0.0)),
    ):
        msp.add_line(
            _shift(origin, *start), _shift(origin, *end), dxfattribs={"layer": LAYER_OUTLINE}
        )
    add_text(
        msp,
        "FORMATION LEVEL",
        at=_shift(origin, xf1 + 2.0 * t, formation_level + 0.7 * t),
        height=0.7 * t,
    )
    msp.add_line(
        _shift(origin, length / 2, formation_level + 3.0 * t),
        _shift(origin, length / 2, h - 2.0 * t),
        dxfattribs={"layer": LAYER_CL},
    )
    add_text(
        msp,
        "CL TRACK",
        at=_shift(origin, length / 2 + 0.6 * t, formation_level + 2.2 * t),
        height=0.7 * t,
    )

    if cushion > 0:
        xd = length / 2 + 8.0 * t
        _dim(
            msp,
            base=_shift(origin, xd + metrics.dim_off1, h + cushion / 2),
            p1=_shift(origin, xd, h),
            p2=_shift(origin, xd, formation_level),
            angle=90,
        )
    _dim(
        msp,
        base=_shift(origin, -metrics.dim_off1, h / 2),
        p1=_shift(origin, 0, 0),
        p2=_shift(origin, 0, h),
        angle=90,
    )

    _view_title(
        msp,
        metrics,
        at=_shift(origin, length / 2, -3.5 * t),
        title="SECTION A-A",
        subtitle="(LONGITUDINAL SECTION)  SCALE: N.T.S.",
    )


def draw_plan(msp: Modelspace, box: BoxMM, metrics: SheetMetrics, origin: Point) -> None:
    """PLAN — top view of the barrel with wall faces hidden under the top slab."""
    t = metrics.text_h
    length, w = box.l_barrel, box.w_ext
    tw = box.t_wall

    _outline(msp, _shift_all(origin, [(0.0, 0.0), (length, 0.0), (length, w), (0.0, w)]))
    for y in (tw, w - tw):
        msp.add_line(
            _shift(origin, 0, y), _shift(origin, length, y), dxfattribs={"layer": LAYER_HIDDEN}
        )

    # Section A-A cut along the barrel axis.
    msp.add_line(
        _shift(origin, -2.0 * t, w / 2),
        _shift(origin, length + 2.0 * t, w / 2),
        dxfattribs={"layer": LAYER_CL},
    )
    for x in (-3.4 * t, length + 3.4 * t):
        add_text(
            msp,
            "A",
            at=_shift(origin, x, w / 2),
            height=t,
            align=TextEntityAlignment.MIDDLE_CENTER,
        )
    # Section B-B cut across the barrel at the track centreline.
    msp.add_line(
        _shift(origin, length / 2, -2.0 * t),
        _shift(origin, length / 2, w + 2.0 * t),
        dxfattribs={"layer": LAYER_CL},
    )
    for y in (w + 3.4 * t, -(metrics.dim_off1 + 2.5 * t)):
        add_text(
            msp,
            "B",
            at=_shift(origin, length / 2, y),
            height=t,
            align=TextEntityAlignment.MIDDLE_CENTER,
        )

    # Barrel length belongs on the plan; the box widths are dimensioned in
    # SECTION B-B, keeping the section-cut labels clear of dimension columns.
    _dim(
        msp,
        base=_shift(origin, length / 2, -metrics.dim_off1),
        p1=_shift(origin, 0, 0),
        p2=_shift(origin, length, 0),
    )

    _view_title(
        msp,
        metrics,
        at=_shift(origin, length / 2, -(metrics.dim_off1 + 5.5 * t)),
        title="PLAN",
        subtitle="SCALE: N.T.S.",
    )


def _shift(origin: Point, x: float, y: float) -> Point:
    return (origin[0] + x, origin[1] + y)


def _shift_all(origin: Point, points: list[Point]) -> list[Point]:
    return [_shift(origin, x, y) for x, y in points]


def _outline(msp: Modelspace, points: list[Point]) -> None:
    msp.add_lwpolyline(points, close=True, dxfattribs={"layer": LAYER_OUTLINE})


def _hatch(
    msp: Modelspace,
    outer: list[Point],
    *,
    inner: list[Point] | None = None,
    scale: float,
) -> None:
    hatch = msp.add_hatch(
        dxfattribs={"layer": LAYER_HATCH, "hatch_style": const.HATCH_STYLE_NESTED}
    )
    hatch.set_pattern_fill(HATCH_PATTERN, scale=scale)
    hatch.paths.add_polyline_path(
        outer, is_closed=True, flags=const.BOUNDARY_PATH_EXTERNAL
    )
    if inner:
        hatch.paths.add_polyline_path(
            inner, is_closed=True, flags=const.BOUNDARY_PATH_OUTERMOST
        )


def _dim(msp: Modelspace, *, base: Point, p1: Point, p2: Point, angle: float = 0) -> None:
    dimension = msp.add_linear_dim(
        base=base,
        p1=p1,
        p2=p2,
        angle=angle,
        dimstyle=DIMSTYLE_GA,
        dxfattribs={"layer": LAYER_DIM},
    )
    dimension.render()


def _view_title(
    msp: Modelspace,
    metrics: SheetMetrics,
    *,
    at: Point,
    title: str,
    subtitle: str,
) -> None:
    t = metrics.text_h
    add_text(msp, title, at=at, height=1.1 * t, align=TextEntityAlignment.MIDDLE_CENTER)
    add_text(
        msp,
        subtitle,
        at=(at[0], at[1] - 1.7 * t),
        height=0.7 * t,
        align=TextEntityAlignment.MIDDLE_CENTER,
    )
