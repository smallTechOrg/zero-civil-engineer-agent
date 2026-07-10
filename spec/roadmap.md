# Roadmap

---

## What This Agent Does

An agentic AI demonstrator for Indian Railways civil engineering: it designs single-cell RCC box culverts from natural-language requests and then proof-checks its own design — covering both the DESIGN and REVIEW halves of the IR civil workflow with real, verifiable artefacts. From one prompt ("single box culvert, 4 m clear span, 3 m height, 2.5 m cushion, BG single line, 25t loading") it streams a visible plan, extracts typed parameters, runs a deterministic IRS closed-form engine (EUDL + CDA per IRS Bridge Rules 25t Loading-2008; member checks per IRS Concrete Bridge Code), and produces: a clause-cited calculation sheet with a drill-down calc trail, a dimensioned GA drawing (genuine DXF + in-browser SVG), an interactive 3D model (GLB + STEP), and an automatic severity-graded proof-check memo with a compliance matrix and an independent FE cross-check. Everything runs on the presenter's laptop; the only network call is the LLM API. No mocks anywhere — the DXF opens in AutoCAD and free viewers.

## Who Uses It

- **The presenter** (primary, demo day): drives a scripted live demo for IRICEN (Indian Railways Institute of Civil Engineering, Pune) trainers and senior railway leadership. The scripted path must be flawless, first-time-right.
- **Leadership self-serve** (immediately after): senior engineers type their own requests — so guard rails (scope gate, one clarifying question, unusual-value flags, transparent failures) matter as much as the happy path.

## Core Problem Being Solved

IR bridge design and independent proof-checking (DDC → Proof Checking Consultant → CBE, tightened post-Pamban) is manual, slow, and expertise-bottlenecked. The demonstrator shows that an agent can (a) produce a genuine, code-cited design package from plain language in under a minute, and (b) act as an instant, independent, clause-cited first-pass proof-checker — the strategic sell to this audience.

## Success Criteria

