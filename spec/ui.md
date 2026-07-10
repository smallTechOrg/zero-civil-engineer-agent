# UI

The demo-grade single-page design studio at `http://localhost:8001/app/`. Quality bar: `harness/patterns/ui-ux.md` (all four states designed per view; feedback ≤100 ms; no fake progress). This UI is watched by senior leadership on a projector — generous type, high contrast, nothing cramped.

---

## UI Type

Web app — Next.js static export served by the backend (single origin). One screen (the Design Studio) with tabbed artefact panels; no routing beyond the single page.

## Views / Screens

### Screen: Design Studio (the only screen)

**Purpose:** type a design request, watch the agent work, inspect and download the artefacts, refine, and browse past designs.

**Layout (desktop-first, three zones):**

```
┌──────────────────────────────────────────────────────────────────────┐
│ Header: "IR Box Culvert Design & Proof-Check Agent"   [tokens/cost]  │
├──────────────┬───────────────────────────────────────────────────────┤
│ Session      │  Step tracker: ● Understand ● Extract ● Analyse       │
│ panel        │                ● Check ● Draw ● Review                │
│ (left rail)  │  Status line: "Sizing members for 4.0 m span…"  ⏱ 12s │
│              ├───────────────────────────────────────────────────────┤
│ · turn       │  Artefact tabs:                                       │
│   history    │  [Drawing] [Calc Sheet] [Proof-Check] [3D Model]      │
│ · prompt box │  [Library]                                            │
│ · suggestion │                                                       │
│   chips      │  (active tab content)                                 │
└──────────────┴───────────────────────────────────────────────────────┘
```

**Key elements:**

- **Prompt box** (left rail, always visible): multiline textarea + "Design" button (label switches to "Answer" when the agent has asked a clarifying question, "Refine" after a completed run). Disabled with a visible reason while a run is active. Placeholder shows the canonical example prompt.
- **Turn history** (left rail): each turn = user prompt + agent outcome chip (Completed / Needs input / Out of scope / Failed) + the clarifying question or scope statement when present. Clicking a past turn loads that run into the tracker + tabs (from the snapshot endpoint).
- **Suggestion chips** (left rail, under history): 2–3 refinement suggestions after a completed run; clicking one fills the prompt box. *Labelled stub until Phase 3.*
- **Step tracker:** the six fixed steps with states pending (grey) / active (pulsing + spinner) / done (check) / skipped (grey with "Coming in Phase N" tag) / failed (red). Driven by SSE `step` events. Elapsed time counts up live; freezes at `done`.
- **Status line:** the narrated plain-language line from SSE `narration` events (the streamed design plan appears here first, then per-step status). Warnings from `warning` events render as amber banners beneath it (e.g. abnormally high fill) — visually distinct from errors.
- **Token/cost display** (header, always visible): this run's tokens + cost, and the session running total — updated by the SSE `tokens` event. Format: `12.4k tok · $0.19 run · $0.83 session`.

**Artefact tabs** (each fires its content in as its SSE `artefact` event arrives — a tab never blocks on another):

