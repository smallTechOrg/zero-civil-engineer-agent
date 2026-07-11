# Architecture

---

## System Overview

A single-machine, single-origin web application that runs entirely on the presenter's laptop: a FastAPI backend (port 8001) serves both the JSON API and the built Next.js static frontend at `/app/`. A LangGraph pipeline orchestrates each design run: Gemini handles natural-language understanding, **component-type classification** and narration; a **deterministic engineering core** (pure Python, no LLM) does all sizing, analysis, code checks, drawing, and 3D geometry. Artefacts (DXF, SVG, GLB, STEP, calc JSON, memo) are written to disk and served by FastAPI. SQLite stores the audit trail (sessions, runs, artefact records, presets). The only network dependency at runtime is the Gemini API.

**This is a multi-domain Indian Railways design PLATFORM, not a single-structure tool.** The pipeline is a **shared core** — extract → analyse → check → draw → 3D → review — that dispatches every engineering step to a **selected Component Module** through a common **component interface**, chosen from a **Component Registry**. Each structure/component type (box culvert, retaining wall, plate girder, … through the mechanical types) is a first-class module implementing that interface; **civil vs mechanical differ only in their codes, checks, and drawing/doc conventions**, not in the pipeline shape or the IR-protocol review spine. The box culvert is the FIRST registered component; the RCC cantilever retaining wall is the second. The abstraction is deliberately neither culvert- nor civil-specific.

## Component Map

```
Browser (Next.js static export at :8001/app/)
    │  fetch (JSON)            EventSource (SSE)
    ▼                              ▼
FastAPI (src/api/*) ──────► Progress event bus (src/observability/progress.py)
    │ POST design → background thread            ▲ publish(run_id, event)
    ▼                                            │
LangGraph pipeline (src/graph/*) ────────────────┘
    │            │
    │            ├──► LLMClient (src/llm/*) ──► Gemini API   [only external call]
    │            │
    ▼            ▼
Deterministic core                      Artefact store (data/artifacts/<run_id>/)
  src/engine/*   IRS sizing/analysis/checks/FE     ▲
  src/drawing/*  ezdxf GA template + SVG render ───┤
  src/model3d/*  build123d solid → GLB/STEP ───────┤
  src/proofcheck/* 12-item checklist + memo ───────┘
    │
    ▼
SQLite (src/db/*, Alembic migrations)  ← audit trail: sessions, design_runs, artifacts, presets
```

## Layers

| Layer | Responsibility |
|-------|----------------|
| Frontend (`frontend/`) | Design studio UI: prompt input, live step tracker, artefact tabs, library, token/cost display |
| API (`src/api/`) | REST endpoints with `ok()`/`api_error()` envelope; SSE progress stream; artefact file serving; static mount at `/app` |
| Agent graph (`src/graph/`) | LangGraph pipeline — see [agent.md](agent.md) for the full graph |
| LLM (`src/llm/`) | `LLMClient` wrapper over the Gemini provider; structured output + token usage; nodes never call the SDK directly |
| Engineering core (`src/engine/`, `src/drawing/`, `src/model3d/`, `src/proofcheck/`) | Deterministic: loading tables, sizing, rigid-frame analysis, IRS CBC checks, FE cross-check, ezdxf GA template, build123d solid, proof-check rules |
| Persistence (`src/db/`, `data/`) | SQLite via SQLAlchemy 2.0 + Alembic; artefact files on disk |
| Observability (`src/observability/`) | structlog JSON logging + in-process progress event bus for SSE |

## Component Registry & Component Interface (the platform spine)

The registry lives in `src/components/`. It is the single extension point: adding a structure type = adding one module directory and one `register()` call — no graph, API, DB or frontend change.

```
src/components/
├── base.py            # the ComponentModule Protocol + shared result dataclasses
├── registry.py        # register() / get(type_id) / list_components() / classify helpers
├── culvert/           # component #1 — box culvert (adapts existing src/engine, src/drawing, src/model3d, src/proofcheck)
│   ├── module.py      # BoxCulvertComponent implementing ComponentModule; register() on import
│   └── ...
└── retaining_wall/    # component #2 — RCC cantilever retaining wall (new, self-contained engine)
    ├── params.py  sizing.py  analysis.py  checks.py  calcsheet.py
    ├── drawing.py  model3d.py  proofcheck.py  summary.py
    └── module.py      # RetainingWallComponent implementing ComponentModule; register() on import
```

`src/components/__init__.py` imports every component module so each `register()` runs at import time; the registry is populated once at process start.

