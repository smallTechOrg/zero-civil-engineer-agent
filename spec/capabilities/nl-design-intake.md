# Capability: NL Design Intake

## What It Does
Turns a natural-language design request into validated, typed culvert parameters — gating scope, asking at most one pointed clarifying question when a critical parameter is missing, and flagging unusual values before any engineering runs.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| Prompt | free text | User (prompt box) | yes |
| Session turn history | messages list | Session's prior runs ([data.md](../data.md#entity-designrun)) | yes (may be empty) |
| Prior accepted params | CulvertParams | Session's last completed run | no |
| Preset defaults | preset values | Default or selected preset | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| Validated parameters | CulvertParams ([data.md](../data.md#culvertparams--the-typed-parameter-model)) | Agent state → engine, drawing, 3D, audit record |
| Design plan narration | text | Status line (streamed) + run record |
| Clarifying question (when needed) | text + missing field | UI clarification card; run ends `needs_input` |
| Unusual-value warnings | list | Amber banners + calc-sheet assumptions block |
| Scope statement (when rejected) | text | Turn history; run ends `out_of_scope` |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| LLM (see [agent.md](../agent.md#llm-provider--model)) | Scope gate + plan; structured parameter extraction | 1 retry, then fatal (transparent error) |

## Business Rules
- Critical parameters (clear span, clear height, cushion) are **never guessed and never defaulted** — if missing after merging history, ask exactly ONE pointed question (highest priority first: span → height → cushion) and stop.
- Merge order: this turn's values override prior accepted params, which override preset defaults; every non-user value is recorded as an explicit Assumption.
- Unusual values are flagged and the run proceeds: cushion > 8.0 m, span > 6.0 m, any thickness override thinner than the engine would size. Hard-invalid values (outside the ranges in data.md) are rejected with the specific range named.
- Out-of-scope requests get a graceful one-paragraph statement of what the demonstrator covers — never an error tone, never an attempt.
- Validity is decided by deterministic schema validation, not by the LLM.

## Success Criteria
- [ ] The canonical prompt ("single box culvert, 4 m clear span, 3 m height, 2.5 m cushion, BG single line, 25t loading") extracts exactly `clear_span_m=4.0, clear_height_m=3.0, cushion_m=2.5, gauge=BG, tracks=1, loading_standard=25t-2008` (real-LLM integration test).
- [ ] Hard case — missing critical param: "design a box culvert for 3 m height and 2 m cushion" ends `needs_input` with ONE question that names the clear span; no artefacts are generated; answering "4.5 m" in the next turn completes the design with span 4.5.
- [ ] Hard case — abnormal fill: a 9 m cushion produces a warning event and an assumptions/warnings record, and the run still completes.
- [ ] Hard case — out of scope: "design a suspension bridge" returns the graceful scope statement, status `out_of_scope`, zero engine/drawing calls.
- [ ] Units and phrasing variants parse: "4000 mm span", "four metre span", and "4 m clear span" all yield 4.0.
- [ ] The design plan streams to the status line before extraction completes (narration events observed in order).
