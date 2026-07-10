# Agent

The LangGraph pipeline for one design run: NL prompt → scoped, **component-classified**, typed parameters → deterministic design → artefacts → automatic proof-check. Extends the skeleton graph (`src/graph/`) in place, replacing the `transform_text` capability slot.

**The graph shape is fixed and component-agnostic.** From the Component-Registry expansion on, every engineering node **dispatches** to the selected Component Module via `registry.get(state["component_type"])` (see [architecture.md](architecture.md#component-registry--component-interface-the-platform-spine)) rather than importing culvert code directly. `understand` classifies the component type; `extract` uses the component's extraction schema; `analyse`/`check`/`draw`/`model3d`/`review` call the component's interface methods. Adding a component type changes **no node** — only the registry.

---

## Agent Architecture Pattern

**Chosen:** **Graph (LangGraph)** with a **human-in-the-loop clarify checkpoint** — a fixed multi-step pipeline with conditional routing (scope gate, clarify branch, error routing), where LLM nodes orchestrate and narrate while every engineering computation is a deterministic tool.

Patterns used (from `harness/patterns/agentic-ai.md`): #5 Tool Use (deterministic engine/drawing/3D/proof-check functions), #6 Planning (visible streamed plan), #12 Exception Handling (error node, transparent failures), #13 Human-in-the-Loop (one clarifying question; user-triggered revise loop — never auto-iterate), #18 Guardrails (scope gate, schema-validated extraction, unusual-value flags), #19 Evaluation & Monitoring (structlog + SSE + validation fixtures). Deliberately **not** used: multi-agent, reflection, auto-retry-until-pass — the engineering core is deterministic, so a second LLM opinion adds risk, not quality.

---

## LLM Provider & Model

| Agent / Node | Provider | Model ID | Rationale |
|-------------|----------|----------|-----------|
| `understand` | Gemini | `gemini-2.5-pro` | Binding intake constraint: one model for ALL agent steps |
| `extract` | Gemini | `gemini-2.5-pro` | Structured output (Pydantic schema) — quality matters more than latency |
| `review` (memo narration only) | Gemini | `gemini-2.5-pro` | Narrates deterministic check results; never computes them |
| `finalize` (refinement suggestions, Phase 3) | Gemini | `gemini-2.5-pro` | 2–3 suggestions from the run summary |

All other nodes are deterministic — **zero LLM involvement** in analyse, check, draw, model3d, clarify, and all proof-check rule evaluation.

**Fallback behaviour:** one retry with backoff on Gemini timeout/5xx; then the run fails transparently (`handle_error` records what was attempted and why it failed; the UI shows it). No stub provider on any tested path.

**Prompt strategy:** system prompts as `.md` files in `src/prompts/` (`understand.md`, `extract.md`, `memo.md`, `suggest.md`). `extract` uses Gemini structured output against the `ExtractionResult` schema (built from `CulvertParams`, [data.md](data.md#culvertparams--the-typed-parameter-model)) with few-shot examples of railway phrasing ("BG single line", "2.5 m cushion", "25t loading"). All prompts instruct: IRS codes only — never IS 456/IS 800/IRC. Clause citations shown to the user come from the deterministic engine's citation records, never from the LLM.

---

## Tools & Tool Calling

Tools are pure functions the graph calls directly from nodes (rule-based, not LLM-selected — the pipeline order is fixed):

| Tool name | Description | Inputs | Output | Side-effects |
|-----------|-------------|--------|--------|--------------|
| `engine.size_culvert` | Geometry + member-thickness sizing | `CulvertParams` | `BoxGeometry` + `Assumption[]` + trail steps | none |
| `engine.analyse_frame` | Load cases + closed-form rigid-frame analysis (Phase 2) | `CulvertParams`, `BoxGeometry` | `AnalysisResult` (member forces per load case + envelopes) + trail steps | none |
| `engine.run_checks` | IRS CBC member checks (Phase 2) | `AnalysisResult`, `BoxGeometry`, `CulvertParams` | `CheckResult[]` (clause, computed, limit, status) | none |
| `engine.compose_calc_sheet` | Assemble clause-cited calc sheet with drill-down trail (Phase 2) | trail steps, checks, assumptions | `calc_sheet.json` | file write |
| `drawing.generate_ga` | Parametric ezdxf GA template + SVG render | `BoxGeometry`, `CulvertParams`, title-block fields | `ga.dxf`, `ga.svg` | file writes |
| `model3d.generate_solid` | build123d solid → GLB + STEP (Phase 3) | `BoxGeometry` | `model.glb`, `model.step` | file writes |
| `fe.cross_check` | anaStruct re-solve + diff vs closed-form; BMD/SFD render (Phase 2) | `CulvertParams`, `BoxGeometry`, `AnalysisResult` | `FeComparison` + `bmd.svg`, `sfd.svg` | file writes |
| `proofcheck.run_checklist` | 12-item deterministic proof-check incl. DXF read-back (Phase 2) | run record, `ga.dxf`, checks, `FeComparison` | `ChecklistItem[]` + compliance matrix | file write (`compliance.json`) |

**Tool selection strategy:** fixed pipeline order — no LLM tool choice anywhere.

**Tool failure handling:** every tool call is wrapped; an exception sets `state["error"]` and routes to `handle_error`. Partial-failure policy: `model3d` failure is **non-fatal** (log + `warning` event + continue — the 2D artefacts stand alone); all other tool failures are fatal for the run.

---

## Agent State

```python
class AgentState(TypedDict, total=False):
    # Identity
    run_id: str                      # set by runner at initialisation
    session_id: str                  # set by runner

    # Input
    user_prompt: str                 # this turn's NL request
    component_type: str              # registry type_id — set by `understand` (classify) or overridden by the API picker
    requested_component: str | None  # explicit picker choice from the API (overrides auto-detect when set)
    messages: list[dict]             # session history: [{role, content}] incl. prior clarification Q/A
    prior_params: dict | None        # accepted params from the session's last completed run (of the same component_type)
    preset_values: dict              # defaults preset applied to this run

    # Understand
    in_scope: bool                   # scope-gate verdict
    scope_message: str | None        # graceful out-of-scope statement (if rejected)
    plan_text: str                   # streamed plain-language design plan

    # Extract
    params: dict | None              # validated CulvertParams (merged: prior_params ← preset ← this turn)
    missing_critical: list[str]      # critical fields absent → clarify
    warnings: list[str]              # unusual-value flags (e.g. abnormally high fill)
    clarification_question: str | None

    # Deterministic pipeline (populated progressively)
    geometry: dict | None            # BoxGeometry
    assumptions: list[dict]          # explicit Assumption records (value + source)
    trail_segments: list[dict]       # engine trail segments, in engine order — input to the calc-sheet composer
    analysis: dict | None            # AnalysisResult (Phase 2)
    checks: list[dict]               # CheckResult rows (Phase 2)
    fe_comparison: dict | None       # FE-vs-closed-form diff (Phase 2)
    checklist: list[dict]            # 12-item proof-check results (Phase 2)
    verdict: str | None              # "recommended_for_approval" | "return_for_revision" (Phase 2)
    type_summary: dict | None        # component-specific summary from module.type_summary (RW → stability; persisted to type_summary_json)
    artefacts: list[dict]            # [{kind, filename}] as written
    suggestions: list[str]           # 2–3 refinement suggestions (Phase 3)

    # Accounting
    token_usage: list[dict]          # per-LLM-call {node, prompt_tokens, completion_tokens, latency_ms}

    # Control
    status: str                      # running | needs_input | out_of_scope | completed | failed
    error: str | None                # set by any node on fatal failure
    steps: list[dict]                # six-step tracker snapshot (persisted as steps_json at finish_run)
    started_monotonic: float         # monotonic clock at run start — elapsed-time base for step timings
```

---

## Nodes / Steps

UI step-tracker mapping (fixed six steps): **Understand**=`understand` · **Extract**=`extract`/`clarify` · **Analyse**=`analyse` · **Check**=`check` · **Draw**=`draw`+`model3d` · **Review**=`review`. Every node publishes `step`/`narration` events to the progress bus on entry/exit (see [api.md](api.md#sse-event-stream)).

### `understand`
**Reads:** `user_prompt`, `messages`, `requested_component`. **Writes:** `in_scope`, `component_type`, `scope_message`, `plan_text`, `token_usage`. **LLM:** yes — `understand.md`; JSON `{in_scope, component_type, scope_message?, plan}`.
**Behaviour:** Scope gate + **component classification** + plan. The prompt is built from `registry.list_components()` metadata (each available type's `display_name`, `summary`, `scope_examples`). In scope = the request maps to a registered `status="available"` component (designing/refining, incl. answering a pending clarification). If `requested_component` (picker) is set, it is used as `component_type` and the LLM only validates scope + produces a type-aware plan. A recognised-but-`coming_soon` type, or anything non-railway/non-engineering ("design a suspension bridge") → `in_scope=false` with a graceful one-paragraph scope statement naming what the platform currently covers; routes to `finalize` with status `out_of_scope`. In scope → set `component_type` and emit the plain-language design plan as narration events.

### `extract`
**Reads:** `user_prompt`, `messages`, `prior_params`, `preset_values`. **Writes:** `params`, `missing_critical`, `warnings`, `token_usage`. **LLM:** yes — structured output against `ExtractionResult`.
**Behaviour:** Dispatches to `module = registry.get(state["component_type"])`. Extracts typed parameters using `module.extraction_schema()` (LLM structured output) and validates against `module.param_model`; merges this turn's values over `prior_params` (refinement) over preset defaults. Missing `module.critical_fields` → `missing_critical` (never guessed, never defaulted). `module.unusual_value_warnings(params)` → `warnings`. For the culvert the schema is `CulvertParams` and critical = span/height/cushion (ranges in [data.md](data.md#culvertparams--the-typed-parameter-model)); for the retaining wall it is `RetainingWallParams` (see [capabilities/retaining-wall.md](capabilities/retaining-wall.md)). Deterministic post-validation in Python — the LLM extracts, Pydantic decides validity.

### `clarify`
**Reads:** `missing_critical`, `params`. **Writes:** `clarification_question`, `status="needs_input"`. **LLM:** no — templated question per missing field (deterministic = demo-safe).
**Behaviour:** Picks the single most critical missing parameter (component's `critical_fields` order) and phrases ONE pointed question via `module.clarify_question(field)` (culvert: span → height → cushion; retaining wall: retained height → SBC → backfill φ). Publishes a `clarification` event and **ends the run**. The answer arrives as the next session turn; `extract` merges it via `messages`/`prior_params`. Exactly one question per run — the merged next turn either completes the params or the new run asks the next-priority question.

> **Dispatch (all deterministic pipeline nodes):** `analyse`, `check`, `draw`, `model3d`, `review` each resolve `module = registry.get(state["component_type"])` and call the corresponding interface method (`module.size`/`analyse`/`run_checks`/`compose_calc_sheet`/`draw`/`model3d`/`proof_check`/`type_summary`). The node bodies are component-agnostic; geometry/analysis/checks are the module's own types, carried through state as dicts and rehydrated via `module.geometry_model` etc. The descriptions below use the culvert as the worked example; the retaining wall follows the same node flow with earth-pressure/stability semantics (see [capabilities/retaining-wall.md](capabilities/retaining-wall.md)).

### `analyse`
**Reads:** `params`, `component_type`. **Writes:** `geometry`, `assumptions`, `analysis`, trail steps. **LLM:** no.
**Behaviour:** Deterministic engine via `module.size` then `module.analyse`. **Culvert Phase 1: sizing only** — geometry + member thicknesses sufficient to drive the GA drawing (`engine.size_culvert`). **Phase 2: full** — load cases (DL, SIDL, EUDL+CDA with cushion dispersal, earth pressure, LL surcharge, box empty/full) and rigid-frame analysis (`engine.analyse_frame`). Every number recorded as a trail step (formula, inputs, value, clause/source citation).

### `check`
**Reads:** `analysis`, `geometry`, `params`. **Writes:** `checks`, calc-sheet artefact. **LLM:** no.
**Behaviour:** *Phase 1: labelled pass-through stub (publishes `step: skipped — Coming in Phase 2`).* Phase 2: IRS CBC member checks (flexure σcbc/σst working stress, shear, min steel, cover, crack width), then `engine.compose_calc_sheet` writes `calc_sheet.json` and publishes its `artefact` event — the calc sheet appears in the UI **before** drawing/review complete.

### `draw`
**Reads:** `geometry`, `params`, `run_id`. **Writes:** `artefacts` += ga.dxf, ga.svg. **LLM:** no.
**Behaviour:** Hand-validated parametric ezdxf GA template — **never LLM-written drawing code** — plan, longitudinal section, cross-section, notes, title block, dimension chains. Renders SVG server-side; publishes both `artefact` events immediately.

### `model3d`
**Reads:** `geometry`, `run_id`. **Writes:** `artefacts` += model.glb, model.step. **LLM:** no.
**Behaviour:** *Phases 1–2: labelled stub (skipped event).* Phase 3: build123d solid from the same `BoxGeometry` → GLB + STEP. **Non-fatal on failure** (warning event; 2D artefacts stand).

### `review`
**Reads:** run record, `checks`, `geometry`, `params`, ga.dxf path. **Writes:** `fe_comparison`, `checklist`, `verdict`, memo artefact, `token_usage`. **LLM:** yes — memo narration only (`memo.md`).
**Behaviour:** *Phase 1: labelled stub.* Phase 2: automatic proof-check after every design via `module.proof_check` — for the culvert `fe.cross_check` (anaStruct re-solve, diff, BMD/SFD) then `proofcheck.run_checklist` (12 deterministic items incl. DXF read-back and FE-agreement); for the retaining wall recomputed stability factors (+ anaStruct where a stem-as-cantilever frame applies) then its own checklist. One Gemini call narrates the severity-graded memo using `module.memo_prompt()` (`memo.md` for culvert, `rw_memo.md` for the retaining wall) from the deterministic results. A narration that fails the deterministic grounding validator is discarded (warning event) and the memo composes fully deterministically; only LLM transport failure (after 1 retry) is fatal. Verdict is computed by rule (any major non-conformity → `return_for_revision`), never by the LLM.

### `finalize`
**Reads:** everything. **Writes:** `status="completed"`, `suggestions`, DB persistence. **LLM:** Phase 3 only — 2–3 refinement suggestions.
**Behaviour:** Computes `module.type_summary(...)` and persists run totals (component_type, params, assumptions, checks, verdict, type_summary, tokens, cost, duration, steps) to `design_runs`; publishes the final `tokens` and `done` events. (Every LLM-calling node also publishes a running `tokens` event right after its call, so the header cost display is live throughout the run.) Phase 3 adds one Gemini call for suggestions (non-fatal on failure).

### `handle_error`
**Reads:** `error`, `run_id`. **Writes:** `status="failed"`, DB update.
**Behaviour:** Records status `failed` + `error_message`, logs with `run_id` context, publishes an `error` event with what was tried and why it failed (transparent failures — never a silent stall). Terminates the graph.

---

## Graph / Flow Topology

```
START
  │
  ▼
understand ──(error)─────────────────────────► handle_error ──► END
  │  │
  │  └─(not in_scope)──► finalize (status=out_of_scope) ──► END
  ▼
extract ──(error)──► handle_error
  │  │
  │  └─(missing_critical non-empty)──► clarify ──► END  (status=needs_input;
  ▼                                                 answer = next session turn)
analyse ──(error)──► handle_error
  ▼
check ──(error)──► handle_error          [Phase 1: skip-stub]
  ▼
draw ──(error)──► handle_error
  ▼
model3d ──(3D failure: warn + continue)  [Phases 1–2: skip-stub]
  ▼
review ──(error)──► handle_error         [Phase 1: skip-stub]
  ▼
finalize ──► END
```

**Conditional edges:**

| Source node | Condition | Target |
|-------------|-----------|--------|
| `understand` | `error` set | `handle_error` |
| `understand` | `not in_scope` | `finalize` |
| `understand` | else | `extract` |
| `extract` | `error` set | `handle_error` |
| `extract` | `missing_critical` non-empty | `clarify` |
| `extract` | else | `analyse` |
| `analyse` / `check` / `draw` / `review` | `error` set | `handle_error` |
| `model3d` | any failure | continue to `review` (warning only) |
| `clarify`, `finalize`, `handle_error` | — | `END` |

---

## Memory & Context

| Scope | Mechanism | What is stored |
|-------|-----------|----------------|
| **Within a run** | LangGraph state | All in-progress data |
| **Across runs (session)** | SQLite `design_runs` per session | Accepted params of the last completed run (`prior_params`), full turn history, artefacts, verdicts |
| **Conversation** | `messages` rebuilt from the session's turns (prompt + plan/clarification per turn) | Enables refinement ("increase fill to 4 m") and clarification answers — **wired in Phase 1** |

**Context window management:** sessions are short (a demo session is < 20 turns); full history fits trivially in `gemini-2.5-pro`'s context. Cap `messages` at the last 20 turns as a guard; no summarisation needed.

---

## Human-in-the-Loop Checkpoints

| Checkpoint | What is shown to the user | Expected user action | Timeout / default |
|------------|--------------------------|----------------------|-------------------|
| Clarify (one question) | The single pointed question + which parameter is missing | Answer in the prompt box (next session turn) | None — run rests at `needs_input` indefinitely |
| Design → review → revise loop | Proof-check memo + compliance matrix + verdict | User decides: refine (types a change / clicks a suggestion) or accept. **Never auto-iterates until pass** | None — user-triggered only |

> **Assumed:** the clarify "interrupt" is realised as a **terminal `needs_input` run + session-turn resume**, not a LangGraph checkpointer interrupt — same UX, no persisted-checkpoint state to corrupt mid-demo, and it reuses the exact refinement path (`extract` merging `prior_params` + `messages`).

---

## Error Handling & Recovery

**Node-level:** every node body is wrapped; exceptions set `state["error"]` (message includes the failed operation) and route to `handle_error`. Gemini calls: 1 retry with backoff on timeout/5xx before erroring.

**Graph-level (`handle_error`):** run status → `failed`, `error_message` persisted, `error` SSE event with what was tried and why it failed, structlog error with `run_id`.

**Resume / retry strategy:** no mid-run resume — runs are < 60 s; the user simply re-submits (the session carries their params forward). `needs_input` runs resume naturally via the next turn.

**Partial failure:** `model3d` degrades gracefully (warning, 2D artefacts stand); Phase 3 `suggestions` failure is swallowed (log only). Everything else is fatal-transparent.

---

## Observability

| Signal | What | Where |
|--------|------|-------|
| **Trace** | One structlog-bound context per run; one event per node enter/exit | stdout (structlog JSON) |
| **LLM calls** | node, model, prompt/completion tokens, latency, error | stdout + `token_usage` state + `design_runs` totals |
| **Tool calls** | tool name, key inputs, duration, success/error | stdout |
| **Progress** | step / narration / artefact / warning / tokens / done events | SSE bus (mirrors the log events) |
| **Run outcome** | status, duration_ms, verdict, cost | `design_runs` + stdout |

No LangSmith (see [architecture.md](architecture.md#observability-wired-in-phase-1-never-deferred)).

---

## Concurrency Model

- **Run isolation:** one active run per session; `POST` while active → `409 RUN_ACTIVE`. Each run's state is scoped by `run_id`; the progress bus keys queues by `run_id`.
- **Parallel nodes within a run:** none — the pipeline is sequential by design. Deterministic steps take milliseconds-to-seconds; Gemini calls dominate the < 60 s budget, and sequential order gives the tracker its clean narrative. Artefact *delivery* is incremental (each publishes on write), which satisfies "never block on the slowest artefact" without parallel branches.
- **Checkpointing:** none (see HITL note above).

---

## Graph Assembly (`src/graph/agent.py`)

```python
graph = StateGraph(AgentState)

for name, fn in [("understand", understand), ("extract", extract), ("clarify", clarify),
                 ("analyse", analyse), ("check", check), ("draw", draw),
                 ("model3d", model3d), ("review", review),
                 ("finalize", finalize), ("handle_error", handle_error)]:
    graph.add_node(name, fn)

graph.set_entry_point("understand")

graph.add_conditional_edges("understand", route_understand,
    {"handle_error": "handle_error", "finalize": "finalize", "extract": "extract"})
graph.add_conditional_edges("extract", route_extract,
    {"handle_error": "handle_error", "clarify": "clarify", "analyse": "analyse"})
graph.add_conditional_edges("analyse", route_on_error("check"),
    {"handle_error": "handle_error", "check": "check"})
graph.add_conditional_edges("check", route_on_error("draw"),
    {"handle_error": "handle_error", "draw": "draw"})
graph.add_conditional_edges("draw", route_on_error("model3d"),
    {"handle_error": "handle_error", "model3d": "model3d"})
graph.add_edge("model3d", "review")            # non-fatal: model3d never errors the run
graph.add_conditional_edges("review", route_on_error("finalize"),
    {"handle_error": "handle_error", "finalize": "finalize"})

graph.add_edge("clarify", END)
graph.add_edge("finalize", END)
graph.add_edge("handle_error", END)

compiled_graph = graph.compile()               # no checkpointer — see Concurrency Model
```

Runner entry point (`src/graph/runner.py`): `start_design_run(session_id: str, prompt: str, preset_id: str | None) -> str` — creates the `design_runs` row, builds initial state (history + prior params from the session), launches the graph in a background thread, returns `run_id` immediately.
