"""Item 12 — calc-vs-drawing consistency is a REAL DXF read-back.

The tamper test (proof-check.md success criterion 3): corrupting one dimension
in a copy of ga.dxf must flip item 12 to NON_CONFORMITY_MAJOR — proving the
check measures the drawing, it does not restate the geometry.
"""

import math
import shutil
from pathlib import Path

import ezdxf

from proofcheck import run_checklist

MAJOR = "NON_CONFORMITY_MAJOR"


def _rerun_with_dxf(chain, ga_dxf_path: Path, out_dir: Path):
    return run_checklist(
        params=chain.params,
        geometry=chain.geometry,
        analysis=chain.analysis,
        checks=chain.checks,
        fe=chain.fe,
        ga_dxf_path=ga_dxf_path,
        out_dir=out_dir,
    )


def _tamper_one_dimension(source_dxf: Path, work_dir: Path, target_mm: float) -> Path:
    """Copy ga.dxf and shift one measured dimension by 37 mm via its defpoints."""
    work_dir.mkdir(parents=True, exist_ok=True)
    tampered = work_dir / "ga.dxf"
    shutil.copyfile(source_dxf, tampered)

    doc = ezdxf.readfile(tampered)
    dimension = next(
        d
        for d in doc.modelspace().query("DIMENSION")
        if abs(d.get_measurement() - target_mm) <= 1.0
    )
    angle = math.radians(float(dimension.dxf.get("angle", 0.0)))
    p3 = dimension.dxf.defpoint3
    dimension.dxf.defpoint3 = (
        p3.x + 37.0 * math.cos(angle),
        p3.y + 37.0 * math.sin(angle),
        0.0,
    )
    # the tamper is real: the measured geometry changed
    assert abs(dimension.get_measurement() - target_mm) > 30.0
    doc.saveas(tampered)
    return tampered


def test_item_12_passes_on_the_genuine_drawing(canonical_chain):
    item12 = canonical_chain.result.items[11]

    assert item12.severity == "PASS"
    # the read-back names the governing values it verified, in mm
    span_mm = round(canonical_chain.geometry.clear_span_m * 1000)
    assert str(span_mm) in item12.computed + item12.detail


def test_tampered_span_dimension_flips_item_12_to_major(canonical_chain, tmp_path):
    span_mm = canonical_chain.geometry.clear_span_m * 1000.0
    tampered = _tamper_one_dimension(
        canonical_chain.ga["ga_dxf"], tmp_path / "tampered", span_mm
    )

    result = _rerun_with_dxf(canonical_chain, tampered, tmp_path / "out")

    item12 = result.items[11]
    assert item12.severity == MAJOR
    assert result.verdict == "return_for_revision"
    # the finding names the discrepancy — a missing span and/or a stray measurement
    assert "clear span" in item12.detail.lower() or "4037" in item12.detail


def test_missing_drawing_file_is_a_major_finding_not_a_crash(canonical_chain, tmp_path):
    result = _rerun_with_dxf(
        canonical_chain, tmp_path / "nowhere" / "ga.dxf", tmp_path / "out"
    )

    item12 = result.items[11]
    assert item12.severity == MAJOR
    assert result.verdict == "return_for_revision"


def test_unreadable_drawing_file_is_a_major_finding_not_a_crash(canonical_chain, tmp_path):
    garbage = tmp_path / "ga.dxf"
    garbage.write_text("this is not a DXF file", encoding="utf-8")

    result = _rerun_with_dxf(canonical_chain, garbage, tmp_path / "out")

    assert result.items[11].severity == MAJOR
    assert result.verdict == "return_for_revision"
