# Capability: GA Drawing

## What It Does
Generates a dimensioned general-arrangement drawing of the designed culvert — plan, longitudinal section, cross-section, notes, and title block — as a genuine DXF that opens cleanly in AutoCAD and free CAD viewers, rendered server-side to SVG for in-browser pan/zoom.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| BoxGeometry | typed model | IRS Design Engine | yes |
| Parameters | CulvertParams | NL Design Intake | yes |
| Title-block fields | run id, date, span/height/fill summary, loading standard | Run record | yes |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| `ga.dxf` | DXF file | Artefact store; "Download DXF" button |
| `ga.svg` | SVG rendered from the same DXF | Artefact store; Drawing tab (pan/zoom) |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Drawing engine (see [architecture.md](../architecture.md#dxf--svg-server-side-rendering)) | template → DXF; DXF → SVG render | fatal for the run (transparent) |

## Business Rules
- The drawing comes ONLY from a **hand-validated parametric template** — LLM-written drawing code is banned; the LLM never touches geometry.
- Sheet contents: plan, longitudinal section, cross-section with dimension chains on all governing dimensions (clear span, clear height, member thicknesses, barrel length, cushion/fill line, haunches), layered per drawing conventions (dims, text, outlines, hatching, centrelines on separate layers), general notes (concrete grade, cover, loading standard incl. ACS level), and a title block.
- The SVG is rendered from the produced DXF by the same engine that wrote it (fidelity rule) — never re-drawn separately.
- Dimension values on the sheet are taken from BoxGeometry — the same source the calc sheet uses — so calc-vs-drawing consistency is structural, and the proof-check's DXF read-back item can verify it independently.
- The template validates its inputs (positive dims, thicknesses < span, etc.) and fails loudly on impossible geometry rather than drawing nonsense.

## Success Criteria
- [ ] The DXF loads without errors through the drawing engine's audit/recover check (structural-validity proxy for AutoCAD/free-viewer compatibility — see [architecture.md](../architecture.md#dxf--svg-server-side-rendering)) and contains DIMENSION entities with rendered geometry blocks, expected layers, and a title-block insert.
- [ ] DXF read-back of the dimensioned values matches BoxGeometry exactly (span, height, thicknesses, barrel length).
- [ ] The SVG renders non-empty, contains text elements for dimensions/notes, and displays in the Drawing tab with pan/zoom (E2E asserts the SVG is present and interactive).
- [ ] Hard case — extreme-but-valid geometry (1 m span / 6 m height, and 8 m span / 1 m height): no overlapping dimension text catastrophes, views stay inside the sheet frame (template auto-scales), file still audits clean.
- [ ] Regeneration on refinement: changing cushion 2.5 → 4.0 m produces a new DXF whose fill dimension reads 4.0 m.
- [ ] The "Download DXF" response carries the attachment disposition and a non-trivial file size (> 5 KB).
