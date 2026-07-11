# Capability: RCC Slab / T-beam Superstructure

## What It Does
Designs an IR RCC bridge superstructure — either a **solid slab** deck or a **T-beam** (rib + deck slab) deck — from a natural-language request: span-driven sizing, flexure/shear/min-steel/deflection code-checks against the IRS Concrete Bridge Code (with IS 456 for RCC section rules), a dimensioned GA drawing + 3D model, and the same IR-protocol proof-check — as a **breadth-first** registered component under the shared-core framework.

> **Breadth-first scope:** this delivers the full journey (NL/picker → typed params → GA drawing + core code-checks + IR-protocol proof-check + 3D) at a working, honest depth. Full culvert/retaining-wall-level parity (transverse deck distribution / Courbon or grillage analysis, crack-width SLS, reinforcement detailing, skew decks) is explicitly **later deepening work**, not this phase.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| Prompt / picker choice | free text / type_id | User | yes |
| Prior params / preset | SlabTBeamParams / preset | Session, default preset | no |

## Fixed parameter model — `SlabTBeamParams` (`src/components/slab_tbeam/params.py`)

**Normative field list** (the code slice builds against exactly this — it is shared with the engine/drawing/3D). **Critical** fields must come from the user (never defaulted → the one clarifying question). `CRITICAL_FIELDS = ("span_m",)`. Any override left `None` is **auto-sized** by the engine.

| Field | Type | Critical | Default | Range / notes |
|-------|------|----------|---------|---------------|
| span_m | float | **yes** | — | `ge 3, le 25` (effective span; solid slab economic below ~10 m, T-beam above) |
| deck_type | Literal[`solid_slab`, `t_beam`] | no | `solid_slab` | selects the section family |
| carriageway_width_m | float | no | 5.0 | 3–12 |
| loading_standard | enum | no | `25t` | 25t Loading-2008 (pluggable) |
| gauge | enum | no | `BG` | Broad Gauge |
| number_of_girders | int | no | 3 | 2–8 (**`t_beam` only**; ignored for `solid_slab`) |
| concrete_grade | enum | no | `M30` | M25 / M30 / M35 |
| steel_grade | enum | no | `Fe500` | Fe415 / Fe500 |
| clear_cover_mm | float | no | 40 | 30–75 |
| slab_depth_mm | float \| None | no | None → auto | override; thinner than sized → warning (under-design demo case) |
| rib_width_mm | float \| None | no | None → auto | as above (`t_beam`) |
| rib_depth_mm | float \| None | no | None → auto | as above (`t_beam`) |
| flange_thickness_mm | float \| None | no | None → auto | as above (`t_beam` compression flange = deck slab) |

