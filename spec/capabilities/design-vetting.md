# Capability: Design Vetting

## What It Does
Independently checks a SUBMITTED structural/mechanical design (received from a consultant/contractor) against the RDSO standards and IRS codes the platform already encodes — the automated "second engineer" review: the design office uploads the submitted drawing and/or calculation, the agent extracts the as-submitted geometry, provided reinforcement and claimed loading, runs the existing deterministic code/standard checks **CHECK-ONLY** (it never re-sizes or re-designs the member), and produces a clause-cited **vetting report** with per-check pass/fail, utilization %, severity-graded reviewer comments, and a rule-computed overall verdict (accept / return-for-revision).

> **Vetting is the INVERSE of the design flow.** The design flow SIZES the member (`size()` chooses dimensions + reinforcement) then checks its own work. Vetting takes dimensions AND reinforcement AND loading as GIVEN inputs and ONLY runs the checks — `size()` is SKIPPED (geometry is given, never computed); `analyse()` still runs to derive member forces from the CLAIMED loading over the given geometry; `run_checks()`/`proof_check()` run exactly as-is over the given values. The heart of the report is **clause-level compliance to standard**: every finding cites the governing RDSO/IRS clause. *(Vetting Phase 1; a labelled stub for the other 7 component types.)*

## Phased Coverage Vision (scope discipline — DO NOT build the whole vision now)
- **Vetting Phase 1 (built now — the smallest user-testable win):** check-only vetting proven end-to-end on the **box culvert** only — the platform's strongest, best-tested component. Upload a submitted culvert drawing (DXF) and/or calc PDF → extract → check-only over the IRS engine → render the vetting report in the existing Design Studio. The other 7 registered types show a clearly-labelled "vetting coming in a later phase" affordance (a stub, never a bug).
- **Later phases (described, NOT built):** vetting across ALL 8 registered component types (5 civil + 3 mechanical), each advertising `supports_vetting` as its extraction schema + check-only path lands; and increasingly robust extraction on messier real-world PDFs/DXFs (multi-page calcs, scanned drawings, non-standard dimension conventions). Each type deepens on the SAME interface + graph — no fork.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| Submitted design file(s) | one or more DXF / PDF / PNG / JPEG | Engineer upload (multipart) | yes (≥1 file) |
| Target component type | registry `type_id` | Picker (`component_type`); default `box_culvert`; must be a `supports_vetting` available type | no |
| Preset defaults | preset values | Default or selected preset — fills only NON-critical check inputs (exposure minimums, permissible-stress grade rows) NEVER the as-submitted geometry | yes |
| Session turn history | messages list | Session's prior runs ([data.md](../data.md#entity-designrun)) | yes (may be empty) |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| `vetting_report.json` | verdict + severity summary + extracted-input provenance + per-check findings (see Business Rules) | Vetting Report tab; artefacts endpoint; run snapshot `vetting` |
| `vetting_memo.md` | Proof-Checking-Consultant-style memo (markdown), LLM-narrated but deterministically grounded | Vetting Report tab |
| Overall verdict | `recommended_for_approval` (= **accept**) \| `return_for_revision` | Run record, snapshot `verdict`, UI verdict banner, library |
| `calc_sheet.json` | the check-only clause-cited calc sheet over the given design (reused artefact) | Calc Sheet tab |
| `compliance.json` | the reused 12-item deterministic checklist over the given design | Vetting Report tab (findings source) |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| LLM **vision** (see [agent.md](../agent.md#llm-provider--model)) | Extract as-submitted geometry + reinforcement + claimed loading from PDF/image parts (structured output against the component's vetting extraction schema) | 1 retry, then fatal (transparent error) |
| LLM text (see [agent.md](../agent.md#llm-provider--model)) | Plan narration (`understand`) + vetting-memo narration (grounded to deterministic findings only) | narration: failed grounding → discarded (warning), memo composes deterministically; transport: 1 retry then fatal |
| Local filesystem (`data/uploads/<run_id>/`) | Store the uploaded submission files; deterministic parse of any submitted DXF (drawing read-back, see [architecture.md](../architecture.md#component-registry--component-interface-the-platform-spine)) | unreadable/oversize file → transparent `422` at upload; a DXF that will not parse becomes a MAJOR finding, not a crash |

## Business Rules
- **CHECK-ONLY — never re-design.** The vet path builds the geometry from the GIVEN values (`build_submitted_geometry`), runs `analyse` for forces from the CLAIMED loading, then runs the EXISTING `run_checks`/`proof_check` over those given values. `size()` is never called in vet mode. A submitted member thinner than the platform would have sized MUST flow through to a FAIL finding — it is never silently corrected.
- **Clause-citation mandate.** Every finding row cites the governing RDSO/IRS clause (from the deterministic engine's citation records — never LLM-invented). A finding without a clause is a defect. Codes are the component's declared `codes` set (culvert → IRS Concrete Bridge Code / IRS Bridge Rules / 25t Loading-2008 / IRS Bridge Substructure & Foundation Code); an IS 456 / IS 800 / IRC citation on a culvert finding is a defect (same rule as the design flow).
- **Extraction provenance.** Every extracted input carries a `source` — `drawing` (a DXF/PDF drawing dimension), `calc` (a calculation-sheet statement), or `assumed_default` (not stated in the submission → filled from preset/engine default and flagged). Provenance is shown in the report so the reviewer sees what came from the submission vs what was assumed. A critical geometry field that cannot be extracted from ANY uploaded file becomes an OBSERVATION/finding ("clear span could not be read from the submission — please confirm"), not a silent default and not a mid-run clarify question (a vet has no submitter in the loop in this POC).
- **Deterministic DXF-parse assist.** When a DXF is uploaded, the geometry is read deterministically (the same drawing read-back as proof-check item 12 — measured dimension entities + printed dimension texts) and takes precedence over the vision extraction for geometry; the vision path reads reinforcement, claimed loading and grades from PDF/image parts. When only a PDF/image is uploaded, the vision path supplies geometry too.
- **Provided reinforcement is captured and checked, not just echoed.** The submission's provided main-steel (bar dia + spacing / area per metre, per member) is extracted and, where the engine yields a required area, checked provided-vs-required (a shortfall → NON_CONFORMITY). Where reinforcement is absent from the submission it is recorded as "not provided" (OBSERVATION) — never assumed adequate.
- **Findings = the reused deterministic checks, graded for a submission.** The vetting findings are derived from the existing IRS CBC member checks (`run_checks`) + the 12-item proof-check (`run_checklist`, incl. the independent FE cross-check and the DXF read-back against the SUBMITTED drawing) — re-projected as vetting rows: `id`, `title`, `clause`, `requirement`, `claimed`/`provided`, `computed`, `limit`, `utilization_pct`, `status` (`PASS`\|`FAIL`\|`NOT_VERIFIED`), `severity` (`PASS`\|`OBSERVATION`\|`NON_CONFORMITY_MINOR`\|`NON_CONFORMITY_MAJOR`), and a `comment` (a forwardable reviewer sentence).
- **Utilization %.** Each strength/serviceability finding reports `utilization_pct = round(demand/capacity × 100, 1)` (e.g. σ_actual/σ_permissible, required_depth/provided_depth, applied_shear/permissible_shear, provided_steel vs required); rows without a numeric demand/capacity pair report `null`.
- **Verdict rule (identical to the proof-check).** Any `NON_CONFORMITY_MAJOR` → `return_for_revision`; otherwise `recommended_for_approval` (surfaced to the reviewer as **Accept — compliant with the cited IRS codes**). Computed by rule; the LLM narrates, it never grades.
- **Memo grounding.** The vetting memo introduces no number or judgement absent from the deterministic findings (the same grounding validator as the design memo); a narration that fails grounding is discarded (warning) and the memo composes fully deterministically.
- **Additive & default-safe.** Vetting is opt-in per component via `supports_vetting` (only the box culvert = `true` in this phase); the other 7 modules and the whole design flow are unchanged. Design-mode runs are byte-for-byte identical.

## Success Criteria
- [ ] Uploading the fixture submitted box-culvert **DXF** (`tests/fixtures/vetting/submitted_box_culvert.dxf`) runs a vet in `mode="vet"` and renders a vetting report whose geometry values match the DXF's dimensioned values (deterministic ezdxf read-back), each tagged `source="drawing"`.
- [ ] **Decisive gate (deliberately under-designed submission):** the thin-top-slab fixture yields at least one `NON_CONFORMITY_MAJOR` flexure/shear finding naming the top slab, `verdict == "return_for_revision"`, and every finding row carries a non-empty RDSO/IRS clause citation. A compliant fixture (`submitted_box_culvert_compliant.dxf`) yields all-PASS/OBSERVATION and `verdict == "recommended_for_approval"` (accept). (sample≠full: an echo-only implementation that restated the submission as compliant would fail this gate.)
- [ ] **Check-only proof:** the vet run never calls `size()` (asserted by test — e.g. `size` is not invoked on the vet path); the reported geometry equals the submitted geometry, not a re-sized geometry.
- [ ] **Vision path:** uploading the fixture calc **PDF** (`submitted_box_culvert_calc.pdf`) extracts the claimed loading standard + provided reinforcement via a real Gemini vision call, each tagged `source="calc"` (real-LLM integration test).
- [ ] Every finding cites a clause in the culvert's declared `codes` set; no IS 456 / IS 800 / IRC citation appears on any finding (asserted).
- [ ] Utilization % is present and numeric on every strength/serviceability finding that has a demand/capacity pair.
- [ ] The vetting memo passes the deterministic grounding validator (no number absent from the findings) — asserted by test.
- [ ] **No regression:** every existing design-mode culvert/retaining-wall/breadth unit/validation/integration/E2E test stays green; a design-mode run is byte-for-byte unchanged.
- [ ] The other 7 component types advertise `supports_vetting=false`; the picker shows their vetting affordance as a labelled "coming in a later phase" stub, never an error.