> **Expansion Phase 2 (civil breadth) — registry proof extends.** Three further civil components are now registered on this **unchanged** interface — `src/components/plate_girder/` (Steel Plate Girder Superstructure; codes IRS Steel Bridge Code + IS 800), `src/components/slab_tbeam/` (RCC Slab / T-beam Superstructure; codes IRS Concrete Bridge Code + IS 456) and `src/components/pier_abutment/` (Bridge Pier & Abutment Substructure; codes IRS Bridge Substructure & Foundation Code + IRS Bridge Rules) — each a new module directory + one `register()` call with **NO change to the graph shape, API routes, DB schema, or frontend shell**. Field lists are fixed in their capability docs ([plate-girder](capabilities/plate-girder.md), [slab-tbeam](capabilities/slab-tbeam.md), [pier-abutment](capabilities/pier-abutment.md)). The pier/abutment reuses the retaining wall's `stability` type-summary panel; the plate girder emits a `stress_summary` panel and the slab/T-beam a `flexure_summary` panel — all rendered by the type-agnostic artefact/summary surface. This is a **breadth-first** delivery (full culvert/RW-level parity deepening is later work); the interface definition below is unchanged.

> **Expansion Phase 3 (mechanical breadth) — the abstraction proven across domains.** Three **mechanical** components are now registered on this **unchanged** interface — `src/components/structural_steel_member/` (Structural Steel / Fabrication Member; codes IS 800 + IS 816; `utilisation_summary` panel), `src/components/rolling_stock_member/` (Rolling-Stock Member; codes RDSO Specifications + IS 800; `strength_summary` panel) and `src/components/machine_element/` (Machine Element; codes Machine Design Code + IS 816; `fos_summary` panel) — each a new module directory + one `register()` call with **NO change to the graph shape, API routes, DB schema, or frontend shell**. They draw with the **existing** `ezdxf` parametric templates (weld symbols + GD&T as hand-validated template geometry — no new CAD lib) and reuse `build123d` for their 3D solids. This confirms `civil` and `mechanical` differ only in codes / checks / drawing conventions. The gallery now shows **8 available components and no coming-soon previews** — the whole roadmap is delivered. Breadth-first (full parity deepening is later work); the interface below is unchanged.

### The component interface (`src/components/base.py`) — the concrete contract slices build against

Each component is an object (or module-level singleton) satisfying this Protocol. **These signatures are normative** — the retaining-wall slices (b, c, d) build against exactly this contract, so they parallelise with slice (a) against the spec, not against each other's code. Shared result types (`SizingOutput`, `AnalysisOutput`, `CheckOutput`, `ProofCheckOutput`) are defined in `base.py` and re-use the existing culvert domain shapes (`Assumption`, `CalcStep`, `CheckResult`) so no existing type is broken.

```python
class ComponentModule(Protocol):
    # ---- declarative metadata (drives the gallery, auto-detect, citations) ----
    type_id: str                       # "box_culvert" | "rcc_cantilever_retaining_wall"
    display_name: str                  # "Box Culvert" | "RCC Cantilever Retaining Wall"
    domain: Literal["civil", "mechanical"]
    summary: str                       # one line for the picker card
    status: Literal["available", "coming_soon"]
    codes: list[str]                   # ["IRS Concrete Bridge Code", "IS 456"] — per-component code set
    scope_examples: list[str]          # few-shot phrases for LLM auto-detect ("retaining wall for a cutting")
    critical_fields: list[str]         # must come from the user (never defaulted)
    param_model: type[BaseModel]       # the typed parameter schema (CulvertParams / RetainingWallParams)
    geometry_model: type[BaseModel]    # engine output (BoxGeometry / RetainingWallGeometry)

    # ---- intake ----
    def extraction_schema(self) -> type[BaseModel]: ...       # Pydantic schema for LLM structured output
    def clarify_question(self, missing_field: str) -> str: ...# ONE pointed question per critical field
    def unusual_value_warnings(self, params) -> list[str]: ...

    # ---- deterministic engineering pipeline ----
    def size(self, params) -> SizingOutput: ...               # geometry + assumptions + trail + warnings
    def analyse(self, params, geometry) -> AnalysisOutput: ...
    def run_checks(self, params, geometry, analysis) -> CheckOutput: ...  # code-checks + assumptions + trail
    def compose_calc_sheet(self, *, params, geometry, analysis, checks,
                           assumptions, warnings, trail_segments, out_dir: Path) -> Path: ...
    def draw(self, params, geometry, out_dir: Path, run_id: str) -> dict[str, Path]: ...  # {"ga_dxf","ga_svg"}
    def model3d(self, geometry, out_dir: Path) -> dict[str, Path]: ...    # {"model_glb","model_step"}

    # ---- IR-protocol review spine (SAME workflow for every component) ----
    def proof_check(self, *, params, geometry, analysis, checks, ga_dxf_path: Path,
                    out_dir: Path) -> ProofCheckOutput: ...   # checklist + verdict + FE/independent cross-check
    def memo_prompt(self) -> str: ...                         # system-prompt text for the memo narration

    # ---- type-specific outputs ----
    def type_summary(self, *, params, geometry, analysis, checks, proof) -> dict: ...
    # culvert → member-check summary; retaining wall → stability summary
    # (FoS overturning/sliding, max bearing pressure vs SBC)
```

