# IR Box Culvert Design & Proof-Check Agent

> **All commands run from the repo root.** The repo root IS the project — there is no subdirectory to `cd` into (the only exception is the explicit `cd frontend` step in the frontend build).

An agentic AI demonstrator for Indian Railways civil engineering: it designs single-cell RCC box culverts from natural-language requests and proof-checks its own design. From one prompt it streams a visible plan, extracts typed parameters with Gemini, runs a deterministic IRS engineering core (no LLM in the maths — 25t Loading-2008 EUDL + CDA, all load cases, closed-form rigid-frame analysis, IRS CBC member checks), and produces: a clause-cited calculation sheet with a drill-down trail, a dimensioned GA drawing as genuine DXF plus in-browser SVG, an interactive 3D solid (GLB viewer + STEP download from the same geometry), and an automatic proof-check — independent anaStruct FE cross-check with BMD/SFD diagrams, a 12-item compliance matrix, and a severity-graded memo with a rule-computed verdict. After every completed run it offers 2–3 grounded refinement suggestions, and the design library keeps every run replayable. Everything runs on your laptop; the only network call is the Gemini API.

## Setup

```bash
cp .env.example .env
```

Edit `.env` and set `AGENT_GEMINI_API_KEY` to your Google AI Studio API key (this is the only required manual step; the key never leaves `.env`).

## Install & build the frontend

```bash
cd frontend && pnpm install && pnpm build && cd ..
```

This produces `frontend/out/`, which the backend serves at `/app`. The server also starts without it (API-only mode).

## Database

```bash
uv run alembic upgrade head
uv run alembic current      # must print a revision (e.g. "0002 (head)") — blank output means it failed
```

## Run

```bash
uv run python -m src
```

Then open <http://localhost:8001/app/>.

| URL | What |
|-----|------|
| `http://localhost:8001/app/` | The Design Studio UI |
| `http://localhost:8001/health` | API liveness check |
| `http://localhost:8001/docs` | Interactive API docs (Swagger) |

Try the canonical prompt:

```
single box culvert, 4 m clear span, 3 m height, 2.5 m cushion, BG single line, 25t loading
```

Watch the six-step tracker: the Calc Sheet tab fills first (click any number to expand its formula and inputs), then the Drawing tab (pan/zoom, **Download DXF** — opens in AutoCAD and free viewers), then the 3D Model tab (orbit/zoom the culvert; **Download STEP** — opens in FreeCAD), then the Proof-Check tab (verdict banner, memo, 12-row compliance matrix, BMD/SFD). After completion 2–3 suggestion chips appear — click one and it fills the prompt box. A follow-up like `increase the fill to 4 m` regenerates everything in the same session, and every run stays browsable in the Library tab (including editing the default preset's values for future runs).

The demo money-shot: add `, top slab only 200 mm` to the canonical prompt → FAIL rows in the calc sheet and a red "Return for revision" verdict naming the thin slab; then type `increase the top slab to 450 mm` → the verdict recovers.

If 3D generation ever fails, the run still completes — a warning event fires and the 2D artefacts stand alone (the 3D tab shows a designed "unavailable" state, never an error page).

## Test

```bash
uv run pytest tests/unit -q                                # no API key needed
uv run pytest tests/unit tests/validation tests/integration -q   # the full gate: fixtures V1–V4 + real-Gemini full pipeline incl. 3D artefacts + suggestions (needs AGENT_GEMINI_API_KEY in .env)
npx playwright test tests/e2e              # E2E — boots the server itself via `uv run python -m src`
```

## Phase status

| Feature | Status |
|---------|--------|
| NL prompt → parameter extraction (Gemini), incl. one-clarifying-question + scope gate | **Real (Phase 1)** |
| Deterministic IRS engine — sizing, 25t-2008 loading, load cases, rigid-frame analysis, IRS CBC member checks | **Real (Phase 2)** |
| Calc Sheet — clause-cited sheet with total drill-down trail, streams before the drawing | **Real (Phase 2)** |
| Proof-check — anaStruct FE cross-check (BMD/SFD), 12-item compliance matrix, grounded memo, rule-computed verdict | **Real (Phase 2)** |
| GA drawing — genuine DXF + pan/zoom SVG in the browser | **Real (Phase 1)** |
| Session turn memory + refinement regeneration (the review → revise loop) | **Real (Phase 1–2)** |
| Live step tracker, narration, tokens/cost display (SSE), structlog JSON logs | **Real (Phase 1–2)** |
| 3D model — build123d solid from the same geometry as the drawing → `model.glb` (in-browser viewer) + `model.step` (**Download STEP**); non-fatal: a 3D failure warns and the 2D artefacts stand | **Real (Phase 3)** |
| Refinement suggestions — 2–3 grounded chips after every completed run (one Gemini call at finalize; failure is invisible-degrading) | **Real (Phase 3)** |
| Design library — every run listed with verdicts/costs, run replay, preset editing (`PUT /api/presets/{id}` with range validation; new runs pick up edited defaults, old runs keep their snapshot) | **Real (Phase 3)** |

## Environment variables

All are read from `.env` (prefix `AGENT_`). Only the Gemini key is required. The LLM provider is Gemini only (fixed, not configurable).

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `AGENT_GEMINI_API_KEY` | **yes** | — | Google AI Studio key; used for all agent LLM steps |
| `AGENT_PORT` | no | `8001` | Server port for `uv run python -m src` (host stays 127.0.0.1) |
| `AGENT_DATABASE_URL` | no | `sqlite:///./data/agent.db` | SQLite audit-trail DB (SQLite IS production for this local demo) |
| `AGENT_ARTIFACTS_DIR` | no | `data/artifacts` | Root for generated artefact files (`<run_id>/ga.dxf`, `ga.svg`, ...) |
| `AGENT_LLM_MODEL` | no | `gemini-2.5-pro` | Model for all agent nodes |
| `AGENT_GEMINI_INPUT_COST_PER_MTOK` | no | `1.25` | USD per million prompt tokens (cost display) |
| `AGENT_GEMINI_OUTPUT_COST_PER_MTOK` | no | `10.0` | USD per million completion tokens (cost display) |
| `AGENT_LOG_LEVEL` | no | `INFO` | structlog JSON log level |

## Project layout

```
src/            FastAPI API (api/), LangGraph agent (graph/), Gemini client (llm/),
                deterministic IRS core (engine/, drawing/, model3d/, proofcheck/),
                SQLite audit trail (db/), settings (config/), typed domain models
                (domain/), observability/ (structlog JSON + SSE progress bus)
frontend/       Next.js static export (served at /app)
alembic/        DB migrations (0002 = culvert schema + seeded default preset)
tests/          unit/ (no key), integration/ (real Gemini), e2e/ (Playwright)
spec/           The spec that drives the build (roadmap, architecture, api, data, ui, agent)
data/           SQLite DB + artefact files (gitignored, created on first run)
```
