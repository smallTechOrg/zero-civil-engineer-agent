# Capability: RCC Cantilever Retaining Wall

## What It Does
Designs an IR RCC cantilever retaining wall from a natural-language request — earth-pressure + stability analysis, RCC section design of stem/heel/toe, a dimensioned GA drawing + 3D model, and the same IR-protocol proof-check — as the second registered component under the shared-core framework.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| Prompt / picker choice | free text / type_id | User | yes |
| Prior params / preset | RetainingWallParams / preset | Session, default preset | no |

## Fixed parameter model — `RetainingWallParams` (`src/components/retaining_wall/params.py`)

**Normative field list** (slices b/c/d build against exactly this). **Critical** fields must come from the user (never defaulted → the one clarifying question, order: `retained_height_m` → `safe_bearing_capacity_kn_m2` → `backfill_friction_angle_deg`).

| Field | Type | Critical | Default (preset) | Range / unusual-flag |
|-------|------|----------|------------------|----------------------|
| retained_height_m | float | **yes** | — | 1.5–8.0 hard; > 6.0 → warning |
| safe_bearing_capacity_kn_m2 | float | **yes** | — | 50–600 hard; < 100 → warning |
| backfill_friction_angle_deg | float | **yes** | — | 25–40 hard |
| backfill_unit_weight_kn_m3 | float | no | 18.0 | 15–22 |
| backfill_slope_deg | float | no | 0.0 | 0–20 (surcharge slope β; drives Coulomb Ka) |
| track_surcharge | bool | no | true | BG single-line track surcharge per IR Bridge Rules (equivalent height of fill) |
| surcharge_kn_m2 | float | no | 0.0 | 0–50 (additional uniform surcharge) |
| base_friction_coeff | float | no | 0.5 | 0.4–0.6 (concrete-on-soil μ) |
| concrete_grade | enum | no | M30 | M25 / M30 / M35 |
| steel_grade | enum | no | Fe500 | Fe415 / Fe500 |
| clear_cover_mm | float | no | 50 | 40–75 |
| stem_top_thickness_mm | float | no | auto-sized | override thinner-than-sized → warning (under-design demo case) |
| stem_base_thickness_mm | float | no | auto-sized | as above |
| base_thickness_mm | float | no | auto-sized | as above |
| toe_length_mm | float | no | auto-sized | override allowed |
| heel_length_mm | float | no | auto-sized | override allowed |

## Fixed engine output — `RetainingWallGeometry` (`src/components/retaining_wall/analysis.py` output)
`{stem_top_thickness_mm, stem_base_thickness_mm, base_thickness_mm, toe_length_mm, heel_length_mm, base_width_mm, total_height_mm, key_depth_mm?}` — the parametric inputs to drawing + 3D. Plus `Assumption[]` (defaulted values + source) and `CalcStep[]` trail.

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| Geometry + assumptions + calc trail | RetainingWallGeometry + Assumption[] + CalcStep[] | State → drawing/3D/calc sheet/audit |
| GA drawing | `ga.dxf` + `ga.svg` (section + plan, dimensions, RDSO title block) | Drawing tab; DXF download |
| 3D model | `model.glb` + `model.step` | 3D tab; STEP download |
| Calc sheet | `calc_sheet.json` (clause-cited, drill-down) | Calc Sheet tab |
| Stability summary | `{fos_overturning, fos_sliding, max_bearing_pressure_kn_m2, sbc_kn_m2, bearing_ok}` | Type-specific Stability panel |
| Proof-check | `compliance.json` + `proof_memo.md` + verdict | Proof-Check tab |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| LLM | Parameter extraction (structured output); memo narration (`rw_memo.md`, grounded) | 1 retry then fatal; a memo narration failing grounding is discarded and the memo composes deterministically |

## Business Rules
- **Earth pressure:** active (and passive at the toe/key where mobilised) by Rankine when `backfill_slope_deg == 0`, Coulomb for a sloped backfill; include IR **track surcharge** as an equivalent height of fill per Bridge Rules plus any uniform `surcharge_kn_m2`.
- **Stability checks:** factor of safety against **overturning** (≥ 2.0), **sliding** (≥ 1.5, including base friction and any passive resistance/shear key), and **bearing** — max toe pressure ≤ SBC and heel pressure ≥ 0 (no tension). These drive the type-specific stability summary.
- **RCC section design** (stem, heel, toe as cantilevers) per IS 456 working-stress + IRS Concrete Bridge Code: flexure, shear, minimum steel, cover — clause-cited. A user thickness override thinner than sized flows through as a FAIL row graded by the proof-check (the under-design demo case).
- **Codes declared** by the module: IRS Concrete Bridge Code, IS 456, IR Bridge Rules (track surcharge), IRS Bridge Substructure & Foundation Code (Rankine/Coulomb earth-pressure & stability basis, as the pier/abutment declares for the same basis). A citation outside this set on a retaining-wall output is a defect.
- Drawing/3D come ONLY from hand-validated parametric templates — never LLM-written CAD code.
- **Validation:** the engine matches a published worked example within ±5% (fixture in `tests/validation/test_rw_worked_example.py`).
- Runs the SAME IR-protocol review spine as the culvert (independent cross-check → severity-graded memo → rule-computed verdict; no number in the memo absent from the deterministic results).

## Success Criteria
- [ ] "design a 5 m high RCC cantilever retaining wall, SBC 200 kN/m², BG single-line track surcharge, backfill φ 30°" completes a full run < 60 s with GA (DXF+SVG), 3D (GLB+STEP), calc sheet, stability summary and a proof-check verdict.
- [ ] Engine matches the published worked example within ±5% on FoS overturning, FoS sliding, max bearing pressure, and stem steel area (validation fixture).
- [ ] `ga.dxf` opens via `ezdxf.readfile` with correct principal dimensions (retained height, base width) read back; the SVG renders styled in the browser.
- [ ] `model.glb` is a valid non-empty GLB; `model.step` opens in FreeCAD.
- [ ] Missing critical param: "design a retaining wall, SBC 200" → ONE question naming the retained height; answering "5 m" completes the design.
- [ ] Under-design: forcing a stem base thinner than sized yields a FAIL row and a `return_for_revision` verdict naming the stem; increasing it recovers the verdict.
- [ ] Stability summary shows FoS overturning, FoS sliding, and max bearing vs SBC with a pass/fail indicator matching the deterministic results.
