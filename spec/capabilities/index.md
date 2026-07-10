# Capabilities Index

One file per capability — each describes exactly one discrete thing the agent does. Phasing lives in [roadmap.md](../roadmap.md#phases-of-development); the graph that orchestrates them lives in [agent.md](../agent.md).

## Capabilities in This Project

| Capability | File | Phase |
|-----------|------|-------|
| NL Design Intake (scope gate, extraction, one clarifying question, unusual-value flags) | [nl-design-intake.md](nl-design-intake.md) | 1 |
| IRS Design Engine (sizing → loads → frame analysis → IRS CBC checks, pluggable loading standard) | [irs-engine.md](irs-engine.md) | 1 (sizing) / 2 (full) |
| GA Drawing (parametric DXF + server-rendered SVG, pan/zoom, DXF download) | [ga-drawing.md](ga-drawing.md) | 1 |
| Calculation Sheet (clause-cited, drill-down calc trail, assumptions block) | [calc-sheet.md](calc-sheet.md) | 2 |
| Proof-Check (12-item checklist, FE cross-check, compliance matrix, severity-graded memo, verdict) | [proof-check.md](proof-check.md) | 2 |
| 3D Model (parametric solid → GLB viewer + STEP download) | [model-3d.md](model-3d.md) | 3 |
| Design Library (audit trail browsing, run replay, presets) | [design-library.md](design-library.md) | 3 (records from 1) |
| Session Refinement (turn memory, refinement regeneration, revise loop, suggestions) | [session-refinement.md](session-refinement.md) | 1 (memory/refine) / 3 (suggestions) |

## How to Add a New Capability

Run `/zero-shot-build [description]` on the existing spec. The spec-writer will create `<name>.md` here (no number prefix), update this index, flag dependencies, and self-review the fit against architecture and data model.
