"""DXF dimension read-back — every governing value comes from BoxGeometry exactly."""

import ezdxf

from ga_test_helpers import count_close, dimension_texts_of, measurements_of, sized


def test_canonical_dimension_text_prints_the_millimetre_values(canonical_doc):
    """The sheet must PRINT the mm values, not just measure them — a dimstyle
    dimlfac scaling factor would corrupt every printed value while leaving
    get_measurement() untouched."""
    texts = dimension_texts_of(canonical_doc)

    expected = {"4000", "3000", "400", "350", "150", "4700", "3800", "32050", "2500"}
    assert expected <= texts, f"missing printed dimension values: {expected - texts}"


def test_canonical_governing_dimensions_read_back_exactly(canonical_doc):
    values = measurements_of(canonical_doc)

    assert count_close(values, 4000) >= 1  # clear span
    assert count_close(values, 3000) >= 1  # clear height
    assert count_close(values, 400) >= 2  # top + bottom slab thickness
    assert count_close(values, 350) >= 1  # wall thickness
    assert count_close(values, 150) >= 1  # haunch leg
    assert count_close(values, 4700) >= 1  # external width
    assert count_close(values, 3800) >= 1  # external height
    assert count_close(values, 32050) >= 1  # barrel length
    assert count_close(values, 2500) >= 1  # cushion / fill


def test_refinement_cushion_2500_to_4000_updates_the_fill_dimension(tmp_path):
    from drawing.ga import generate_ga

    params_before, geometry_before = sized(4.5, 3.0, 2.5)
    params_after, geometry_after = sized(4.5, 3.0, 4.0)

    before = generate_ga(geometry_before, params_before, tmp_path / "before")
    after = generate_ga(geometry_after, params_after, tmp_path / "after")

    values_before = measurements_of(ezdxf.readfile(before["ga_dxf"]))
    values_after = measurements_of(ezdxf.readfile(after["ga_dxf"]))

    assert count_close(values_before, 2500) >= 1
    assert count_close(values_after, 2500) == 0
    assert count_close(values_after, 4000) >= 1  # the new fill value
    # the unchanged clear span still reads back in both drawings
    assert count_close(values_before, 4500) >= 1
    assert count_close(values_after, 4500) >= 1


def test_canonical_refinement_swaps_fill_where_2500_was_before(tmp_path):
    from drawing.ga import generate_ga

    params_before, geometry_before = sized(4.0, 3.0, 2.5)
    params_after, geometry_after = sized(4.0, 3.0, 4.0)

    before = generate_ga(geometry_before, params_before, tmp_path / "before")
    after = generate_ga(geometry_after, params_after, tmp_path / "after")

    values_before = measurements_of(ezdxf.readfile(before["ga_dxf"]))
    values_after = measurements_of(ezdxf.readfile(after["ga_dxf"]))

    assert count_close(values_before, 2500) >= 1
    assert count_close(values_after, 2500) == 0
    # span already reads 4000; the 4.0 m fill adds one more 4000 mm dimension
    assert count_close(values_after, 4000) == count_close(values_before, 4000) + 1
