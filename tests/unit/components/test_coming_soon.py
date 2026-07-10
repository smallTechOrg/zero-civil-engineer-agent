"""Coming-soon roadmap stubs — registered, catalogued, greyed, never dispatched.

These metadata-only entries make the picker/gallery show greyed "Coming soon"
cards for the roadmap's future types (spec/roadmap.md, spec/ui.md). They must be
registered and listed, but `is_available()` must be False for each so a POST is
rejected (422) and the graph never dispatches to them.
"""

import pytest

from components import registry

# Registration order == gallery order: three civil previews, then three mechanical.
EXPECTED = {
    "plate_girder": "civil",
    "slab_tbeam": "civil",
    "pier_abutment": "civil",
    "structural_steel_member": "mechanical",
    "rolling_stock_member": "mechanical",
    "machine_element": "mechanical",
}


def test_all_six_coming_soon_types_are_registered_and_listed():
    catalogue = {c["type_id"]: c for c in registry.list_components()}
    for type_id, domain in EXPECTED.items():
        assert type_id in catalogue, f"{type_id} missing from the component catalogue"
        row = catalogue[type_id]
        assert row["status"] == "coming_soon"
        assert row["domain"] == domain


def test_available_and_coming_soon_split_populates_both_domain_groups():
    catalogue = registry.list_components()
    available = [c for c in catalogue if c["status"] == "available"]
    coming_soon = [c for c in catalogue if c["status"] == "coming_soon"]

    # The two available civil components + the six roadmap stubs.
    assert len(available) >= 2
    assert len(coming_soon) >= 6

    civil = [c for c in coming_soon if c["domain"] == "civil"]
    mechanical = [c for c in coming_soon if c["domain"] == "mechanical"]
    # Both gallery groups (Civil / Mechanical) populate with greyed cards.
    assert len(civil) >= 3
    assert len(mechanical) >= 3


def test_available_cards_sort_ahead_of_coming_soon_in_gallery_order():
    # Registration order (culvert → retaining wall → previews) is gallery order.
    catalogue = registry.list_components()
    first_coming_soon = next(
        i for i, c in enumerate(catalogue) if c["status"] == "coming_soon"
    )
    last_available = max(
        i for i, c in enumerate(catalogue) if c["status"] == "available"
    )
    assert last_available < first_coming_soon


@pytest.mark.parametrize("type_id", sorted(EXPECTED))
def test_coming_soon_type_is_registered_but_not_available(type_id):
    # Retrievable (so metadata surfaces) but NOT available: POST → 422, no dispatch.
    assert registry.has(type_id)
    assert registry.is_available(type_id) is False
    component = registry.get(type_id)
    assert component.status == "coming_soon"


@pytest.mark.parametrize("type_id", sorted(EXPECTED))
def test_coming_soon_catalogue_row_carries_real_metadata(type_id):
    row = next(c for c in registry.list_components() if c["type_id"] == type_id)
    # Exactly the spec/api.md GET /api/components row keys.
    assert set(row) == {
        "type_id",
        "display_name",
        "domain",
        "summary",
        "status",
        "codes",
        "example_prompt",
    }
    assert row["display_name"].strip()
    assert len(row["summary"]) > 20, "a real one-line summary of what it will design"
    assert isinstance(row["codes"], list) and row["codes"], "a plausible code set"
    assert row["example_prompt"].strip(), "first scope example powers the picker card"


def test_classify_metadata_marks_stubs_coming_soon_for_the_llm():
    # The understand prompt renders these as [COMING SOON] and routes them to a
    # graceful scope statement rather than into the pipeline.
    meta = {m["type_id"]: m for m in registry.classify_metadata()}
    for type_id in EXPECTED:
        assert type_id in meta
        assert meta[type_id]["status"] == "coming_soon"
        assert meta[type_id]["scope_examples"], "scope few-shots aid graceful routing"


def test_coming_soon_stub_reads_metadata_without_engineering_methods():
    # A metadata-only stub: no engineering method is required or invoked. The
    # defensive placeholder param/geometry models are present but never populated.
    stub = registry.get("plate_girder")
    assert stub.param_model is not None
    assert stub.geometry_model is not None
    assert stub.critical_fields == []
