export type StepName = 'Understand' | 'Extract' | 'Analyse' | 'Check' | 'Draw' | 'Review'

export const STEP_NAMES: StepName[] = ['Understand', 'Extract', 'Analyse', 'Check', 'Draw', 'Review']

export type StepStatus = 'pending' | 'active' | 'done' | 'skipped' | 'failed'

export type RunStatus = 'running' | 'completed' | 'needs_input' | 'out_of_scope' | 'failed'

export interface StepState {
  name: StepName
  status: StepStatus
  detail: string | null
}

export interface StepEvent {
  step: StepName
  status: 'active' | 'done' | 'skipped' | 'failed'
  detail?: string | null
  elapsed_ms: number
}

export interface NarrationEvent {
  text: string
}

export interface WarningEvent {
  message: string
}

export interface ClarificationEvent {
  question: string
  missing_param?: string | null
}

export interface ArtefactEvent {
  kind: string
  filename: string
  url: string
}

export interface TokensEvent {
  prompt_tokens: number
  completion_tokens: number
  cost_usd: number
  session_total_cost_usd: number
}

export type Verdict = 'recommended_for_approval' | 'return_for_revision'

export interface DoneEvent {
  status: 'completed' | 'needs_input' | 'out_of_scope'
  verdict: Verdict | null
}

export interface RunErrorEvent {
  code: string
  message: string
}

export interface SnapshotStep {
  name: StepName
  status: StepStatus
  started_at?: string | null
  ended_at?: string | null
  detail?: string | null
}

export interface ArtefactRecord {
  kind: string
  filename: string
  url: string
  size_bytes?: number
}

export interface Assumption {
  field: string
  value: string
  source: string
  note?: string | null
}

// ---------------------------------------------------------------------------
// calc_sheet.json — pinned Phase-2 artefact shape (SSE artefact kind
// `calc_sheet`, also re-fetchable from the artifacts URL).
// ---------------------------------------------------------------------------

export type CalcLineStatus = 'PASS' | 'FAIL' | null

export interface CalcLine {
  description: string
  value: number | string | null
  unit: string | null
  citation: string | null
  /** Links the line into the drill-down trail; null = no expansion. */
  trail_ref?: string | null
  status?: CalcLineStatus
}

export interface CalcSection {
  /** design_basis | loading | analysis | member_checks */
  id: string
  title: string
  lines: CalcLine[]
}

export type TrailInputValue = number | string

/** A trail input is a plain value, or a {ref, value} link to another step. */
export type TrailInput = TrailInputValue | { ref: string; value: TrailInputValue }

export interface TrailStep {
  step_id: string
  description: string
  formula: string
  inputs: Record<string, TrailInput>
  value: number | string
  unit: string | null
  citation: string | null
}

export interface CalcSheetData {
  sections: CalcSection[]
  assumptions: Assumption[]
  warnings: string[]
  trail: TrailStep[]
}

// ---------------------------------------------------------------------------
// compliance.json — pinned Phase-2 artefact shape (SSE artefact kind
// `compliance`); the run snapshot's `checklist[]` mirrors `items`.
// ---------------------------------------------------------------------------

export type ComplianceSeverity = 'PASS' | 'OBSERVATION' | 'NON_CONFORMITY_MINOR' | 'NON_CONFORMITY_MAJOR'

export interface ComplianceItem {
  item: number
  title: string
  clause: string
  requirement: string
  computed: string
  limit: string
  severity: ComplianceSeverity
  detail: string
}

export interface ComplianceData {
  items: ComplianceItem[]
  verdict: Verdict | null
  fe_agreement_pct: number | null
}

/** Snapshot `checks[]` row (spec/api.md). */
export interface CheckRow {
  clause: string
  requirement: string
  computed: string
  limit: string
  status: 'PASS' | 'FAIL' | string
}

// ---------------------------------------------------------------------------
// Component catalogue (GET /api/components) — Expansion Phase 1. The picker
// greys `coming_soon` cards; `available` cards are selectable.
// ---------------------------------------------------------------------------

export type ComponentStatus = 'available' | 'coming_soon'

