# Capability: Calculation Sheet

## What It Does
Presents the engine's design as a clause-cited calculation sheet in which every number can be expanded to its formula and substituted inputs, with an explicit assumptions block — the deliverable a proof-checking engineer expects to scrutinise. *(Phase 2; labelled stub in Phase 1.)*

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| Calc trail | CalcStep[] | IRS Design Engine | yes |
| Check results | CheckResult[] | IRS Design Engine | yes |
| Assumptions | Assumption[] | IRS Design Engine + intake | yes |
| Warnings | list | NL Design Intake | yes (may be empty) |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| `calc_sheet.json` | structured sheet (sections → lines → trail refs) | Artefact store; Calc Sheet tab |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| — none — | deterministic composition | fatal for the run (transparent) |

## Business Rules
- Sheet structure: Design basis (parameters + assumptions + warnings) → Loading (EUDL, CDA, dispersal, earth pressure, surcharge) → Analysis (load cases, envelope forces) → Member checks (per member: flexure, shear, min steel, cover, crack) — each line shows description, value + unit, and citation.
- **Drill-down is total:** every displayed number references a CalcStep; expanding shows formula and substituted inputs; inputs that are themselves computed link to their own steps (recursive trail).
- Citations are IRS only (Bridge Rules with ACS level, IRS CBC) — an IS 456/IRC citation anywhere in the sheet is a defect.
- The assumptions block lists every non-user value with its source (preset / engine default) — nothing implicit.
- The sheet streams in as soon as checks complete — before drawing render and review finish (never blocks on slower artefacts).

## Success Criteria
- [ ] For the canonical run, the sheet contains all four sections, ≥ 1 line per load case, and ≥ 1 check line per member (top slab, bottom slab, walls).
- [ ] Machine-verifiable trail closure: every line's `trail_ref` resolves to a CalcStep, and every CalcStep input marked computed resolves to another step (no dangling refs) — asserted by test over the whole sheet.
- [ ] Every loading line's citation includes the source document and ACS correction-slip level.
- [ ] Hard case — failing design: the under-designed run renders FAIL lines visibly distinct (status carried in JSON), and the sheet still composes completely.
- [ ] E2E: expanding a calc row in the UI reveals formula + inputs for a real run.
- [ ] The `calc_sheet` artefact SSE event arrives before the `review`-step `done` event in a full run.
