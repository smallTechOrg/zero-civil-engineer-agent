"""Items 1–5 and 11 are RE-VERIFICATION, not restatement.

Each test corrupts one recorded value in a deep copy of the real run record
and proves the corresponding checklist item flips to NON_CONFORMITY_MAJOR —
i.e. the proof-check recomputes from primary sources and compares against
what the run recorded. Also covers the error path of an incomplete record.
"""

import pytest

from engine.loads import CASE_EP_ACTIVE
from proofcheck import run_checklist

MAJOR = "NON_CONFORMITY_MAJOR"


def _rerun(chain, out_dir, *, analysis=None, checks=None, fe=None):
    return run_checklist(
        params=chain.params,
        geometry=chain.geometry,
        analysis=analysis if analysis is not None else chain.analysis,
        checks=checks if checks is not None else chain.checks,
        fe=fe if fe is not None else chain.fe,
        ga_dxf_path=chain.ga["ga_dxf"],
        out_dir=out_dir,
    )


def test_corrupted_recorded_eudl_flips_item_2_to_major(canonical_chain, tmp_path):
    analysis = canonical_chain.analysis.model_copy(deep=True)
    step = next(
        s for s in analysis.trail if s.description.startswith("LL: EUDL for bending moment")
    )
    step.value += 25.0  # the recorded EUDL no longer matches the cited table

    result = _rerun(canonical_chain, tmp_path, analysis=analysis)

    assert result.items[1].severity == MAJOR
    assert result.verdict == "return_for_revision"


def test_corrupted_recorded_cda_flips_item_3_to_major(canonical_chain, tmp_path):
    analysis = canonical_chain.analysis.model_copy(deep=True)
    step = next(
        s
        for s in analysis.trail
        if s.description.startswith("LL: coefficient of dynamic augment")
    )
    step.value += 0.25  # canonical CDA is 0.0 (cushion 2.5 m kills the augment)

    result = _rerun(canonical_chain, tmp_path, analysis=analysis)

    assert result.items[2].severity == MAJOR
    assert result.verdict == "return_for_revision"


def test_missing_earth_pressure_case_flips_item_4_to_major(canonical_chain, tmp_path):
    analysis = canonical_chain.analysis.model_copy(deep=True)
    analysis.load_cases = [c for c in analysis.load_cases if c.name != CASE_EP_ACTIVE]

    result = _rerun(canonical_chain, tmp_path, analysis=analysis)

    assert result.items[3].severity == MAJOR
    assert CASE_EP_ACTIVE in result.items[3].detail
    assert result.verdict == "return_for_revision"


def test_corrupted_recorded_loaded_length_flips_item_5_to_major(canonical_chain, tmp_path):
    analysis = canonical_chain.analysis.model_copy(deep=True)
    step = next(
        s
        for s in analysis.trail
        if s.description.startswith("LL: dispersed loaded length for EUDL")
    )
    step.value += 0.5  # recorded dispersal no longer matches the documented formula

    result = _rerun(canonical_chain, tmp_path, analysis=analysis)

    assert result.items[4].severity == MAJOR
    assert result.verdict == "return_for_revision"

    # the other re-verification items stay unaffected — the corruption is localised
    assert result.items[1].severity == "PASS"
    assert result.items[2].severity == "PASS"


def test_fe_tolerance_breach_flips_item_11_to_major(canonical_chain, tmp_path):
    fe = canonical_chain.fe.model_copy(
        update={"within_tolerance": False, "agreement_pct": 8.7}
    )

    result = _rerun(canonical_chain, tmp_path, fe=fe)

    assert result.items[10].severity == MAJOR
    assert result.fe_agreement_pct == pytest.approx(8.7)
    assert result.verdict == "return_for_revision"


def test_empty_check_record_makes_items_6_to_10_major_not_a_crash(canonical_chain, tmp_path):
    """Error path: an unauditable record is itself a major finding."""
    result = _rerun(canonical_chain, tmp_path, checks=[])

    for index in (5, 6, 7, 8, 9):  # items 6..10
        assert result.items[index].severity == MAJOR, f"item {index + 1}"
    assert result.verdict == "return_for_revision"
