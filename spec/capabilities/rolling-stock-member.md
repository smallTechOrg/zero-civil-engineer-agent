# Capability: Rolling-Stock Structural Member

## What It Does
Designs a fabricated Indian-Railways freight-stock underframe member (a **sole bar**, **headstock**, or **underframe cross member**) from a natural-language request — length-driven section sizing, RDSO wagon-design load-case analysis (vertical payload with dynamic augment + longitudinal buffing/draft load), IS 800 working-stress section checks (bending, shear, axial and combined interaction), a dimensioned fabrication drawing with weld symbols + a 3D model, and the same IR-protocol proof-check — as the first **mechanical-domain**, **breadth-first** registered component under the shared-core framework.

> **Breadth-first scope:** this delivers the full journey (NL/picker → typed params → fabrication drawing + core RDSO/IS 800 checks + IR-protocol proof-check + 3D) at a working, honest depth. Full rolling-stock parity (every RDSO load combination, detailed fillet-weld sizing / length, welded-detail fatigue S-N categorisation, column-buckling slenderness reduction, connection & bolster design) is explicitly **later deepening work**, not this phase.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| Prompt / picker choice | free text / type_id | User | yes |
| Prior params / preset | RollingStockMemberParams / preset | Session, default preset | no |

## Fixed parameter model — `RollingStockMemberParams` (`src/components/rolling_stock_member/params.py`)

**Normative field list** (the code slice builds against exactly this — it is shared with the engine/drawing/3D). **Critical** fields must come from the user (never defaulted → the one clarifying question). `CRITICAL_FIELDS = ("member_length_m",)`. Any override left `None` is **auto-sized** by the engine.

