# Capability: 3D Model

## What It Does
Generates an interactive 3D solid of the designed culvert from the same parameters that drove the drawing — viewable in the browser and downloadable as STEP for free CAD tools. *(Phase 3; labelled stub in Phases 1–2.)*

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| BoxGeometry | typed model | IRS Design Engine | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| `model.glb` | binary glTF | Artefact store; 3D Model tab viewer |
| `model.step` | STEP file | Artefact store; "Download STEP" button ("opens in FreeCAD — free") |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| 3D kernel (see [architecture.md](../architecture.md#stack) — version-pinned) | parametric solid → GLB + STEP export | **non-fatal**: warning event, 2D artefacts stand, run completes |

## Business Rules
- The solid comes from a **fixed parametric template** driven by BoxGeometry — the same numbers as the GA drawing; no free-form generated CAD code, ever.
- Solid contents: barrel (top/bottom slabs, walls, haunches) over the computed barrel length — a faithful structural solid, not a scenery model.
- 3D failure never blocks or fails a run (the 2D deliverables are the core) — the tab shows a designed "3D unavailable for this run" state, not an error page.
- The viewer loads the GLB only in the browser (client-only component); the STEP download is the audience-takeaway artefact.

## Success Criteria
- [ ] GLB parses as valid binary glTF (magic header + parseable structure) and its bounding box matches BoxGeometry external dimensions within 1 mm.
- [ ] STEP file is non-trivial (> 10 KB) and contains a manifold solid (validated by re-import in the same kernel).
- [ ] Same-source rule holds: for the canonical run, GLB bounding box, STEP solid dims, and the DXF dimensions all agree.
- [ ] Hard case — refinement regenerates: changing clear height 3.0 → 3.5 m changes the GLB bounding-box height accordingly.
- [ ] Hard case — simulated export failure: run still completes, warning event fires, Drawing/Calc/Proof-Check artefacts unaffected.
- [ ] E2E: the 3D tab shows an interactive model (camera-controls element present and loaded) for a real run.
