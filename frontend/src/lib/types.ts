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

export interface RunSnapshot {
  run_id: string
  session_id: string
  prompt: string
  status: RunStatus
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
  prompt: string
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