- [ ] The canonical prompt completes a full run (all artefacts + proof-check) in **under 60 seconds**, with artefacts streaming in as ready (calc sheet before drawing before review).
- [ ] The downloaded DXF passes ezdxf's audit cleanly and opens in free CAD viewers with correct dimensions (verified manually before demo day).
- [ ] The engine matches its named validation fixtures (V1–V4 in [irs-engine.md](capabilities/irs-engine.md#validation-fixtures--named--the-phase-2-gate-runs-these)): EUDL/CDA transcription, RDSO B-10152/R cross-check ±10%, published worked example ±5%, FE-vs-closed-form ±5%.
- [ ] Every transcribed loading/code table surfaces its source document and ACS correction-slip level in the calc sheet and UI.
- [ ] The three-act demo script (design → refine → deliberately-under-designed run caught by the proof-check) passes headless E2E against the real LLM.
- [ ] Guard rails behave: missing critical param → exactly one pointed question; "design a suspension bridge" → graceful scope statement; abnormal fill → visible flag.

## What This Agent Does NOT Do (Out of Scope)

- Other structures: plate girders, retaining walls, FOBs, multi-cell/double-line boxes, skew culverts (plate-girder *review-only* is the named post-demo follow-on).
- Loading standards beyond 25t Loading-2008 (the loading layer is pluggable; DFC 32.5t is a later drop-in, not built now).
- Hydraulic design computation (vent area, HFL, afflux, scour per RBF-16) — echoed as user-supplied inputs in the proof-check, honestly marked "not verified".
- Reinforcement detailing drawings and bar-bending schedules — the GA drawing is the drawing deliverable.
- Auto-iterate-until-pass — revision is always user-triggered. (This refers to the agent-level design → review → revise loop; engine-internal check-governed sizing of AUTO-sized members is in scope — see [irs-engine.md](capabilities/irs-engine.md).)
- LLM-generated CAD/drawing code, DWG output, hosted deployment, authentication/multi-user, licensed-software integration (OpenSTAAD/OpenRail stay on the pitch slide).

## Key Constraints

- **Fixed demo date a few weeks out** — the demoable core (Phases 1–2) lands early; 3D/library polish (Phase 3) is the bonus tier and is cuttable without harming the core story.
- Runs entirely on the presenter's laptop (localhost:8001); internet used only for LLM API calls; zero paid licenses or GUI CAD processes.
- LLM = Gemini `gemini-2.5-pro` for ALL agent steps (key already in `.env` as `AGENT_GEMINI_API_KEY`).
- Full run ≤ ~60 s; UI shows the agent working the whole time (step tracker, narration, elapsed time, tokens/cost).
- Engineering must be validated against published worked examples before demo day (fixtures V1–V4); a team IR engineer and an IRICEN contact pre-review the encoded tables and drawing conventions.
- IRS codes only — an IS 456/IS 800/IRC citation anywhere is a defect.

---

## Phases of Development

Three phases: Phase 1 (smallest first-time-right win), two requirements phases of ≥3 capabilities each. Every slice below lists its exact owned paths — disjoint within a phase; dependencies are declared where true. All gates run against the real Gemini API via `.env` and the production DB driver (SQLite — production for this local demo).

### Phase 1 — NL → Real Drawing (the smallest first-time-right win)

- **Goal:** the full primary journey, real end-to-end: type an NL request → watch the live step tracker with narrated status and elapsed time → parameter extraction (real Gemini, incl. the one-clarifying-question and scope-gate guard rails) → deterministic IRS engine sizes the culvert (**sizing only in this phase — full loads/analysis/checks land in Phase 2**, explicitly deferred) → hand-validated parametric DXF GA drawing → SVG with pan/zoom in the browser + "Download DXF" that opens cleanly in free viewers. Session turn memory works (a follow-up "increase fill to 4 m" regenerates the drawing). Tokens/cost display live. Calc Sheet, Proof-Check, 3D, Library tabs are clearly-labelled "Coming in Phase N" stubs (never mistakable for bugs). Observability (structlog JSON per LLM call/node/run) wired from day one.
- **Capabilities delivered:** [nl-design-intake](capabilities/nl-design-intake.md) (full) · [irs-engine](capabilities/irs-engine.md) (sizing subset) · [ga-drawing](capabilities/ga-drawing.md) (full) · [session-refinement](capabilities/session-refinement.md) (turn memory + refinement regeneration; suggestions deferred to Phase 3).
- **Independent slices (parallel build units):**
  - `p1-domain-engine` (backend) — CulvertParams/BoxGeometry/Assumption/CalcStep models + sizing engine with defaults and trail. Owns: `src/domain/culvert.py`, `src/engine/__init__.py`, `src/engine/sizing.py`, `src/engine/defaults.py`, `src/engine/trail.py`, `tests/unit/engine/`. Deps: none.
  - `p1-drawing` (backend) — parametric ezdxf GA template + SVG render. Owns: `src/drawing/` (all), `tests/unit/drawing/`. Deps: `p1-domain-engine` (imports the domain models).
  - `p1-graph-llm` (backend) — graph rewrite (understand/extract/clarify/analyse/check-stub/draw/model3d-stub/review-stub/finalize/handle_error), LLM structured-output + usage extension, prompts, progress event bus, runner. Owns: `src/graph/` (all), `src/llm/client.py`, `src/llm/providers/gemini.py`, `src/prompts/` (all, incl. deleting `transform.md`), `src/observability/progress.py`, `tests/unit/graph/`, `tests/integration/`. Deps: `p1-domain-engine`, `p1-drawing` (calls their spec'd function signatures).
  - `p1-api-db` (backend) — schema migration 0002 (sessions/design_runs/artifacts/presets, drops legacy `runs`), sessions/designs/SSE/artifact endpoints incl. the designs listing (powers turn-history rehydration) and preset-read, settings additions (artifacts dir, cost rates, `llm_model` default `gemini-2.5-pro`), `.env.example` update, `pyproject.toml` deps for the phase (ezdxf dependency already pinned at scaffold as `ezdxf==1.4.4` — plain, no `[draw]` extra). Owns: `src/db/models.py`, `src/db/session.py` (if touched), `alembic/versions/0002_culvert_schema.py`, `src/api/` (all: replaces `runs.py` with `sessions.py`, `designs.py`, `presets.py`; router registration in `__init__.py`), `src/domain/api.py` (DTOs, replacing `src/domain/run.py`), `src/config/settings.py`, `.env.example`, `pyproject.toml`, `README.md`, `tests/unit/api/`, `tests/unit/db/`. Deps: `p1-graph-llm` (invokes `start_design_run`).
  - `p1-frontend` (frontend) — the full Design Studio per [ui.md](ui.md): prompt panel, step tracker, status line, Drawing tab (pan/zoom + DXF download), turn history, token/cost badge, labelled stub tabs; Playwright E2E. Owns: `frontend/` (all), `tests/e2e/`, `playwright.config.ts`, root `package.json`. Deps: none (builds against [api.md](api.md)).
- **Key surfaces / files:** as owned above; the agentic stack (graph, state, nodes, assembly) is fully wired this phase with `check`/`model3d`/`review` as labelled skip-stub nodes.
- **Gate command (run in order, from repo root):**
  ```bash
  uv run alembic upgrade head && uv run alembic current            # must print a revision
  uv run pytest tests/unit tests/integration -q                     # real Gemini key from .env
  cd frontend && pnpm install && pnpm build && cd ..
  npx playwright test tests/e2e --reporter=line                     # boots `uv run python -m src` via webServer; asserts styled render + real drawing
  ```
  The Playwright `webServer` command is exactly the documented run command (`uv run python -m src`), so the boots-via-run-command gate is covered; the E2E asserts the page is styled, submits the canonical prompt, watches the tracker advance, and asserts a real SVG drawing appears and the DXF download responds.
- **How the user tests it (handoff seed):**
  1. `cd frontend && pnpm install && pnpm build && cd ..`, then `uv run alembic upgrade head && uv run python -m src`; open `http://localhost:8001/app/`.
  2. Type: `single box culvert, 4 m clear span, 3 m height, 2.5 m cushion, BG single line, 25t loading` → Design. Watch the six-step tracker light up with the narrated plan and elapsed time; within ~30 s the Drawing tab shows a dimensioned GA sheet — pan/zoom it; click **Download DXF** and open the file in a free CAD viewer (dimensions read 4000/3000 etc.).
  3. Type: `increase the fill to 4 m` → the drawing regenerates with the 4.0 m fill dimension.
  4. Type: `design a suspension bridge` → graceful scope statement (not an error). Type: `box culvert 3 m height, 2 m cushion` → exactly one question asking for the clear span; answer `4.5 m` → drawing appears.
  5. Labelled stubs (not bugs): Calc Sheet / Proof-Check tabs say "Coming in Phase 2", 3D Model / Library say "Coming in Phase 3", one muted "suggestions coming in Phase 3" chip. Real: everything else on the path you just walked. Header shows live tokens/cost.

### Phase 2 — Engineering Core: Full IRS Engine + Calc Sheet + Proof-Check

- **Goal:** the REVIEW half becomes real. Full deterministic engine (25t Loading-2008 EUDL + CDA with cushion dispersal, all load cases, rigid-frame analysis, IRS CBC member checks) validated against the named fixtures; the clause-cited calc sheet with total drill-down streams in before the drawing; every design is automatically proof-checked (12-item checklist incl. independent anaStruct FE cross-check ±5% and DXF read-back, compliance matrix, severity-graded memo, verdict) — enabling the deliberately-under-designed demo act and the user-triggered design → review → revise loop.
- **Capabilities delivered:** [irs-engine](capabilities/irs-engine.md) (complete) · [calc-sheet](capabilities/calc-sheet.md) · [proof-check](capabilities/proof-check.md).
- **Independent slices:**
  - `p2-loading-tables` (backend) — pluggable LoadingStandard layer + transcribed 25t-2008 tables with source + ACS-level citations; fixture V1. Owns: `src/engine/loading/` (all), `tests/unit/engine/loading/`. Deps: none.
  - `p2-frame-analysis` (backend) — load-case builder + closed-form rigid-frame analysis + envelopes; domain model extensions (AnalysisResult, MemberForces); fixture V3. Owns: `src/engine/loads.py`, `src/engine/analysis.py`, `src/domain/culvert.py` (extensions), `tests/unit/engine/test_loads.py`, `tests/unit/engine/test_analysis.py`, `tests/validation/`. Deps: `p2-loading-tables`.
  - `p2-cbc-checks` (backend) — IRS CBC member checks + calc-sheet composer; fixture V2. Owns: `src/engine/checks.py`, `src/engine/calcsheet.py`, `tests/unit/engine/test_checks.py`, `tests/unit/engine/test_calcsheet.py`. Deps: `p2-frame-analysis` (AnalysisResult type).
  - `p2-fe-crosscheck` (backend) — anaStruct re-solve, diff vs closed-form, BMD/SFD SVG via matplotlib; fixture V4. Owns: `src/engine/fe_check.py`, `tests/unit/engine/test_fe_check.py`, `pyproject.toml` (adds `anastruct==1.7.0`, `matplotlib`). Deps: `p2-frame-analysis` (load-case interface).
  - `p2-proofcheck` (backend) — 12-item deterministic rules (incl. DXF read-back), memo composer + narration prompt. Owns: `src/proofcheck/` (all), `src/prompts/memo.md`, `tests/unit/proofcheck/`. Deps: `p2-cbc-checks`, `p2-fe-crosscheck` (result types).
  - `p2-graph-wiring` (backend) — analyse goes full, check/review nodes go real, integration tests for the full pipeline incl. the under-designed run. Owns: `src/graph/` (all), `tests/integration/` (updates), `README.md` (phase updates). Deps: all four slices above.
  - `p2-frontend` (frontend) — Calc Sheet tab (sections, expandable trail rows, assumptions block) and Proof-Check tab (verdict banner, memo, compliance matrix, BMD/SFD) go real; E2E additions. Owns: `frontend/` (all), `tests/e2e/`. Deps: none.
- **Gate command:**
  ```bash
  uv run pytest tests/unit tests/validation tests/integration -q    # fixtures V1–V4 + real-Gemini full pipeline
  cd frontend && pnpm build && cd ..
  npx playwright test tests/e2e --reporter=line                     # expands a calc row; asserts verdict banner + matrix render
  ```
- **How the user tests it:** run the canonical prompt → the Calc Sheet tab fills first (click any number: formula + inputs expand; assumptions block on top; ACS level visible on loading lines), then Drawing, then the Proof-Check tab: green "Recommended for approval", memo, 12-row matrix, BMD/SFD with the FE agreement figure. Then the demo money-shot: `same culvert but make the top slab only 200 mm` → amber warning at extraction, FAIL rows in the calc sheet, red "Return for revision" verdict naming the thin slab; type `increase top slab to 450 mm` → verdict recovers. Stubs remaining: 3D Model, Library, suggestion chips (all "Coming in Phase 3").

### Phase 3 — Demo Completeness: 3D + Library + Refinement Suggestions

- **Goal:** the remaining stubs go real: interactive 3D model (GLB viewer + STEP download) from the same parameters, the browsable design library (audit trail + run replay + presets editing), and post-run refinement suggestion chips — plus the cost/polish pass that makes self-serve smooth.
- **Capabilities delivered:** [model-3d](capabilities/model-3d.md) · [design-library](capabilities/design-library.md) · [session-refinement](capabilities/session-refinement.md) (complete: suggestions).
- **Independent slices:**
  - `p3-model3d` (backend) — build123d parametric solid → GLB + STEP, geometry-agreement tests. Owns: `src/model3d/` (all), `tests/unit/model3d/`, `pyproject.toml` (adds `build123d==0.11.1`). Deps: none.
  - `p3-library-api` (backend) — preset editing (PUT) with range validation + library-query polish (pagination/filters on the existing listing). Owns: `src/api/presets.py`, `src/api/designs.py` (listing additions only), `tests/unit/api/` (additions). Deps: none.
  - `p3-graph-suggestions` (backend) — model3d node goes real (non-fatal policy), finalize gains the suggestions call. Owns: `src/graph/` (all), `src/prompts/suggest.md`, `tests/integration/` (additions), `README.md` (phase updates). Deps: `p3-model3d` (imports the generator).
  - `p3-frontend` (frontend) — 3D tab (model-viewer, STEP download), Library tab (table, run replay, presets editor, empty state), suggestion chips; E2E additions. Owns: `frontend/` (all), `tests/e2e/`. Deps: none.
- **Gate command:**
  ```bash
  uv run pytest tests/unit tests/validation tests/integration -q
  cd frontend && pnpm build && cd ..
  npx playwright test tests/e2e --reporter=line                     # asserts 3D viewer loads, library lists runs, chips render
  ```
- **How the user tests it:** run the canonical prompt → 3D Model tab shows the rotating culvert (orbit/zoom); **Download STEP** and open it in FreeCAD. After completion, 2–3 suggestion chips appear — click one, it fills the prompt box; submit and everything regenerates. Open Library: every run from all phases listed with verdict chips and costs; click an old run — its drawing/calc/check replay exactly; edit the default preset's cover 50 → 40 mm and confirm old runs still show 50 while a new run shows 40. Nothing is a stub anymore.

---

**After the demo (not scheduled):** plate-girder review-only capability, DFC 32.5t loading drop-in, reinforcement drawings + BBS — the named follow-ons, deliberately out of this POC.
