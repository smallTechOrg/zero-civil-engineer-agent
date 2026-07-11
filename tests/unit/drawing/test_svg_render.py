"""ga.svg — rendered from the same DXF document, non-empty, searchable text."""

from ga_test_helpers import sized


def test_svg_is_nonempty_wellformed_and_over_5kb(canonical_svg):
    assert canonical_svg.lstrip().startswith("<?xml")
    assert "<svg" in canonical_svg
    assert len(canonical_svg.encode("utf-8")) > 5 * 1024


def test_svg_contains_text_elements_for_dimensions_notes_and_title(canonical_svg):
    assert "<text" in canonical_svg
    assert ">4000<" in canonical_svg  # clear span, exact element content
    assert ">32050<" in canonical_svg  # barrel length, exact element content
    assert "BOX CULVERT" in canonical_svg  # title block
    assert "GENERAL NOTES" in canonical_svg  # notes block


def test_svg_draws_visible_geometry_on_a_white_sheet(canonical_svg):
    assert "<path" in canonical_svg
    assert "#ffffff" in canonical_svg.lower()


def test_svg_structure_is_stable_for_identical_inputs(tmp_path):
    """Byte-equality is out of scope: ezdxf deliberately jiggles hatch-pattern
    origins with random offsets. The meaningful invariants — the searchable
    text layer and the number of drawn elements — must not vary."""
    import datetime as dt
    import re

    from drawing.ga import generate_ga

    params, geometry = sized(4.0, 3.0, 2.5)
    fixed_date = dt.date(2026, 7, 10)

    first = generate_ga(
        geometry, params, tmp_path / "a", run_id="run-x", drawing_date=fixed_date
    )
    second = generate_ga(
        geometry, params, tmp_path / "b", run_id="run-x", drawing_date=fixed_date
    )

    svg_first = first["ga_svg"].read_text()
    svg_second = second["ga_svg"].read_text()

    def text_layer(svg: str) -> str:
        match = re.search(r'<g class="dxf-text-layer".*?</g>', svg, re.DOTALL)
        assert match, "searchable text layer missing"
        return match.group()

    assert text_layer(svg_first) == text_layer(svg_second)
    assert svg_first.count("<path") == svg_second.count("<path")
    assert svg_first.count("<text") == svg_second.count("<text")


def test_visible_glyphs_render_without_system_fonts():
    """Deploy-parity regression: on a container with NO system fonts, ezdxf must
    still render TEXT/MTEXT as glyph paths (not empty placeholder boxes).

    render_svg registers matplotlib's bundled DejaVu Sans with ezdxf's font
    manager, so glyphs resolve regardless of host fonts. We simulate the
    fontless container by clearing the font manager, then confirm a text-bearing
    document renders substantial glyph path data with no "no fonts" fallback.
    """
    import ezdxf
    from ezdxf.fonts import fonts

    from drawing.svg_render import _ensure_render_fonts, render_svg

    # Simulate a fontless deploy container, then let render_svg's font bootstrap
    # (invoked internally) restore a usable font. Reset the once-cache first.
    _ensure_render_fonts.cache_clear()
    fonts.font_manager.clear()

    doc = ezdxf.new()
    doc.modelspace().add_text("SPAN 4000", height=2).set_placement((0, 0))
    svg = render_svg(doc)

    # The searchable (invisible) layer is one <text> element; the VISIBLE text is
    # glyph paths. Total path 'd' data must be far larger than an empty box (~60
    # chars); a real glyph run is hundreds+ of chars.
    import re

    d_chars = sum(len(m) for m in re.findall(r'd="([^"]*)"', svg))
    assert d_chars > 500, f"expected glyph path data, got {d_chars} chars (boxes?)"
