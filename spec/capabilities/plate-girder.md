# Capability: Steel Plate Girder Superstructure

## What It Does
Designs an IR welded steel plate-girder bridge superstructure from a natural-language request — span-driven girder sizing, bending/shear/deflection code-checks against the IRS Steel Bridge Code (with IS 800 for section/stiffener rules), a dimensioned GA drawing + 3D model, and the same IR-protocol proof-check — as a **breadth-first** registered component under the shared-core framework.

> **Breadth-first scope:** this delivers the full journey (NL/picker → typed params → GA drawing + core code-checks + IR-protocol proof-check + 3D) at a working, honest depth. Full culvert/retaining-wall-level parity (every load case, fatigue-detail categorisation, connection & splice design, curved/skew girders) is explicitly **later deepening work**, not this phase.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| Prompt / picker choice | free text / type_id | User | yes |
| Prior params / preset | PlateGirderParams / preset | Session, default preset | no |

## Fixed parameter model — `PlateGirderParams` (`src/components/plate_girder/params.py`)

**Normative field list** (the code slice builds against exactly this — it is shared with the engine/drawing/3D). **Critical** fields must come from the user (never defaulted → the clarifying question, in priority order). `CRITICAL_FIELDS = ("span_m", "steel_grade")`. Any override left `None` is **auto-sized** by the engine.

| Field | Type | Critical | Default | Range / notes |
|-------|------|----------|---------|---------------|
| span_m | float | **yes** | — | `ge 6, le 60` (effective span, plate-girder economic range) |
| loading_standard | enum | no | `25t-2008` | pluggable loading layer; 25t Loading-2008 built |
| gauge | enum | no | `BG` | Broad Gauge |
| deck_type | Literal[`deck`, `through`] | no | `deck` | deck-type (girders below deck) vs through-type (girders beside deck) |
| number_of_girders | int | no | 2 | 2–6 |
| steel_grade | Literal[`E250`, `E350`] | **yes** | — | structural steel grade (IS 2062 / IS 800) |
| web_depth_mm | float \| None | no | None → auto | override; thinner/shallower than sized → warning (under-design demo case) |
| web_thickness_mm | float \| None | no | None → auto | as above |
| flange_width_mm | float \| None | no | None → auto | as above |
| flange_thickness_mm | float \| None | no | None → auto | as above |

## Fixed engine output — `PlateGirderGeometry` (`src/components/plate_girder/analysis.py` output)
`{span_mm, web_depth_mm, web_thickness_mm, flange_width_mm, flange_thickness_mm, overall_depth_mm, number_of_girders, girder_spacing_mm, stiffener_spacing_mm}` — the parametric inputs to drawing + 3D. Plus `Assumption[]` (defaulted values + source) and `CalcStep[]` trail.

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| Geometry + assumptions + calc trail | PlateGirderGeometry + Assumption[] + CalcStep[] | State → drawing/3D/calc sheet/audit |
| GA drawing | `ga.dxf` + `ga.svg` (elevation + cross-section, dimensions, RDSO title block) | Drawing tab; DXF download |
| 3D model | `model.glb` + `model.step` | 3D tab; STEP download |
| Calc sheet | `calc_sheet.json` (clause-cited, drill-down) | Calc Sheet tab |
| Stress summary | `{kind:"stress_summary", max_bending_stress_mpa, permissible_bending_stress_mpa, bending_ok, max_shear_stress_mpa, permissible_shear_stress_mpa, shear_ok, max_deflection_mm, deflection_limit_mm, deflection_ok, verdict}` | Type-specific Stress panel |
| Proof-check | `compliance.json` + `proof_memo.md` + verdict | Proof-Check tab |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| LLM (see [agent.md](../agent.md#llm-provider--model)) | Parameter extraction (structured output); memo narration (grounded) | 1 retry then fatal; a memo narration failing grounding is discarded (warning) and the memo composes deterministically |

## Business Rules
- **Declared code set** (`ComponentModule.codes`): **IRS Steel Bridge Code** (permissible stresses, deflection limit, moving-load effects) + **IS 800** (plate-girder proportioning, web slenderness, stiffener spacing) + **IR Bridge Rules** (railway loading — the 25t live load and its impact/CDA effects derive from these rules). A citation outside this set on a plate-girder output is a defect.
- **Sizing:** from `span_m`, `loading_standard`, `deck_type`, `number_of_girders` and `steel_grade`, the engine auto-sizes web depth (~span/10–span/12 railway deck-girder band), web thickness (slenderness-governed), and flange plates to the required section modulus; any user override (`web_depth_mm`, `web_thickness_mm`, `flange_width_mm`, `flange_thickness_mm`) replaces the auto value and flows through the checks — an override thinner than sized surfaces as a FAIL row (the under-design demo case).
- **Analysis:** maximum design bending moment and shear from the moving load (EUDL for the loaded length under the 25t-2008 standard, with CDA/impact) plus dead load, distributed to the girders; section properties (I, Z) computed from the plate geometry.
- **Checks (clause-cited):** (1) max bending stress ≤ permissible bending stress; (2) max web shear stress ≤ permissible shear stress; (3) deflection ≤ **span/600** (IRS Steel Bridge Code moving-load deflection limit); (4) web slenderness / intermediate-stiffener spacing **note** per IS 800 (governs whether stiffeners are required and their pitch → `stiffener_spacing_mm`); (5) fatigue is reported as an **OBSERVATION** only (detail-category fatigue verification is later deepening work, honestly marked).
- Drawing/3D come ONLY from hand-validated parametric templates — never LLM-written CAD code.
- **Transcription honesty:** every transcribed engineering value (permissible stresses, EUDL/CDA table entries, deflection limit) carries `needs_verification=true`, is surfaced as such in the calc sheet + UI, and is validated against a reference worked example before demo day.
- Runs the SAME IR-protocol review spine as the culvert/retaining wall (independent cross-check → severity-graded memo → rule-computed verdict; no number in the memo absent from the deterministic results).

## Success Criteria
- [ ] "design a 30 m simply-supported deck-type welded plate girder, BG, 25t loading" completes a full run < 60 s with GA (DXF+SVG), 3D (GLB+STEP), calc sheet, a stress-summary panel and a proof-check verdict.
- [ ] Missing critical params: "design a plate girder bridge, BG single line" → questions asked in order (**span** first, then **steel grade**); answering "30 m" then "E250" completes the design.
- [ ] Missing only steel grade: "design a plate girder bridge, 30 m span, BG single line" → ONE question asking for the **steel grade**, naming the choices E250 or E350; answering "E350" completes the design.
- [ ] The stress-summary panel shows max bending / max shear vs permissible and max deflection vs span/600, each with a pass/fail indicator matching the deterministic results.
- [ ] Under-design: forcing `web_thickness_mm` (or `web_depth_mm`) below the sized value yields a FAIL row and a `return_for_revision` verdict naming the web; restoring it recovers the verdict.
- [ ] `ga.dxf` opens via `ezdxf.readfile` with the principal dimensions (span, overall depth) read back; the SVG renders styled in the browser; `model.glb` is a valid non-empty GLB.
- [ ] Every proof-check citation is within {IRS Steel Bridge Code, IS 800, IR Bridge Rules}; a genuinely out-of-domain RCC/road citation (IS 456 or IRC) on a plate-girder output fails the code-set check.
- [ ] Transcribed values are flagged `needs_verification` in the calc sheet and UI until reference-validated.
