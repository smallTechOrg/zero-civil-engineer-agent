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

---

## Phase 2 — Full RDSO/M-00004 GA sheet (all six drawings + STEP parts + composed sheet + zip)

> **Scope.** Phase 1 delivered ONE combined GA (`ga.dxf`/`ga.svg`), one fused 3D solid (`model.glb`/`model.step`) and one single-view PDF (`m00004_sheet.pdf`). Phase 2 expands the drawing deliverable to the **full M-00004 GA sheet**: **one DXF+SVG per diagram** (six drawings + four detail blocks/tables), **genuinely-3D STEP parts** (assembly + box + curtain/drop wall + return wall), and a **review-stage composed PDF laid out like the real M-00004 sheet + a `.zip` bundle** of every per-diagram DXF + STEP. It stays **100% deterministic parametric** (ezdxf 2D, build123d 3D, matplotlib+reportlab for the composed sheet — **NO LLM CAD**), every value sourced from `M00004Geometry`/`M00004Params`, and the **PROVISIONAL / NOT-FOR-CONSTRUCTION** discipline is preserved on every new surface. **All Phase-1 artefacts (`ga.dxf`/`ga.svg`/`model.glb`/`model.step`/`m00004_sheet.pdf`) keep working unchanged** — the Phase-2 outputs are additive. The params-direct pipeline + memo-narration-non-fatal behaviour are preserved.

### Materials — DEFAULT changes (normative, foundation slice)

| Item | Phase-1 default | **Phase-2 default** | Rule |
|------|-----------------|---------------------|------|
| `steel_grade` | `Fe500` | **`Fe415`** | RDSO/M-00004 uses Fe415. Still user-overridable to Fe500. |
| `concrete_grade` | `M30` (static) | **`None` = derive** | `None` ⇒ resolve per exposure/size rule below. A set value overrides. |
| Resolved concrete grade (derivation) | — | **`M-35`** (typical) | `very_severe` exposure → **M40**; else `max(span, height) < 1 m` → **M30**; else → **M35**. (Given `clear_span_m`/`clear_height_m` are `ge=1.0`, the M30 branch is unreachable in-range and documented as such.) |

- **Shared enum change (owned by the foundation slice, additive & regression-safe):** add member **`M40 = "M40"`** to `domain.culvert.ConcreteGrade` (currently `M25`/`M30`/`M35`). Additive only — no existing component defaults to or selects M40, so the retaining-wall / culvert / breadth-first types are unaffected and the regression suite stays green. A component-local enum is **not** used; the shared enum is extended because the addition is safe. This one-line edit is owned by the **foundation slice (a)** — not the wiring slice — so `params.py`/`sizing.py` can reference `ConcreteGrade.M40` within their own slice and no two slices touch `domain/culvert.py`.
- The resolved grade is stored on geometry as `concrete_grade_resolved` (string) and is the single value the drawings, notes, title blocks and composed sheet render. `resolve_concrete_grade(params)` lives in `sizing.py` and records the choice as a PROVISIONAL `Assumption`.

### New `M00004Params` fields (normative — FIX these; wave-2 slices build against this table)

| Field | Type | Required | Default | Range / role |
|-------|------|----------|---------|--------------|
| concrete_grade | `ConcreteGrade \| None` | no | **`None`** | `None` = derive (M35 typical / M40 very-severe / M30 below 1 m). Overridable to M25/M30/M35/M40. |
| steel_grade | `SteelGrade` | no | **`Fe415`** | Fe415 / Fe500. |
| exposure | `ExposureCondition` | no | **`ExposureCondition.SEVERE`** | New **component-local** enum in `params.py`: `MODERATE="moderate"`, `SEVERE="severe"`, `VERY_SEVERE="very_severe"`. Drives the M40 derivation branch. Title-block/notes + concrete derivation only. |

All other `M00004Params` fields are unchanged from Phase 1.

### New engine constants (`src/components/m00004_box_culvert/params.py`) — normative

