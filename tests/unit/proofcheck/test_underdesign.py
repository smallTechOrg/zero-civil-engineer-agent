"""Hard case — the deliberately under-designed 200 mm top slab (demo act 3).

proof-check.md success criterion 2: items 7 AND 8 NON_CONFORMITY_MAJOR,
verdict return_for_revision, and the memo names the failing member and the
clause. Runs through the same REAL chain as the canonical case.
"""

from proofcheck import render_memo

MAJOR = "NON_CONFORMITY_MAJOR"


def test_items_7_and_8_are_major_and_the_verdict_returns_for_revision(under_design_chain):
    result = under_design_chain.result

    assert result.items[6].severity == MAJOR, result.items[6].detail  # flexure
    assert result.items[7].severity == MAJOR, result.items[7].detail  # shear
    assert result.verdict == "return_for_revision"


def test_the_failure_is_localised_to_the_thin_top_slab(under_design_chain):
    flexure = under_design_chain.result.items[6]

    assert "Top slab" in flexure.detail
    for untouched in ("Bottom slab", "Wall"):
        assert f"{untouched} fails" not in flexure.detail


def test_crack_item_10_degrades_but_only_as_a_minor_non_conformity(under_design_chain):
    # SLS follows the working-stress breach; the strength defect itself is
    # already graded MAJOR under item 7 — documented severity mapping.
    assert under_design_chain.result.items[9].severity == "NON_CONFORMITY_MINOR"


def test_memo_names_the_top_slab_and_the_clause(under_design_chain):
    chain = under_design_chain
    memo = render_memo(
        chain.result,
        narration=None,
        params=chain.params,
        geometry=chain.geometry,
        warnings=chain.sizing.warnings,
        assumptions=chain.sizing.assumptions,
    )

    assert "RETURN FOR REVISION" in memo
    assert "Top slab" in memo
    assert "IRS Concrete Bridge Code" in memo
    # the honest hydraulics scope note is always present
    assert "not verified by this POC" in memo
