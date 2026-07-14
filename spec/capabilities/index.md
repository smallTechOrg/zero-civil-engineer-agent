# Capabilities Index

One file per capability — each describes exactly one discrete thing the agent does. Phasing lives in [roadmap.md](../roadmap.md#phases-of-development); the graph that orchestrates them lives in [agent.md](../agent.md).

## Capabilities in This Project

| Capability | File | Phase |
|-----------|------|-------|
| **Component Registry & Shared-Core Framework** (registry, common component interface, domain plug-ins, auto-detect + picker) | [component-registry.md](component-registry.md) | Expansion 1 |
| **RCC Cantilever Retaining Wall** (second registered component — earth pressure + stability + RCC design + drawing + 3D + proof-check) | [retaining-wall.md](retaining-wall.md) | Expansion 1 |
| **Steel Plate Girder Superstructure** (breadth-first component — girder sizing + bending/shear/deflection checks + drawing + 3D + proof-check; IRS Steel Bridge Code / IS 800) | [plate-girder.md](plate-girder.md) | Expansion 2 |
| **RCC Slab / T-beam Superstructure** (breadth-first component — flexure/shear/min-steel/deflection checks + drawing + 3D + proof-check; IRS Concrete Bridge Code / IS 456) | [slab-tbeam.md](slab-tbeam.md) | Expansion 2 |
| **Bridge Pier & Abutment Substructure** (breadth-first component — stability + bearing + concrete-stress checks + drawing + 3D + proof-check; IRS Bridge Substructure & Foundation Code / IRS Bridge Rules) | [pier-abutment.md](pier-abutment.md) | Expansion 2 |
| **Structural Steel / Fabrication Member** (breadth-first mechanical component — section utilisation (axial/bending/shear/combined) + fillet-weld connection checks + fabrication drawing (weld symbols) + 3D + proof-check; IS 800 / IS 816) | [structural-steel-member.md](structural-steel-member.md) | Expansion 3 |
| **Rolling-Stock Member** (breadth-first mechanical component — RDSO wagon load-case analysis + IS 800 working-stress strength checks + fabrication drawing + 3D + proof-check; RDSO Specifications / IS 800) | [rolling-stock-member.md](rolling-stock-member.md) | Expansion 3 |
| **Machine Element** (breadth-first mechanical component — shaft / welded-hub sizing + combined bending+torsion strength + fatigue/factor-of-safety checks + detail drawing (GD&T + weld symbols) + 3D + proof-check; Machine Design Code / IS 816) | [machine-element.md](machine-element.md) | Expansion 3 |
| **M-00004 Standard Box Culvert (RDSO)** (standard-driven, params-direct component — typed form → deterministic catalogue lookup → 2D GA (DXF/SVG) + 3D (STEP/GLB) + a M-00004-style PDF sheet with a1..h reinforcement in position + schedule table; bypasses the LLM intake; RDSO/M-00004 / IRS Concrete Bridge Code; all catalogue values PROVISIONAL) | [m00004-box-culvert.md](m00004-box-culvert.md) | Component Addition |
| NL Design Intake (scope gate, **component classification**, extraction, one clarifying question, unusual-value flags) | [nl-design-intake.md](nl-design-intake.md) | 1 (generalised in Expansion 1) |
| IRS Design Engine (sizing → loads → frame analysis → IRS CBC checks, pluggable loading standard) | [irs-engine.md](irs-engine.md) | 1 (sizing) / 2 (full) |
| GA Drawing (parametric DXF + server-rendered SVG, pan/zoom, DXF download) | [ga-drawing.md](ga-drawing.md) | 1 |
| Calculation Sheet (clause-cited, drill-down calc trail, assumptions block) | [calc-sheet.md](calc-sheet.md) | 2 |
| Proof-Check (12-item checklist, FE cross-check, compliance matrix, severity-graded memo, verdict) | [proof-check.md](proof-check.md) | 2 |
| 3D Model (parametric solid → GLB viewer + STEP download) | [model-3d.md](model-3d.md) | 3 |
| Design Library (audit trail browsing, run replay, presets) | [design-library.md](design-library.md) | 3 (records from 1) |
| Session Refinement (turn memory, refinement regeneration, revise loop, suggestions) | [session-refinement.md](session-refinement.md) | 1 (memory/refine) / 3 (suggestions) |

## Expansion-phase components (built — capability docs authored per phase)

Both expansion phases are **built**. Expansion 2 (civil breadth): `plate-girder.md`, `slab-tbeam.md`, `pier-abutment.md`. Expansion 3 (mechanical): `structural-steel-member.md`, `rolling-stock-member.md`, `machine-element.md`. All are authored above and their modules are registered `status="available"` (breadth-first — full parity deepening is later work), so the gallery now shows 8 available components and no coming-soon previews. Each is a new `src/components/<type>/` plug-in against the same interface; see [roadmap.md](../roadmap.md#expansion-phases-platform-evolution--culvert-phases-13-above-are-done).

## How to Add a New Capability

Run `/zero-shot-build [description]` on the existing spec. The spec-writer will create `<name>.md` here (no number prefix), update this index, flag dependencies, and self-review the fit against architecture and data model.
