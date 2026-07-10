"""Roadmap ("coming soon") component stubs — the picker/gallery preview slots.

Each entry here is a **metadata-only** registry row for a structure/component
type on the phased plan (Expansion Phases 2 & 3) that is not yet built. It
declares ONLY the descriptive metadata the catalogue reads — `type_id`,
`display_name`, `domain`, `summary`, `status`, `codes`, `scope_examples` — so
that `GET /api/components` surfaces it and the frontend renders a greyed
"Coming soon" card (the roadmap is visible, "not silently absent"; see
spec/roadmap.md and spec/ui.md).

A `coming_soon` stub implements **no** engineering methods and is **never**
dispatched to:

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
module AFTER every available component, so the available cards sort ahead of
these previews. As of Expansion Phase 2 only the three mechanical types remain
here; the civil breadth types (plate girder, slab/T-beam, pier & abutment) are
now real available modules.
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


# --- Mechanical domain (Expansion Phase 3) ----------------------------------------
#
# The three civil breadth types (plate_girder, slab_tbeam, pier_abutment) were
# roadmap stubs here through Expansion Phase 1; as of Expansion Phase 2 they are
# real, self-registering `available` component packages (src/components/<type>/),
# so their stubs have been removed. Only the mechanical previews remain.

STRUCTURAL_STEEL_MEMBER = ComingSoonComponent(
    type_id="structural_steel_member",
    display_name="Structural Steel / Fabrication Member",
    domain="mechanical",
    summary=(
        "Fabricated structural-steel member (beam, column or bracket) — section "
        "capacity, bolted/welded connection and weld design to IS 800 and the "
        "Indian welding codes, a fabrication drawing with weld symbols, and the "
        "same IR-protocol proof-check."
    ),
    codes=["IS 800", "IS 816", "IS 9595"],
    scope_examples=[
        "design a welded steel bracket to IS 800 with fillet-weld connections",
        "fabricated steel column for a workshop gantry, IS 800 + weld checks",
    ],
)

ROLLING_STOCK_MEMBER = ComingSoonComponent(
    type_id="rolling_stock_member",
    display_name="Rolling-Stock Member",
    domain="mechanical",
    summary=(
        "Rolling-stock structural member (underframe or body member) — load-case "
        "analysis and strength/fatigue checks to RDSO specifications, a fabrication "
        "drawing with weld symbols, and the same IR-protocol proof-check."
    ),
    codes=["RDSO Specifications", "IS 800"],
    scope_examples=[
        "design a wagon underframe sole-bar member to RDSO specs",
        "rolling-stock body pillar member, fatigue-checked to RDSO loading",
    ],
)

MACHINE_ELEMENT = ComingSoonComponent(
    type_id="machine_element",
    display_name="Machine Element",
    domain="mechanical",
    summary=(
        "Machine element (shaft, gear, coupling or fastener) — strength, fatigue "
        "and stress-concentration checks to standard machine-design codes, a "
        "detailed part drawing with GD&T, and the same IR-protocol proof-check."
    ),
    codes=["IS 2825", "IS 4218", "Machine-Design Codes"],
    scope_examples=[
        "design a power-transmission shaft for 15 kW at 1450 rpm",
        "size a keyed coupling and check the fastener group",
    ],
)


# Registration order == gallery order: the mechanical previews (Expansion
# Phase 3). The civil types are now built, available modules registered ahead of
# this import (see src/components/__init__.py).
_COMING_SOON: tuple[ComingSoonComponent, ...] = (
    STRUCTURAL_STEEL_MEMBER,
    ROLLING_STOCK_MEMBER,
    MACHINE_ELEMENT,
)

for _component in _COMING_SOON:
    register(_component)
