# Capability: Fabricated Structural Steel / Fabrication Member

## What It Does
Designs a fabricated welded-I structural-steel member — a cantilever **bracket**, **gantry post** or **OHE mast** — from a natural-language request: length/load-driven section sizing, working-stress code-checks (axial, bending, shear, the combined axial+bending interaction) against **IS 800**, a **base fillet-weld-group** check to **IS 816**, a fabrication drawing with **weld symbols** + a 3D model, and the same IR-protocol proof-check — as a **breadth-first** registered component under the shared-core framework. It is the first **mechanical-domain** component, replacing the `structural_steel_member` coming-soon stub.

> **Breadth-first scope:** this delivers the full journey (NL/picker → typed params → fabrication drawing + core code-checks + IR-protocol proof-check + 3D) at a working, honest depth. Full parity (lateral-torsional-buckling reduction, second-order P-delta, fatigue-detail categorisation, bolt-group / base-plate / stiffener detailing, biaxial bending, member types beyond the welded-I cantilever) is explicitly **later deepening work**, not this phase.

## Design method
**Working-stress / allowable-stress design to IS 800** (declared in the module docstring and calc sheet, and consistent everywhere): elastic section actions, permissible-stress comparisons, the IS 800 combined axial+bending interaction, and the IS 816 fillet-weld permissible stress. The member is a doubly-symmetric welded I-section cantilever carrying, in member-local axes, a transverse tip load (bending + shear) and a co-existent axial force, fillet-welded to its base.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| Prompt / picker choice | free text / type_id | User | yes |
| Prior params / preset | SteelMemberParams / preset | Session, default preset | no |

## Fixed parameter model — `SteelMemberParams` (`src/components/structural_steel_member/params.py`)

**Normative field list** (the code slice builds against exactly this — it is shared with the engine/drawing/3D). **Critical** fields must come from the user (never defaulted → the clarifying question, in priority order). `CRITICAL_FIELDS = ("cantilever_length_m", "transverse_load_kn")`. Any override left `None` is **auto-sized** by the engine.

| Field | Type | Critical | Default | Range / notes |
|-------|------|----------|---------|---------------|
| cantilever_length_m | float | **yes** | — | `ge 0.5, le 12` (projection / height from the welded base to the load point) |
| transverse_load_kn | float | **yes** | — | `ge 1, le 2000` (governing transverse/bending service load at the tip) |
| member_type | Literal[`bracket`, `gantry_post`, `ohe_mast`] | no | `gantry_post` | labelling + drawing title (unified cantilever mechanics) |
| axial_load_kn | float | no | 80 | `ge 0, le 5000` (co-existent axial compression along the member) |
| steel_grade | Literal[`E250`, `E350`] | no | `E250` | structural steel grade |
| web_depth_mm | float \| None | no | None → auto | clear web depth override; thinner/shallower than sized → warning (under-design demo case) |
| web_thickness_mm | float \| None | no | None → auto | as above |
| flange_width_mm | float \| None | no | None → auto | as above |
| flange_thickness_mm | float \| None | no | None → auto | as above |
| weld_size_mm | float \| None | no | None → auto | base fillet-weld leg override; smaller than sized → warning (connection under-design) |

