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
