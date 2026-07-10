"""Validation Fixture V1 — 25t Loading-2008 EUDL/CDA spot checks (irs-engine.md).

The spot values below are an INDEPENDENT second transcription of the table rows —
kept as literals in this file, never imported from the module under test. Both
transcriptions must be verified against the source PDF by an IR engineer before
demo day; this fixture guards against drift between module and fixture and
against any edit that breaks the engineering invariants.
"""

import pytest

from engine.loading import get_loading_standard

AXLE_LOAD_KN = 245.25  # 25.0 t x 9.81 — the standard's namesake axle

# Independent spot transcription: loaded length (m) -> EUDL (kN, per track, BG).
SPOT_EUDL_BM_KN = {
    1.0: 490.5,
    2.0: 490.5,
    3.0: 490.5,
    4.0: 551.8,
    5.0: 649.9,
    8.0: 971.4,
    12.0: 1293.4,
    20.0: 1872.3,
    30.0: 2817.4,
}
SPOT_EUDL_SHEAR_KN = {
    1.0: 490.5,
    2.0: 490.5,
    3.0: 654.0,
    4.0: 735.8,
    5.0: 864.4,
    8.0: 1203.1,
    12.0: 1508.7,
    20.0: 2265.9,
    30.0: 3177.0,
}


@pytest.fixture
def std():
    return get_loading_standard("25t-2008")


def test_eudl_bm_matches_the_independent_spot_transcription(std):
    for loaded_length_m, expected_kn in SPOT_EUDL_BM_KN.items():
        assert std.eudl_bm_kn(loaded_length_m) == expected_kn, f"L={loaded_length_m} m"


def test_eudl_shear_matches_the_independent_spot_transcription(std):
    for loaded_length_m, expected_kn in SPOT_EUDL_SHEAR_KN.items():
        assert std.eudl_shear_kn(loaded_length_m) == expected_kn, f"L={loaded_length_m} m"


def test_eudl_bm_interpolates_linearly_between_adjacent_rows(std):
    # Adjacent published rows: 12.0 m -> 1293.4 kN and 13.0 m -> 1343.7 kN.
    assert std.eudl_bm_kn(12.5) == pytest.approx((1293.4 + 1343.7) / 2.0, rel=1e-12)
    assert std.eudl_bm_kn(12.25) == pytest.approx(1293.4 + 0.25 * (1343.7 - 1293.4), rel=1e-12)


def test_eudl_shear_interpolates_linearly_between_adjacent_rows(std):
    # Adjacent published rows: 4.0 m -> 735.8 kN and 4.5 m -> 796.9 kN.
    assert std.eudl_shear_kn(4.2) == pytest.approx(735.8 + 0.4 * (796.9 - 735.8), rel=1e-12)


@pytest.mark.parametrize("loaded_length_m", [0.99, 30.01, 0.0, -4.0])
def test_out_of_range_loaded_length_raises_a_clear_value_error(std, loaded_length_m):
    with pytest.raises(ValueError, match="outside"):
        std.eudl_bm_kn(loaded_length_m)
    with pytest.raises(ValueError, match="outside"):
        std.eudl_shear_kn(loaded_length_m)


def test_cda_matches_the_bridge_rules_formula_anchors(std):
    # CDA = 0.15 + 8/(6+L), Bridge Rules Cl. 2.4.1.1 (BG, single track).
    assert std.cda(6.0) == pytest.approx(0.15 + 8.0 / 12.0)  # ~0.8167
    assert std.cda(4.0) == pytest.approx(0.95)
    assert std.cda(20.0) == pytest.approx(0.15 + 8.0 / 26.0)


def test_cda_is_capped_at_one_for_short_loaded_lengths(std):
    assert std.cda(1.0) == 1.0
    assert std.cda(3.0) == 1.0  # 0.15 + 8/9 = 1.039 -> capped


def test_cda_cushion_reduction_follows_the_encoded_fill_rule(std):
    full = std.cda(4.0)

    assert std.cda(4.0, 0.0) == full  # zero cushion -> full CDA
    assert std.cda(4.0, 0.5) == full  # fill below 0.9 m -> no reduction
    assert std.cda(4.0, 0.9) == pytest.approx(full * (2.0 - 0.9) / 2.0)
    assert std.cda(4.0, 1.5) == pytest.approx(full * (2.0 - 1.5) / 2.0)
    assert std.cda(4.0, 2.0) == 0.0  # no dynamic augment at 2 m fill and beyond
    assert std.cda(4.0, 2.5) == 0.0


def test_cda_is_monotone_non_increasing_with_cushion_depth(std):
    cushions = [0.0, 0.3, 0.6, 0.89, 0.9, 1.0, 1.5, 1.99, 2.0, 3.0, 10.0]
    values = [std.cda(4.0, cushion_m) for cushion_m in cushions]

    assert all(later <= earlier for earlier, later in zip(values, values[1:]))
    assert all(value >= 0.0 for value in values)


def test_cda_rejects_nonpositive_length_and_negative_cushion(std):
    with pytest.raises(ValueError, match="positive"):
        std.cda(0.0)
    with pytest.raises(ValueError, match="positive"):
        std.cda(-2.0)
    with pytest.raises(ValueError, match="negative"):
        std.cda(4.0, -0.1)


def test_tables_cover_the_poc_range_and_stay_engineering_consistent(std):
    for table in (std.eudl_bm_table(), std.eudl_shear_table()):
        assert table[0].loaded_length_m <= 1.0
        assert table[-1].loaded_length_m >= 30.0
        assert len(table) >= 30  # dense enough for faithful linear interpolation

        lengths = [row.loaded_length_m for row in table]
        assert lengths == sorted(lengths) and len(set(lengths)) == len(lengths)

        eudls = [row.eudl_kn for row in table]
        assert all(b >= a for a, b in zip(eudls, eudls[1:]))  # monotone non-decreasing
        # bounded below by the single-axle equivalent (2 x 25t axle)
        assert min(eudls) >= 2 * AXLE_LOAD_KN

    # long lengths asymptote to >= trailing train intensity (~91.6 kN/m)
    assert std.eudl_bm_kn(30.0) / 30.0 >= 91.0


def test_needs_verification_flags_encode_transcription_honesty(std):
    for table in (std.eudl_bm_table(), std.eudl_shear_table()):
        flags = {row.needs_verification for row in table}
        assert flags == {True, False}  # anchors are pinned, the rest awaits PDF review
        for row in table:
            if row.loaded_length_m <= 2.0:
                assert row.needs_verification is False  # single-axle rows: 2 x axle exactly


def test_citation_carries_source_table_clauses_and_acs_level(std):
    citation = std.citation

    assert "Bridge Rules" in citation
    assert "25t" in citation
    assert "ACS" in citation  # correction-slip level is part of the citation
    assert "2.4.1.1" in citation  # CDA formula clause
    assert "EUDL" in citation


def test_no_road_or_building_code_citations_anywhere(std):
    citation = std.citation
    for forbidden in ("IS 456", "IS 800", "IRC "):
        assert forbidden not in citation
