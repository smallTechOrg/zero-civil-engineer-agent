# Data Model

---

## Storage Technology

SQLite via SQLAlchemy 2.0 + Alembic (the skeleton's stack, extended in place). SQLite **is** production for this local single-user demo — tests run against the same driver. Artefact **files** live on disk under `data/artifacts/`; the DB stores their records. Migration `alembic/versions/0002_culvert_schema.py` creates the four tables below and drops the legacy skeleton `runs` table (the `transform_text` capability it served is replaced). Expansion-Phase-1 migration `alembic/versions/0003_component_platform.py` adds the `component_type` (default `box_culvert`, backfilled) and `type_summary_json` columns to `design_runs` — no table is dropped; the schema is otherwise component-agnostic (params/geometry are component-specific JSON, artefact `kind` is the shared fixed set). Vetting-Phase-1 migration `alembic/versions/0004_design_vetting.py` adds the `mode` (default `design`, backfilled) and `vetting_json` columns to `design_runs` — additive only, no table dropped; a vet run reuses the SAME `design_runs`/`artifacts` tables as a design run.

> **Assumed:** `design_runs.params_json` stays a free-form JSON blob keyed by the component's `param_model`; it is not reshaped per component, so no per-component tables are needed. The `artifacts.kind` set is shared across components (a retaining wall simply omits kinds it doesn't emit).

## Entities

### Entity: Session

A design conversation — the container for turns, the unit of cost totalling, and the scope of parameter carry-over.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | TEXT (uuid) | yes | Primary key |
| title | TEXT | yes | Auto-derived from the first prompt (first ~60 chars); not editable in the POC (no rename endpoint) |
| created_at | TIMESTAMP | yes | |
| updated_at | TIMESTAMP | yes | Touched on every run |

Session token/cost totals are **derived** (SUM over its runs) — never stored redundantly.

### Entity: DesignRun

One agent run = one turn: prompt in, artefacts + proof-check out. This is the audit trail: every run is stored forever with everything needed to reconstruct what the agent did and why.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | TEXT (uuid) | yes | Primary key; also the artefact directory name |
| session_id | TEXT FK → sessions.id | yes | |
| component_type | TEXT | yes (default `box_culvert`) | Registry `type_id` this run designed (`box_culvert` \| `rcc_cantilever_retaining_wall` \| …). Added by the Expansion-Phase-1 migration `0003`; existing rows backfill to `box_culvert` |
| mode | TEXT | yes (default `design`) | `design` (design a new component) \| `vet` (check-only vetting of a SUBMITTED design). Added by Vetting-Phase-1 migration `0004`; existing rows backfill to `design` |
| prompt | TEXT | yes | The user's NL request for this turn |
| status | TEXT | yes | `running` \| `needs_input` \| `out_of_scope` \| `completed` \| `failed` |
| plan_text | TEXT | no | The streamed design plan (Understand) |
| scope_message | TEXT | no | Graceful statement when `out_of_scope` |
| clarification_question | TEXT | no | Set when `needs_input` |
| params_json | TEXT (JSON) | no | Validated `CulvertParams` used for this run |
| assumptions_json | TEXT (JSON) | no | `Assumption[]` — every defaulted value with its source (preset / engine default) |
| warnings_json | TEXT (JSON) | no | Unusual-value flags raised at extraction |
| steps_json | TEXT (JSON) | no | Step-tracker snapshot: per step {name, status, started_at, ended_at} — written once at terminal `finish_run` (audit + completed-state snapshot); mid-run reload recovery comes from the SSE replay buffer, not this column |
| checks_json | TEXT (JSON) | no | `CheckResult[]` rows (Phase 2) |
| checklist_json | TEXT (JSON) | no | 12-item proof-check results (Phase 2) |
| verdict | TEXT | no | `recommended_for_approval` \| `return_for_revision` (Phase 2) |
| type_summary_json | TEXT (JSON) | no | Component's type-specific summary (culvert → member-check summary; retaining wall → stability summary {FoS overturning/sliding, max bearing, SBC}). Added by migration `0003` |
| suggestions_json | TEXT (JSON) | no | 2–3 refinement suggestions (Phase 3) |
| vetting_json | TEXT (JSON) | no | The full vetting report `{verdict, summary, inputs[], findings[]}` for a `mode="vet"` run (`null` for a design run). Added by migration `0004` |
| prompt_tokens | INTEGER | yes (default 0) | Sum over the run's LLM calls |
| completion_tokens | INTEGER | yes (default 0) | |
| cost_usd | REAL | yes (default 0) | Computed from env-configured rates |
| error_message | TEXT | no | Transparent failure record |
| started_at | TIMESTAMP | yes | |
| completed_at | TIMESTAMP | no | |
| duration_ms | INTEGER | no | |

