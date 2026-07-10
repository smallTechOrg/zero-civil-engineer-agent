# Capability: Proof-Check

## What It Does
Automatically reviews every completed design like an independent Proof Checking Consultant: a 12-item deterministic checklist (including an independent FE re-solve and a DXF read-back consistency check), a compliance matrix, and a severity-graded memo with a verdict — mirroring the IR design-review workflow (IS 18299:2023 / post-Pamban tightening). *(Phase 2; labelled stub in Phase 1.)*

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| Run record (params, assumptions, geometry, analysis, checks) | typed models | IRS Design Engine + intake | yes |
| `ga.dxf` | DXF file | GA Drawing | yes |
| FE comparison | FeComparison | Independent FE re-solve (this capability) | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| `compliance.json` | matrix rows: clause \| requirement \| computed \| limit \| status | Proof-Check tab |
| `proof_memo.md` | severity-graded memo (markdown) | Proof-Check tab |
| `bmd.svg`, `sfd.svg` | FE bending-moment / shear-force diagrams | Proof-Check tab |
| Verdict | `recommended_for_approval` \| `return_for_revision` | Run record, UI banner, library |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| FE solver (see [architecture.md](../architecture.md#stack)) | independent 2D frame re-solve + diff vs closed-form | fatal for the run (transparent) |
| LLM (see [agent.md](../agent.md#llm-provider--model)) | narrate the memo from deterministic results ONLY | transport failure: 1 retry, then fatal; failed grounding: narration discarded (warning), memo composes deterministically |

## Business Rules
- **The 12 checklist items (fixed set for the box culvert):** (1) loading standard correct & ACS level current; (2) EUDL for the loaded length matches the cited table; (3) CDA applied incl. cushion reduction; (4) load cases complete (DL, SIDL, LL+impact, earth pressure at-rest/active, LL surcharge, box empty/full); (5) cushion dispersal applied correctly; (6) concrete grade & clear cover per IRS CBC exposure; (7) flexure adequacy (σcbc, σst within permissible); (8) shear adequacy; (9) min steel / max spacing / haunch & distribution steel; (10) crack width / SLS limits; (11) **independent FE re-solve agrees with closed-form within ±5%** — agreement is itself a check item; (12) **calc-vs-drawing consistency** — dimensions read back from the produced DXF match the designed geometry.
- Hydraulic adequacy (vent area, HFL, scour per RBF-16) is **echoed as user-supplied information, never computed** — shown honestly as "not verified by this POC" in the memo.
- Severity grading: PASS / OBSERVATION / NON-CONFORMITY (minor | major). Verdict is computed by rule — any major non-conformity → `return_for_revision`; the LLM narrates, it never grades or decides.
- The proof-check runs automatically after every design; **revision is user-triggered** ("increase slab to 450 mm" as a new turn) — the agent never auto-iterates until pass.
- The memo is styled as a Proof Checking Consultant memo (structure: reference, scope of check, observations by severity, recommendation) and flags any IS-456-style citation as a defect.
- All 12 items evaluate deterministically; the memo must not introduce any number or judgement absent from the checklist results — enforced by a deterministic grounding validator: a narration that fails it is discarded (warning event) and the memo composes fully deterministically.

## Success Criteria
- [ ] A sound canonical design yields all 12 items PASS/OBSERVATION, verdict `recommended_for_approval`, and an FE agreement figure ≤ 5% shown in the matrix.
- [ ] Hard case — deliberately under-designed run (thin top slab override): items 7/8 report NON-CONFORMITY (major), verdict `return_for_revision`, and the memo names the failing member and clause.
- [ ] Hard case — DXF tamper test: corrupting a dimension in a copy of ga.dxf makes item 12 fail (proves read-back is real, not a restatement).
- [ ] BMD/SFD SVGs are generated for every reviewed run and render in the tab (E2E).
- [ ] Memo grounding: every numeric value in the memo also appears in the checklist/matrix results (asserted by test) — no LLM-invented numbers.
- [ ] Revise loop: after `return_for_revision`, submitting a corrective refinement produces a new run whose verdict improves to `recommended_for_approval`.
