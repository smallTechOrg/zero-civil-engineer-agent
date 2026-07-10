"""The Component Registry — the single extension point of the platform.

Adding a structure type = adding one `src/components/<type>/` module and one
`register()` call at its import. Nothing in the graph, API, DB or frontend
changes. The registry is populated once at process start by
`src/components/__init__.py`, which imports every component module.
"""

from __future__ import annotations

from components.base import ComponentModule

# The component every run defaults to when none is classified/requested — the
# box culvert (component #1). Keeps the pre-registry pipeline's behaviour intact.
DEFAULT_COMPONENT_TYPE = "box_culvert"

# Insertion-ordered: registration order == gallery order (culvert first).
_REGISTRY: dict[str, ComponentModule] = {}


def register(component: ComponentModule) -> None:
    """Register a component module by its `type_id` (idempotent per type_id)."""
    if not getattr(component, "type_id", None):
        raise ValueError("component must declare a non-empty type_id")
    _REGISTRY[component.type_id] = component


def get(type_id: str) -> ComponentModule:
    """Return the registered module for `type_id`, or raise KeyError."""
    try:
        return _REGISTRY[type_id]
    except KeyError as exc:
        known = ", ".join(sorted(_REGISTRY)) or "<none>"
        raise KeyError(
            f"No component registered for type_id {type_id!r} (known: {known})"
        ) from exc


def resolve(type_id: str | None) -> ComponentModule:
    """Return the module for `type_id`, falling back to the default component."""
    return get(type_id or DEFAULT_COMPONENT_TYPE)


def has(type_id: str) -> bool:
    return type_id in _REGISTRY


def is_available(type_id: str) -> bool:
    """True only for a registered component with status 'available'."""
    component = _REGISTRY.get(type_id)
    return component is not None and component.status == "available"


def modules() -> list[ComponentModule]:
    """Every registered module, in registration order."""
    return list(_REGISTRY.values())


def component_metadata(component: ComponentModule) -> dict:
    """The picker/gallery catalogue row for one component (spec/api.md shape)."""
    return {
        "type_id": component.type_id,
        "display_name": component.display_name,
        "domain": component.domain,
        "summary": component.summary,
        "status": component.status,
        "codes": list(component.codes),
        "example_prompt": component.scope_examples[0] if component.scope_examples else "",
    }


def list_components() -> list[dict]:
    """The component catalogue for `GET /api/components` and LLM classification."""
    return [component_metadata(c) for c in _REGISTRY.values()]


def classify_metadata() -> list[dict]:
    """Compact per-available-component metadata the `understand` prompt classifies against.

    Only `status='available'` components are selectable; a `coming_soon` type is
    listed separately so the prompt can route it to a graceful scope statement.
    """
    return [
        {
            "type_id": c.type_id,
            "display_name": c.display_name,
            "summary": c.summary,
            "scope_examples": list(c.scope_examples),
            "status": c.status,
        }
        for c in _REGISTRY.values()
    ]