### Entity: Artifact

One generated file belonging to a run.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | TEXT (uuid) | yes | Primary key |
| run_id | TEXT FK → design_runs.id | yes | |
| kind | TEXT | yes | `ga_dxf` \| `ga_svg` \| `calc_sheet` \| `compliance` \| `proof_memo` \| `bmd_svg` \| `sfd_svg` \| `model_glb` \| `model_step` \| `vetting_report` \| `vetting_memo` (last two: Vetting Phase 1) |
| filename | TEXT | yes | Fixed name from the layout below |
| mime | TEXT | yes | e.g. `image/vnd.dxf`, `image/svg+xml`, `model/gltf-binary`, `application/json`, `text/markdown` |
| size_bytes | INTEGER | yes | |
| created_at | TIMESTAMP | yes | |

### Entity: Preset

A named set of standards/defaults so prompts stay short and every assumption is explicit.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | TEXT (uuid) | yes | Primary key |
| name | TEXT | yes | e.g. "IR standard defaults" |
| is_default | BOOLEAN | yes | Exactly one default; applied when the user picks none |
| values_json | TEXT (JSON) | yes | Subset of `CulvertParams` non-critical fields (concrete grade, cover, soil parameters, …) |
| created_at / updated_at | TIMESTAMP | yes | |

Seeded by migration 0002 with one default preset (values = the engine defaults in the table below). Read-only until Phase 3 (editing UI).

### Relationships

`Session 1—N DesignRun 1—N Artifact`; `Preset` referenced by value (a run snapshots the preset values into `params_json`/`assumptions_json` — editing a preset never rewrites history).

---

## Component parameter models

Each component declares its own typed parameter model (`ComponentModule.param_model`). The culvert's is `CulvertParams` (below); the retaining wall's is `RetainingWallParams` (field list normative in [capabilities/retaining-wall.md](capabilities/retaining-wall.md)). Both follow the same discipline: **critical** fields must come from the user (missing → one clarifying question); all others default with an explicit `Assumption` record. `Assumption`, `CalcStep`, and the derived-geometry pattern are shared shapes reused by every component. Presets carry component-scoped non-critical defaults; a run snapshots the applied preset values into `params_json`/`assumptions_json`.

## CulvertParams — the culvert parameter model

The Pydantic model (in `src/domain/culvert.py`) that drives the culvert component: extraction schema, engine input, drawing input, 3D input, audit record. **Critical** fields must come from the user (never guessed — missing → the one clarifying question). All others default with an explicit `Assumption` record shown in the calc sheet.

| Field | Type | Critical | Default (preset) | Valid range / unusual-flag rule |
|-------|------|----------|------------------|--------------------------------|
| clear_span_m | float | **yes** | — | 1.0–8.0 hard; **> 6.0 → warning** (beyond RDSO standard family — agent flags, proceeds) |
| clear_height_m | float | **yes** | — | 1.0–6.0 hard |
| cushion_m | float | **yes** | — | 0.0–10.0 hard; **> 8.0 → warning** (abnormally high fill) |
| gauge | enum | no | `BG` | `BG` only in POC |
| tracks | int | no | 1 | 1 only in POC (single line) |
| loading_standard | enum | no | `25t-2008` | `25t-2008` only in POC (pluggable layer for DFC 32.5t later) |
| concrete_grade | enum | no | `M30` | M25 / M30 / M35 |
| steel_grade | enum | no | `Fe500` | Fe415 / Fe500 |
| clear_cover_mm | float | no | 50 | 40–75 |
| soil_unit_weight_kn_m3 | float | no | 18.0 | 15–22 |
| angle_of_friction_deg | float | no | 30.0 | 25–40 (drives earth-pressure coefficient) |
| formation_width_m | float | no | 6.85 | BG single-line formation; drives barrel length |
| side_slope_h_per_v | float | no | 2.0 | Embankment slope; drives barrel length |
| top_slab_thickness_mm | float | no | auto-sized | Override allowed; **overridden-thinner-than-sized → warning** (the deliberate under-design demo case) |
| bottom_slab_thickness_mm | float | no | auto-sized | as above |
| wall_thickness_mm | float | no | auto-sized | as above |
| haunch_mm | float | no | 150 | 0–300 |

