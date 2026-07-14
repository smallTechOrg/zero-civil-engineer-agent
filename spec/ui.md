# UI

The enterprise-grade design workspace at `http://localhost:8001/app/` (E2E on `:8004`). Quality bar: `harness/patterns/ui-ux.md` (all four states designed per view; feedback ≤100 ms; no fake progress). This UI is watched by senior leadership on a projector AND used daily by IR civil engineers — generous type, high contrast, roomy spacing, nothing cramped. It is a **refined technical dark studio**: dark, projector-friendly, restrained accents, strong canvas contrast for drawings and 3D.

> This document describes the **redesigned** studio delivered by the Phase 4 Redesign (see [roadmap.md](roadmap.md#phases-of-development)). It supersedes the earlier single-page "Design Studio" layout. All backend data, endpoints, artefacts, the agent graph, the 8 registered component types and the extract→analyse→check→draw→3D→review pipeline are **unchanged** — this is a pure information-architecture + presentation redesign that reorganises the SAME elements into a lifecycle-oriented, extensible experience.

---

## Design principle: a lifecycle-oriented, extensible IA

The old UI crammed the whole product into one 858-line page: a 24rem left rail (picker + prompt + history) beside a flat six-tab results area, with an always-on generic "Stability" tab that was frequently blank, culvert-centric header/hero copy, and a tab that reset to Drawing on every run. The redesign reorganises the **same** functionality around how an engineer actually works — a design as a first-class record moving through lifecycle **stages** — and leaves visible, clearly-labelled room for future lifecycle stages this version does NOT build (Simulate, Test, Approve/sign-off).

Three organising ideas:

1. **A DESIGN is a first-class record.** Every run is a design record with a prompt, a component type, artefacts, a verdict and a status. Records are listed, filtered and **replayed** (today's turn/library history, elevated). Multi-design **PROJECTS** grouping is a visible, clearly-labelled STUB ("coming") — not built this version.
2. **A design moves through STAGES.** Opening a design shows a **Stage Rail**: **Define → Design → Review**, plus **Simulate / Test / Approve** shown as visibly-coming (non-functional, clearly-labelled) stages. The rail is the primary spatial metaphor and the extension seam for future lifecycle work.
3. **Prompt-first, gallery-backed entry.** Entry is "describe what you need" with agent auto-detect of the component type, backed by a roomy Civil/Mechanical gallery for users who want to pick or force a type. "Let the agent decide" stays prominent.

---

## UI Type

Web app — Next.js 15 static export served by the backend at `/app/` (single origin). A single-page application; no server routing beyond the one page. Client-side view state selects the active design, stage and inner panel. No new routes are added.

---

## Global shell

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ TOP BAR:  ◈ IR Engineering Design & Proof-Check Platform    [tokens/cost badge]│
├───────────────┬─────────────────────────────────────────────────────────────┤
│ DESIGN RECORDS│  WORKSPACE (the open design)                                  │
│ (left rail)   │  ┌─────────────────────────────────────────────────────────┐ │
│               │  │ Stage Rail: ① Define · ② Design · ③ Review               │ │
│ [+ New design]│  │             · ④ Simulate ⊘ · ⑤ Test ⊘ · ⑥ Approve ⊘     │ │
│ ▸ Projects ⊘  │  ├─────────────────────────────────────────────────────────┤ │
│  (stub)       │  │ Stage content (Overview / Define / Design / Review)      │ │
│ ── Records ── │  │                                                         │ │
│ ▪ 4×3 culvert │  │                                                         │ │
│   Reviewed ✓  │  │                                                         │ │
│ ▪ 5m ret.wall │  │                                                         │ │
│   Needs rev ✗ │  │                                                         │ │
│ ▪ …           │  │                                                         │ │
└───────────────┴──┴─────────────────────────────────────────────────────────┘┘
```

- **Top bar (always visible):** platform wordmark **"IR Engineering Design & Proof-Check Platform"** (NOT "Box Culvert" — the culvert-centric title is removed) + the **token/cost badge** (see below). Restrained: a thin accent rule, no clutter.
- **Design Records rail (left, always visible, collapsible):** `[+ New design]` action at top; a **Projects** disclosure shown as a clearly-labelled `⊘ coming` stub (multi-design grouping, not built); then the **Records list** — every design, newest first, each a card with prompt summary, component-type label, cost, and a **status chip** (Draft / Reviewed ✓ / Needs revision ✗). Clicking a record opens it in the workspace (replays its artefacts). This is today's TurnHistory + LibraryPanel merged and elevated into one persistent, first-class surface.
- **Workspace (right, the open design):** a **Stage Rail** header + the active stage's content. When no design is open, the workspace shows the **New-design entry** (prompt-first + gallery).

`⊘` marks a visibly-coming stub throughout — muted, dashed, a "coming" badge, never an error and never disabled-looking-as-a-bug.

---

## Views / Screens

### Screen: New-design entry (prompt-first, gallery-backed)

Shown in the workspace when `[+ New design]` is chosen or on first visit. Replaces the culvert-specific hero ("Design a single-cell RCC box culvert…").

- **Prompt-first hero:** platform-level headline ("Describe the component you need — the platform designs and proof-checks it") + a roomy multiline **prompt box** with a "Design" button and the canonical example as a one-click starter. **"Let the agent decide"** is the default and is visually prominent.
- **Component gallery (backing the prompt):** a roomy gallery from `GET /api/components`, grouped **Civil / Mechanical**. All 8 cards are `available` (Box Culvert, Retaining Wall, Plate Girder, Slab / T-beam, Pier & Abutment; Structural Steel / Fabrication, Rolling-Stock Member, Machine Element), each showing its declared code set and one-line summary. Selecting a card **forces** that type (sets `component_type`, swaps the prompt placeholder + type-aware hints); "Let the agent decide" clears it back to auto-detect. Any future `coming_soon` card greys with a "Coming soon" badge (none are greyed today). This is the existing ComponentPicker, given room to breathe as a real gallery rather than a compressed rail widget.

### Screen: Open design — the Stage Rail workspace

Opening a record (or starting a run) shows the **Stage Rail** and one stage's content. The rail is horizontal, top of the workspace:

| Stage | State | Content |
|-------|-------|---------|
| **Overview** (default landing) | always | verdict + key numbers + drawing thumbnail + cost (below) |
| **① Define** | active during intake | component choice + prompt + clarify loop |
| **② Design** | engine artefacts | Drawing · Calc Sheet · 3D Model |
| **③ Review** | sign-off view | verdict banner · compliance matrix · BMD/SFD + FE-agreement · proof memo |
| **④ Simulate** | `⊘ coming` stub | non-functional, clearly labelled |
| **⑤ Test** | `⊘ coming` stub | non-functional, clearly labelled |
| **⑥ Approve** | `⊘ coming` stub | non-functional, clearly labelled |

Clicking a stage switches the workspace content. During a live run the rail reflects progress (Define → Design → Review light up as the pipeline advances) but **never yanks** the user off a stage they are watching (see Tab/stage focus rule below).

#### Overview (default landing on opening a design)

Replaces the old always-on, frequently-blank generic "Stability" tab. Every design opens here. A roomy dashboard card:

- **Verdict banner:** green "Recommended for approval" / red "Return for revision" / neutral "Draft — not yet reviewed" (when Review hasn't produced a verdict).
- **Key numbers:** the component's headline figures rendered **generically from the existing `type_summary`** (no per-type frontend code beyond the generic renderer): e.g. culvert → member-check summary; retaining wall / pier → FoS overturning, FoS sliding, max bearing vs SBC; plate girder → bending/shear/deflection utilisation; slab/T-beam → flexure/shear; mechanical → utilisation/strength/FoS. A missing figure is never a blank panel — the Overview renders whatever `type_summary` provides and omits the rest cleanly.
- **Drawing thumbnail:** a small non-interactive preview of the GA SVG, click-through to the Design → Drawing panel.
- **Cost:** this design's tokens + cost.
- **Design metadata:** component type, code set (traceability — which IR/IS codes govern), created time, duration.

> The old generic "Stability" tab is **removed**; its content is folded into this Overview and driven per component type by `type_summary`. No blank panels.

#### ① Define stage

Component choice (gallery or "let the agent decide") + the prompt box + the clarify loop. Auto-detect surfacing: after the `understand` step the classified type shows as a chip ("Detected: Retaining Wall — switch"); the user can switch and re-run. A clarifying question renders as an amber "One question:" card above the prompt (button reads "Answer"). Refinement turns ("increase the fill to 4 m") happen here too (button reads "Refine"). This is the existing PromptPanel + DetectedTypeChip + ComponentPicker, relocated into the Define stage.

#### ② Design stage — engine artefacts

The deterministic artefacts, as inner panels (a segmented control, NOT a flat six-tab bar):

- **Drawing** — the GA SVG inside a pan/zoom wrapper (`react-zoom-pan-pinch`: wheel zoom, drag pan, double-click reset). Toolbar: **Download DXF** ("opens in AutoCAD and free viewers"). Loading: skeleton sheet with "Drawing the GA…" while mid-Draw.
- **Calc Sheet** — the clause-cited calc sheet from `calc_sheet.json`: sections (Loading → Analysis → Member checks), each line with description, value + unit, and **clause/source citation incl. ACS correction-slip level**; each number is an expandable calc-trail row (formula + substituted inputs; computed inputs link deeper). An **Assumptions** block lists every defaulted value and its source.
- **3D Model** — `@google/model-viewer` (dynamic import, `ssr:false`) showing `model.glb` with `camera-controls`; **Download STEP** ("opens in FreeCAD — free").

#### ③ Review stage — sign-off view

The REVIEW half as a dedicated sign-off surface (today's Proof-Check tab, elevated to a stage):

- **Verdict banner** — green "Recommended for approval" / red "Return for revision".
- **Compliance matrix** — `clause | requirement | computed | limit | status` with PASS (green) / OBSERVATION (amber) / NON-CONFORMITY (red) accents.
- **BMD/SFD + FE-agreement** — the BMD/SFD SVGs side by side with the FE-vs-closed-form agreement figure captioned.
- **Proof memo** — the severity-graded memo (markdown via `react-markdown`).

#### ④⑤⑥ Simulate / Test / Approve — visibly-coming stages

Each renders a designed **stub** panel: dashed border, muted icon, a "Coming in a later release" badge, and one sentence describing the future lifecycle stage (e.g. "Simulate will run parametric load sweeps against this design"). Clearly non-functional; never an error, never a blank.

---

## Cross-cutting surfaces (surfaced at DESIGN level)

- **Run/refine history (audit trail):** every run and refinement of a design is a replayable record in the Design Records rail; clicking one loads that snapshot into the workspace (stage rail + all stages). This is today's TurnHistory/Library elevated to a first-class, always-present rail.
- **Status-at-a-glance chips (across the records list):** each record shows **Draft** (completed, not yet a verdict / needs_input / out_of_scope) · **Reviewed ✓** (verdict `recommended_for_approval`) · **Needs revision ✗** (verdict `return_for_revision`). Derived client-side from the existing `status` + `verdict` fields — **no schema change**.
- **Code/standards traceability:** each design surfaces its governing code set (from the component's declared `codes`) on the Overview and inline clause citations in the Calc Sheet and Review — the data already lives in `calc_sheet.json` / `compliance.json`.
- **Token/cost transparency (top bar):** per-run tokens + cost AND a session/day running total. Format: `12.4k tok · $0.19 run · $0.83 session`. Driven by the SSE `tokens` event (running totals) — existing data, given a clearer per-run vs session split.
- **Step tracker + narration:** during a live run the six pipeline steps (Understand · Extract · Analyse · Check · Draw · Review) show pending/active/done/skipped/failed with elapsed time, and the narrated status line renders warnings as amber banners. This lives within the Stage Rail workspace (the Design stage shows it inline while artefacts stream).

---

## Tab / stage focus rule (fixes the tab-yank)

The old UI reset the active tab to **Drawing on every run** (`setActiveTab('drawing')` in `beginLiveRun`), yanking the user off whatever they were watching. **The redesign never changes the user's active stage/panel out from under them.** On a new run the workspace opens on the stage the user is in (Define while composing, or Overview) and advances the Stage Rail's *progress indicators* without forcing a stage switch. A user watching the Calc Sheet while refining stays on the Calc Sheet. Auto-advance to a stage happens only on explicit user action (submitting from Define may advance to Overview/Design once artefacts begin) and is a documented, non-jarring transition — never a mid-watch reset.

---

## Stub Presentation Rules (a stub must NEVER look like a bug)

- **Projects grouping** (records rail): a disclosure with a `⊘ coming` badge and one line ("Group related designs into a project — coming in a later release"). Clickable to reveal the intent; visually distinct from a real, empty list.
- **Simulate / Test / Approve stages:** designed stub panels (dashed border, muted icon, "Coming in a later release" badge, one descriptive sentence). Enabled/clickable so a presenter can show the lifecycle vision; visually distinct from loading (no spinners) and errors (no red).
- **Greyed component cards** (any future `coming_soon`): muted card + "Coming soon" badge + one line naming what it will design. As of Expansion Phase 3 the roadmap is fully delivered, so **no card is currently greyed**; the rule stands ready for future additions.
- The step tracker's `skipped` steps show a neutral tag, never a failure state.

---

## Error States

- **Run failure:** the failed step turns red; a red banner shows the transparent failure (what was tried, why) with a "Try again" affordance re-enabling the prompt. Never a raw stack trace.
- **Out of scope:** rendered as a normal agent reply in the design record / Define stage (the graceful scope statement) — informational styling, not an error.
- **Clarification:** amber "One question:" card above the prompt in the Define stage; prompt focused, button reads "Answer".
- **SSE drop / reload:** the workspace rehydrates from `GET /api/designs/{run_id}` and re-subscribes; a brief "Reconnected" toast — never a frozen tracker.
- **Empty states:** first visit shows the New-design entry (prompt-first hero + gallery) with the canonical example as a one-click starter; an empty Records rail says "Every design you run is stored here — run your first design".
- **Loading:** every action acknowledges ≤100 ms (button disables + tracker goes active); panels show contextual skeletons driven by real events only (no fake progress).

---

## Accessibility & copy

Per `harness/patterns/ui-ux.md`: real buttons, keyboard reachable, visible focus, labels linked, WCAG AA contrast on the dark theme; body ≥16 px (projector: tracker and status line larger). Copy is platform-level and IR-literate: "GA drawing", "EUDL + CDA", "proof-check memo", "compliance matrix", "25t Loading-2008" — the audience's own vocabulary. Header is the platform title, never a single component's name.

---

## Tech Stack

See [architecture.md](architecture.md#stack) — Next.js 15 static export + Tailwind v4, `react-zoom-pan-pinch` (drawing), `@google/model-viewer` (GLB), `react-markdown` + `remark-gfm` (memo/narration), native `EventSource` (SSE). **No new frontend dependency is required for the redesign** — it re-composes existing components into the new IA.

**Key files (frontend surface after the redesign):**
- `frontend/src/app/page.tsx` — thinned orchestrator: session/run state + SSE wiring only; layout delegated to shell components.
- New shell components: `frontend/src/components/AppShell.tsx` (top bar + rails), `DesignRecordsRail.tsx` (records list + status chips + projects stub, replacing the inline TurnHistory/Library merge), `StageRail.tsx` (Define/Design/Review + coming stubs), `OverviewPanel.tsx` (verdict + key numbers + thumbnail + cost, replacing the always-on Stability tab), `StatusChip.tsx`, `ProjectsStub.tsx`, `StageStub.tsx` (Simulate/Test/Approve).
- Reused (relocated, not rewritten): `ComponentPicker` (→ gallery in New-design entry), `PromptPanel`, `DetectedTypeChip`, `StepTracker`, `StatusLine`, `TokenCostBadge` (per-run/session split), `DrawingViewer`, `CalcSheet`, `ProofCheckPanel` (→ Review stage), `Model3DViewer`, `TypeSummaryPanel` (its generic renderer now feeds `OverviewPanel`).
- Retired: the flat `ArtefactTabs` six-tab bar (its `summary` tab is removed; its panels move under the Design/Review stages); `LibraryPanel` and `TurnHistory` fold into `DesignRecordsRail`.
- `frontend/src/lib/{api.ts,sse.ts,types.ts}` — `api.ts` `submitDesign` gains an optional `params` arg (M-00004 params-direct submit) alongside the redesign's `DesignStatusChip` helper in `types.ts`.
- **M-00004 component addition:** `frontend/src/components/M00004ParamForm.tsx` — the typed, range-validated parameter form shown in the **① Define** stage in place of the NL prompt box when the M-00004 (params-direct) gallery card is picked; it submits a `params` object. The **Open M-00004 sheet (PDF)** affordance (opens `m00004_sheet.pdf` inline) lives in `DrawingViewer.tsx`, shown only when the run emits the `m00004_sheet` artefact.