export interface ComponentCard {
  type_id: string
  display_name: string
  domain: string
  summary: string
  status: ComponentStatus
  codes: string[]
  example_prompt?: string | null
  /**
   * Standard-driven components (e.g. M-00004) are form-only: intake bypasses the
   * LLM. The API may expose this flag; when absent the frontend gates on the
   * known `m00004_box_culvert` type id (see `isParamsDirectComponent`).
   */
  params_direct_only?: boolean | null
}

export interface ComponentCatalogue {
  components: ComponentCard[]
}

// ---------------------------------------------------------------------------
// M-00004 Standard Box Culvert (RDSO) — params-direct component. Picking its
// card reveals `M00004ParamForm` in place of the NL prompt box; the form submits
// a typed `params` object (spec/capabilities/m00004-box-culvert.md § Inputs).
// ---------------------------------------------------------------------------

export const M00004_TYPE_ID = 'm00004_box_culvert'

export type ConcreteGrade = 'M25' | 'M30' | 'M35' | 'M40'
export type SteelGrade = 'Fe415' | 'Fe500'

/** Exposure class — drives the backend's derived concrete grade (Very severe → M40). */
export type ExposureCondition = 'moderate' | 'severe' | 'very_severe'

/** `M00004Params` — the exact typed fields, defaults and hard ranges.
 *  `concrete_grade` is `null` for Auto (the backend DERIVES the grade per
 *  exposure/size — M35 typical, M40 under very-severe); a set value overrides. */
export interface M00004Params {
  clear_span_m: number
  clear_height_m: number
  cushion_m: number
  surcharge_kn_m2: number
  formation_width_m: number
  side_slope_h_per_v: number
  concrete_grade: ConcreteGrade | null
  steel_grade: SteelGrade
  exposure: ExposureCondition
}

// ---------------------------------------------------------------------------
// M-00004 Phase 2 — the full RDSO/M-00004 GA sheet. The run now emits one
// DXF + SVG per diagram (ten drawings/tables), genuinely-3D STEP parts, a
// composed PDF sheet and a .zip bundle. The frontend renders these
// data-drivenly: it maps each artefact KIND → a human label and shows only the
// artefacts actually present on the run (a missing kind degrades gracefully —
// omitted, never an error). The exact kind→filename strings are fixed by
// spec/capabilities/m00004-box-culvert.md § "New artefact kinds → filenames".
// ---------------------------------------------------------------------------

/** One per-diagram drawing: its inline SVG kind + downloadable DXF kind + label. */
export interface M00004Diagram {
  /** Base identifier (used only for stable keys / test ids). */
  key: string
  /** Artefact kind whose SVG renders inline (e.g. `elevation_svg`). */
  svgKind: string
  /** Artefact kind downloadable as DXF (e.g. `elevation_dxf`). */
  dxfKind: string
  /** DXF filename for the download attribute (e.g. `elevation.dxf`). */
  dxfFilename: string
  /** Human name shown as the drawing's caption. */
  label: string
}

/** The ten M-00004 per-diagram drawings/tables, in sheet order. */
export const M00004_DIAGRAMS: M00004Diagram[] = [
  { key: 'elevation', svgKind: 'elevation_svg', dxfKind: 'elevation_dxf', dxfFilename: 'elevation.dxf', label: 'Sectional Elevation at X-Y' },
  { key: 'cross_section', svgKind: 'cross_section_svg', dxfKind: 'cross_section_dxf', dxfFilename: 'cross_section.dxf', label: 'Cross Section of R.C.C. Box' },
  { key: 'plan', svgKind: 'plan_svg', dxfKind: 'plan_dxf', dxfFilename: 'plan.dxf', label: 'Plan' },
  { key: 'curtain_wall', svgKind: 'curtain_wall_svg', dxfKind: 'curtain_wall_dxf', dxfFilename: 'curtain_wall.dxf', label: 'Section of Curtain / Drop Wall' },
  { key: 'typical_details', svgKind: 'typical_details_svg', dxfKind: 'typical_details_dxf', dxfFilename: 'typical_details.dxf', label: 'Typical Details at A & B' },
  { key: 'return_wall', svgKind: 'return_wall_svg', dxfKind: 'return_wall_dxf', dxfFilename: 'return_wall.dxf', label: 'Return Wall' },
  { key: 'bar_shape_table', svgKind: 'bar_shape_table_svg', dxfKind: 'bar_shape_table_dxf', dxfFilename: 'bar_shape_table.dxf', label: 'Bar-Bending Shape Table' },
  { key: 'notations', svgKind: 'notations_svg', dxfKind: 'notations_dxf', dxfFilename: 'notations.dxf', label: 'Notations' },
  { key: 'notes', svgKind: 'notes_svg', dxfKind: 'notes_dxf', dxfFilename: 'notes.dxf', label: 'Notes' },
  { key: 'haunch_table', svgKind: 'haunch_table_svg', dxfKind: 'haunch_table_dxf', dxfFilename: 'haunch_table.dxf', label: 'B×B Haunch Table' },
]