## Fixed engine output — `SlabTBeamGeometry` (`src/components/slab_tbeam/analysis.py` output)
`{span_mm, deck_type, overall_depth_mm, slab_depth_mm, rib_width_mm, rib_depth_mm, flange_width_mm, number_of_girders, girder_spacing_mm, deck_width_mm}` — the parametric inputs to drawing + 3D. Plus `Assumption[]` (defaulted values + source) and `CalcStep[]` trail.

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| Geometry + assumptions + calc trail | SlabTBeamGeometry + Assumption[] + CalcStep[] | State → drawing/3D/calc sheet/audit |
| GA drawing | `ga.dxf` + `ga.svg` (cross-section + longitudinal, dimensions, RDSO title block) | Drawing tab; DXF download |
| 3D model | `model.glb` + `model.step` | 3D tab; STEP download |
| Calc sheet | `calc_sheet.json` (clause-cited, drill-down) | Calc Sheet tab |
| Flexure summary | `{kind:"flexure_summary", design_moment_knm, required_depth_mm, provided_depth_mm, flexure_ok, design_shear_kn, shear_stress_mpa, permissible_shear_mpa, shear_ok, steel_area_mm2, min_steel_mm2, verdict}` | Type-specific Flexure panel |
| Proof-check | `compliance.json` + `proof_memo.md` + verdict | Proof-Check tab |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| LLM (see [agent.md](../agent.md#llm-provider--model)) | Parameter extraction (structured output); memo narration (grounded) | 1 retry then fatal; a memo narration failing grounding is discarded (warning) and the memo composes deterministically |

## Business Rules
- **Declared code set** (`ComponentModule.codes`): **IRS Concrete Bridge Code** (permissible stresses, load effects, exposure) + **IS 456** (RCC flexure, shear, minimum steel, deflection span/depth) + **IR Bridge Rules** (railway loading — the 25t live load and its impact/CDA effects derive from these rules). A citation outside this set on a slab/T-beam output is a defect.
- **Sizing:** from `span_m`, `deck_type`, `carriageway_width_m` and `number_of_girders` (T-beam), the engine auto-sizes `slab_depth_mm` (solid slab ~span/15–span/20; T-beam deck slab from panel span) and, for `t_beam`, `rib_depth_mm` (~span/10–span/15), `rib_width_mm`, `flange_thickness_mm` and `girder_spacing_mm` from the carriageway width. Any override replaces the auto value and flows through the checks — an override thinner than sized surfaces as a FAIL row (the under-design demo case).
- **Analysis:** design bending moment and shear from the moving load (EUDL for the loaded length under 25t-2008, with CDA/impact) plus dead load, per longitudinal member (slab strip for `solid_slab`, one rib for `t_beam`).
- **Checks (clause-cited):** (1) **flexure** — required effective depth vs provided, and required tensile-steel area vs provided (working-stress / limit-state per IS 456 with IRS CBC permissibles); (2) **shear** — nominal shear stress `τ_v` vs permissible `τ_c` (IS 456 Table 19/23); (3) **minimum steel** per **IS 456 cl. 26.5** (and max spacing); (4) **deflection** by the span/depth ratio check (IS 456 cl. 23.2); (5) **cover** vs the exposure requirement.
- Drawing/3D come ONLY from hand-validated parametric templates — never LLM-written CAD code.
- **Transcription honesty:** every transcribed engineering value (permissible stresses, EUDL/CDA entries, `τ_c` table values) carries `needs_verification=true`, is surfaced as such in the calc sheet + UI, and is validated against a reference worked example before demo day.
- Runs the SAME IR-protocol review spine as the culvert/retaining wall (independent cross-check → severity-graded memo → rule-computed verdict; no number in the memo absent from the deterministic results).

## Success Criteria
- [ ] "design a 12 m RCC T-beam bridge deck, 7.5 m carriageway, BG, 25t loading, M30/Fe500" completes a full run < 60 s with GA (DXF+SVG), 3D (GLB+STEP), calc sheet, a flexure-summary panel and a proof-check verdict.
- [ ] "design an 8 m solid RCC slab bridge" auto-sizes a solid-slab section (no rib fields) and completes end-to-end.
- [ ] Missing critical param: "design an RCC slab bridge, 6 m carriageway" → ONE question naming the **span**; answering "8 m" completes the design.
- [ ] The flexure-summary panel shows design moment, required vs provided depth, shear stress vs permissible, and steel area vs min steel, each with a pass/fail indicator matching the deterministic results.
- [ ] Under-design: forcing `slab_depth_mm` (or `rib_depth_mm`) below the sized value yields a FAIL row and a `return_for_revision` verdict naming the member; restoring it recovers the verdict.
- [ ] `ga.dxf` opens via `ezdxf.readfile` with the principal dimensions (span, overall depth, deck width) read back; the SVG renders styled; `model.glb` is a valid non-empty GLB.
- [ ] Every proof-check citation is within {IRS Concrete Bridge Code, IS 456, IR Bridge Rules}; a genuinely out-of-domain steel/road citation (IS 800 or IRC) on a slab/T-beam output fails the code-set check.
- [ ] Transcribed values are flagged `needs_verification` in the calc sheet and UI until reference-validated.
