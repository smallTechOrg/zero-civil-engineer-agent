"""DXF → SVG rendering — same-document fidelity plus a searchable text layer.

The visible drawing (outlines, hatches, dimension glyphs) is rendered by
ezdxf's own SVGBackend from the very document written to ga.dxf — the
architecture's fidelity rule (spec/architecture.md#dxf--svg-server-side-rendering).
ezdxf outputs text as filled glyph paths (font-independent), so an additional
invisible-but-selectable ``<text>`` layer carrying the same strings at the same
sheet positions is appended, keeping the SVG machine-searchable (dimension
values, notes, title block) for the UI and downstream assertions.
"""

from __future__ import annotations

from typing import Iterator, NamedTuple
from xml.sax.saxutils import escape

from drawing import _pil_compat  # noqa: F401  (PIL placeholder when Pillow absent)
from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.config import (
    BackgroundPolicy,
    Configuration,
    LineweightPolicy,
)
from ezdxf.addons.drawing.layout import Page
from ezdxf.addons.drawing.svg import SVGBackend
from ezdxf.document import Drawing
from ezdxf.math import Matrix44


def render_svg(doc: Drawing) -> str:
    """Render the modelspace to SVG and append the searchable text layer."""
    context = RenderContext(doc)
    backend = SVGBackend()
    # RELATIVE lineweights: the model-space sheet is metres across, so absolute
    # millimetre pen widths would render as invisible hairlines.
    config = Configuration(
        background_policy=BackgroundPolicy.WHITE,
        lineweight_policy=LineweightPolicy.RELATIVE,
    )
    Frontend(context, backend, config=config).draw_layout(doc.modelspace())
    svg = backend.get_string(Page(0, 0))  # auto page size from content
    text_layer = _searchable_text_layer(doc, backend.transformation_matrix)
    if text_layer:
        svg = svg.replace("</svg>", f"{text_layer}</svg>", 1)
    return svg


class _TextItem(NamedTuple):
    content: str
    x: float
    y: float
    height: float
    rotation: float
    anchor: str


def _searchable_text_layer(doc: Drawing, matrix: Matrix44 | None) -> str:
    if matrix is None:
        return ""
    scale = (matrix.transform((1, 0, 0)) - matrix.transform((0, 0, 0))).magnitude
    parts = [
        '<g class="dxf-text-layer" fill="#000000" fill-opacity="0"'
        ' font-family="Arial, sans-serif">'
    ]
    for item in _text_items(doc):
        position = matrix.transform((item.x, item.y, 0))
        font_size = max(1.0, item.height * scale)
        attributes = (
            f'x="{position.x:.1f}" y="{position.y:.1f}" font-size="{font_size:.1f}"'
        )
        if item.anchor != "start":
            attributes += f' text-anchor="{item.anchor}"'
        if abs(item.rotation) > 0.01:
            # model space rotates counter-clockwise, SVG y points down
            attributes += (
                f' transform="rotate({-item.rotation:.1f}'
                f' {position.x:.1f} {position.y:.1f})"'
            )
        parts.append(f"<text {attributes}>{escape(item.content)}</text>")
    parts.append("</g>")
    return "".join(parts) if len(parts) > 2 else ""


def _text_items(doc: Drawing) -> Iterator[_TextItem]:
    msp = doc.modelspace()
    yield from _entity_text_items(msp)
    for dimension in msp.query("DIMENSION"):
        block_name = dimension.dxf.get("geometry", None)
        if block_name and block_name in doc.blocks:
            yield from _entity_text_items(doc.blocks[block_name])


def _entity_text_items(layout) -> Iterator[_TextItem]:
    for entity in layout.query("TEXT"):
        content = entity.dxf.text.strip()
        if not content:
            continue
        uses_align_point = entity.dxf.halign != 0 and entity.dxf.hasattr("align_point")
        position = entity.dxf.align_point if uses_align_point else entity.dxf.insert
        yield _TextItem(
            content=content,
            x=position.x,
            y=position.y,
            height=entity.dxf.height,
            rotation=entity.dxf.get("rotation", 0.0),
            anchor={1: "middle", 4: "middle", 2: "end"}.get(entity.dxf.halign, "start"),
        )
    for entity in layout.query("MTEXT"):
        content = entity.plain_text().strip()
        if not content:
            continue
        column = (entity.dxf.attachment_point - 1) % 3
        yield _TextItem(
            content=content,
            x=entity.dxf.insert.x,
            y=entity.dxf.insert.y,
            height=entity.dxf.char_height,
            rotation=entity.dxf.get("rotation", 0.0),
            anchor={0: "start", 1: "middle", 2: "end"}[column],
        )