`SizingOutput` = `{geometry: BaseModel, assumptions: list[Assumption], trail: list[CalcStep], warnings: list[str]}` (the existing `SizingResult` shape). `AnalysisOutput`/`CheckOutput`/`ProofCheckOutput` likewise wrap the existing culvert shapes; the retaining-wall module produces the same wrappers with its own semantics (analysis = earth-pressure + stability rather than a rigid frame; checks = RCC section design + stability factors). Drawing/3D artefact **kinds and filenames are the shared fixed set** (`ga.dxf`, `ga.svg`, `model.glb`, `model.step`, `calc_sheet.json`, `compliance.json`, `proof_memo.md`, `bmd.svg`/`sfd.svg`) so the API whitelist, DB `artifacts.kind` enum, and frontend are type-agnostic. A component that has no BMD/SFD (e.g. a retaining wall reports a pressure/stability diagram) still writes under an allowed kind or omits it — the frontend renders whatever artefacts arrive.

### Component selection (auto-detect AND picker)

- **Auto-detect (default):** the `understand` node's LLM call classifies the prompt against `registry.list_components()` metadata (`scope_examples`, `display_name`, `summary`) and returns `component_type` alongside the scope verdict + plan. "Design a 5 m retaining wall for a cutting" → `rcc_cantilever_retaining_wall`. Only `status == "available"` types are selectable; a recognised-but-`coming_soon` type routes to a graceful "that component is coming in a later phase" scope statement.
- **Explicit picker:** the frontend gallery lists every registered component (each `available`, or greyed if `coming_soon` — the whole roadmap is now delivered, so none remain greyed). Choosing one passes `component_type` on `POST /api/sessions/{id}/designs`; when present it **overrides** auto-detect (the LLM still validates scope and produces a type-aware plan/prompt hints).

### Culvert re-registration (zero regression)

The box culvert becomes `src/components/culvert/module.py` — a thin `BoxCulvertComponent` whose methods delegate to the **unchanged** `src/engine`, `src/drawing`, `src/model3d`, `src/proofcheck` functions. All existing culvert unit/validation/integration/E2E tests stay green; the refactor only moves the dispatch decision from hard-coded node bodies into `registry.get(component_type)`.

## Data Flow

1. **Trigger:** user submits a natural-language prompt (`POST /api/sessions/{id}/designs`). The API creates a `design_runs` row (status `running`), starts the LangGraph run in a background thread, and returns `run_id` immediately.
2. Each graph node publishes progress events (step transitions, narration, warnings, token usage) to the in-process event bus, keyed by `run_id`; the browser consumes them via `GET /api/designs/{run_id}/events` (SSE).
3. Gemini nodes (understand — incl. component classification, extract, review-memo, suggestions) call `LLMClient`; deterministic nodes (analyse, check, draw, model3d, proof-check rules) dispatch to the selected Component Module via `registry.get(state["component_type"])` and run its engineering core.
4. As each artefact is written to `data/artifacts/<run_id>/`, an `artefact` SSE event fires and the UI loads it — calc sheet before drawing before review; nothing blocks on the slowest artefact.
5. **Output:** run row updated (status, params, assumptions, checks, verdict, tokens, duration); artefact records inserted; the design library and session history read from these tables.
6. On page reload or SSE drop, the UI recovers from `GET /api/designs/{run_id}` (full snapshot) — SSE is the primary channel, the snapshot endpoint is the fallback.

## External Dependencies

| Dependency | Purpose | Failure Mode |
|------------|---------|--------------|
| Gemini API (`gemini-2.5-pro`) | NL understanding, parameter extraction, memo narration, refinement suggestions | Retry once with backoff; then run → `failed` with a transparent error (what was tried, why it failed) surfaced in the UI. Deterministic core never depends on it. |
| Local filesystem (`data/`) | Artefact storage, SQLite file | Fatal at startup if not writable; fail fast with a clear message |

There are **no** other external services: no hosted CAD APIs, no licensed software, no GUI processes.

