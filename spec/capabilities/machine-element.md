# Capability: Machine Element (Mechanical Domain)

## What It Does
Designs a **machine element** — a transmission **shaft** or a **welded coupling joint** — from a natural-language request: torque from the transmitted power, combined bending + torsion (maximum-shear-stress theory) with a static factor of safety and a rotating-shaft fatigue check for a shaft, or the torsional shear in a circular fillet weld for a welded joint; a dimensioned detail drawing with GD&T and weld symbols + a 3D model; and the same IR-protocol proof-check — as a **breadth-first** registered component under the shared-core framework. It is the first **mechanical-domain** component, running on the SAME `ComponentModule` interface and proof-check spine as the civil components.

> **Breadth-first scope:** this delivers the full journey (NL/picker → typed params → detail drawing + core strength checks + IR-protocol proof-check + 3D) at a working, honest depth. Full machine-design parity (gear/bearing/coupling selection, critical-speed/whirling, keys & splines sizing, detailed notch-sensitivity fatigue, bolted-joint groups, lifting-hook plasticity) is explicitly **later deepening work**, not this phase.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| Prompt / picker choice | free text / type_id | User | yes |
| Prior params / preset | MachineElementParams / preset | Session, default preset | no |

## Fixed parameter model — `MachineElementParams` (`src/components/machine_element/params.py`)

**Normative field list** (the code slice builds against exactly this — it is shared with the engine/drawing/3D). **Critical** fields must come from the user (never defaulted → the one clarifying question). `CRITICAL_FIELDS = ("power_kw",)`. Any override left `None` is **auto-sized** by the engine.

| Field | Type | Critical | Default | Range / notes |
|-------|------|----------|---------|---------------|
| power_kw | float | **yes** | — | `ge 0.05, le 5000` (transmitted power, kW) |
| speed_rpm | float | no | 1450 | `ge 10, le 30000` (rotational speed) |
| element_kind | Literal[`shaft`, `welded_joint`] | no | `shaft` | transmission shaft vs welded coupling hub |
| material_grade | Literal[`40C8`, `EN24`] | no | `40C8` | 40C8 plain carbon / EN24 alloy steel (Design Data Book) |
| required_factor_of_safety | float | no | 2.0 | `ge 1.1, le 6` design FoS against shear yield |
| mounting_pcd_mm | float | no | 200 | pitch-circle diameter of the overhung gear/pulley (shaft) |
| overhang_mm | float | no | 150 | overhang of the mounted load from the bearing (shaft) |
| bending_shock_factor | float | no | 1.5 | combined-shock/fatigue factor Cm (shaft) |
| torsion_shock_factor | float | no | 1.0 | combined-shock/fatigue factor Ct (shaft) |
| has_keyway | bool | no | True | a keyway/keyseat is cut (drawing + GD&T note) |
| hub_diameter_mm | float | no | 120 | fillet-welded hub diameter (welded_joint) |
| diameter_mm | float \| None | no | None → auto | shaft diameter override; smaller than sized → warning (under-design demo case) |
| weld_size_mm | float \| None | no | None → auto | fillet-weld leg override; as above |

