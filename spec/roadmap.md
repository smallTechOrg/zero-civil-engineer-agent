# Roadmap

---

## What This Agent Does

An agentic AI **design platform** for Indian Railways engineering — a **multi-domain (civil AND mechanical)** demonstrator that designs an IR engineering component from a natural-language request and then proof-checks its own design against IR/IRS codes, covering both the DESIGN and REVIEW halves of the IR workflow with real, verifiable artefacts. It is built on a **shared core pipeline** (extract → analyse → check → draw → 3D → review) and a **Component Registry**: each structure/component type is a first-class plug-in implementing a common interface (typed parameters, sizing/analysis, code-checks, drawing template, 3D model, proof-check rules, type-specific outputs). The agent **auto-detects the component type from the prompt** ("design a 5 m retaining wall for a cutting" → retaining-wall module) and also offers an **explicit component picker/gallery**.

The **single box culvert** is the first registered component; the **RCC cantilever retaining wall** is the second. From one prompt the platform streams a visible plan, classifies the component, extracts typed parameters, runs the selected component's deterministic engineering core, and produces: a clause-cited calculation sheet with a drill-down calc trail, a dimensioned GA drawing (genuine DXF + in-browser SVG, RDSO-style title block), an interactive 3D model (GLB + STEP), and an automatic severity-graded proof-check memo with a compliance matrix and an independent cross-check.

