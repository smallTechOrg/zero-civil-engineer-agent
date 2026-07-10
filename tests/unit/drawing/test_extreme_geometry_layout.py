"""Extreme-but-valid geometry — the template auto-arranges inside the sheet frame."""

import ezdxf
import pytest

from ga_test_helpers import content_bbox_of, frame_bbox_of, measurements_of, sized

EXTREME_CASES = [
    pytest.param(1.0, 6.0, 2.5, id="tall-narrow-1x6"),
    pytest.param(8.0, 1.0, 2.5, id="wide-flat-8x1"),
    pytest.param(4.0, 3.0, 9.0, id="abnormally-high-fill-9m"),
    pytest.param(4.0, 3.0, 0.0, id="zero-cushion"),
]

FRAME_TOLERANCE_MM = 1.0


@pytest.mark.parametrize(("span", "height", "cushion"), EXTREME_CASES)
def test_extreme_geometry_audits_clean_and_stays_inside_the_frame(
    tmp_path, span, height, cushion
):
    from drawing.ga import generate_ga

    params, geometry = sized(span, height, cushion)

    paths = generate_ga(geometry, params, tmp_path)
    doc = ezdxf.readfile(paths["ga_dxf"])

    assert len(doc.audit().errors) == 0

    frame = frame_bbox_of(doc)
    content = content_bbox_of(doc)
    assert content.extmin.x >= frame.extmin.x - FRAME_TOLERANCE_MM
    assert content.extmin.y >= frame.extmin.y - FRAME_TOLERANCE_MM
    assert content.extmax.x <= frame.extmax.x + FRAME_TOLERANCE_MM
    assert content.extmax.y <= frame.extmax.y + FRAME_TOLERANCE_MM

    assert paths["ga_svg"].stat().st_size > 5 * 1024


def test_zero_cushion_skips_the_fill_dimension_but_keeps_the_rest(tmp_path):
    from drawing.ga import generate_ga

    params, geometry = sized(4.0, 3.0, 0.0)

    paths = generate_ga(geometry, params, tmp_path)
    values = measurements_of(ezdxf.readfile(paths["ga_dxf"]))

    assert len(values) > 8
    assert all(v > 0 for v in values)
