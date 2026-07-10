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
module AFTER the two available civil components, so the available cards (Box
Culvert, Retaining Wall) sort ahead of these previews.
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


# --- Civil breadth (Expansion Phase 2) --------------------------------------------

PLATE_GIRDER = ComingSoonComponent(
    type_id="plate_girder",
    display_name="Steel Plate Girder Superstructure",
    domain="civil",
    summary=(
        "Welded steel plate-girder railway bridge superstructure — flange/web "
        "sizing, bending & shear capacity, stiffener design, a dimensioned GA "
        "drawing + 3D model, and the same IR-protocol proof-check to the IRS "
        "Steel Bridge Code / IS 800."
    ),
    codes=["IRS Steel Bridge Code", "IS 800"],
    scope_examples=[
        "design a steel plate girder for a 24 m railway bridge span, BG single line",
        "welded plate-girder superstructure, 25t loading, deck-type girder",
    ],
)

SLAB_TBEAM = ComingSoonComponent(
    type_id="slab_tbeam",
    display_name="RCC Slab / T-beam Superstructure",
    domain="civil",
    summary=(
        "RCC slab and T-beam railway bridge superstructure — deck/girder sizing, "
        "flexure & shear design, a dimensioned GA drawing + 3D model, and the "
        "same IR-protocol proof-check to the IRS Concrete Bridge Code / IS 456."
    ),
    codes=["IRS Concrete Bridge Code", "IS 456"],
    scope_examples=[
        "design an RCC T-beam superstructure for a 12 m railway span",
        "solid RCC slab bridge deck, 6 m span, 25t loading",
    ],
)

PIER_ABUTMENT = ComingSoonComponent(
    type_id="pier_abutment",
    display_name="Pier & Abutment Substructure",
    domain="civil",
    summary=(
        "Bridge pier and abutment substructure — load combinations, stability and "
        "foundation-pressure checks, RCC section design, a GA drawing + 3D model, "
        "and the same IR-protocol proof-check to the IRS Bridge Substructure & "
        "Foundation Code."
    ),
    codes=["IRS Bridge Substructure & Foundation Code", "IRS Bridge Rules"],
    scope_examples=[
        "design a bridge pier for a 20 m railway span, SBC 300 kN/m²",
        "RCC abutment with wing walls for a single-span railway bridge",
    ],
)


# --- Mechanical domain (Expansion Phase 3) ----------------------------------------

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


# Registration order == gallery order: civil previews first, then mechanical.
_COMING_SOON: tuple[ComingSoonComponent, ...] = (
    PLATE_GIRDER,
    SLAB_TBEAM,
    PIER_ABUTMENT,
    STRUCTURAL_STEEL_MEMBER,
    ROLLING_STOCK_MEMBER,
    MACHINE_ELEMENT,
)

for _component in _COMING_SOON:
    register(_component)