1. **Drawing** *(real from Phase 1)* — the GA drawing SVG inlined inside a pan/zoom wrapper (`react-zoom-pan-pinch`: wheel zoom, drag pan, double-click reset, zoom controls). Toolbar: **Download DXF** button (`ga.dxf` — "opens in AutoCAD and free viewers"). Loading state: skeleton sheet with "Drawing the GA…" while the run is mid-Draw.
2. **Calc Sheet** *(Phase 2; labelled stub in Phase 1)* — the clause-cited calculation sheet rendered from `calc_sheet.json`: sections (Loading → Analysis → Member checks), every line showing description, value + unit, and clause/source citation (incl. the ACS correction-slip level of every loading table). Each number is an **expandable calc-trail row**: click to drill down to formula + substituted inputs; inputs that are themselves computed link deeper. An **Assumptions** block at top lists every defaulted value and its source (user / preset / engine default).
3. **Proof-Check** *(Phase 2; labelled stub in Phase 1)* — four stacked blocks: (a) verdict banner — green "Recommended for approval" or red "Return for revision"; (b) the severity-graded memo (markdown-rendered, via `react-markdown`); (c) the compliance matrix table — `clause | requirement | computed | limit | status` with PASS (green) / OBSERVATION (amber) / NON-CONFORMITY (red) row accents; (d) BMD/SFD diagrams (SVG) side by side with the FE-vs-closed-form agreement figure captioned.
4. **3D Model** *(Phase 3; labelled stub in Phases 1–2)* — `@google/model-viewer` (dynamic import, `ssr: false`) showing `model.glb` with `camera-controls`; **Download STEP** button ("opens in FreeCAD — free").
5. **Library** *(Phase 3; labelled stub in Phases 1–2)* — the audit trail: table of all runs (timestamp, prompt, params summary, verdict chip, cost, duration) with session filter; clicking a row loads that run into the tracker + tabs. Presets editor (name + defaults form) lives here too.

**Actions available:** submit design / answer clarification / refine; pan-zoom drawing; download DXF / STEP; expand calc-trail rows; click suggestion chip; browse library and reload past runs; edit presets (Phase 3).

## Stub Presentation Rules (a stub must NEVER look like a bug)

- A stubbed tab renders a designed panel: dashed border, muted illustration/icon, a **"Coming in Phase N"** badge, one sentence describing exactly what will appear ("The clause-cited calculation sheet with drill-down to every formula lands in Phase 2"), and — where it sells the vision — a static preview mock clearly watermarked "PREVIEW".
- Stub tabs stay enabled (clickable) so the presenter can show the roadmap; they are visually distinct from loading (no spinners) and from errors (no red).
- The step tracker uses the same rule: `skipped` steps show the grey "Coming in Phase N" tag, never a failure state.
- Suggestion chips area in Phases 1–2 shows a single muted chip: "Refinement suggestions — coming in Phase 3".

## Error States

- **Run failure:** the failed step turns red; a red banner shows the transparent failure (what was tried, why it failed — from the SSE `error` event) with a "Try again" affordance re-enabling the prompt box. Never a raw stack trace.
- **Out of scope:** rendered as a normal agent reply in the turn history (the graceful scope statement) — informational styling, not an error.
- **Clarification:** amber "One question:" card above the prompt box with the pointed question; prompt box focused, button reads "Answer".
- **SSE drop / reload:** the page rehydrates from `GET /api/designs/{run_id}` and re-subscribes; a brief "Reconnected" toast — never a frozen tracker.
- **Empty states:** first visit shows a hero explainer with the canonical example prompt as a one-click starter; empty Library says "Every design you run is stored here — run your first design".
- **Loading:** every action acknowledges ≤100 ms (button disables + tracker goes active); artefact tabs show contextual skeletons, driven by real events only (no fake progress).

## Accessibility & copy

Per `harness/patterns/ui-ux.md`: real buttons, keyboard reachable, visible focus, labels linked, WCAG AA contrast; body ≥16 px (projector demo: tracker and status line larger). Copy is IR-literate: "GA drawing", "EUDL + CDA", "cushion", "proof-check memo", "25t Loading-2008" — the audience's own vocabulary.

## Tech Stack

See [architecture.md](architecture.md#stack) — Next.js 15 static export + Tailwind v4 (existing skeleton), `react-zoom-pan-pinch` for the drawing viewer, `@google/model-viewer` for GLB, `react-markdown` + `remark-gfm` for memo/narration rendering, native `EventSource` for SSE.

**Key files (frontend slice surface):** `frontend/src/app/page.tsx` (studio layout), `frontend/src/components/{StepTracker,StatusLine,PromptPanel,TurnHistory,SuggestionChips,ArtefactTabs,DrawingViewer,CalcSheet,ProofCheckPanel,Model3DViewer,LibraryPanel,PresetsEditor,TokenCostBadge}.tsx`, `frontend/src/lib/{api.ts,sse.ts,types.ts}`.