/** The six named engineering drawings the E2E asserts (subset of the ten). */
export const M00004_NAMED_DRAWING_KEYS = [
  'elevation',
  'cross_section',
  'plan',
  'curtain_wall',
  'typical_details',
  'return_wall',
] as const

/** A downloadable STEP part (genuinely-3D solids + the Phase-1 fused solid). */
export interface M00004StepPart {
  kind: string
  filename: string
  label: string
}

/** The STEP downloads offered for an M-00004 run — the four Phase-2 parts plus
 *  the Phase-1 fused solid. Rendered only for the parts actually present. */
export const M00004_STEP_PARTS: M00004StepPart[] = [
  { kind: 'assembly_step', filename: 'assembly.step', label: 'Full assembly (all bodies)' },
  { kind: 'box_step', filename: 'box.step', label: 'Box barrel' },
  { kind: 'curtain_wall_step', filename: 'curtain_wall.step', label: 'Curtain / drop wall' },
  { kind: 'return_wall_step', filename: 'return_wall.step', label: 'Return wall' },
  { kind: 'model_step', filename: 'model.step', label: 'Fused solid (Phase 1)' },
]

/** Composed full-sheet PDF (inline) + zip bundle artefact kinds. */
export const M00004_GA_SHEET_KIND = 'm00004_ga_sheet'
export const M00004_GA_SHEET_FILENAME = 'm00004_ga_sheet.pdf'
export const M00004_BUNDLE_KIND = 'm00004_bundle'
export const M00004_BUNDLE_FILENAME = 'm00004_bundle.zip'

/** type_summary for M-00004 — `kind: "m00004_standard"`. */
export interface M00004TypeSummary {
  kind: 'm00004_standard'
  config_id: string
  thickness_mm: number
  haunch_mm: number
  barrel_length_mm: number
  provisional_flags: string[]
  verdict?: string
}

/**
 * A params-direct (standard-driven) component is form-only. Prefer explicit
 * API metadata when exposed, else gate on the known M-00004 type id.
 */
export function isParamsDirectComponent(card: ComponentCard | null | undefined): boolean {
  if (!card) return false
  return card.params_direct_only === true || card.type_id === M00004_TYPE_ID
}

// ---------------------------------------------------------------------------
// type_summary — type-aware Stability panel (tab 0). Driven generically by
// component_type + type_summary; for a retaining wall the shape is the
// stability summary below (spec/capabilities/retaining-wall.md). A new
// component's summary needs no new frontend code beyond the generic renderer.
// ---------------------------------------------------------------------------

export interface RetainingWallTypeSummary {
  fos_overturning: number
  fos_sliding: number
  max_bearing_pressure_kn_m2: number
  sbc_kn_m2: number
  bearing_ok: boolean
}

// --- Expansion Phase 2 (civil breadth) type_summary shapes -------------------
// Documentary only — the renderer (TypeSummaryPanel) keys off field names via
// its FOS/COMPARISON descriptors, so `TypeSummary` stays `Record<string,unknown>`.

/** plate_girder — `kind: "stress_summary"`. */
export interface PlateGirderTypeSummary {
  kind: 'stress_summary'
  max_bending_stress_mpa: number
  permissible_bending_stress_mpa: number
  bending_ok: boolean
  max_shear_stress_mpa: number
  permissible_shear_stress_mpa: number
  shear_ok: boolean
  max_deflection_mm: number
  deflection_limit_mm: number
  deflection_ok: boolean
  verdict: string
}