| Constant | Value | Meaning |
|----------|-------|---------|
| WEARING_COURSE_THICKNESS_MM | `150.0` | Wearing course on the top slab / formation. |
| PCC_THICKNESS_MM | `150.0` | PCC levelling course under the box. |
| STONE_PITCHING_THICKNESS_MM | `300.0` | Stone pitching w/ cement grouting on the embankment slopes. |
| BASE_COURSE_THICKNESS_MM | `150.0` | Base course under the pitching/apron (the "150 base course"). |
| BED_SLOPE_RUN | `100.0` | Bed slope 1 in `BED_SLOPE_RUN` (1 in 100). |
| WEEP_HOLE_DIA_MM | `75.0` | 75-dia PVC weep holes. |
| WEEP_HOLE_SPACING_MM | `1000.0` | Weep holes @ 1000 c/c. |
| DROP_WALL_DEPTH_MM | `1500.0` | Drop-wall depth below bed at the outlet (deeper than the curtain wall's 1000; a drawing/detail value). |
| HFL_ABOVE_BED_FACTOR | `0.75` | HFL above bed = factor × clear height (PROVISIONAL assumption; hydraulics not verified). |
| RETURN_WALL_BASE_FACTOR | `0.5` | Return-wall base width = factor × outer height (PROVISIONAL taper basis). |

### New `M00004Geometry` fields (normative — FIX these; single source for every new diagram/model)

| Field | Type | Default | Role |
|-------|------|---------|------|
| concrete_grade_resolved | `str` | — | Resolved grade value (e.g. `"M35"`) — the one grade rendered everywhere. |
| cushion_mm | `float` | — | `cushion_m × 1000` — fill over the top slab (elevation). |
| formation_width_mm | `float` | — | `formation_width_m × 1000` — formation level width (elevation). |
| side_slope_h_per_v | `float` | — | Echo of the param — earth-bank slope (elevation) + wing-wall splay (plan). |
| wearing_course_thickness_mm | `float` | `WEARING_COURSE_THICKNESS_MM` | Elevation/notes. |
| pcc_thickness_mm | `float` | `PCC_THICKNESS_MM` | Elevation/notes. |
| stone_pitching_thickness_mm | `float` | `STONE_PITCHING_THICKNESS_MM` | Elevation slopes. |
| base_course_thickness_mm | `float` | `BASE_COURSE_THICKNESS_MM` | Elevation. |
| bed_slope_run | `float` | `BED_SLOPE_RUN` | Elevation bed-slope callout (1 in 100). |
| weep_hole_dia_mm | `float` | `WEEP_HOLE_DIA_MM` | Plan + typical details. |
| weep_hole_spacing_mm | `float` | `WEEP_HOLE_SPACING_MM` | Plan + typical details. |
| drop_wall_depth_mm | `float` | `DROP_WALL_DEPTH_MM` | Curtain/drop-wall section + elevation. |
| hfl_above_bed_mm | `float` | — | Derived `HFL_ABOVE_BED_FACTOR × clear_height_mm` (PROVISIONAL). Elevation HFL line. |
| return_wall_base_width_mm | `float` | — | Derived `RETURN_WALL_BASE_FACTOR × outer_height_mm` (PROVISIONAL). Return-wall diagram. |
| return_wall_top_width_mm | `float` | — | `= thickness_mm` — return-wall taper top width. |

All Phase-1 `M00004Geometry` fields are unchanged. New fields are populated in `sizing.py` (foundation slice) so every diagram/model/compose slice reads them from one source.

### Deliverable 1 — one DXF + SVG per diagram (NOT one combined DXF)

`drawing.py` is refactored into an **aggregator**: it still returns the Phase-1 `{ga_dxf, ga_svg, m00004_sheet}` (byte-behaviour preserved — `ga.dxf` remains the combined section+plan+title GA) **and** additionally returns a `<kind>_dxf` + `<kind>_svg` pair per diagram below, each authored by its own module under a new `drawings/` subpackage and each rendered to SVG via the shared `drawing.svg_render.render_svg`. Every value comes from `M00004Geometry`; every drawing carries the PROVISIONAL caption. `module.draw()` already returns the aggregator dict verbatim, so it needs no change for the new keys.

| # | Diagram | Module | Content (all dimensioned, from geometry) |
|---|---------|--------|------------------------------------------|
| 1 | Sectional Elevation at X-Y | `drawings/elevation.py` | Longitudinal section along the waterway: box under the embankment; C.L. of track + formation level + `formation_width_mm`; earth banks at `side_slope_h_per_v` (H:V); HFL line at `hfl_above_bed_mm`; bed level + bed slope `1 in bed_slope_run`; `stone_pitching_thickness_mm` pitching w/ cement grouting; hand-packed boulders; wing/return + drop/curtain walls each end; `base_course_thickness_mm` base course. |
| 2 | Cross Section of R.C.C. Box | `drawings/cross_section.py` | The Phase-1 `_draw_section` refactored into its own module with the **a1..h bars in position** (reuses `reinforcement.bar_layout`); identical geometry/behaviour. |
| 3 | Plan | `drawings/plan.py` | Promotes the Phase-1 part-plan: barrel opening, wing/return walls splaying along the embankment slope both ends, aprons, curtain & drop walls, `weep_hole_dia_mm` PVC weep holes @ `weep_hole_spacing_mm` c/c. |
| 4 | Section of Curtain / Drop Wall | `drawings/curtain_wall.py` | Detail through curtain + drop wall: `curtain_thickness_mm`, `curtain_depth_mm`, `drop_wall_depth_mm` key below bed, reinforcement. |
| 5 | Typical Details at A & B | `drawings/typical_details.py` | Reinforcement-placement details: weep holes (75-dia PVC @ 1000 c/c) + earth retainer + skin reinforcement + main reinforcement + distributors in top/bottom slabs + haunch bars. |
| 6 | Return Wall | `drawings/return_wall.py` | Section/elevation of the return wall: tapering profile (`return_wall_base_width_mm` → `return_wall_top_width_mm`), base width, reinforcement. |
| — | Reinforcement-for-Box bar-bending SHAPE table | `drawings/bar_shape_table.py` | a1..h bent-bar **shapes + length formulae** (distinct from the existing dia@spacing schedule); reuses `reinforcement.py` + `bar_schedule`. |
| — | Notations glossary | `drawings/notations.py` | Legend mapping each mark/notation to its member/face. |
| — | Notes block | `drawings/notes.py` | Standard M-00004 notes incl. grades, cover, wearing course, PCC, pitching, bed slope, "ALL DIMENSIONS IN mm", PROVISIONAL / NOT-FOR-CONSTRUCTION. |
| — | B×B Haunch table | `drawings/haunch_table.py` | Haunch `B×B` schedule vs box size. |

Each of the ten produces a `.dxf` (ezdxf) **and** a `.svg`. `reinforcement.py` (a1..h layout) stays in place and is reused by cross-section + bar-shape-table.

### Deliverable 2 — genuinely-3D STEP parts (build123d, NOT cadquery)

`model3d.py` is refactored to build and export, each part self-verifying its own closed-form sub-volume before export (as the Phase-1 `_verify` does):

| Part | Solid | Closed-form basis |
|------|-------|-------------------|
| Full assembly | box barrel + wing/return walls + apron + curtain/drop walls, exported as a build123d **assembly/compound** (multiple bodies) | `analytic_concrete_volume_m3` (total). |
| Box | barrel only (outer prism − haunched opening) | barrel term. |
| Curtain / drop wall | the two curtain/drop walls | curtains term. |
| Return wall | the four wing/return-wall bands | walls term. |

- The Phase-1 **fused** `model.glb` (viewer) + `model.step` (single fused solid) are **kept unchanged** for backward compatibility. `assembly.step` is a NEW, genuinely multi-body assembly (distinct from the fused `model.step`). Pure-2D outputs (plan, bar-shape table, notations, notes, haunch table) get **NO STEP**.
- `model3d()` returns `{model_glb, model_step, assembly_step, box_step, curtain_wall_step, return_wall_step}`. The graph `model3d` node is extended to emit **whatever keys `model3d()` returns** (backward-compatible loop over the returned dict rather than the hardcoded `("model_glb","model_step")` tuple), so existing components (which return only `model_glb`/`model_step`) are byte-identical.

### Deliverable 3 — review-stage composed sheet + zip bundle

- **Composed PDF `m00004_ga_sheet.pdf`** (`compose.py`, using **matplotlib + ezdxf's matplotlib backend** — matplotlib is already a repo dependency; **no new dep**): renders each on-disk per-diagram **DXF** into panels arranged in the M-00004 GA layout (the six drawings positioned as on the real sheet) + notations glossary + notes block + bar-bending table + haunch table + material specs + RDSO title block + the bold PROVISIONAL / NOT-FOR-CONSTRUCTION strip.
- **Bundle `m00004_bundle.zip`** (`bundle.py`, stdlib `zipfile`): zips every individual per-diagram **DXF** + every **STEP** part found on disk for the run (whatever is present — robust if the non-fatal 3D step produced no STEP files).
- **Emission point — the REVIEW node (documented, precise):** both are produced by an M-00004-only `module.compose(params, geometry, out_dir, run_id) -> {m00004_ga_sheet, m00004_bundle}` hook, invoked in the `review` node inside its **own non-fatal try/except** (mirroring the `model3d` non-fatal policy) and guarded by `getattr(module, "compose", None)` so **no other component is affected**. It runs at review because by then `draw` (2D — always on disk) and `model3d` (STEP — possibly absent, non-fatal) have completed; it is independent of the proof-check and of the non-fatal 3D step. A compose failure emits one `warning` event and the individual diagrams/STEP files remain downloadable — the run and verdict are unaffected.

### New artefact kinds → filenames → mime (normative — slices (e)+(f) wire these exact strings)

| Kind | Filename | `_ARTIFACT_MIME` (graph) | `ARTIFACT_FILES` (api) — mime, disposition |
|------|----------|--------------------------|--------------------------------------------|
| elevation_dxf | `elevation.dxf` | `image/vnd.dxf` | `image/vnd.dxf`, attachment |
| elevation_svg | `elevation.svg` | `image/svg+xml` | `image/svg+xml`, inline |
| cross_section_dxf | `cross_section.dxf` | `image/vnd.dxf` | `image/vnd.dxf`, attachment |
| cross_section_svg | `cross_section.svg` | `image/svg+xml` | `image/svg+xml`, inline |
| plan_dxf | `plan.dxf` | `image/vnd.dxf` | `image/vnd.dxf`, attachment |
| plan_svg | `plan.svg` | `image/svg+xml` | `image/svg+xml`, inline |
| curtain_wall_dxf | `curtain_wall.dxf` | `image/vnd.dxf` | `image/vnd.dxf`, attachment |
| curtain_wall_svg | `curtain_wall.svg` | `image/svg+xml` | `image/svg+xml`, inline |
| typical_details_dxf | `typical_details.dxf` | `image/vnd.dxf` | `image/vnd.dxf`, attachment |
| typical_details_svg | `typical_details.svg` | `image/svg+xml` | `image/svg+xml`, inline |
| return_wall_dxf | `return_wall.dxf` | `image/vnd.dxf` | `image/vnd.dxf`, attachment |
| return_wall_svg | `return_wall.svg` | `image/svg+xml` | `image/svg+xml`, inline |
| bar_shape_table_dxf | `bar_shape_table.dxf` | `image/vnd.dxf` | `image/vnd.dxf`, attachment |
| bar_shape_table_svg | `bar_shape_table.svg` | `image/svg+xml` | `image/svg+xml`, inline |
| notations_dxf | `notations.dxf` | `image/vnd.dxf` | `image/vnd.dxf`, attachment |
| notations_svg | `notations.svg` | `image/svg+xml` | `image/svg+xml`, inline |
| notes_dxf | `notes.dxf` | `image/vnd.dxf` | `image/vnd.dxf`, attachment |
| notes_svg | `notes.svg` | `image/svg+xml` | `image/svg+xml`, inline |
| haunch_table_dxf | `haunch_table.dxf` | `image/vnd.dxf` | `image/vnd.dxf`, attachment |
| haunch_table_svg | `haunch_table.svg` | `image/svg+xml` | `image/svg+xml`, inline |
| assembly_step | `assembly.step` | `application/step` | `application/step`, attachment |
| box_step | `box.step` | `application/step` | `application/step`, attachment |
| curtain_wall_step | `curtain_wall.step` | `application/step` | `application/step`, attachment |
| return_wall_step | `return_wall.step` | `application/step` | `application/step`, attachment |
| m00004_ga_sheet | `m00004_ga_sheet.pdf` | `application/pdf` | `application/pdf`, inline |
| m00004_bundle | `m00004_bundle.zip` | `application/zip` | `application/zip`, attachment |

The Phase-1 kinds/filenames (`ga_dxf`/`ga.dxf`, `ga_svg`/`ga.svg`, `model_glb`/`model.glb`, `model_step`/`model.step`, `m00004_sheet`/`m00004_sheet.pdf`) are unchanged. DB `artifacts.kind`/`filename` are free-text — **no migration**.

### Phase 2 Success Criteria

- [ ] `module.draw(...)` returns all Phase-1 keys PLUS the ten `<diagram>_dxf`/`<diagram>_svg` pairs; each file is emitted, opens via `ezdxf.readfile`, and contains the expected key entities (e.g. `elevation.dxf` has the HFL line + bed-slope callout; `cross_section.dxf` has the a1..h bars; `plan.dxf` has weep holes @ 1000 c/c).
- [ ] `model3d(...)` returns `assembly_step`/`box_step`/`curtain_wall_step`/`return_wall_step` in addition to `model_glb`/`model_step`; each STEP opens in FreeCAD and each part's built volume matches its closed-form sub-volume within tolerance.
- [ ] At review, `m00004_ga_sheet.pdf` (valid non-empty `application/pdf`, inline) lays out the six drawings + notations + notes + bar-bending + haunch tables + title block, every catalogue value PROVISIONAL; `m00004_bundle.zip` (valid `application/zip`) contains every per-diagram DXF + STEP present on disk.
- [ ] Materials: default steel = `Fe415`; `concrete_grade=None` + normal exposure resolves `concrete_grade_resolved="M35"`; `exposure="very_severe"` resolves `"M40"`; an explicit `concrete_grade` overrides; `ConcreteGrade.M40` added additively with **no** regression in any other component.
- [ ] Every new drawing/model/table generator has a unit test (geometry sanity + file emitted + key entities present); api/artifact tests cover the new whitelist entries; the `model3d` emit-loop and the review compose hook have graph/integration tests.
- [ ] **No regression:** Phase-1 artefacts (`ga.dxf`/`ga.svg`/`model.glb`/`model.step`/`m00004_sheet.pdf`) unchanged; every existing unit/validation/integration/E2E test stays green; PROVISIONAL / NOT-FOR-CONSTRUCTION captions on every new surface.
