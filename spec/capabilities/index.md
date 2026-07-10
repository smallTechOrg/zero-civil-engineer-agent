# Capabilities Index

One file per capability — each describes exactly one discrete thing the agent does. Phasing lives in [roadmap.md](../roadmap.md#phases-of-development); the graph that orchestrates them lives in [agent.md](../agent.md).

## Capabilities in This Project

| Capability | File | Phase |
|-----------|------|-------|
| **Component Registry & Shared-Core Framework** (registry, common component interface, domain plug-ins, auto-detect + picker) | [component-registry.md](component-registry.md) | Expansion 1 |
| **RCC Cantilever Retaining Wall** (second registered component — earth pressure + stability + RCC design + drawing + 3D + proof-check) | [retaining-wall.md](retaining-wall.md) | Expansion 1 |
| NL Design Intake (scope gate, **component classification**, extraction, one clarifying question, unusual-value flags) | [nl-design-intake.md](nl-design-intake.md) | 1 (generalised in Expansion 1) |
| IRS Design Engine (sizing → loads → frame analysis → IRS CBC checks, pluggable loading standard) | [irs-engine.md](irs-engine.md) | 1 (sizing) / 2 (full) |
| GA Drawing (parametric DXF + server-rendered SVG, pan/zoom, DXF download) | [ga-drawing.md](ga-drawing.md) | 1 |
| Calculation Sheet (clause-cited, drill-down calc trail, assumptions block) | [calc-sheet.md](calc-sheet.md) | 2 |
| Proof-Check (12-item checklist, FE cross-check, compliance matrix, severity-graded memo, verdict) | [proof-check.md](proof-check.md) | 2 |
| 3D Model (parametric solid → GLB viewer + STEP download) | [model-3d.md](model-3d.md) | 3 |
| Design Library (audit trail browsing, run replay, presets) | [design-library.md](design-library.md) | 3 (records from 1) |
| Session Refinement (turn memory, refinement regeneration, revise loop, suggestions) | [session-refinement.md](session-refinement.md) | 1 (memory/refine) / 3 (suggestions) |

## Planned components (later expansion phases — capability docs authored when the phase is built)

Expansion 2 (civil breadth): `plate-girder.md`, `slab-tbeam.md`, `pier-abutment.md`. Expansion 3 (mechanical): `structural-steel-member.md`, `rolling-stock-member.md`, `machine-element.md`. Each is a new `src/components/<type>/` plug-in against the same interface; see [roadmap.md](../roadmap.md#expansion-phases-platform-evolution--culvert-phases-13-above-are-done).

## How to Add a New Capability

Run `/zero-shot-build [description]` on the existing spec. The spec-writer will create `<name>.md` here (no number prefix), update this index, flag dependencies, and self-review the fit against architecture and data model.