Derived (engine output, not extracted): `BoxGeometry` — external dims, member thicknesses (sized or overridden), barrel length (from formation width + side slopes + fill), haunches. `Assumption` — `{field, value, source: "user" | "preset" | "engine_default", note}`.

---

## Artefact File Storage

```
data/
├── agent.db                          # SQLite (existing skeleton path)
├── uploads/                          # submitted-design inputs (Vetting Phase 1)
│   └── <run_id>/
│       └── <original filename(s)>    # the uploaded DXF/PDF/image — inputs, NOT served back
└── artifacts/
    └── <run_id>/
        ├── ga.dxf                    # genuine DXF (Phase 1; design mode only)
        ├── ga.svg                    # server-rendered from the same DXF (Phase 1)
        ├── calc_sheet.json           # clause-cited sheet + drill-down trail (Phase 2; also vet check-only)
        ├── compliance.json           # 12-item matrix rows (Phase 2; also vet check-only)
        ├── proof_memo.md             # severity-graded memo (Phase 2)
        ├── bmd.svg / sfd.svg         # FE cross-check diagrams (Phase 2; also vet)
        ├── model.glb                 # 3D view (Phase 3)
        ├── model.step                # CAD-openable download (Phase 3)
        ├── vetting_report.json       # per-check findings + verdict + provenance (Vetting Phase 1; vet mode)
        └── vetting_memo.md           # PCC-style vetting memo (Vetting Phase 1; vet mode)
```

Fixed filenames (whitelisted for serving — no user-controlled paths). `data/` is gitignored. `AGENT_ARTIFACTS_DIR` (default `data/artifacts`) configures the artefact root; `AGENT_UPLOADS_DIR` (default `data/uploads`) configures the upload root. Uploaded files keep their original names under `data/uploads/<run_id>/` and are read as pipeline INPUTS only — they are never exposed through the artefacts whitelist.

### Submitted reinforcement & claimed loading (Vetting Phase 1)

The as-submitted extraction (`ComponentModule.vetting_extraction_schema()`) is a component-specific Pydantic model (culvert: `src/components/culvert/vetting.py`). For the box culvert it carries: (a) **geometry** — the `BoxGeometry`-facing fields as GIVEN (clear span/height/cushion, member thicknesses, haunch, barrel length); (b) **provided reinforcement** — per member `{member, bar_dia_mm, spacing_mm, area_mm2_per_m}` (NEW data, not in the design-flow `CulvertParams`/`BoxGeometry`); (c) **claimed loading & materials** — the `CulvertParams` non-critical fields the submitter states (loading standard, concrete/steel grade, clear cover, soil γ, φ, formation width, side slope); and (d) **provenance** — each field's `source` (`drawing` \| `calc` \| `assumed_default`). Nothing here reshapes the existing tables: the extraction is snapshotted into `params_json` (the `CulvertParams` subset) and `vetting_json` (reinforcement + provenance + findings). No per-vetting table is added.

## Data Lifecycle

- **Create:** session on first prompt; run row at submission; artefact rows as files are written; steps_json written once at terminal `finish_run`. Mid-run reload recovery is delivered by the SSE replay buffer (`src/observability/progress.py` replays the full channel on reconnect); the snapshot endpoint serves completed state.
- **Update:** runs are append-only after completion (audit trail) — presets (Phase 3) are the only editable record.
- **Delete:** nothing is deleted in the POC. No archival, no time-boxing — the design library is the point.

## Sensitive Data

No PII beyond free-text prompts. The Gemini API key lives only in `.env` (gitignored) — never in the DB, logs, or artefacts. Nothing else is secret; the DB and artefacts are plain local files on the presenter's laptop.