## Stack

> Generic every-project rules (dev port 8001, real-key tests, DB-driver rules) live in `harness/patterns/tech-stack.md`. This section is what **this** project picked.

- **Language:** Python (skeleton `requires-python >=3.11`; developed on 3.12)
- **Agent framework:** LangGraph (existing skeleton graph, extended in place)
- **LLM provider + model:** Google Gemini, **`gemini-2.5-pro` for ALL agent nodes** (binding intake constraint; key already in `.env` as `AGENT_GEMINI_API_KEY`). Configured via `AGENT_LLM_MODEL=gemini-2.5-pro`; the settings default `llm_model` is changed to `gemini-2.5-pro` for this project.
- **Backend:** FastAPI + uvicorn, single origin (frontend static export mounted at `/app`). Port is configurable via `AGENT_PORT` (settings field `port`, default 8001); tests set `E2E_PORT` to run gates on 8002 without touching a live 8001 server
- **Database + ORM:** SQLite + SQLAlchemy 2.0 + Alembic. SQLite **is** the production database for this project — a local, single-user, on-laptop demo (binding: the brief mandates extending the SQLite skeleton). Tests run against SQLite, the same driver as production.
- **Frontend:** Next.js 15 static export (existing `frontend/`), React 19, Tailwind v4
- **Dependency management:** uv (`pyproject.toml`) / pnpm (`frontend/`)

> **Mechanical libraries (Expansion Phase 3 — now landed).** The mechanical modules draw with the **existing** `ezdxf` parametric templates: weld symbols + GD&T are drawn as hand-validated template geometry (same rule as civil — `ezdxf` proved sufficient, so no new CAD/drafting lib was added), and they reuse `build123d` for their 3D solids. RDSO / IS-800 / machine-design code tables are transcribed data, not a dependency. **No new library was needed for the mechanical domain** — the Component Registry kept the plug-in surface, not the library set, as the extension point.

> **Assumed:** keep the skeleton's `LLMClient`/provider abstraction (native `google-genai` SDK) rather than adding `langchain-google-genai`. The Gemini provider is extended with (a) structured output (`response_mime_type="application/json"` + `response_schema` from a Pydantic model) and (b) token usage capture (`response.usage_metadata`), returning an `LLMResult` (text or parsed model, prompt/completion tokens, latency ms). Nodes still never touch the SDK.

| Key library | Version | Purpose |
|-------------|---------|---------|
| `ezdxf` | `==1.4.4` (exact pin, **no `[draw]` extra**) | Parametric GA drawing template → genuine DXF; `drawing` add-on SVGBackend renders the same DXF to SVG server-side (pure Python — needs no extra); DXF read-back for the calc-vs-drawing proof-check item. The `[draw]` extra is deliberately NOT used: it pulls in AGPL-3.0 PyMuPDF and ~420 MB Qt (PySide6), while SVGBackend works with the plain install |
| `build123d` | `==0.11.1` (exact pin — pre-1.0 API drift) | 3D solid from the same parameters; `export_gltf(binary=True)` → GLB; `export_step()` → STEP |
| `anastruct` | `==1.7.0` | Independent 2D FE cross-check of the box frame (Phase 2); BMD/SFD via matplotlib |
| `matplotlib` | `>=3.9,<4` | BMD/SFD diagram rendering (SVG/PNG) and any raster/PDF output. **Replaces PyMuPDF everywhere** — PyMuPDF is AGPL and is banned |
| `google-genai` | `>=2.9.0` (existing) | Gemini SDK behind the provider abstraction |
| `react-zoom-pan-pinch` | `^4.0.3` | Pan/zoom wrapper around the inline drawing SVG |
| `@google/model-viewer` | `^4.3.1` | GLB display web component (dynamic import, `ssr: false`) |
| `react-markdown` + `remark-gfm` | latest | Render the proof-check memo and agent narration as markdown (never raw text) |
| `@playwright/test` | latest 1.x | Headless E2E smoke of the primary journey (`tests/e2e/`, root `playwright.config.ts`) |

> **Assumed:** **anaStruct over PyNite.** The box culvert is a closed 2D rigid frame — anaStruct is 2D-native, models it in ~a day, and ships BMD/SFD matplotlib plots for free; PyNite's 3D frame machinery adds integration surface with no benefit here. One FE dependency, not two. (anaStruct is LGPL-3.0 — fine as an unmodified dependency.)

