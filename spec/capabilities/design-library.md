# Capability: Design Library

## What It Does
Stores every design run permanently as a browsable audit trail — timestamp, prompt, parameters, assumptions, artefacts, check results, and review verdict — and manages the standards/defaults presets. *(Phase 3 for the browsing UI + preset editing; the underlying records are written from Phase 1.)*

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| Completed/failed runs | DesignRun + Artifact records | Every agent run ([data.md](../data.md#entity-designrun)) | yes |
| Preset edits | name + values | User (Library tab, Phase 3) | no |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| Library listing | run summaries (timestamp, prompt, params summary, verdict, cost, duration) | Library tab |
| Run detail reload | full snapshot | Step tracker + artefact tabs (read-only replay) |
| Presets | named default sets | Intake merging; Library tab editor |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Database (see [architecture.md](../architecture.md#stack)) | list/read runs; read/update presets | API error surfaced; agent runs unaffected |

## Business Rules
- Every run is stored regardless of outcome (`completed`, `needs_input`, `out_of_scope`, `failed`) — failures are part of the audit trail.
- Runs are immutable after completion; editing a preset never rewrites past runs (each run snapshots the values it used).
- Exactly one preset is the default; preset values cover only non-critical parameters (critical ones must always come from the user).
- Opening a library run replays its stored snapshot (steps, params, artefacts, verdict) without re-running anything.
- Session cost totals shown in the library are derived sums, computed at read time.

## Success Criteria
- [ ] After a mixed session (completed + needs_input + out_of_scope runs), the library lists all of them with correct status/verdict chips, newest first.
- [ ] Clicking a past run loads its drawing, calc sheet, and proof-check exactly as originally generated (artefact files still served).
- [ ] Hard case — preset immutability: edit the default cover 50 → 40 mm, then reopen a pre-edit run: its assumptions still show 50 mm; a new run picks up 40 mm.
- [ ] Preset validation: attempting to set a preset value outside the CulvertParams range is rejected with the range named (422).
- [ ] Filtering by session returns only that session's runs; pagination works past 50 runs.
- [ ] E2E: the Library tab renders the populated table for a real run history and the empty state before any runs.
