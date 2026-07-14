# Capability: M-00004 Standard Box Culvert (RDSO)

## What It Does
Reproduces the **published RDSO/M-00004 standard single box culvert** from a typed parameter form — the user enters the box dimensions and site data, a **deterministic catalogue lookup** picks the nearest/enclosing standard configuration, and the component emits the full standard package: a 2D GA (DXF + SVG), a 3D solid (STEP + GLB) and a **PDF drawing sheet styled like the real M-00004** with dimensioned cross-section, reinforcement bars **a1..h drawn in position**, a reinforcement schedule table, notations glossary and the standard notes. It is a **standard-driven, NOT a load-engineered** component: slab/wall **thickness, haunch and bar schedule come from the digitized annexure catalogue**, never from analysis. It is the ninth registered component (`type_id = m00004_box_culvert`), distinct from the load-engineered `box_culvert`, and it is reachable **only via the picker → parameter form** (a params-direct path that **bypasses the LLM understand/extract intake nodes** — zero LLM cost on intake).

> **PROVISIONAL policy (hard constraint):** every thickness, haunch and reinforcement value originates from a small, digitized, **PROVISIONAL** subset of the M-00004 annexure. Every such value rendered anywhere (PDF sheet, calc sheet, type summary, memo) MUST carry a clear **"PROVISIONAL — verify against RDSO/M-00004"** marking. Out-of-catalogue inputs are never silently guessed — they carry an explicit nearest-config / extrapolation note.

## Inputs

