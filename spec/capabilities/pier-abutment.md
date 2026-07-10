# Capability: Bridge Pier & Abutment Substructure

## What It Does
Designs an IR bridge **substructure** — either a **pier** or an **abutment** — from a natural-language request: sizing of the pier/abutment stem, cap and spread footing, a load/stability analysis (self-weight, superstructure reaction, and, for an abutment, active earth pressure from the backfill), overturning/sliding/bearing stability + concrete-stress code-checks against the IRS Bridge Substructure & Foundation Code (with IRS Bridge Rules for loads), a dimensioned GA drawing + 3D model, and the same IR-protocol proof-check — as a **breadth-first** registered component under the shared-core framework.

> **Breadth-first scope:** this delivers the full journey (NL/picker → typed params → GA drawing + core code-checks + IR-protocol proof-check + 3D) at a working, honest depth. Full culvert/retaining-wall-level parity (seismic/wind/braking longitudinal cases, pile foundations, well foundations, RCC reinforcement design of stem/cap/footing) is explicitly **later deepening work**, not this phase.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| Prompt / picker choice | free text / type_id | User | yes |
| Prior params / preset | PierAbutmentParams / preset | Session, default preset | no |

## Fixed parameter model — `PierAbutmentParams` (`src/components/pier_abutment/params.py`)

**Normative field list** (the code slice builds against exactly this — it is shared with the engine/drawing/3D). **Critical** fields must come from the user (never defaulted → the one clarifying question, order: `pier_height_m` → `superstructure_reaction_kn` → `safe_bearing_capacity_kn_m2`). `CRITICAL_FIELDS = ("pier_height_m", "superstructure_reaction_kn", "safe_bearing_capacity_kn_m2")`. Any override left `None` is **auto-sized** by the engine.

| Field | Type | Critical | Default | Range / notes |
|-------|------|----------|---------|---------------|
| pier_height_m | float | **yes** | — | `ge 2, le 30` (stem height, bed/foundation level to bearing level) |
| superstructure_reaction_kn | float | **yes** | — | `ge 100, le 20000` (vertical reaction per support from the deck) |
| safe_bearing_capacity_kn_m2 | float | **yes** | — | `ge 50, le 1000` (founding-stratum SBC) |
| component_kind | Literal[`pier`, `abutment`] | no | `pier` | pier (both faces free) vs abutment (retains backfill on one face) |
| span_m | float | no | 20 | 3–60 (contributing span, sizes the cap and dead-load share) |
| backfill_friction_angle_deg | float | no | 30 | 25–40 (**`abutment` only** — drives active earth pressure) |
| backfill_unit_weight_kn_m3 | float | no | 18 | backfill unit weight (abutment) |
| base_friction_coeff | float | no | 0.5 | 0.4–0.6 (concrete-on-soil μ, sliding resistance) |
| concrete_grade | enum | no | `M30` | M25 / M30 / M35 |
| steel_grade | enum | no | `Fe500` | Fe415 / Fe500 |
| clear_cover_mm | float | no | 50 | substructure exposure cover |
| pier_width_mm | float \| None | no | None → auto | override; thinner than sized → warning (under-design demo case) |
| pier_length_mm | float \| None | no | None → auto | as above |
| cap_thickness_mm | float \| None | no | None → auto | as above |
| footing_length_mm | float \| None | no | None → auto | as above (governs overturning/bearing) |
| footing_width_mm | float \| None | no | None → auto | as above |
| footing_thickness_mm | float \| None | no | None → auto | as above |

