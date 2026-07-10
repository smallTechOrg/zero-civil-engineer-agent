"""Param-level unusual-value flags per spec/data.md: span > 6.0 m, cushion > 8.0 m."""

from domain.culvert import CulvertParams, unusual_value_warnings


def _params(**overrides) -> CulvertParams:
    base = {"clear_span_m": 4.0, "clear_height_m": 3.0, "cushion_m": 2.5}
    return CulvertParams(**{**base, **overrides})


def test_canonical_case_raises_no_warnings():
    warnings = unusual_value_warnings(_params())

    assert warnings == []


def test_span_above_six_metres_raises_a_warning():
    warnings = unusual_value_warnings(_params(clear_span_m=6.5))

    assert len(warnings) == 1
    assert "6.5" in warnings[0]
    assert "span" in warnings[0].lower()


def test_cushion_above_eight_metres_raises_a_warning():
    warnings = unusual_value_warnings(_params(cushion_m=8.5))

    assert len(warnings) == 1
    assert "8.5" in warnings[0]
    assert "cushion" in warnings[0].lower()


def test_both_unusual_values_raise_two_warnings():
    warnings = unusual_value_warnings(_params(clear_span_m=7.0, cushion_m=9.0))

    assert len(warnings) == 2


def test_thresholds_are_exclusive_boundary_values_stay_silent():
    warnings = unusual_value_warnings(_params(clear_span_m=6.0, cushion_m=8.0))

    assert warnings == []


def test_warnings_are_human_readable_strings():
    warnings = unusual_value_warnings(_params(clear_span_m=7.5))

    assert all(isinstance(w, str) and len(w) > 20 for w in warnings)