**Avoid:**
- **PyMuPDF / `PyMuPdfBackend`** — AGPL-3.0; use ezdxf's SVGBackend + matplotlib instead (verified correction from research)
- **PyNite** — redundant beside anaStruct for a 2D frame (see above)
- **`dxf-viewer` npm (client-side WebGL DXF)** — README-admitted incomplete dimension/hatch/MTEXT rendering would make a correct drawing look broken to CAD-literate reviewers; server-rendered SVG is canonical
- **FreeCAD headless / any GUI-coupled MCP** — demo-fatal flakiness; FreeCAD is positioned only as the free viewer for the STEP download
- **LLM-written drawing/CAD code** — the GA drawing and 3D model come ONLY from hand-validated parametric templates; no generated code is ever executed
- **`langchain-google-genai`** — the skeleton's provider abstraction already does Gemini natively
- **IS 456 / IS 800 / IRC citations** — railway structures are governed by IRS codes; the proof-check flags IS-456-style citations as a defect

## Key Design Decisions

### Progress streaming: SSE (chosen) vs polling

**SSE.** One-directional server→client progress is exactly SSE's use case; FastAPI serves it natively via `StreamingResponse` (no new dependency); the app is single-origin localhost so there are no proxy/buffering hazards; and the demo's "watch the agent work" moment needs sub-second step updates that polling would blur. Design: `POST` returns `run_id` immediately; the graph runs in a background thread; nodes `publish(run_id, event)` to an in-process bus (`src/observability/progress.py`, one queue per active run); `GET /api/designs/{run_id}/events` drains the queue as SSE. `GET /api/designs/{run_id}` returns a full snapshot for reload-recovery/fallback. Single-process deployment makes the in-process bus safe (no Redis needed).

### DXF → SVG server-side rendering

The GA drawing is generated as DXF by the parametric ezdxf template, then rendered **by the same library** to SVG: `RenderContext` + `Frontend` + `draw_layout(modelspace)` + `SVGBackend.get_string(Page(...))` (~10 lines, pure Python, headless). Because generator and renderer share one engine, dimensions, hatches, linetypes and text display exactly as generated — the fidelity a CAD-literate audience will scrutinise. The SVG is stored as an artefact next to the DXF and inlined in the browser inside `react-zoom-pan-pinch`.

### Artefact storage & serving

All artefacts for a run live in `data/artifacts/<run_id>/` with fixed names (see [data.md](data.md#artefact-file-storage)). `GET /api/designs/{run_id}/artifacts/{filename}` serves them with correct MIME types (`Content-Disposition: attachment` for `.dxf`/`.step`/`.glb`). `data/` is gitignored; an `artifacts` DB row records each file (kind, path, size). Path traversal is blocked by whitelisting the fixed filename set.

### Run execution & concurrency

One uvicorn process. A design run executes in a `threading.Thread` (the graph and engine are sync); at most **one active run per session** — submitting while a run is active returns `409 RUN_ACTIVE`. Global concurrency is irrelevant for a single-presenter demo. No LangGraph checkpointer: the clarify step ends the run at `needs_input` and the answer arrives as the next session turn (see [agent.md](agent.md#human-in-the-loop-checkpoints)).

### Token & cost accounting

Every `LLMClient` call returns prompt/completion token counts from `usage_metadata`. Nodes accumulate them in graph state; `finalize` persists per-run totals and computed cost to `design_runs`; the session total is the sum over its runs. Cost rates are env-configurable: `AGENT_GEMINI_INPUT_COST_PER_MTOK` (default `1.25`), `AGENT_GEMINI_OUTPUT_COST_PER_MTOK` (default `10.0`).

> **Assumed:** Gemini 2.5 Pro pricing defaults $1.25 / $10 per million tokens (≤200k-token prompts); env-overridable so a price change never needs a code change.

### Observability (wired in Phase 1, never deferred)

structlog JSON to stdout: one log line per LLM call (node, model, prompt/completion tokens, latency, error), per node transition, per artefact write, per run outcome. The same events feed the SSE stream and the DB audit trail — three views of one event flow.

> **Assumed:** no LangSmith — no LangSmith key was provided at intake and the demo runs offline-except-Gemini; structured request/response logging + SSE step events + the DB audit trail satisfy the observability gate.

### Security posture

No LLM-generated code is ever executed (parametric templates only), so no sandbox is required. Localhost-only, single user, no authentication (see [api.md](api.md#authentication)). The Gemini key lives in `.env` and is never logged or stored in the DB.

## Deployment Model

Runs on the presenter's laptop. Build once: `cd frontend && pnpm install && pnpm build`. Run: `uv run alembic upgrade head && uv run python -m src` from the repo root, then open `http://localhost:8001/app/`. Internet is required only for Gemini API calls. No containers, no services, no cloud.