## Fixed engine output — `PierAbutmentGeometry` (`src/components/pier_abutment/analysis.py` output)
`{total_height_mm, component_kind, pier_width_mm, pier_length_mm, cap_thickness_mm, cap_width_mm, cap_length_mm, footing_length_mm, footing_width_mm, footing_thickness_mm}` — the parametric inputs to drawing + 3D. Plus `Assumption[]` (defaulted values + source) and `CalcStep[]` trail.

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| Geometry + assumptions + calc trail | PierAbutmentGeometry + Assumption[] + CalcStep[] | State → drawing/3D/calc sheet/audit |
| GA drawing | `ga.dxf` + `ga.svg` (elevation + plan, dimensions, RDSO title block) | Drawing tab; DXF download |
| 3D model | `model.glb` + `model.step` | 3D tab; STEP download |
| Calc sheet | `calc_sheet.json` (clause-cited, drill-down) | Calc Sheet tab |
| Stability summary | `{kind:"stability", fos_overturning, fos_sliding, max_bearing_pressure_kn_m2, sbc_kn_m2, bearing_ok, verdict}` | Type-specific Stability panel (**reuses the existing retaining-wall stability panel**) |
| Proof-check | `compliance.json` + `proof_memo.md` + verdict | Proof-Check tab |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| LLM (see [agent.md](../agent.md#llm-provider--model)) | Parameter extraction (structured output); memo narration (grounded) | 1 retry then fatal; a memo narration failing grounding is discarded (warning) and the memo composes deterministically |

## Business Rules
- **Declared code set** (`ComponentModule.codes`): **IRS Bridge Substructure & Foundation Code** (stability factors, base-pressure limits, permissible concrete stresses) + **IRS Bridge Rules** (loads — dead, superstructure reaction, earth pressure) + **IRS Concrete Bridge Code** and **IS 456** (RCC section design of the stem/cap/footing — direct compressive stress and cover, exactly as the retaining wall declares). A citation outside this set on a pier/abutment output is a defect.
- **Sizing:** from `pier_height_m`, `superstructure_reaction_kn`, `span_m` and `component_kind`, the engine auto-sizes the stem section (`pier_width_mm`, `pier_length_mm`), cap (`cap_thickness_mm`, `cap_width_mm`, `cap_length_mm`) and spread footing (`footing_length_mm`, `footing_width_mm`, `footing_thickness_mm`), the footing plan being enlarged until the bearing and stability checks are satisfied against the supplied `safe_bearing_capacity_kn_m2`. Any override replaces the auto value and flows through the checks — an override smaller than sized surfaces as a FAIL row (the under-design demo case).
- **Analysis:** resolves vertical load (self-weight of stem/cap/footing + `superstructure_reaction_kn`) and, for an **abutment**, Rankine active earth pressure from `backfill_friction_angle_deg` / `backfill_unit_weight_kn_m3` acting on the stem; computes the resultant, its eccentricity at the footing base, and the base-pressure distribution.
- **Checks (clause-cited):** (1) **FoS overturning ≥ 2.0**; (2) **FoS sliding ≥ 1.5** (base friction via `base_friction_coeff`); (3) **max base pressure ≤ SBC**; (4) **min base pressure ≥ 0** (no tension / no uplift at the heel); (5) **pier concrete compressive stress ≤ permissible** (axial + bending at the stem base).
- Drawing/3D come ONLY from hand-validated parametric templates — never LLM-written CAD code.
- **Transcription honesty:** every transcribed engineering value (stability-factor limits, permissible concrete stresses, load factors) carries `needs_verification=true`, is surfaced as such in the calc sheet + UI, and is validated against a reference worked example before demo day.
- Runs the SAME IR-protocol review spine as the culvert/retaining wall (independent cross-check → severity-graded memo → rule-computed verdict; no number in the memo absent from the deterministic results).

## Success Criteria
- [ ] "design a 10 m high bridge pier, superstructure reaction 3000 kN, SBC 300 kN/m², 20 m span" completes a full run < 60 s with GA (DXF+SVG), 3D (GLB+STEP), calc sheet, a stability-summary panel and a proof-check verdict.
- [ ] "design an abutment, 8 m high, reaction 2500 kN, SBC 250, backfill φ 32°" runs the abutment path (earth pressure included) and completes end-to-end.
- [ ] Missing critical params: "design a bridge pier, SBC 300" → questions asked in order (`pier_height_m` first, then `superstructure_reaction_kn`); answering them completes the design.
- [ ] The stability-summary panel shows FoS overturning, FoS sliding, and max base pressure vs SBC, each with a pass/fail indicator matching the deterministic results.
- [ ] Under-design: forcing `footing_length_mm` below the sized value yields a FAIL row (overturning/bearing) and a `return_for_revision` verdict naming the footing; restoring it recovers the verdict.
- [ ] `ga.dxf` opens via `ezdxf.readfile` with the principal dimensions (total height, footing plan) read back; the SVG renders styled; `model.glb` is a valid non-empty GLB.
- [ ] Every proof-check citation is within {IRS Bridge Substructure & Foundation Code, IRS Bridge Rules, IRS Concrete Bridge Code, IS 456}; a genuinely out-of-domain road/steel citation (IRC or IS 800) on a pier/abutment output fails the code-set check.
- [ ] Transcribed values are flagged `needs_verification` in the calc sheet and UI until reference-validated.