| Field | Type | Critical | Default | Range / notes |
|-------|------|----------|---------|---------------|
| member_length_m | float | **yes** | — | `ge 0.5, le 15.0` (effective span between supports) |
| member_kind | Literal[`sole_bar`, `headstock`, `underframe_cross_member`] | no | `sole_bar` | underframe member type |
| design_vertical_load_kn | float | no | 120.0 | `ge 10, le 2000` (this member's share of payload + tare) |
| design_buffing_load_kn | float | no | 400.0 | `ge 0, le 3000` (member's share of the RDSO draft-gear buffing/draft load) |
| steel_grade | Literal[`E250`, `E350`] | no | `E250` | structural steel grade (IS 2062 / IS 800) |
| web_depth_mm | float \| None | no | None → auto | override; thinner/shallower than sized → warning (under-design demo case) |
| web_thickness_mm | float \| None | no | None → auto | as above |
| flange_width_mm | float \| None | no | None → auto | as above |
| flange_thickness_mm | float \| None | no | None → auto | as above |

## Fixed engine output — `RollingStockMemberGeometry`
`{member_length_mm, member_kind, web_depth_mm, web_thickness_mm, flange_width_mm, flange_thickness_mm, overall_depth_mm, weld_size_mm}` — the parametric inputs to the fabrication drawing + 3D. Plus `Assumption[]` (defaulted values + source) and `CalcStep[]` trail.

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| Geometry + assumptions + calc trail | RollingStockMemberGeometry + Assumption[] + CalcStep[] | State → drawing/3D/calc sheet/audit |
| Fabrication drawing | `ga.dxf` + `ga.svg` (elevation + cross-section, dimensions, **weld symbols on a WELD layer**, RDSO title block + drawing number) | Drawing tab; DXF download |
| 3D model | `model.glb` + `model.step` | 3D tab; STEP download |
| Calc sheet | `calc_sheet.json` (clause-cited, drill-down) | Calc Sheet tab |
| Strength summary | `{kind:"strength_summary", max_bending_stress_mpa, permissible_bending_stress_mpa, bending_ok, max_shear_stress_mpa, permissible_shear_stress_mpa, shear_ok, governing_load_case, verdict}` | Type-specific Strength panel |
| Proof-check | `compliance.json` + `proof_memo.md` + verdict | Proof-Check tab |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| LLM (see [agent.md](../agent.md#llm-provider--model)) | Parameter extraction (structured output); memo narration (grounded) | 1 retry then fatal; a memo narration failing grounding is discarded (warning) and the memo composes deterministically |

## Business Rules
- **Declared code set** (`ComponentModule.codes`): **RDSO Specifications** (the wagon-design vertical + longitudinal buffing/draft load cases and the vertical dynamic-augment factor) + **IS 800** (the working-stress permissible stresses and the section bending / shear / axial / combined-interaction checks for the fabricated steel member). A citation outside this set on a rolling-stock-member output is a defect; concrete (IS 456) and road-congress (IRC) codes are out-of-domain and forbidden.
- **Load cases (declared, honest basis):** (1) **Vertical payload** — the member's share of the payload + tare vertical load applied as a UDL over the span, augmented by the RDSO wagon-design dynamic-augment (impact) factor, plus the member self-weight → bending + shear. (2) **Longitudinal buffing** — the member's share of the RDSO draft-gear buffing (compressive) / draft (tensile) load applied as an axial force. The engine tracks a `governing_load_case` (the vertical payload case vs the longitudinal buffing case, by utilisation).
- **Sizing:** from `member_length_m`, `design_vertical_load_kn`, `design_buffing_load_kn` and `steel_grade`, the engine auto-sizes a welded I-section (web depth ~length/12, web thickness shear/slenderness-governed, flanges grown until bending, axial and the combined interaction are within a working target); any user override replaces the auto value and flows through the checks — an override thinner than sized surfaces as a FAIL row (the under-design demo case).
- **Checks (clause-cited):** (1) bending stress ≤ permissible; (2) web shear stress ≤ permissible; (3) axial (buffing) stress ≤ permissible; (4) combined axial+bending interaction ≤ 1.0; (5) welds & fatigue reported as an **OBSERVATION** only (detailed fillet-weld sizing and detail-category fatigue verification are later deepening work, honestly marked).
- Drawing/3D come ONLY from hand-validated parametric templates — never LLM-written CAD code. The fabrication drawing carries a **standard fillet-weld symbol** (leader arrow + reference line + fillet-weld triangle + leg-size text) on a dedicated `WELD` layer annotating the web-to-flange welds.
- **Transcription honesty:** every transcribed engineering value (permissible stresses, the RDSO vertical impact factor, the RDSO buffing-load magnitudes/distribution) carries `needs_verification=true`, is surfaced as such in the calc sheet + UI, and is validated against a reference worked example before demo day.
- Runs the SAME IR-protocol review spine as the civil components (independent cross-check → severity-graded memo → rule-computed verdict; no number in the memo absent from the deterministic results).

## Success Criteria
- [ ] "design a wagon underframe sole-bar member, 10 m, to RDSO specs" completes a full run < 60 s with the fabrication drawing (DXF+SVG), 3D (GLB+STEP), calc sheet, a strength-summary panel and a proof-check verdict.
- [ ] Missing critical param: "design a rolling-stock underframe member" → ONE question naming the **member length**; answering "2.4 m" completes the design.
- [ ] The strength-summary panel shows max bending / max shear vs permissible and the governing load case, each with a pass/fail indicator matching the deterministic results.
- [ ] Under-design: forcing `flange_thickness_mm` (or `web_thickness_mm`) below the sized value yields a FAIL row and a `return_for_revision` verdict naming the member; restoring it recovers the verdict.
- [ ] `ga.dxf` opens via `ezdxf.readfile` with the principal dimensions (member length, overall depth) read back and **weld-symbol entities present on the `WELD` layer**; the SVG renders styled in the browser; `model.glb` is a valid non-empty GLB.
- [ ] Every proof-check citation is within {RDSO Specifications, IS 800}; a genuinely out-of-domain concrete/road citation (IS 456 or IRC) on a rolling-stock-member output fails the code-set check.
- [ ] Transcribed values are flagged `needs_verification` in the calc sheet and UI until reference-validated.

## Validation Fixture
`tests/validation/test_rolling_stock_member_worked_example.py` — an underframe cross member (length 2.4 m; welded I web 300×10, flanges 150×12; E250; vertical load 300 kN, buffing 800 kN) whose section modulus, vertical design moment, extreme-fibre bending stress, axial buffing stress and combined interaction ratio are independently hand-derived (closed-form, in the fixture docstring) and matched within ±5%.