## Fixed engine output — `MachineElementGeometry` (`src/components/machine_element/params.py`)
`{element_kind, diameter_mm, length_mm, step_diameter_mm, step_length_mm, fillet_radius_mm, keyway_width_mm, keyway_depth_mm, hub_diameter_mm, weld_size_mm, weld_throat_mm, plate_thickness_mm}` — the parametric inputs to drawing + 3D (the inapplicable kind's fields are zero). Plus `Assumption[]` (defaulted values + source) and `CalcStep[]` trail.

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| Geometry + assumptions + calc trail | MachineElementGeometry + Assumption[] + CalcStep[] | State → drawing/3D/calc sheet/audit |
| Detail drawing | `ga.dxf` + `ga.svg` (shaft elevation + section, or hub-on-plate; dimensions, GD&T callouts, weld symbols, title block) | Drawing tab; DXF download |
| 3D model | `model.glb` + `model.step` (stepped shaft / hub-on-plate) | 3D tab; STEP download |
| Calc sheet | `calc_sheet.json` (clause-cited, drill-down) | Calc Sheet tab |
| FoS summary | `{kind:"fos_summary", max_stress_mpa, permissible_stress_mpa, stress_ok, factor_of_safety, required_fos, fos_ok, verdict}` | Type-specific FoS panel |
| Proof-check | `compliance.json` + `proof_memo.md` + verdict | Proof-Check tab |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| LLM (see [agent.md](../agent.md#llm-provider--model)) | Parameter extraction (structured output); memo narration (grounded) | 1 retry then fatal; a memo narration failing grounding is discarded (warning) and the memo composes deterministically |

## Business Rules
- **Declared code set** (`ComponentModule.codes`): **Machine Design Code (Shigley / PSG / Design Data Book)** — the standard closed-form machine-element methods (torque from power, combined bending+torsion by the maximum-shear-stress theory, permissible shear = shear-yield / FoS, Soderberg rotating-shaft fatigue) — plus **IS 816** (fillet-weld effective throat = 0.707 × leg, weld-group strength) for the welded-joint kind. A machine element is **mechanical**: a citation to a bridge/road/concrete code (IRC, IS 456, IRS Concrete Bridge Code) on a machine-element output is a defect. Honest and minimal — standard machine-design texts ARE the recognised code basis for these elements.
- **Sizing:** from `power_kw` and `speed_rpm` the engine computes the torque; for a **shaft** it auto-sizes the diameter to the larger of the static combined-stress demand and the rotating-shaft fatigue demand (then journals, shoulder fillet and keyway by standard proportions); for a **welded_joint** it auto-sizes the fillet leg from the circular-weld torsional strength (floored at a minimum practical leg). Any override (`diameter_mm`, `weld_size_mm`) replaces the auto value and flows through the checks — an override thinner than sized surfaces as a FAIL row (the under-design demo case).
- **Analysis:** torque `T = 9550·P/N`; for a shaft, the overhung bending moment from the mounted gear/pulley, the equivalent twisting moment `Te = sqrt((Cm·M)² + (Ct·T)²)`, the maximum shear stress `16·Te/(π·d³)`, the static factor of safety against shear yield, and the Soderberg fatigue factor of safety with a corrected endurance limit; for a weld, the throat shear `T/(0.707·s·π·D²/2)`.
- **Checks (clause-cited):** shaft — (1) combined bending + torsion: max shear stress ≤ permissible / static FoS ≥ required; (2) fatigue: rotating-shaft Soderberg FoS ≥ required; (3) stress-concentration (fillet/keyway) **OBSERVATION**. Welded joint — (1) throat shear ≤ permissible; (2) weld-detail **OBSERVATION**.
- Drawing/3D come ONLY from hand-validated parametric templates — never LLM-written CAD code. The detail drawing carries **GD&T** (diameter/tolerance callout ⌀d h7, surface-finish symbol Ra, datum feature symbol) and, for a welded joint, a **weld symbol** (arrow + reference line + fillet triangle + leg-size text on a `WELD` layer).
- **Transcription honesty:** every transcribed engineering value (material yield/ultimate strengths, endurance-correction and stress-concentration factors, belt-load factor) carries `needs_verification=true`, is surfaced as such in the calc sheet + UI, and is validated against a reference worked example before demo day.
- Runs the SAME IR-protocol review spine as the civil components (independent closed-form cross-check → severity-graded memo → rule-computed verdict; no number in the memo absent from the deterministic results).

## Success Criteria
- [ ] "design a power-transmission shaft for 20 kW at 1000 rpm" completes a full run < 60 s with the detail drawing (DXF+SVG), 3D (GLB+STEP), calc sheet, a FoS-summary panel and a proof-check verdict.
- [ ] Missing critical param: "design a transmission shaft" → ONE question naming the **power**; answering "20 kW" completes the design.
- [ ] The FoS-summary panel shows max stress vs permissible and the factor of safety vs required, each with a pass/fail indicator matching the deterministic results.
- [ ] Under-design: forcing `diameter_mm` (shaft) or `weld_size_mm` (weld) below the sized value yields a FAIL row and a `return_for_revision` verdict naming the member; restoring it recovers the verdict.
- [ ] `ga.dxf` opens via `ezdxf.readfile` with the principal dimensions read back and 0 audit errors; the GD&T callouts render, and for a welded joint the weld symbol renders on the `WELD` layer; the SVG renders styled in the browser; `model.glb` is a valid non-empty GLB.
- [ ] Every proof-check citation is within {Machine Design Code, IS 816}; a genuinely out-of-domain civil citation (IRC, IS 456 or IRS Concrete Bridge Code) on a machine-element output fails the code-set check.
- [ ] The reference worked example (shaft torque, required diameter for combined bending+torsion and the resulting FoS — including a FoS-fail case) matches the engine within ±5 %.
- [ ] Transcribed values are flagged `needs_verification` in the calc sheet and UI until reference-validated.
