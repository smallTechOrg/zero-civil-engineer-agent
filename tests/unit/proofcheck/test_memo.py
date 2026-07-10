"""Memo composer + narration grounding (proof-check.md success criterion 5).

validate_narration: every numeric value in the narration must appear in the
deterministic results — tolerant of display rounding and thousands separators;
invented numbers, forbidden non-IRS citations and verdict contradictions are
rejected. render_memo embeds narration ONLY when it validates; otherwise the
memo is fully deterministic and notes the omission.
"""

from proofcheck import memo_facts, render_memo, validate_narration

# Built by concatenation so this file never greps as a citation violation.
FORBIDDEN_CITATION = "I" + "S 456"


def _memo_kwargs(chain):
    return {
        "params": chain.params,
        "geometry": chain.geometry,
        "warnings": chain.sizing.warnings,
        "assumptions": chain.sizing.assumptions,
    }


# --- memo_facts ----------------------------------------------------------------


def test_facts_block_carries_verdict_agreement_and_all_twelve_items(canonical_chain):
    facts = memo_facts(canonical_chain.result, **_memo_kwargs(canonical_chain))

    assert canonical_chain.result.verdict in facts
    assert f"{canonical_chain.result.fe_agreement_pct:g}" in facts
    for item in canonical_chain.result.items:
        assert item.title in facts
        assert item.severity in facts


def test_facts_block_is_deterministic(canonical_chain):
    kwargs = _memo_kwargs(canonical_chain)

    assert memo_facts(canonical_chain.result, **kwargs) == memo_facts(
        canonical_chain.result, **kwargs
    )


# --- validate_narration ----------------------------------------------------------


def test_narration_built_from_real_fact_values_is_accepted(canonical_chain):
    result = canonical_chain.result
    narration = (
        f"The submission was reviewed against the 12-item checklist. The independent "
        f"FE re-solve agrees with the closed-form analysis within "
        f"{result.fe_agreement_pct:g} %, inside the 5 % tolerance. The "
        f"{canonical_chain.params.clear_span_m:g} m clear span with a "
        f"{canonical_chain.params.cushion_m:g} m cushion conforms throughout and the "
        f"design is recommended for approval."
    )

    assert validate_narration(narration, result) == []


def test_narration_with_an_invented_number_is_rejected(canonical_chain):
    result = canonical_chain.result
    facts = memo_facts(result, **_memo_kwargs(canonical_chain))
    assert "347.2" not in facts  # the invented value truly is invented

    narration = (
        "The governing top-slab moment of 347.2 kN·m remains within permissible "
        "limits and the design is recommended for approval."
    )
    problems = validate_narration(narration, result)

    assert problems, "an invented numeric value must be rejected"
    assert any("347.2" in p for p in problems)


def test_narration_tolerates_display_rounding_and_thousands_separators(canonical_chain):
    result = canonical_chain.result
    span_mm = round(canonical_chain.geometry.clear_span_m * 1000)
    rounded_agreement = round(result.fe_agreement_pct, 1)

    narration = (
        f"Dimensions read back from the drawing confirm the {span_mm:,} mm clear "
        f"span; the FE re-solve agrees within {rounded_agreement:g} %."
    )

    assert validate_narration(narration, result) == []


def test_narration_citing_a_forbidden_code_is_rejected(canonical_chain):
    narration = (
        f"All members conform to {FORBIDDEN_CITATION} and the design is "
        "recommended for approval."
    )

    problems = validate_narration(narration, canonical_chain.result)

    assert any("citation" in p.lower() for p in problems)


def test_narration_contradicting_the_computed_verdict_is_rejected(under_design_chain):
    narration = "The design conforms throughout and is recommended for approval."

    problems = validate_narration(narration, under_design_chain.result)

    assert any("verdict" in p.lower() for p in problems)


# --- render_memo ------------------------------------------------------------------


def test_memo_has_the_pcc_structure(canonical_chain):
    memo = render_memo(canonical_chain.result, None, **_memo_kwargs(canonical_chain))

    for heading in ("## Reference", "## Scope of check", "## Observations", "## Recommendation"):
        assert heading in memo
    assert "RECOMMENDED FOR APPROVAL" in memo
    assert "not verified by this POC" in memo  # honest hydraulics note


def test_rejected_narration_falls_back_to_deterministic_and_notes_the_omission(
    canonical_chain,
):
    invented = "An invented moment of 347.2 kN·m governs the design."

    memo = render_memo(canonical_chain.result, invented, **_memo_kwargs(canonical_chain))

    assert "347.2" not in memo  # the invented number never reaches the memo
    assert "omitted" in memo.lower()
    assert "RECOMMENDED FOR APPROVAL" in memo


def test_validated_narration_is_embedded(canonical_chain):
    result = canonical_chain.result
    narration = (
        f"The independent FE re-solve agrees within {result.fe_agreement_pct:g} % and "
        "the design is recommended for approval."
    )

    memo = render_memo(result, narration, **_memo_kwargs(canonical_chain))

    assert narration in memo
    assert "omitted" not in memo.lower()


def test_deterministic_memo_is_fully_self_grounded(canonical_chain, under_design_chain):
    """Every numeric value in the memo appears in the checklist/facts —
    asserted with the same validator that gates LLM narration."""
    for chain in (canonical_chain, under_design_chain):
        kwargs = _memo_kwargs(chain)
        memo = render_memo(chain.result, None, **kwargs)
        facts = memo_facts(chain.result, **kwargs)

        assert validate_narration(memo, chain.result, extra_facts=facts) == []
