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
│ Header: "IR Engineering Design & Proof-Check Platform" [tokens/cost] │
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

- **Component picker / gallery** (top of the left rail, Expansion Phase 1): a compact gallery of cards from `GET /api/components`, grouped by domain (Civil / Mechanical). **Available** cards — the five Civil types (Box Culvert, Retaining Wall, Plate Girder, Slab / T-beam, Pier & Abutment) and the three Mechanical types (Structural Steel / Fabrication Member, Rolling-Stock Member, Machine Element) — are selectable and show the declared code set. The picker still greys any **`coming_soon`** roadmap card (a "Coming soon" badge, clickable only to show what's planned, never an error), but as of Expansion Phase 3 the whole roadmap is delivered, so **all 8 cards are available and none are greyed**. Selecting a card sets the active component and switches the prompt-box placeholder + type-aware hints; submitting sends `component_type`. A "Let the agent decide" option leaves it to auto-detect.
- **Auto-detect surfacing:** when no component is picked, after the `understand` step the classified component type is shown as a chip above the tabs ("Detected: Retaining Wall — switch"); the user can switch and re-run. This makes both selection paths (auto + explicit) visible and non-magical.
- **Mode toggle** (left rail, top of the prompt panel, Vetting Phase 1): **Design** | **Vet a submitted design**. Design mode is the existing prompt flow. **Vet mode** replaces the prompt box with a file **upload dropzone** (accepts DXF / PDF / PNG / JPEG, up to 5 files / 25 MB each) + a **Vet** button, restricts the component picker to `supports_vetting` cards (only **Box Culvert** enabled this phase), and posts `POST /api/sessions/{id}/vettings` (multipart). A `supports_vetting=false` card shows a muted "Vetting — coming in a later phase" label (a stub, never an error). Once a vet run starts it streams through the SAME tracker/SSE as a design run.
- **Prompt box** (left rail, always visible in Design mode): multiline textarea + "Design" button (label switches to "Answer" when the agent has asked a clarifying question, "Refine" after a completed run). Disabled with a visible reason while a run is active. Placeholder shows the canonical example prompt.
- **Turn history** (left rail): each turn = user prompt + agent outcome chip (Completed / Needs input / Out of scope / Failed) + the clarifying question or scope statement when present. Clicking a past turn loads that run into the tracker + tabs (from the snapshot endpoint).
- **Suggestion chips** (left rail, under history): 2–3 refinement suggestions after a completed run; clicking one fills the prompt box. *Labelled stub until Phase 3.*
- **Step tracker:** the six fixed steps with states pending (grey) / active (pulsing + spinner) / done (check) / skipped (grey with "Coming in Phase N" tag) / failed (red). Driven by SSE `step` events. Elapsed time counts up live; freezes at `done`.
- **Status line:** the narrated plain-language line from SSE `narration` events (the streamed design plan appears here first, then per-step status). Warnings from `warning` events render as amber banners beneath it (e.g. abnormally high fill) — visually distinct from errors.
- **Token/cost display** (header, always visible): this run's tokens + cost, and the session running total — updated by the SSE `tokens` event. Format: `12.4k tok · $0.19 run · $0.83 session`.

**Artefact tabs** (each fires its content in as its SSE `artefact` event arrives — a tab never blocks on another):

0. **Stability / Type Summary** *(Expansion Phase 1; type-aware — retaining wall only)* — for a retaining wall, a compact panel from the snapshot's `type_summary`: FoS overturning, FoS sliding (each vs its required minimum, green/red), and max bearing pressure vs SBC with a pass/fail indicator. For a culvert this panel shows the member-check summary (or is absent — the frontend renders whatever `type_summary` provides; a missing panel is never a bug). Type-aware panels are driven purely by `component_type` + `type_summary`, so a new component's summary needs no new frontend code beyond a small renderer.
1. **Drawing** *(real from Phase 1)* — the GA drawing SVG inlined inside a pan/zoom wrapper (`react-zoom-pan-pinch`: wheel zoom, drag pan, double-click reset, zoom controls). Toolbar: **Download DXF** button (`ga.dxf` — "opens in AutoCAD and free viewers"). Loading state: skeleton sheet with "Drawing the GA…" while the run is mid-Draw.
2. **Calc Sheet** *(Phase 2; labelled stub in Phase 1)* — the clause-cited calculation sheet rendered from `calc_sheet.json`: sections (Loading → Analysis → Member checks), every line showing description, value + unit, and clause/source citation (incl. the ACS correction-slip level of every loading table). Each number is an **expandable calc-trail row**: click to drill down to formula + substituted inputs; inputs that are themselves computed link deeper. An **Assumptions** block at top lists every defaulted value and its source (user / preset / engine default).
3. **Proof-Check** *(Phase 2; labelled stub in Phase 1)* — four stacked blocks: (a) verdict banner — green "Recommended for approval" or red "Return for revision"; (b) the severity-graded memo (markdown-rendered, via `react-markdown`); (c) the compliance matrix table — `clause | requirement | computed | limit | status` with PASS (green) / OBSERVATION (amber) / NON-CONFORMITY (red) row accents; (d) BMD/SFD diagrams (SVG) side by side with the FE-vs-closed-form agreement figure captioned.
4. **3D Model** *(Phase 3; labelled stub in Phases 1–2)* — `@google/model-viewer` (dynamic import, `ssr: false`) showing `model.glb` with `camera-controls`; **Download STEP** button ("opens in FreeCAD — free").
5. **Library** *(Phase 3; labelled stub in Phases 1–2)* — the audit trail: table of all runs (timestamp, prompt, params summary, verdict chip, cost, duration) with session filter; clicking a row loads that run into the tracker + tabs. Presets editor (name + defaults form) lives here too.
6. **Vetting Report** *(Vetting Phase 1; shown/active for `mode="vet"` runs only)* — from the snapshot's `vetting` payload: (a) a verdict banner — green **"Accept — compliant with the cited IRS codes"** (`recommended_for_approval`) or red **"Return for revision"** (`return_for_revision`); (b) an **Extracted inputs** provenance list — each `{field, value, unit, source}` with the source badge (drawing / calc / assumed); (c) the **findings table** — `clause | requirement | claimed/computed | limit | utilization % | status | severity | comment` with PASS (green) / OBSERVATION (amber) / NON-CONFORMITY (red) row accents (reusing the ProofCheckPanel severity chips); (d) the **vetting memo** (markdown via `react-markdown`). In vet mode Draw and 3D show a grey "skipped — not applicable to vetting" tag; the Calc Sheet and Proof-Check tabs still fill (the check-only calc sheet + compliance run over the given design). For a design run this tab is hidden (or a one-line "Vetting Report appears for submitted-design reviews" note) — never a bug.

**Actions available:** submit design / answer clarification / refine; pan-zoom drawing; download DXF / STEP; expand calc-trail rows; click suggestion chip; browse library and reload past runs; edit presets (Phase 3).

## Stub Presentation Rules (a stub must NEVER look like a bug)

- A stubbed tab renders a designed panel: dashed border, muted illustration/icon, a **"Coming in Phase N"** badge, one sentence describing exactly what will appear ("The clause-cited calculation sheet with drill-down to every formula lands in Phase 2"), and — where it sells the vision — a static preview mock clearly watermarked "PREVIEW".
- Stub tabs stay enabled (clickable) so the presenter can show the roadmap; they are visually distinct from loading (no spinners) and from errors (no red).
- The step tracker uses the same rule: `skipped` steps show the grey "Coming in Phase N" tag, never a failure state.
- Suggestion chips area in Phases 1–2 shows a single muted chip: "Refinement suggestions — coming in Phase 3".
- **Greyed component cards** (any future `coming_soon` roadmap item): muted card + "Coming soon" badge + one line naming what it will design; clickable to reveal the roadmap, visually distinct from available cards (never an error/disabled-looking bug). As of Expansion Phase 3 the roadmap is fully delivered, so **no card is currently greyed** — this rule stands ready for future roadmap additions.

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

**Key files (frontend slice surface):** `frontend/src/app/page.tsx` (studio layout), `frontend/src/components/{ComponentPicker,DetectedTypeChip,StepTracker,StatusLine,PromptPanel,ModeToggle,VettingUpload,TurnHistory,SuggestionChips,ArtefactTabs,TypeSummaryPanel,DrawingViewer,CalcSheet,ProofCheckPanel,VettingReportPanel,Model3DViewer,LibraryPanel,PresetsEditor,TokenCostBadge}.tsx`, `frontend/src/lib/{api.ts,sse.ts,types.ts}`. `TypeSummaryPanel` renders `component_type`-specific summaries (stability for the retaining wall) generically from `type_summary`. `ModeToggle` + `VettingUpload` drive Design/Vet mode (Vetting Phase 1); `VettingReportPanel` renders the `mode="vet"` report from the snapshot's `vetting` payload, reusing the ProofCheckPanel severity chips + memo renderer.