/** slab_tbeam — `kind: "flexure_summary"`. */
export interface SlabTbeamTypeSummary {
  kind: 'flexure_summary'
  design_moment_knm: number
  required_depth_mm: number
  provided_depth_mm: number
  flexure_ok: boolean
  design_shear_kn: number
  shear_stress_mpa: number
  permissible_shear_mpa: number
  shear_ok: boolean
  steel_area_mm2: number
  min_steel_mm2: number
  verdict: string
}

/** pier_abutment — `kind: "stability"` (FoS + bearing, like the retaining wall). */
export interface PierAbutmentTypeSummary {
  kind: 'stability'
  fos_overturning: number
  fos_sliding: number
  max_bearing_pressure_kn_m2: number
  sbc_kn_m2: number
  bearing_ok: boolean
  verdict: string
}

/** Loosely typed: the renderer keys off known fields but tolerates any shape. */
export type TypeSummary = Record<string, unknown>

export interface RunSnapshot {
  run_id: string
  session_id: string
  /** Refinement-lineage record root; null when this run IS the root. */
  root_run_id?: string | null
  prompt: string
  status: RunStatus
  component_type?: string | null
  type_summary?: TypeSummary | null
  plan_text: string | null
  scope_message: string | null
  clarification_question: string | null
  params: Record<string, unknown> | null
  assumptions: Assumption[] | null
  warnings: string[] | null
  steps: SnapshotStep[]
  checks: CheckRow[] | null
  checklist: ComplianceItem[] | null
  verdict: Verdict | null
  suggestions: string[] | null
  artefacts: ArtefactRecord[]
  tokens: { prompt_tokens: number; completion_tokens: number; cost_usd: number } | null
  error_message: string | null
  started_at: string | null
  completed_at: string | null
  duration_ms: number | null
}

export interface SubmitDesignResponse {
  run_id: string
  status: string
  events_url: string
  snapshot_url: string
}

export interface SessionInfo {
  session_id: string
  title: string
  created_at: string
}

/** `GET /api/sessions` listing row (spec/api.md). */
export interface SessionSummary {
  session_id: string
  title: string
  created_at: string
  run_count: number
  total_prompt_tokens: number
  total_completion_tokens: number
  total_cost_usd: number
}

/** `GET /api/presets` item / `PUT /api/presets/{id}` response (spec/api.md). */
export interface Preset {
  preset_id: string
  name: string
  is_default: boolean
  values: Record<string, string | number>
}

export interface RunListItem {
  run_id: string
  session_id: string
  /**
   * Refinement-lineage record root; null when this run IS the root. The records
   * rail groups on the effective record id `root_run_id ?? run_id`.
   */
  root_run_id?: string | null
  prompt: string
  /** Component type of the run (NOT NULL on the row; defaults to box_culvert). */
  component_type: string
  status: RunStatus
  verdict: string | null
  params_summary: string | null
  cost_usd: number | null
  started_at: string | null
  duration_ms: number | null
}

export interface DesignListing {
  runs: RunListItem[]
  total: number
}

// ---------------------------------------------------------------------------
// DesignStatusChip — client-side derivation of a design's status-at-a-glance
// chip from the existing `status` + `verdict` fields (NO schema change).
//   • Reviewed ✓  — verdict `recommended_for_approval`
//   • Needs revision ✗ — verdict `return_for_revision`
//   • Draft — everything else (completed w/o verdict, needs_input, out_of_scope,
//     running, failed, or no verdict yet)
// ---------------------------------------------------------------------------

export type DesignChipTone = 'draft' | 'reviewed' | 'needs_revision'

export interface DesignStatusChipInfo {
  tone: DesignChipTone
  label: string
}

/** Derive the records-rail status chip from a design's raw status + verdict. */
export function DesignStatusChip(status: string, verdict: string | null): DesignStatusChipInfo {
  if (verdict === 'recommended_for_approval') {
    return { tone: 'reviewed', label: 'Reviewed ✓' }
  }
  if (verdict === 'return_for_revision') {
    return { tone: 'needs_revision', label: 'Needs revision ✗' }
  }
  return { tone: 'draft', label: 'Draft' }
}
