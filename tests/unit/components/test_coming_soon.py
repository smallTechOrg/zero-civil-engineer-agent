"""Roadmap reconciliation — the delivered catalogue is 8 available, 0 coming-soon.

As of Expansion Phase 3 every roadmap component is a real, self-registering
`available` module. The civil breadth types (plate girder, slab/T-beam, pier &
abutment) landed in Expansion Phase 2, and the three MECHANICAL types
(structural steel / fabrication member, rolling-stock member, machine element)
land in Expansion Phase 3 — each replacing its former greyed "Coming soon" stub.
There are therefore NO coming-soon preview cards left: `components/coming_soon.py`
registers nothing.

These tests pin that end state: the full catalogue is 8 `available` components
and there are ZERO coming-soon rows anywhere the picker/gallery or the LLM
classifier reads. (The reusable `ComingSoonComponent` mechanism is retained for
future roadmap items and is exercised without polluting the delivered catalogue.)
"""

from __future__ import annotations

import pytest

from components import registry
from components.coming_soon import ComingSoonComponent, _PendingModel

# The full delivered catalogue after Expansion Phase 3: 8 available components.
EXPECTED_AVAILABLE: dict[str, str] = {
    "box_culvert": "civil",
    "rcc_cantilever_retaining_wall": "civil",
    "plate_girder": "civil",
    "slab_tbeam": "civil",
    "pier_abutment": "civil",
    "structural_steel_member": "mechanical",
    "rolling_stock_member": "mechanical",
    "machine_element": "mechanical",
}

# The three MECHANICAL types that flip from coming_soon → available this phase.
MECHANICAL = {"structural_steel_member", "rolling_stock_member", "machine_element"}

# Exactly the spec/api.md GET /api/components row keys.
CATALOGUE_KEYS = {
    "type_id",
    "display_name",
    "domain",
    "summary",
    "status",
    "codes",
    "example_prompt",
}


def _catalogue() -> dict[str, dict]:
    return {c["type_id"]: c for c in registry.list_components()}


def test_all_eight_expected_components_are_registered_and_available():
    catalogue = _catalogue()
    for type_id, domain in EXPECTED_AVAILABLE.items():
        assert type_id in catalogue, f"{type_id} missing from the component catalogue"
        row = catalogue[type_id]
        assert row["status"] == "available", f"{type_id} must be available"
        assert row["domain"] == domain
        assert registry.has(type_id)
        assert registry.is_available(type_id) is True


def test_the_three_mechanical_types_are_available_in_the_mechanical_domain():
    # Expansion Phase 3: each mechanical preview stub is replaced by a real,
    # self-registering available module in the Mechanical domain group.
    catalogue = _catalogue()
    for type_id in sorted(MECHANICAL):
        assert type_id in catalogue, f"{type_id} missing from the catalogue"
        row = catalogue[type_id]
        assert row["status"] == "available"
        assert row["domain"] == "mechanical"
        assert registry.is_available(type_id) is True


def test_zero_coming_soon_components_anywhere_in_the_catalogue():
    # The whole roadmap is delivered: no card reads as a greyed "Coming soon".
    catalogue = registry.list_components()
    available = {c["type_id"] for c in catalogue if c["status"] == "available"}
    coming_soon = [c for c in catalogue if c["status"] == "coming_soon"]

    assert coming_soon == [], "no component may still read as coming_soon"
    assert set(EXPECTED_AVAILABLE) <= available


def test_classify_metadata_lists_no_coming_soon_type_for_the_llm():
    # The understand prompt classifies against available components only; with the
    # roadmap delivered there is nothing left for it to route to a scope statement.
    meta = registry.classify_metadata()
    statuses = {m["status"] for m in meta}
    assert "coming_soon" not in statuses, "no coming_soon type may reach the classifier"

    by_id = {m["type_id"]: m for m in meta}
    for type_id in sorted(MECHANICAL):
        assert by_id[type_id]["status"] == "available"
        assert by_id[type_id]["scope_examples"], "auto-detect few-shots must be present"


@pytest.mark.parametrize("type_id", sorted(EXPECTED_AVAILABLE))
def test_catalogue_row_carries_the_api_key_set_and_real_metadata(type_id):
    row = next(c for c in registry.list_components() if c["type_id"] == type_id)
    # Exactly the spec/api.md GET /api/components row keys (gallery/catalogue shape).
    assert set(row) == CATALOGUE_KEYS
    assert row["display_name"].strip()
    assert len(row["summary"]) > 20, "a real one-line summary of what it designs"
    assert isinstance(row["codes"], list) and row["codes"], "a declared code set"
    assert row["example_prompt"].strip(), "first scope example powers the picker card"


def test_available_components_satisfy_the_component_module_protocol():
    # Every one of the 8 catalogue rows is backed by a real ComponentModule — not
    # a metadata-only stub — so the gallery never surfaces an undispatched card.
    from components.base import ComponentModule

    for type_id in sorted(EXPECTED_AVAILABLE):
        assert isinstance(registry.get(type_id), ComponentModule), type_id


def test_coming_soon_mechanism_remains_ready_for_future_roadmap_items():
    # The reusable coming-soon infra is intact (kept for future roadmap items): a
    # ComingSoonComponent carries catalogue metadata, defaults to a non-available
    # status, and exposes the defensive placeholder models; is_available() reports
    # False for such a not-yet-built type. Constructed only — never registered —
    # so the delivered catalogue stays 8 available / 0 coming-soon.
    stub = ComingSoonComponent(
        type_id="__synthetic_future_component__",
        display_name="Synthetic Future Component",
        domain="mechanical",
        summary="A throwaway preview proving the coming-soon mechanism still exists.",
        codes=["Some Future Code"],
        scope_examples=["design a synthetic future component"],
    )
    assert stub.status == "coming_soon"
    assert stub.param_model is _PendingModel
    assert stub.geometry_model is _PendingModel
    assert stub.critical_fields == []
    assert registry.is_available(stub.type_id) is False
    assert not registry.has(stub.type_id), "the synthetic stub must not be registered"
