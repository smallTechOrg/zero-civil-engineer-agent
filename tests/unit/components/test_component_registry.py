"""The Component Registry — culvert self-registration, catalogue, availability, dispatch."""

import pytest

from components import registry
from components.base import ComponentModule


def test_box_culvert_is_registered_and_available():
    assert registry.has("box_culvert")
    assert registry.is_available("box_culvert")
    culvert = registry.get("box_culvert")
    assert culvert.type_id == "box_culvert"
    assert culvert.status == "available"
    assert culvert.domain == "civil"


def test_get_unknown_type_raises():
    with pytest.raises(KeyError):
        registry.get("no_such_component")


def test_is_available_false_for_unknown():
    assert registry.is_available("no_such_component") is False


def test_list_components_returns_the_api_catalogue_shape():
    catalogue = registry.list_components()
    assert catalogue, "at least the box culvert must be listed"
    culvert = next(c for c in catalogue if c["type_id"] == "box_culvert")
    # Exactly the spec/api.md GET /api/components row keys.
    assert set(culvert) == {
        "type_id",
        "display_name",
        "domain",
        "summary",
        "status",
        "codes",
        "example_prompt",
    }
    assert culvert["status"] == "available"
    assert isinstance(culvert["codes"], list) and culvert["codes"]
    assert culvert["example_prompt"]  # first scope example — powers the picker card


def test_classify_metadata_carries_scope_examples_for_the_llm():
    meta = {m["type_id"]: m for m in registry.classify_metadata()}
    culvert = meta["box_culvert"]
    assert culvert["status"] == "available"
    assert culvert["scope_examples"], "auto-detect few-shots must be present"
    assert any("box culvert" in ex.lower() for ex in culvert["scope_examples"])


def test_culvert_satisfies_the_component_module_protocol():
    # runtime_checkable structural conformance — the retaining-wall module must
    # satisfy the SAME Protocol.
    assert isinstance(registry.get("box_culvert"), ComponentModule)


def test_culvert_declares_the_full_metadata_and_method_set():
    culvert = registry.get("box_culvert")
    for attr in (
        "type_id",
        "display_name",
        "domain",
        "summary",
        "status",
        "codes",
        "scope_examples",
        "critical_fields",
        "param_model",
        "geometry_model",
    ):
        assert hasattr(culvert, attr), f"missing metadata: {attr}"
    for method in (
        "extraction_schema",
        "clarify_question",
        "unusual_value_warnings",
        "size",
        "analyse",
        "run_checks",
        "compose_calc_sheet",
        "draw",
        "model3d",
        "proof_check",
        "memo_prompt",
        "type_summary",
    ):
        assert callable(getattr(culvert, method)), f"missing method: {method}"
    # Critical fields are the three the user must supply (never defaulted).
    assert culvert.critical_fields == ["clear_span_m", "clear_height_m", "cushion_m"]
