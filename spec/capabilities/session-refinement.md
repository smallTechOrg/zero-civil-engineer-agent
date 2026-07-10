# Capability: Session Refinement

## What It Does
Makes a session a real design conversation: turn memory carries accepted parameters forward so short refinements ("increase fill to 4 m") regenerate all artefacts, clarification answers resume seamlessly, and — after each answer — the agent suggests 2–3 sensible refinements. *(Turn memory + refinement-regeneration land in Phase 1; suggestion chips land in Phase 3.)*

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| Refinement / answer prompt | free text | User | yes |
| Session turn history + prior accepted params | messages + CulvertParams | Session runs | yes |
| Completed-run summary (for suggestions) | params, warnings, verdict | Run record | yes (Phase 3) |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| New design run (fully regenerated artefacts) | DesignRun | Same pipeline as any run |
| Refinement suggestions | 2–3 short strings | Suggestion chips → prompt box |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| LLM (see [agent.md](../agent.md#llm-provider--model)) | merge-aware extraction (shared with intake); suggestion generation (Phase 3) | extraction: 1 retry then fatal; suggestions: swallowed (log only, chips stay empty) |

## Business Rules
- A refinement changes only what the user named — every other parameter carries over from the session's last completed run (merge rules in [nl-design-intake.md](nl-design-intake.md)).
- Every refinement is a **full new run**: all artefacts regenerate from the merged parameters; nothing is patched in place; the previous run stays in the library untouched.
- A clarification answer is just the next turn — the agent recognises it against the pending question and completes the original request.
- The design → review → revise loop is **user-triggered**: the proof-check verdict informs, the human decides; no auto-iteration.
- Suggestions are grounded in the actual run (e.g. respond to a warning, a near-limit check, or a natural next exploration) — clicking one only fills the prompt box; the user still submits.
- Suggestion failure is invisible-degrading: the run is complete with or without chips.

## Success Criteria
- [ ] Hard case — pronoun-thin refinement: after the canonical 4 m/3 m/2.5 m run, "increase the fill to 4 m" yields a completed run with `cushion_m=4.0` and all other params identical; the new drawing's fill dimension reads 4.0 m (regeneration proven, not just re-extraction).
- [ ] Contradiction resolution: "make it 5 m span instead" overrides span only; history shows both runs with their own params.
- [ ] Clarification resumption: pending question + answer "4.5 m" completes the ORIGINAL request (all originally-stated params intact).
- [ ] Refinement of a `return_for_revision` run ("increase top slab to 450 mm") produces a new run and an improved verdict (shared criterion with proof-check).
- [ ] Suggestions (Phase 3): after a completed run, 2–3 chips render; each is < 15 words and references a real aspect of the run; clicking fills the prompt box without submitting.
- [ ] Hard case — suggestions failure: with the suggestion call failing, the run still reports `completed` and the UI shows no error.
