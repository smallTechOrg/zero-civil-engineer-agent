"""Happy path — the canonical sound design through the REAL full chain.

Covers proof-check.md success criterion 1 (all 12 items PASS/OBSERVATION,
verdict recommended_for_approval, FE agreement <= 5%) and the PINNED
compliance.json shape the frontend is already built against.
"""

import json

from proofcheck import COMPLIANCE_FILENAME, ChecklistItem, ProofCheckResult

PINNED_ITEM_KEYS = [
    "item", "title", "clause", "requirement", "computed", "limit", "severity", "detail",
]
SEVERITIES = {"PASS", "OBSERVATION", "NON_CONFORMITY_MINOR", "NON_CONFORMITY_MAJOR"}
EXPECTED_TITLES = [
    "Loading standard & ACS level",
    "EUDL matches the cited table",
    "CDA incl. cushion reduction",
    "Load-case completeness",
    "Cushion dispersal",
    "Concrete grade & clear cover",
    "Flexure adequacy",
    "Shear adequacy",
    "Minimum steel & distribution",
    "Crack control / SLS",
    "Independent FE cross-check",
    "Calc-vs-drawing consistency",
]


def test_canonical_design_is_recommended_for_approval(canonical_chain):
    result: ProofCheckResult = canonical_chain.result

    assert result.verdict == "recommended_for_approval"
    assert result.fe_agreement_pct <= 5.0
    bad = [i for i in result.items if i.severity not in ("PASS", "OBSERVATION")]
    assert bad == [], [f"item {i.item} {i.title}: {i.severity} — {i.detail}" for i in bad]


def test_exactly_twelve_items_in_the_fixed_spec_order(canonical_chain):
    items: list[ChecklistItem] = canonical_chain.result.items

    assert [i.item for i in items] == list(range(1, 13))
    assert [i.title for i in items] == EXPECTED_TITLES


def test_every_item_row_is_fully_populated(canonical_chain):
    for item in canonical_chain.result.items:
        assert item.severity in SEVERITIES
        for field in ("title", "clause", "requirement", "computed", "limit", "detail"):
            value = getattr(item, field)
            assert isinstance(value, str) and value.strip(), f"item {item.item}.{field}"


def test_compliance_json_matches_the_pinned_shape_key_for_key(canonical_chain):
    path = canonical_chain.out_dir / COMPLIANCE_FILENAME

    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert list(payload.keys()) == ["items", "verdict", "fe_agreement_pct"]
    assert len(payload["items"]) == 12
    for position, item in enumerate(payload["items"], start=1):
        assert list(item.keys()) == PINNED_ITEM_KEYS, f"item {position} key order"
        assert item["item"] == position
        assert item["severity"] in SEVERITIES
        for key in ("title", "clause", "requirement", "computed", "limit", "detail"):
            assert isinstance(item[key], str) and item[key].strip()
    assert payload["verdict"] in ("recommended_for_approval", "return_for_revision")
    assert isinstance(payload["fe_agreement_pct"], (int, float))
    assert payload["verdict"] == canonical_chain.result.verdict
    assert payload["fe_agreement_pct"] == canonical_chain.result.fe_agreement_pct


def test_item_1_notes_the_pending_acs_verification_honestly(canonical_chain):
    item1 = canonical_chain.result.items[0]

    assert item1.severity == "OBSERVATION"
    assert "acs" in (item1.computed + item1.detail).lower()
    assert "pending verification" in item1.detail.lower()


def test_item_11_reports_the_fe_agreement_figure(canonical_chain):
    item11 = canonical_chain.result.items[10]

    assert item11.severity == "PASS"
    assert f"{canonical_chain.result.fe_agreement_pct:g}" in item11.computed
    assert "5" in item11.limit  # the ±5% tolerance is stated as the limit
