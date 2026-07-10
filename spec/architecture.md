# Architecture

---

## System Overview

A single-machine, single-origin web application that runs entirely on the presenter's laptop: a FastAPI backend (port 8001) serves both the JSON API and the built Next.js static frontend at `/app/`. A LangGraph pipeline orchestrates each design run: Gemini handles natural-language understanding and narration; a **deterministic IRS engineering core** (pure Python, no LLM) does all sizing, analysis, code checks, drawing, and 3D geometry. Artefacts (DXF, SVG, GLB, STEP, calc JSON, memo) are written to disk and served by FastAPI. SQLite stores the audit trail (sessions, runs, artefact records, presets). The only network dependency at runtime is the Gemini API.

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

## Data Flow

1. **Trigger:** user submits a natural-language prompt (`POST /api/sessions/{id}/designs`). The API creates a `design_runs` row (status `running`), starts the LangGraph run in a background thread, and returns `run_id` immediately.
2. Each graph node publishes progress events (step transitions, narration, warnings, token usage) to the in-process event bus, keyed by `run_id`; the browser consumes them via `GET /api/designs/{run_id}/events` (SSE).
3. Gemini nodes (understand, extract, review-memo, suggestions) call `LLMClient`; deterministic nodes (analyse, check, draw, model3d, proof-check rules) run the engineering core.
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