Submitted as a **typed `params` object** on `POST /api/sessions/{id}/designs` (see [api.md](../api.md#post-apisessionssession_iddesigns)), validated server-side against `M00004Params` before the run starts. No natural-language prompt is required on this path; a short synthetic prompt (e.g. `"M-00004 standard box culvert 4x4 m, fill 2 m"`) is stored for the audit trail/library row.

### Fixed parameter model — `M00004Params` (`src/components/m00004_box_culvert/params.py`)

| Field | Type | Required | Default | Range / role |
|-------|------|----------|---------|--------------|
| clear_span_m | float | **yes** | — | 1.0–8.0 hard; **selects standard config** (catalogue covers 2–6 m; outside → PROVISIONAL nearest) |
| clear_height_m | float | **yes** | — | 1.0–8.0 hard; **selects standard config** |
| cushion_m | float | **yes** | — | 0.0–6.0 hard; earth fill over the top slab; **selects standard fill tier** (catalogue 0/1/2 m; > 2 → PROVISIONAL) |
| surcharge_kn_m2 | float | no | 0.0 | 0–50; catalogue subset is surcharge = 0 only → any value > 0 adds a PROVISIONAL flag |
| formation_width_m | float | no | 6.85 | BG single-line formation width; **drives barrel length** |
| side_slope_h_per_v | float | no | 2.0 | Embankment side slope H:V; **drives barrel length** |
| concrete_grade | enum | no | M30 | M25 / M30 / M35 — title-block/notes only |
| steel_grade | enum | no | Fe500 | Fe415 / Fe500 — schedule/notes only |

`critical_fields = (clear_span_m, clear_height_m, cushion_m)` are declared for interface conformance, but the clarify path is **unreachable** on this component — the form enforces them client-side and the API rejects a missing/invalid params object with `422 PARAMS_INVALID` (see wiring below). Appendage dimensions (wing/return-wall length, apron length + thickness, curtain-wall thickness + depth) are **fixed engine constants** recorded as `Assumption`s (from the pilot: `WING_LEN = APRON_LEN = 2500`, `APRON_T = 300`, `CURTAIN_T = 400`, `CURTAIN_DEP = 1000` mm), not form fields, to keep the form small.

### Fixed engine output — `M00004Geometry` (`src/components/m00004_box_culvert/params.py`)
`{clear_span_mm, clear_height_mm, thickness_mm, haunch_mm, outer_width_mm, outer_height_mm, barrel_length_mm, config_id, bar_schedule, wing_len_mm, apron_len_mm, apron_thickness_mm, curtain_thickness_mm, curtain_depth_mm, provisional_flags}` — the single geometry source for the GA drawing, the 3D solid and the PDF sheet. Derived: `outer_width_mm = clear_span_mm + 2·thickness_mm`; `outer_height_mm = clear_height_mm + 2·thickness_mm`; `barrel_length_mm = formation_width_mm + 2·(cushion_mm + outer_height_mm)·side_slope_h_per_v` (the pilot's derived barrel length). `bar_schedule` is the selected config's `bars` map (mark → `{dia_mm, spacing_mm}`). Plus `Assumption[]` (config selection + appendage constants, each source-tagged and PROVISIONAL where catalogue-derived) and `CalcStep[]` trail.

## Catalogue data — the small pilot subset, extended (`src/components/m00004_box_culvert/catalog.json` + `catalog.py`)

Copied from `E:\smalltech\rdso-pilot\catalog.json` (15 configs = fill 0/1/2 m × five box sizes 2×2…6×6, `thickness_cm` + `haunch_mm`) into the component directory, and **extended in place** with a **PROVISIONAL bar schedule** per config. **Do NOT digitize the full 16-page annexure** — reuse only these 15 configs.

Extended per-config schema:
```json
{
  "id": "F2_4x4", "span_m": 4.0, "height_m": 4.0, "fill_m": 2.0, "surcharge_m": 0.0,
  "thickness_cm": 50, "haunch_mm": 450,
  "bars": {
    "a1": {"dia_mm": 16, "spacing_mm": 150}, "a2": {"dia_mm": 16, "spacing_mm": 150},
    "b":  {"dia_mm": 10, "spacing_mm": 200},
    "c":  {"dia_mm": 16, "spacing_mm": 150}, "d": {"dia_mm": 12, "spacing_mm": 200},
    "e":  {"dia_mm": 10, "spacing_mm": 200},
    "f1": {"dia_mm": 16, "spacing_mm": 150}, "f2": {"dia_mm": 16, "spacing_mm": 150},
    "g1": {"dia_mm": 12, "spacing_mm": 200}, "g2": {"dia_mm": 12, "spacing_mm": 200},
    "g3": {"dia_mm": 10, "spacing_mm": 250}, "h": {"dia_mm": 10, "spacing_mm": 200}
  }
}
```
The `_meta.status` field stays `"PROVISIONAL"`; a `_meta.bars_status` note records that the bar schedule is a provisional demonstration set, not transcribed from the annexure. `catalog.py` loads the file once and exposes `select_config(clear_span_m, clear_height_m, cushion_m, surcharge_kn_m2) -> (config, provisional_flags)`.

### Config-selection rule (deterministic, `catalog.py`)
1. **Fill tier:** choose the smallest catalogue `fill_m` that is **≥ requested `cushion_m`** (enclosing/conservative). If `cushion_m` exceeds the max tier (2 m), use the 2 m tier and append PROVISIONAL flag `"fill {x} m exceeds digitized range (0–2 m); using 2 m standard config"`.
2. **Box size:** within that fill tier, choose the config whose `span_m ≥ clear_span_m` **and** `height_m ≥ clear_height_m` with the **smallest** `span_m·height_m` (smallest enclosing standard box). If none encloses (input beyond 6×6), use the 6×6 config and append PROVISIONAL flag `"box {a}×{b} m exceeds digitized range (≤6×6 m); using 6×6 standard config"`.
3. **Surcharge:** the digitized subset is `surcharge = 0` only. If `surcharge_kn_m2 > 0`, keep the selected config and append PROVISIONAL flag `"surcharge {s} kN/m² not covered by the digitized subset (surcharge = 0)"`.
4. If the requested box does **not** exactly match the selected config's `span_m`/`height_m`, append a note `"opening {a}×{b} m drawn at entered size; thickness/haunch/bars taken from nearest standard config {id} ({span}×{height} m)"`.

The **opening** (clear span × clear height) is always drawn at the **entered** size; only **thickness, haunch and the bar schedule** come from the selected standard config — reproducing the standard's detailing on the entered box.

## Reinforcement bar marks — deterministic positions (`src/components/m00004_box_culvert/reinforcement.py`)

WHERE each bar goes is **deterministic geometry** from the standard single-cell box GA (no annexure needed); the **dia @ spacing NUMBERS** come from the selected config's `bars` map. All twelve marks, in cross-section:

| Mark | Member & face | Direction | Position rule (from geometry) |
|------|---------------|-----------|-------------------------------|
| a1 | Top slab — **bottom** (inner) face main | Transverse (across span) | Row of bars at cover below the top-slab soffit, spanning the clear span |
| a2 | Top slab — **top** (outer) face main | Transverse | Row at cover below the outer top face, concentrated over the haunches/walls |
| b | Top slab — distribution | Longitudinal | Both faces, orthogonal to a1/a2 |
| c | Side wall — main vertical, **earth (outer)** face | Vertical | Row at cover inside the outer wall face, full height |
| d | Side wall — main vertical, **inner** face | Vertical | Row at cover inside the inner wall face, full height |
| e | Side wall — horizontal distribution | Horizontal | Both faces, orthogonal to c/d |
| f1 | Bottom slab — **top** (inner) face main | Transverse | Row at cover above the bottom-slab top face |
| f2 | Bottom slab — **bottom** (outer) face main | Transverse | Row at cover above the bottom-slab underside |
| g1 | **Top** haunch corner bars | Diagonal | Corner bars across the two top internal haunches |
| g2 | **Bottom** haunch corner bars | Diagonal | Corner bars across the two bottom internal haunches |
| g3 | Corner / link bars | — | Nominal corner links tying the haunch bars |
| h | Bottom slab — distribution | Longitudinal | Both faces, orthogonal to f1/f2 |

`reinforcement.py` returns, per mark, the polyline/point set (in the section's coordinate frame) at which the PDF sheet draws the bar, plus a leader anchor for its `mark : dia @ spacing` tag. Positions are computed from `clear_span_mm`, `clear_height_mm`, `thickness_mm`, `haunch_mm` and a nominal clear cover (50 mm assumption).

## PDF sheet layout — `m00004_sheet.pdf` (`src/components/m00004_box_culvert/pdfsheet.py`)

One landscape page (A3) rendered by **reportlab** (hand-built parametric template — never LLM-generated), sections:
1. **Cross-section (main view):** outer concrete rectangle + inner octagon (four 45° haunches), hatched concrete, **all a1..h bars drawn in position** with leader tags (`a1 : 16Ø @ 150`), and dimension chains — clear span, clear height, slab/wall thickness `t`, haunch `B×B`, overall width/height.
2. **Longitudinal / part-plan view:** barrel length + return/wing walls + apron floor + curtain walls (the pilot's appendages), dimensioned.
3. **Reinforcement schedule table:** columns `Mark | Bar Ø (mm) | Spacing (mm) | Member / face | Notation` for rows a1..h, header **"REINFORCEMENT SCHEDULE (PROVISIONAL — verify against RDSO/M-00004)"**.
4. **Notations glossary:** legend mapping each mark to its member/face description.
5. **NOTES block:** standard M-00004 notes — concrete grade, clear cover, "ALL DIMENSIONS IN mm", lap/development notes, and the PROVISIONAL / "NOT FOR CONSTRUCTION" caveat.
6. **Title block (bottom-right):** "RDSO/M-00004 STANDARD SINGLE BOX CULVERT — GENERAL ARRANGEMENT & REINFORCEMENT", the entered box (`{span}×{height} m, fill {f} m`), selected `config_id`, material grades, scale N.T.S., date + run id, and a bold **"PROVISIONAL — NOT FOR CONSTRUCTION — verify every value against RDSO/M-00004"** strip.

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| Geometry + assumptions + calc trail | M00004Geometry + Assumption[] + CalcStep[] | State → drawing / 3D / PDF / calc sheet / audit |
| GA drawing | `ga.dxf` + `ga.svg` (concrete cross-section + part-plan, dimensions, RDSO-style title block) | Drawing tab; DXF download |
| **M-00004 PDF sheet** | `m00004_sheet.pdf` (dimensioned section + a1..h bars in position + schedule table + notations + notes + title block) | Drawing tab → "Open M-00004 sheet" (opens inline / downloads) |
| 3D model | `model.glb` + `model.step` (box + haunches + wing walls + apron + curtain walls) | 3D tab; STEP download |
| Calc sheet | `calc_sheet.json` (standard basis: config selection, thickness/haunch source, barrel-length derivation, bar schedule — every catalogue value PROVISIONAL) | Calc Sheet tab |
| Type summary | `{kind: "m00004_standard", config_id, thickness_mm, haunch_mm, barrel_length_mm, provisional_flags[], verdict}` | Type-summary panel |
| Proof-check | `compliance.json` + `proof_memo.md` + verdict | Proof-Check tab |

Artefact **kinds/filenames** reuse the shared fixed set plus one new kind: `m00004_sheet` → `m00004_sheet.pdf` (mime `application/pdf`, disposition `inline`), added to the API whitelist and the DB (free-text `artifacts.kind`, no migration). All other kinds/filenames are the existing shared set.

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| LLM (Gemini) | **Intake (understand/extract): NOT CALLED** — params are typed; the run is seeded directly (see wiring). Review-memo narration: ONE grounded call (same as every component), narrating the standard-reproduction + PROVISIONAL caveats | Memo narration failing grounding is discarded → the memo composes deterministically (never fatal). No other LLM call on this path |

## Params-direct pipeline wiring (bypasses the LLM intake)

Reference: [architecture.md → Params-direct intake path](../architecture.md#params-direct-intake-path-standard-driven-components). Precisely:
- `POST /api/sessions/{id}/designs` accepts an optional `params` object (see [api.md](../api.md)). When present it requires `component_type`; the API validates `params` against the module's `param_model` **synchronously** (`422 PARAMS_INVALID` on failure) and threads the validated dict to `start_design_run(..., params=validated)`. A `params_direct_only` component (M-00004 declares `params_direct_only = True`) submitted **without** `params` is rejected `422 PARAMS_REQUIRED`.
- `start_design_run` seeds `state["params"]` with the validated dict, `state["component_type"] = m00004_box_culvert`, `state["params_direct"] = True`, `in_scope = True`.
- The graph uses a **conditional entry point**: `params_direct` routes to a thin deterministic `seed_params` node (marks the Understand + Extract steps `done`, emits a deterministic plan narration + any unusual-value warnings, then routes to `analyse`); every NL run routes to `understand` unchanged. **No `understand`/`extract` LLM call runs on this path.**
- From `analyse` on, the shared pipeline is unchanged: `module.size()` runs config selection → geometry + thickness/haunch + bar schedule; `analyse()`/`run_checks()` are standard-conformance (no load analysis); `draw()` returns `{ga_dxf, ga_svg, m00004_sheet}`; `model3d()` builds the solid; `review()` runs the proof-check + one grounded memo narration.
- **Finalize suggestions are skipped for params-direct runs** (`finalize` only runs `_refinement_suggestions` when `not state["params_direct"]`) — refinement chips fill the NL prompt box, which this form-only component does not show, so they would dangle. This keeps the M-00004 path to **exactly one** (optional, grounded) LLM call — the review memo narration — with zero intake and zero suggestion cost.

## Business Rules
- **Standard-driven, not load-engineered:** thickness, haunch and reinforcement come ONLY from the selected catalogue config — no sizing from loads, no rigid-frame analysis, no code-check math. `analyse()` returns a minimal record stating the standard basis; `run_checks()` emits standard-conformance rows (each `PASS` with a PROVISIONAL note that the value is reproduced from the standard, not independently verified).
- **Config selection is deterministic** per the rule above; out-of-catalogue inputs always carry an explicit PROVISIONAL nearest-config / extrapolation flag — never a silent guess.
- **Bar layout is deterministic geometry**; bar dia @ spacing is catalogue data; the two are combined only for rendering.
- **Every catalogue-derived value is PROVISIONAL** and marked as such on every surface.
- **No cadquery:** the 3D solid reuses the pilot's geometry approach (box + haunches + return/wing walls + apron + curtain walls + derived barrel length) **reimplemented with `build123d`** (the repo's 3D library) — cadquery is not a repo dependency and must not be added. The solid verifies its own volume against the closed-form concrete volume before export (as the retaining-wall model3d does).
- **Drawings come only from hand-validated parametric templates** (ezdxf for the GA, reportlab for the sheet) — never LLM-written CAD.
- **Codes declared** by the module: `["RDSO/M-00004", "IRS Concrete Bridge Code"]`. Reproduces a standard drawing; it does not re-derive it.
- **No existing component is affected:** M-00004 is a new, self-contained `src/components/m00004_box_culvert/` module; it never imports the load-engineered `box_culvert` engine. The 8 existing components and the shared interface signatures are untouched.

## Success Criteria
- [ ] Picking **M-00004 Standard Box Culvert** in the gallery reveals the parameter form; submitting span 4 m / height 4 m / fill 2 m / surcharge 0 completes a full run in the studio and produces `ga.dxf`, `ga.svg`, `model.step`, `model.glb` **and** `m00004_sheet.pdf`.
- [ ] The run makes **zero LLM intake calls** — the Understand and Extract steps show `done` with a "standard component / parameter form" detail, and token cost for intake is 0 (only the review-memo call, if any, appears).
- [ ] Config selection: (4 m, 4 m, 2 m, 0) selects config `F2_4x4` (thickness 50 cm, haunch 450 mm); (3.5 m, 3.5 m, 1.2 m, 0) selects the enclosing `F2_4x4`-tier config and carries a nearest-config PROVISIONAL note; (7 m, 7 m, 3 m, 10) selects the 6×6 / 2 m config and carries fill + box + surcharge PROVISIONAL flags.
- [ ] `m00004_sheet.pdf` is a valid PDF served inline at `/api/designs/{run_id}/artifacts/m00004_sheet.pdf`; it shows the dimensioned cross-section, **all a1..h bars in position** with `mark : dia @ spacing` tags, the reinforcement schedule table, the notations glossary, the notes block and a title block — every catalogue value carries a **PROVISIONAL** marking.
- [ ] `ga.dxf` opens via `ezdxf.readfile` with the clear span / clear height read back correctly; the SVG renders styled in the browser.
- [ ] `model.glb` is a valid non-empty GLB and `model.step` opens in FreeCAD; the solid's volume matches the closed-form concrete volume within tolerance.
- [ ] The design library row and type-summary panel show the selected `config_id`, thickness, haunch and derived barrel length, each PROVISIONAL where catalogue-derived.
- [ ] `m00004_sheet.pdf` is in the `ARTIFACT_FILES` whitelist (`application/pdf`, inline); a request for it on a run that has not generated it returns 404, and a non-whitelisted filename returns 400 (existing behaviour, unchanged).
- [ ] **No regression:** every existing component (box_culvert, retaining_wall, and the six breadth-first types) and every existing unit/validation/integration/E2E test stays green; the NL path is byte-identical (routes to `understand`).
