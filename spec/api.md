# API

---

## API Style

REST + one SSE stream, served by FastAPI on `http://localhost:8001`. Every JSON route returns the skeleton envelope: `ok(data)` → `{"data": ..., "error": null}`; failures raise `api_error(code, message, status)` → `{"detail": {"code", "message"}}`. New routes live under `/api/*`; the skeleton's `/health` stays; the skeleton's `/runs` transform endpoints are **replaced** by the design endpoints below. The built frontend is mounted at `/app`.

> **Assumed:** `/api` prefix for all new routes (keeps them disjoint from the `/app` static mount and `/health`).

Routers: `src/api/sessions.py`, `src/api/designs.py` (submit + snapshot + SSE + artifacts), `src/api/presets.py` (Phase 3).

---

## Endpoints

### `POST /api/sessions`

**Purpose:** create a design session. **Request:** `{"title": "optional string"}` (title auto-derived from first prompt if omitted).
**Response `data`:** `{"session_id", "title", "created_at"}`

### `GET /api/sessions`

**Purpose:** list sessions, newest first, with derived cost totals.
**Response `data`:** `{"sessions": [{"session_id", "title", "created_at", "run_count", "total_prompt_tokens", "total_completion_tokens", "total_cost_usd"}]}`

### `POST /api/sessions/{session_id}/designs`

**Purpose:** submit a natural-language design request (new design, refinement turn, or clarification answer — the agent distinguishes them). Returns immediately; the run executes in the background.

**Request:**
```json
{
  "prompt": "single box culvert, 4 m clear span, 3 m height, 2.5 m cushion, BG single line, 25t loading",
  "preset_id": "optional — default preset used when omitted"
}
```

**Response `data`:**
```json
{
  "run_id": "uuid",
  "status": "running",
  "events_url": "/api/designs/{run_id}/events",
  "snapshot_url": "/api/designs/{run_id}"
}
```

**Error cases:**
| Status | Code | Condition |
|--------|------|-----------|
| 404 | NOT_FOUND | Unknown session |
| 409 | RUN_ACTIVE | A run in this session is still `running` |
| 422 | EMPTY_PROMPT | Blank/whitespace prompt |

### `GET /api/designs/{run_id}/events` — SSE event stream

**Purpose:** live progress for the step tracker, narration line, streaming artefacts, and token/cost display. `Content-Type: text/event-stream`; each message is `event: <type>` + `data: <json>`. On connect, a `snapshot` event replays current state (safe reconnect); the stream closes after `done` or `error`.

| event | data payload |
|-------|-------------|
| `snapshot` | The full run snapshot (same shape as `GET /api/designs/{run_id}`) |
| `step` | `{"step": "Understand"\|"Extract"\|"Analyse"\|"Check"\|"Draw"\|"Review", "status": "active"\|"done"\|"skipped"\|"failed", "detail": "e.g. 'Coming in Phase 2'", "elapsed_ms": int}` |
| `narration` | `{"text": "plain-language status / plan fragment"}` |
| `warning` | `{"message": "Cushion of 9.0 m is abnormally high — proceeding, flagged in the calc sheet"}` |
| `clarification` | `{"question": "...", "missing_param": "clear_span_m"}` |
| `artefact` | `{"kind": "ga_svg", "filename": "ga.svg", "url": "/api/designs/{run_id}/artifacts/ga.svg"}` |
| `tokens` | `{"prompt_tokens", "completion_tokens", "cost_usd", "session_total_cost_usd"}` — emitted after every LLM call (running totals) and once more at finalize |
| `done` | `{"status": "completed"\|"needs_input"\|"out_of_scope", "verdict": "recommended_for_approval"\|"return_for_revision"\|null}` |
| `error` | `{"code": "RUN_FAILED", "message": "what was tried and why it failed"}` |

**Error cases:** 404 unknown run. Reconnecting to a finished run yields `snapshot` + `done` (completed / needs_input / out_of_scope) or `snapshot` + `error` (failed runs) and closes.

### `GET /api/designs/{run_id}`

**Purpose:** full run snapshot — reload recovery, SSE fallback, and the library's detail view.

**Response `data`:**
```json
{
  "run_id": "...", "session_id": "...", "prompt": "...",
  "status": "completed",
  "plan_text": "...", "scope_message": null, "clarification_question": null,
  "params": { "clear_span_m": 4.0, "...": "CulvertParams fields" },
  "assumptions": [{"field": "concrete_grade", "value": "M30", "source": "preset", "note": "..."}],
  "warnings": ["..."],
  "steps": [{"name": "Understand", "status": "done", "started_at": "...", "ended_at": "..."}],
  "checks": [{"clause": "...", "requirement": "...", "computed": "...", "limit": "...", "status": "PASS"}],
  "checklist": [{"item": 1, "title": "Loading standard & ACS level", "clause": "...", "requirement": "...", "computed": "...", "limit": "...", "severity": "PASS", "detail": "..."}],
  "verdict": "recommended_for_approval",
  "suggestions": ["Increase cushion to 4 m", "..."],
  "artefacts": [{"kind": "ga_dxf", "filename": "ga.dxf", "url": ".../artifacts/ga.dxf", "size_bytes": 12345}],
  "tokens": {"prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0},
  "error_message": null,
  "started_at": "...", "completed_at": "...", "duration_ms": 41500
}
```

Phase-gated fields (`checks`, `checklist`, `verdict`, `suggestions`) are `null`/empty until their phase lands.

### `GET /api/designs/{run_id}/artifacts/{filename}`

**Purpose:** fetch/download an artefact file. Filename must be one of the fixed set in [data.md](data.md#artefact-file-storage) (whitelist — no path traversal). Served with the artefact's MIME type; `ga.dxf`, `model.step`, `model.glb` get `Content-Disposition: attachment`; `ga.svg`, `bmd.svg`, `sfd.svg`, JSON and markdown are served inline.

**Error cases:** 404 unknown run / artefact not (yet) generated; 400 filename not in whitelist.

### `GET /api/designs`

**Purpose:** the design library — every run ever, newest first. Available from **Phase 1** (it powers turn-history rehydration on reload); the Library *tab* UI lands in Phase 3.
**Query:** `session_id` (optional filter), `limit` (default 50), `offset`.
**Response `data`:** `{"runs": [{"run_id", "session_id", "prompt", "status", "verdict", "params_summary": "4.0 × 3.0 m, cushion 2.5 m, 25t-2008", "cost_usd", "started_at", "duration_ms"}], "total": int}`

### `GET /api/presets` *(Phase 3 for editing; GET available from Phase 1 so the UI can show the applied defaults)*

**Response `data`:** `{"presets": [{"preset_id", "name", "is_default", "values": {…}}]}`

### `PUT /api/presets/{preset_id}` *(Phase 3)*

**Request:** `{"name": "...", "values": {…}}` — values validated against the `CulvertParams` non-critical fields. **Response `data`:** the updated preset. **Errors:** 404; 422 invalid field/range.

### `GET /health` *(existing skeleton)*

Liveness check — unchanged.

---

## Authentication

None — localhost-only, single presenter, demo scope. The server binds for local use and is never exposed; adding auth is explicitly out of scope (see [roadmap.md](roadmap.md#what-this-agent-does-not-do-out-of-scope)).