Every component shares one **IR-protocol review spine**: design → independent check → severity-graded proof-check memo → rule-computed verdict, LLM-narrated but numerically grounded (no number in the memo that isn't in the deterministic results). Only the **code set** differs per component (civil → IRS Bridge Rules / IRS Concrete & Steel Bridge Codes / IS 456 / IS 800; mechanical, later → RDSO specs, IS 800, welding codes). Everything runs on the presenter's laptop; the only network call is the LLM API. No mocks anywhere — the DXF opens in AutoCAD and free viewers.

## Who Uses It

- **The presenter** (primary, demo day): drives a scripted live demo for IRICEN (Indian Railways Institute of Civil Engineering, Pune) trainers and senior railway leadership. The scripted path must be flawless, first-time-right.
- **Leadership self-serve** (immediately after): senior engineers type their own requests — so guard rails (scope gate, one clarifying question, unusual-value flags, transparent failures) matter as much as the happy path.

## Core Problem Being Solved

IR bridge design and independent proof-checking (DDC → Proof Checking Consultant → CBE, tightened post-Pamban) is manual, slow, and expertise-bottlenecked. The demonstrator shows that an agent can (a) produce a genuine, code-cited design package from plain language in under a minute, and (b) act as an instant, independent, clause-cited first-pass proof-checker — the strategic sell to this audience.

## Success Criteria

- [ ] **Platform:** a new component type is added by adding ONE `src/components/<type>/` module implementing the `ComponentModule` interface and registering it — with NO change to the graph shape, API routes, DB schema, or frontend shell (proven by the retaining wall landing purely as a registry plug-in).
- [ ] **Both selection paths work:** auto-detect routes a retaining-wall prompt to the retaining-wall module and a culvert prompt to the culvert module; the picker lets the user force either, and a `coming_soon` type degrades gracefully.
- [ ] **No culvert regression:** every existing culvert unit/validation/integration/E2E test stays green after the refactor.
- [ ] Both a retaining wall AND a culvert complete a full run (all artefacts + proof-check) in **under 60 seconds** each, with artefacts streaming in as ready (calc sheet before drawing before review).
- [ ] The downloaded DXF passes ezdxf's audit cleanly and opens in free CAD viewers with correct dimensions (verified manually before demo day).
- [ ] The engine matches its named validation fixtures (V1–V4 in [irs-engine.md](capabilities/irs-engine.md#validation-fixtures--named--the-phase-2-gate-runs-these)): EUDL/CDA transcription, RDSO B-10152/R cross-check ±10%, published worked example ±5%, FE-vs-closed-form ±5%.
- [ ] Every transcribed loading/code table surfaces its source document and ACS correction-slip level in the calc sheet and UI.
- [ ] The three-act demo script (design → refine → deliberately-under-designed run caught by the proof-check) passes headless E2E against the real LLM.
- [ ] Guard rails behave: missing critical param → exactly one pointed question; "design a suspension bridge" → graceful scope statement; abnormal fill → visible flag.

## What This Agent Does NOT Do (Out of Scope)

- **Not a generic CAD tool.** The platform stays IR-specific: every design on the demo path is IR/IRS-validated and clause-cited. Non-railway or non-engineering requests get a graceful scope statement.
- Component types beyond those **registered and `status="available"`** at the current phase. New civil types (plate girder, slab/T-beam, pier & abutment) and mechanical domains (structural steel/fabrication, rolling-stock members, machine elements) are on the phased plan below — they appear in the picker as greyed "Coming soon" until their phase lands, not silently absent.
- FOBs, multi-cell/double-line boxes, skew culverts remain unscheduled follow-ons.
- Loading standards beyond 25t Loading-2008 for the culvert (the loading layer is pluggable; DFC 32.5t is a later drop-in, not built now).
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
- **Codes are per-component, declared by the module** (`ComponentModule.codes`), and the demo path stays clause-cited under the IR umbrella. For the **culvert** the code set is IRS-only — an IS 456/IS 800/IRC citation on a culvert output is a defect. For the **retaining wall** the module declares IRS Concrete Bridge Code + IS 456 (RCC section design) + IR track-surcharge per Bridge Rules; a citation outside a component's declared `codes` set is the defect, not IS-citations per se.

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

## Expansion Phases (platform evolution — culvert Phases 1–3 above are DONE)

Phases 1–3 delivered the full culvert (design + proof-check + 3D + library). The expansion turns that single-structure tool into the multi-domain platform. **Expansion Phase 1 is the only phase built now.** All gates run against the real Gemini key in `.env`; live servers run on **port 8004** (`E2E_PORT=8004`) so a live 8001 is never touched.

### Expansion Phase 1 — Shared Framework + RCC Cantilever Retaining Wall (second registered component, FULL parity)

- **Goal:** extract the shared **Component Registry + component interface**, re-register the box culvert against it with **zero regression**, and add the **RCC cantilever retaining wall** as the second fully-featured component — NL/picker selection, deterministic engine (earth pressure + stability + RCC section design), GA drawing (DXF+SVG) + 3D (GLB+STEP), and the SAME IR-protocol proof-check (severity-graded memo + verdict) — with the whole existing UX (step tracker, narration, tokens/cost, calc drill-down, library, presets, refinement) working for BOTH types and a component picker/gallery exposing the roadmap via greyed "Coming soon" stubs.
- **Capabilities delivered:** [component-registry](capabilities/component-registry.md) (new) · [retaining-wall](capabilities/retaining-wall.md) (new) · plus every existing capability generalised to dispatch by component type (nl-design-intake, irs-engine, ga-drawing, calc-sheet, proof-check, model-3d, session-refinement, design-library).
- **The concrete agreed interface** (so slices b/c/d parallelise with a on the spec, not on each other's code) is defined in [architecture.md](architecture.md#the-component-interface-srccomponentsbasepy--the-concrete-contract-slices-build-against). Slices b/c/d import from `src/components/base.py` and the retaining-wall `params.py`/geometry model whose **field lists are fixed in [capabilities/retaining-wall.md](capabilities/retaining-wall.md)**.
- **Independent slices (disjoint owned paths):**
  - **(a) core-framework + registry + culvert re-registration** (backend). **Owns:** `src/components/__init__.py`, `src/components/base.py`, `src/components/registry.py`, `src/components/culvert/` (all — the adapter wrapping the unchanged `src/engine`, `src/drawing`, `src/model3d`, `src/proofcheck`), refactors of `src/graph/state.py` (adds `component_type`), `src/graph/nodes.py` (dispatch via `registry.get`), `src/graph/edges.py`, `src/graph/agent.py` (shape unchanged), `src/graph/runner.py` (thread `component_type` through initial state), `src/prompts/understand.md` + `src/prompts/extract.md` (classify + dynamic-schema instructions), `tests/unit/components/test_registry.py`, `tests/unit/components/test_culvert_module.py`, updates to `tests/unit/graph/`. **Deps:** none. Publishes the interface everything else builds against.
  - **(b) retaining-wall engine** (backend). **Owns:** `src/components/retaining_wall/params.py`, `sizing.py`, `analysis.py` (Rankine/Coulomb active & passive earth pressure incl. IR track surcharge + optional surcharge), `checks.py` (overturning/sliding/bearing stability factors + RCC stem/heel/toe section design per IS 456 / IRS Concrete Bridge Code, clause-cited), `calcsheet.py`, `summary.py` (type-specific stability summary: FoS overturning/sliding, max bearing vs SBC), `tests/unit/components/retaining_wall/engine/`, `tests/validation/test_rw_worked_example.py` (published worked example, ±5%). **Deps:** (a) — imports `base.py` result types + interface. Builds against the spec'd interface + its own param/geometry field lists.
  - **(c) retaining-wall drawing + 3D** (backend). **Owns:** `src/components/retaining_wall/drawing.py` (parametric ezdxf GA: cross-section + plan, dimensions, RDSO-style title block → SVG + DXF), `src/components/retaining_wall/model3d.py` (build123d solid → GLB + STEP), `tests/unit/components/retaining_wall/test_drawing.py`, `test_model3d.py`. **Deps:** (a) interface + (b)'s `RetainingWallParams`/`RetainingWallGeometry` field lists (fixed in the capability doc — so builds in parallel).
  - **(d) retaining-wall proof-check + module assembly** (backend). **Owns:** `src/components/retaining_wall/proofcheck.py` (retaining-wall-specific checklist + severity-graded memo through the SAME IR checking-engineer workflow; independent cross-check = recomputed stability factors, plus anaStruct where a stem-as-cantilever frame applies), `src/components/retaining_wall/module.py` (the `RetainingWallComponent` wiring b+c+d and calling `registry.register()`), `src/components/retaining_wall/__init__.py`, `src/prompts/rw_memo.md`, `tests/unit/components/retaining_wall/test_proofcheck.py`, `tests/unit/components/retaining_wall/test_module.py`. **Deps:** (a), (b), (c) — assembles the full module; imports are call-time so it builds in parallel against the spec'd signatures.
  - **(e) frontend** (frontend). **Owns:** `frontend/` (all), `tests/e2e/`. Component picker/gallery (Box Culvert + Retaining Wall available; greyed "Coming soon" for plate girder, slab/T-beam, pier & abutment, and a "Mechanical" domain group), auto-detect surfacing (shows the classified type + lets the user switch), type-aware prompts, type-aware artefact panels (retaining-wall **stability summary** panel; culvert panels unchanged), library/presets/refinement chips/cost/token/step-tracker all working for BOTH types. Stubs clearly labelled so they never read as bugs. **Deps:** none (builds against [api.md](api.md) + [ui.md](ui.md)).
- **Gate command (run in order from repo root; `E2E_PORT=8004`):**
  ```bash
  uv run alembic upgrade head && uv run alembic current
  uv run pytest tests/unit tests/validation tests/integration -q       # real Gemini; registry + RW engine + NO culvert regression
  cd frontend && pnpm install && pnpm build && cd ..
  E2E_PORT=8004 npx playwright test tests/e2e --reporter=line          # boots `uv run python -m src` on 8004
  ```
  The E2E asserts, on a styled render: (1) the canonical **culvert** prompt still completes with a real SVG GA + passing/graded proof-check (regression); (2) a **retaining-wall** prompt ("design a 5 m high RCC cantilever retaining wall, SBC 200 kN/m², BG single line track surcharge") auto-routes to the retaining-wall module, streams a real GA SVG, a stability-summary panel with FoS overturning/sliding + bearing-vs-SBC, and a proof-check verdict; (3) `ga.dxf` for the retaining wall round-trips via `ezdxf.readfile`; (4) the retaining-wall `model.glb` is a valid non-empty GLB. The integration suite includes a backend assertion that `ezdxf.readfile` opens the RW DXF and that the GLB parses.
- **How the user tests it (handoff seed):**
  1. `cd frontend && pnpm install && pnpm build && cd ..`, then `AGENT_PORT=8004 uv run alembic upgrade head && AGENT_PORT=8004 uv run python -m src`; open `http://localhost:8004/app/`.
  2. **Picker:** the gallery shows Box Culvert and Retaining Wall as available, with greyed "Coming soon" cards (plate girder, slab/T-beam, pier & abutment, Mechanical). Pick **Retaining Wall** → type-aware prompt hint appears. Submit `5 m high RCC cantilever retaining wall, SBC 200 kN/m², BG single-line track surcharge, backfill φ 30°`. Watch the tracker; a GA drawing (section + plan, RDSO title block) appears — download DXF, open in a free viewer; the **Stability** panel shows FoS overturning / sliding and max bearing vs SBC; the Proof-Check tab shows a verdict + memo.
  3. **Auto-detect:** in the prompt box (no picker) type `design a retaining wall for a 4 m cutting` → the agent classifies it as a retaining wall and shows the classified type.
  4. **Regression:** run the canonical culvert prompt → identical behaviour to before (GA, calc sheet, proof-check, 3D, library entry).
  5. **Stubs (not bugs):** greyed component cards say "Coming in a later phase"; everything on the two working types is real.

### Expansion Phase 2 — Civil Breadth: Plate Girder + Slab / T-beam Superstructure + Pier & Abutment

- **Goal:** register three more civil components **breadth-first** (NL/picker → typed params → GA drawing + core code-checks + IR-protocol proof-check + 3D), each as an independent `src/components/<type>/` plug-in; they then deepen toward culvert/retaining-wall parity in follow-up work. Each reuses the shared core and review spine; each declares its own code set (plate girder → IRS Steel Bridge Code / IS 800; slab & T-beam → IRS Concrete Bridge Code / IS 456; pier & abutment → IRS Bridge Substructure & Foundation Code).
- **Capabilities delivered:** [plate-girder](capabilities/plate-girder.md) · [slab-tbeam](capabilities/slab-tbeam.md) · [pier-abutment](capabilities/pier-abutment.md) (each a new component module; ≥3 capabilities).
- **Independent slices:** one module-directory slice per component type (`src/components/plate_girder/`, `src/components/slab_tbeam/`, `src/components/pier_abutment/`), each disjoint; one frontend slice (gallery cards go available, type-aware panels). **Deps:** the Phase-1 interface (stable).
- **Gate command:** `uv run pytest tests/unit tests/validation tests/integration -q && cd frontend && pnpm build && cd .. && E2E_PORT=8004 npx playwright test tests/e2e --reporter=line` — E2E exercises one prompt per new type plus culvert + retaining-wall regression.
- **How the user tests it:** pick or describe each new type; a real GA drawing + core checks + proof-check verdict appears; previously-built types unchanged.

### Expansion Phase 3 — Mechanical Domain: Structural Steel / Fabrication + Rolling-Stock Members + Machine Elements

- **Goal:** prove the abstraction is **not civil-specific** by registering mechanical components under the same interface and review spine, differing only in codes (IS 800 for structural steel, RDSO specs for rolling-stock members, standard machine-element codes) and drawing/doc conventions (mechanical/assembly drawings with **weld symbols** and GD&T from hand-validated parametric templates). Breadth-first (NL → mechanical drawing + core checks + proof-check), then deepen.
- **Capabilities delivered:** [structural-steel-member](capabilities/structural-steel-member.md) · [rolling-stock-member](capabilities/rolling-stock-member.md) · [machine-element](capabilities/machine-element.md) (≥3 capabilities).
- **Independent slices:** one module-directory slice per mechanical type (each disjoint `src/components/<type>/`); a mechanical-drafting helper is added **only if** `ezdxf` templates prove insufficient (decided at that phase, not now); one frontend slice (Mechanical domain group goes available). **Deps:** the Phase-1 interface + the drawing-convention hooks.
- **Gate command:** as Phase 2, with E2E covering one mechanical prompt (weld-symbol drawing renders, IS 800 / RDSO checks + proof-check verdict) plus civil regression.
- **How the user tests it:** switch to the Mechanical domain in the gallery, design a steel member or machine element; a mechanical drawing with weld symbols + a code-checked proof-check verdict appears; all civil types still work.

---

**After the platform (not scheduled):** DFC 32.5t loading drop-in, reinforcement drawings + BBS, deepening each breadth-first type to full parity — follow-ons beyond this POC.
