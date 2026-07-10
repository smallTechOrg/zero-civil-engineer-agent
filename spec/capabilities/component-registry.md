# Capability: Component Registry & Shared-Core Framework

## What It Does
Turns the culvert-only pipeline into a multi-domain platform: a curated, validated registry of component modules — each a first-class plug-in implementing a common interface — that the shared core pipeline dispatches to by component type, selected either by auto-detection from the prompt or by an explicit picker.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| Prompt | free text | User (prompt box) | yes |
| Explicit component choice | type_id | UI picker/gallery (`requested_component`) | no |
| Registered components | ComponentModule[] | `src/components/registry.py` (populated at import) | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| Selected component type | type_id | Agent state `component_type` → every pipeline node's dispatch |
| Component catalogue | list of {type_id, display_name, domain, summary, status, codes} | `GET /api/components` → picker/gallery |
| Type-aware artefacts | DXF/SVG/GLB/STEP/calc/memo | The selected module, via the shared node flow |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| LLM (see [agent.md](../agent.md#llm-provider--model)) | Classify the prompt against registered `available` components (in `understand`) | 1 retry, then fatal (transparent error); an explicit picker choice bypasses classification |

## Business Rules
- The interface (`ComponentModule` Protocol, `src/components/base.py`) is normative — see [architecture.md](../architecture.md#the-component-interface-srccomponentsbasepy--the-concrete-contract-slices-build-against). Every component declares metadata (`type_id`, `display_name`, `domain`, `summary`, `status`, `codes`, `scope_examples`, `critical_fields`, `param_model`, `geometry_model`) and implements the full method set (`extraction_schema`, `clarify_question`, `unusual_value_warnings`, `size`, `analyse`, `run_checks`, `compose_calc_sheet`, `draw`, `model3d`, `proof_check`, `type_summary`, `memo_prompt`).
- Adding a component type = adding ONE `src/components/<type>/` module + one `register()` call — NO change to the graph shape, API routes, DB schema, or frontend shell.
- Artefact **kinds and filenames are the shared fixed set** so the API whitelist, DB `artifacts.kind` enum and frontend stay type-agnostic; a component may omit kinds it doesn't produce.
- `civil` and `mechanical` components differ ONLY in codes, checks and drawing/doc conventions — never in the pipeline shape or the IR-protocol review spine.
- Selection: an explicit picker choice (`requested_component`) overrides auto-detect; otherwise `understand` classifies. Only `status="available"` types are selectable; `coming_soon` types are shown greyed and route to a graceful scope statement.
- The box culvert is re-registered against the interface as an adapter over the unchanged `src/engine`/`src/drawing`/`src/model3d`/`src/proofcheck` — zero behavioural change.

## Success Criteria
- [ ] `registry.list_components()` returns both `box_culvert` and `rcc_cantilever_retaining_wall` as `status="available"` (plus any `coming_soon` metadata entries), each satisfying the `ComponentModule` Protocol (checked structurally in a unit test).
- [ ] `registry.get("box_culvert")` drives a full culvert run producing byte-identical-in-shape artefacts to the pre-refactor pipeline; every existing culvert unit/validation/integration/E2E test passes unchanged.
- [ ] Auto-detect: "design a 5 m retaining wall for a cutting" classifies `component_type == "rcc_cantilever_retaining_wall"`; "single box culvert, 4 m span…" classifies `box_culvert` (real-LLM integration test).
- [ ] Picker override: submitting with `requested_component="rcc_cantilever_retaining_wall"` runs the retaining-wall module regardless of prompt phrasing.
- [ ] A `coming_soon` type ("design a plate girder") returns a graceful `out_of_scope` statement naming it as a future component — not an error.
- [ ] No node in `src/graph/nodes.py` imports a component-specific engine directly — all engineering dispatch goes through `registry.get(component_type)`.
