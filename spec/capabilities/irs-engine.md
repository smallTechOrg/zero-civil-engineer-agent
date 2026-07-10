# Capability: IRS Design Engine

## What It Does
Deterministically sizes and analyses a single-cell RCC box culvert to IRS standards — geometry/thickness sizing, load cases, rigid-frame analysis, and IRS Concrete Bridge Code member checks — with every number traceable to formula, inputs, and clause citation. No LLM anywhere in this capability.

**Phasing (explicit):** Phase 1 delivers **sizing only** — geometry + member thicknesses sufficient to drive the GA drawing. Phase 2 delivers the full engine: load cases, EUDL+CDA, frame analysis, and all member checks.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| Parameters | CulvertParams | NL Design Intake | yes |
| Loading tables | 25t Loading-2008 EUDL/CDA data with citations | Transcribed table module (see rules) | yes (Phase 2) |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| BoxGeometry (external dims, thicknesses, barrel length, haunches) | typed model | Drawing, 3D model, audit record |
| Assumptions | Assumption[] | Calc sheet, audit record |
| Load cases + member-force envelopes (Phase 2) | AnalysisResult | Checks, FE cross-check, calc sheet |
| Check results (Phase 2) | CheckResult[] (clause, requirement, computed, limit, status) | Calc sheet, proof-check matrix |
| Calc trail | CalcStep[] (id, description, formula, inputs, value, unit, citation) | Calc sheet drill-down |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| — none — | pure deterministic Python | any exception is fatal for the run (transparent) |

## Business Rules
- **Loading-standard layer is pluggable:** a `LoadingStandard` interface (EUDL for bending/shear by loaded length, CDA impact incl. cushion reduction, citations) with `25t Loading-2008` as the only POC implementation; DFC 32.5t slots in later without touching the engine.
- **Every transcribed table cites its source:** the table module carries `source_document` (official iricen.gov.in IRS Bridge Rules PDF), `source_pages`, and the **ACS correction-slip level** encoded — surfaced in the calc sheet and UI. Same rule for IRS CBC limits.
- Load cases (Phase 2): dead load, SIDL (ballast/track), EUDL + CDA dispersed through the cushion, earth pressure (at-rest and active), live-load surcharge, box empty/full — combined per IRS practice.
- Analysis: closed-form rigid-frame (moment distribution on the closed box) — member end/mid-span moments, shears per load case, and envelopes.
- Checks (Phase 2) per **IRS Concrete Bridge Code** (never IS 456): flexure as working stress (σcbc, σst vs permissible), shear, minimum steel, clear cover, crack width as applicable.
- **Check-governed sizing:** sizing starts from the RDSO-family heuristic, then iterates analyse → check → bump-50 mm on AUTO-sized members until the design passes its own IRS CBC checks — bounded and deterministic, with every bump recorded as a cited CalcStep. User-overridden thicknesses are NEVER bumped.
- Sizing respects user thickness overrides but records a warning when the override is thinner than the sized value (the deliberate under-design demo case must flow through to a failing check, not be silently corrected).
- Every computed quantity appends a CalcStep — there is no number in any artefact that lacks a trail entry.
- Barrel length is computed from formation width + side slopes + fill height (defaults per data.md) and recorded as an assumption.

## Validation Fixtures (named — the Phase 2 gate runs these)
- **V1 — EUDL/CDA table spot checks:** transcribed 25t Loading-2008 EUDL (BM + shear) and CDA values for loaded lengths spanning the POC range, asserted against the source PDF transcription (independent second transcription in the test file) incl. interpolation behaviour.
- **V2 — RDSO B-10152/R family cross-check:** for a standard span/height/fill combination covered by the RDSO single-cell 25t standard drawings, engine-sized member thicknesses fall within ±10% of (or match) the standard-drawing values.
- **V3 — published worked example:** mid-span and corner moments for the load cases of a published railway box-culvert worked example (IRICEN course material lineage) within ±5%.
- **V4 — FE agreement:** closed-form envelope moments/shears agree with the independent FE re-solve within ±5% (shared with [proof-check](proof-check.md)).

## Success Criteria
- [ ] Sizing is deterministic: same CulvertParams → byte-identical BoxGeometry and trail (property test over the valid range).
- [ ] Fixtures V1–V3 pass (V4 under proof-check); tolerance breaches fail the build, not just warn.
- [ ] Every CheckResult and every loading value carries a non-empty citation with document + ACS level.
- [ ] Hard case — under-design override: forcing `top_slab_thickness_mm` well below the sized value yields at least one FAIL CheckResult in flexure or shear.
- [ ] Hard case — zero cushion (cushion_m=0): dispersal logic degrades correctly (no negative dispersion widths, CDA at full value) and the run completes.
- [ ] Engine completes (sizing + analysis + checks) in under 2 s for any valid input — it never threatens the 60 s run budget.