## Fixed engine output — `SteelMemberGeometry`
`{member_type, cantilever_length_mm, web_depth_mm, web_thickness_mm, flange_width_mm, flange_thickness_mm, overall_depth_mm, weld_size_mm}` — the parametric inputs to drawing + 3D. Plus `Assumption[]` (defaulted values + source, incl. `needs_verification` flags) and `CalcStep[]` trail.

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| Geometry + assumptions + calc trail | SteelMemberGeometry + Assumption[] + CalcStep[] | State → drawing/3D/calc sheet/audit |
| Fabrication drawing | `ga.dxf` + `ga.svg` (elevation + cross-section, dimensions, **weld symbol** on a `WELD` layer, GD&T flatness/datum callout, RDSO-style title block) | Drawing tab; DXF download |
| 3D model | `model.glb` + `model.step` | 3D tab; STEP download |
| Calc sheet | `calc_sheet.json` (clause-cited, drill-down) | Calc Sheet tab |
| Utilisation summary | `{kind:"utilisation_summary", max_bending_stress_mpa, permissible_bending_stress_mpa, bending_ok, max_shear_stress_mpa, permissible_shear_stress_mpa, shear_ok, max_axial_stress_mpa, permissible_axial_stress_mpa, axial_ok, weld_stress_mpa, permissible_weld_stress_mpa, weld_ok, verdict}` | Type-specific Stress panel |
| Proof-check | `compliance.json` + `proof_memo.md` + verdict | Proof-Check tab |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| LLM (see [agent.md](../agent.md#llm-provider--model)) | Parameter extraction (structured output); memo narration (grounded) | 1 retry then fatal; a memo narration failing grounding is discarded (warning) and the memo composes deterministically |

## Business Rules
- **Declared code set** (`ComponentModule.codes`): **IS 800** (section proportioning, permissible axial/bending/shear stresses, the combined interaction, compression slenderness) + **IS 816** (fillet-weld permissible stress and the weld-group check). Only codes the pipeline HONESTLY cites are declared; IRC (roads) and the concrete codes (IS 456 / IRS Concrete Bridge Code) are out-of-domain and a citation to any of them on a steel-member output is a defect (enforced by `test_ssm_codeset.py`).
- **Sizing:** from `cantilever_length_m`, `transverse_load_kn`, `axial_load_kn` and `steel_grade` the engine auto-sizes the clear web depth (a length + moment-scaled law, capped a fraction of the length so the drawing stays a slender cantilever), flange width (proportioned to the depth AND grown until the weak-axis slenderness `KL/r` meets the compression target), web thickness (shear + unstiffened-web slenderness), flange thickness (the required section modulus, RESERVING capacity for the axial force so the combined interaction passes) and the base fillet-weld leg (to the IS 816 permissible). Any override replaces the auto value and flows through the checks — an override thinner/smaller than sized surfaces as a FAIL row (the under-design demo case).
- **Analysis:** cantilever design actions M = P·L + self-weight, V, and the co-existent axial N (member-local axes); exact elastic section properties (I_xx, Z, I_yy, r_min); slenderness `KL/r` with the cantilever effective length K = 2.0; the permissible axial stress from the Merchant-Rankine formula (fcc = π²E/λ², n = 1.4).
- **Checks (clause-cited):** (1) axial stress ≤ permissible axial stress (slenderness-dependent); (2) bending stress ≤ permissible bending stress (0.66 fy); (3) web shear ≤ permissible shear (0.40 fy); (4) combined axial+bending interaction ≤ 1.0; (5) base fillet-weld-group resultant throat stress ≤ IS 816 permissible; (6) compression slenderness `KL/r` ≤ 180 (minor on fail — a stockier or tubular/lattice member is indicated). Lateral-torsional buckling is taken as laterally-restrained and flagged as an OBSERVATION (later deepening work, honestly marked).
- **Weld symbol:** the base fillet weld is annotated on a dedicated `WELD` layer with a proper AWS/ISO-style symbol — leader/arrow line, horizontal reference line, filled fillet-weld triangle, weld-size text, and a weld-all-round circle — plus a basic GD&T flatness/datum callout on the machined base-plate face. Drawing/3D come ONLY from hand-validated parametric templates — never LLM-written CAD code.
- **Transcription honesty:** every transcribed engineering value (permissible bending/shear stresses, the transcribed `sigma_ac` table, the IS 816 fillet-weld permissible, the IS 816 minimum weld size) carries `needs_verification=true`, is surfaced as such in the calc-sheet assumptions + UI, and is cross-validated (the recorded `sigma_ac` is re-derived from the Merchant-Rankine formula and cross-checked against the transcribed table) and reference-validated before demo day.
- Runs the SAME IR-protocol review spine as the civil components (independent cross-check re-solving the section modulus, the N/A and M/Z stresses and the fillet-weld resultant → severity-graded 10-item memo → rule-computed verdict; no number in the memo absent from the deterministic results; only IS 800 / IS 816 may be cited).

## Success Criteria
- [ ] "design a welded steel gantry post, 6 m, 20 kN tip load, IS 800" completes a full run with the fabrication drawing (DXF+SVG), 3D (GLB+STEP), calc sheet, a utilisation-summary panel and a proof-check verdict.
- [ ] Missing critical param: "design a fabricated steel bracket" → ONE question naming the **length**, then the **load**; answering completes the design.
- [ ] The utilisation-summary panel shows max axial / bending / shear / weld vs their permissibles, each with a pass/fail indicator matching the deterministic results.
- [ ] Under-design: forcing `weld_size_mm` (or a thin `flange_thickness_mm`) below the sized value yields a FAIL row and a `return_for_revision` verdict naming the weld (or the member); restoring it recovers the verdict.
- [ ] `ga.dxf` opens via `ezdxf.readfile` with 0 audit errors and the principal dimensions (length, overall depth) read back; the base **weld symbol** renders on the `WELD` layer; the SVG renders styled in the browser; `model.glb` is a valid non-empty GLB.
- [ ] Every proof-check citation is within {IS 800, IS 816}; a genuinely out-of-domain concrete/road citation (IS 456 / IRS Concrete Bridge Code / IRC) on a steel-member output fails the code-set check.
- [ ] Transcribed values are flagged `needs_verification` in the calc sheet and UI until reference-validated; the worked-example fixture matches the engine within ±5 % (±10 % for the transcribed `sigma_ac` table value).
