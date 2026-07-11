"""Roadmap ("coming soon") component stubs — the picker/gallery preview slots.

This module is the reusable mechanism for surfacing a structure/component type
that is on the phased plan but **not yet built**: a metadata-only registry row
declaring ONLY the descriptive metadata the catalogue reads — `type_id`,
`display_name`, `domain`, `summary`, `status`, `codes`, `scope_examples` — so
that `GET /api/components` surfaces it and the frontend renders a greyed
"Coming soon" card (the roadmap is visible, "not silently absent"; see
spec/roadmap.md and spec/ui.md).

**As of Expansion Phase 3 the whole phased roadmap is delivered:** the civil
breadth types (plate girder, slab/T-beam, pier & abutment, Expansion Phase 2)
and the mechanical types (structural steel / fabrication member, rolling-stock
member, machine element, Expansion Phase 3) are all real, self-registering
`status="available"` component packages. There are therefore currently **NO**
coming-soon previews — `_COMING_SOON` is empty and this module registers
nothing. The `ComingSoonComponent` class, `_PendingModel` and the registration
loop are kept as ready infrastructure so a FUTURE roadmap item is one tuple entry
away, with no other wiring.

A `coming_soon` stub (were one added) implements **no** engineering methods and
is **never** dispatched to:

* `registry.is_available()` returns False for it (status != "available"), so
  `POST /api/sessions/{id}/designs` with such a `component_type` is rejected
  with a 422 `UNKNOWN_COMPONENT`;
* the `understand` node renders it to the LLM as `[COMING SOON]`, so an
  auto-detected request for one is routed to a graceful scope statement rather
  than into the deterministic pipeline.

The graph dispatches only to `status="available"` types, whose `param_model` /
`size` / `analyse` / … are read — never these stubs'. The placeholder
`param_model` / `geometry_model` below exist purely so an incidental attribute
read never raises; they are never populated.

Registration order == gallery order. `src/components/__init__.py` imports this
module AFTER every available component, so any future preview card sorts after
the built components in the gallery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

from components.registry import register


class _PendingModel(BaseModel):
    """Placeholder param/geometry model for a not-yet-built component.

    A coming_soon stub is never sized/analysed/dispatched, so this model is
    never instantiated with real data. It exists only so a defensive
    `component.param_model` / `component.geometry_model` read cannot raise.
    """


@dataclass(frozen=True)
class ComingSoonComponent:
    """A metadata-only registry entry for a roadmap component not yet built.

    Structurally carries the declarative metadata fields the catalogue reads
    (`registry.component_metadata()` / `classify_metadata()`); it implements no
    `ComponentModule` engineering methods and must never be dispatched to.
    """

    type_id: str
    display_name: str
    domain: Literal["civil", "mechanical"]
    summary: str
    codes: list[str]
    scope_examples: list[str]
    status: Literal["available", "coming_soon"] = "coming_soon"
    # Never read for a coming_soon type (kept for defensive attribute parity).
    critical_fields: list[str] = field(default_factory=list)
    param_model: type[BaseModel] = _PendingModel
    geometry_model: type[BaseModel] = _PendingModel


# The roadmap is fully delivered as of Expansion Phase 3 — every civil-breadth
# and mechanical component is a real, self-registering `available` module
# (src/components/<type>/), registered ahead of this import. There are therefore
# no coming-soon previews. Add a future roadmap item by appending one
# `ComingSoonComponent(...)` entry here; registration order == gallery order.
_COMING_SOON: tuple[ComingSoonComponent, ...] = ()

for _component in _COMING_SOON:
    register(_component)
