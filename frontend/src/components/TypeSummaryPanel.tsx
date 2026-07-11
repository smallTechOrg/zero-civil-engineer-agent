'use client'

import type { TypeSummary } from '@/lib/types'

interface TypeSummaryPanelProps {
  componentType: string | null
  typeSummary: TypeSummary | null
  isRunning: boolean
  runFailed: boolean
  hasRun: boolean
}

// ---------------------------------------------------------------------------
// Generic, config-driven metric renderer. A new component's stability summary
// needs no new code beyond (optionally) adding descriptors here: any numeric
// field with a known descriptor renders as a pass/fail metric; a paired
// value-vs-limit renders as a comparison; anything unrecognised falls back to
// a plain labelled value. A missing panel is NEVER a bug (spec/ui.md tab 0).
// ---------------------------------------------------------------------------

interface FosDescriptor {
  label: string
  requiredMin: number
  requiredLabel: string
}

// Factor-of-safety fields: value must be >= requiredMin (spec/capabilities/retaining-wall.md).
const FOS_DESCRIPTORS: Record<string, FosDescriptor> = {
  fos_overturning: { label: 'FoS — Overturning', requiredMin: 2.0, requiredLabel: '≥ 2.0' },
  fos_sliding: { label: 'FoS — Sliding', requiredMin: 1.5, requiredLabel: '≥ 1.5' },
}

// Value-vs-limit comparisons: {valueKey, limitKey, okKey?} rendered as one row.
interface ComparisonDescriptor {
  key: string
  label: string
  valueKey: string
  limitKey: string
  limitLabel: string
  unit: string
  okKey?: string
  /** pass when value <= limit (bearing pressure must not exceed SBC). */
  passWhen: 'lte' | 'gte'
}

// A flat, order-independent list. Each descriptor renders one row IFF its
// valueKey and limitKey are both present in the summary — so descriptors for a
// different component simply render nothing. New components need no new code
// beyond (optionally) adding a descriptor here (spec/ui.md tab 0).
const COMPARISON_DESCRIPTORS: ComparisonDescriptor[] = [
  // Pier & abutment / retaining wall — foundation bearing vs SBC.
  {
    key: 'bearing',
    label: 'Max bearing pressure vs SBC',
    valueKey: 'max_bearing_pressure_kn_m2',
    limitKey: 'sbc_kn_m2',
    limitLabel: 'SBC',
    unit: 'kN/m²',
    okKey: 'bearing_ok',
    passWhen: 'lte',
  },
  // Steel plate girder — stress_summary (bending / shear / deflection).
  {
    key: 'bending',
    label: 'Max bending stress vs permissible',
    valueKey: 'max_bending_stress_mpa',
    limitKey: 'permissible_bending_stress_mpa',
    limitLabel: 'Permissible',
    unit: 'MPa',
    okKey: 'bending_ok',
    passWhen: 'lte',
  },
  {
    key: 'shear_stress',
    label: 'Max shear stress vs permissible',
    valueKey: 'max_shear_stress_mpa',
    limitKey: 'permissible_shear_stress_mpa',
    limitLabel: 'Permissible',
    unit: 'MPa',
    okKey: 'shear_ok',
    passWhen: 'lte',
  },
  {
    key: 'deflection',
    label: 'Max deflection vs limit',
    valueKey: 'max_deflection_mm',
    limitKey: 'deflection_limit_mm',
    limitLabel: 'Limit',
    unit: 'mm',
    okKey: 'deflection_ok',
    passWhen: 'lte',
  },
  // RCC slab / T-beam — flexure_summary (required vs provided depth; shear).
  {
    key: 'flexure_depth',
    label: 'Required vs provided depth',
    valueKey: 'required_depth_mm',
    limitKey: 'provided_depth_mm',
    limitLabel: 'Provided',
    unit: 'mm',
    okKey: 'flexure_ok',
    passWhen: 'lte',
  },
  {
    key: 'slab_shear',
    label: 'Shear stress vs permissible',
    valueKey: 'shear_stress_mpa',
    limitKey: 'permissible_shear_mpa',
    limitLabel: 'Permissible',
    unit: 'MPa',
    okKey: 'shear_ok',
    passWhen: 'lte',
  },
  // --- Mechanical domain (Expansion Phase 3) ------------------------------
  // Structural steel member — utilisation_summary adds axial + weld rows on top
  // of the shared bending + shear rows above. Rolling-stock member reuses those
  // shared bending + shear rows (its governing_load_case renders via fallback).
  {
    key: 'axial',
    label: 'Max axial stress vs permissible',
    valueKey: 'max_axial_stress_mpa',
    limitKey: 'permissible_axial_stress_mpa',
    limitLabel: 'Permissible',
    unit: 'MPa',
    okKey: 'axial_ok',
    passWhen: 'lte',
  },
  {
    key: 'weld',
    label: 'Weld stress vs permissible',
    valueKey: 'weld_stress_mpa',
    limitKey: 'permissible_weld_stress_mpa',
    limitLabel: 'Permissible',
    unit: 'MPa',
    okKey: 'weld_ok',
    passWhen: 'lte',
  },
  // Machine element — fos_summary: max stress vs permissible + FoS vs required.
  {
    key: 'machine_stress',
    label: 'Max stress vs permissible',
    valueKey: 'max_stress_mpa',
    limitKey: 'permissible_stress_mpa',
    limitLabel: 'Permissible',
    unit: 'MPa',
    okKey: 'stress_ok',
    passWhen: 'lte',
  },
  {
    key: 'machine_fos',
    label: 'Factor of safety vs required',
    valueKey: 'factor_of_safety',
    limitKey: 'required_fos',
    limitLabel: 'Required',
    unit: '',
    okKey: 'fos_ok',
    passWhen: 'gte',
  },
]

function asNumber(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

function fmt(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(2)
}

function MetricRow({
  testid,
  label,
  value,
  requirement,
  pass,
}: {
  testid: string
  label: string
  value: string
  requirement: string
  pass: boolean
}) {
  return (
    <div
      data-testid={testid}
      data-pass={pass ? 'true' : 'false'}
      className={`flex items-center justify-between gap-4 rounded-lg border px-4 py-3 ${
        pass ? 'border-emerald-200 bg-emerald-50' : 'border-red-200 bg-red-50'
      }`}
    >
      <div>
        <p className="text-sm font-semibold text-slate-700">{label}</p>
        <p className="text-xs text-neutral-400">Required: {requirement}</p>
      </div>
      <div className="flex items-center gap-3">
        <span className={`text-lg font-bold tabular-nums ${pass ? 'text-emerald-800' : 'text-red-800'}`}>{value}</span>
        <span
          className={`rounded-full px-2.5 py-0.5 text-xs font-bold uppercase tracking-wide ${
            pass ? 'bg-emerald-600 text-white' : 'bg-red-600 text-white'
          }`}
        >
          {pass ? 'Pass' : 'Fail'}
        </span>
      </div>
    </div>
  )
}

export default function TypeSummaryPanel({
  componentType,
  typeSummary,
  isRunning,
  runFailed,
  hasRun,
}: TypeSummaryPanelProps) {
  if (!hasRun) {
    return (
      <div data-testid="type-summary-empty" className="flex h-full items-center justify-center p-8 text-center">
        <p className="max-w-md text-base leading-relaxed text-neutral-400">
          Run a design to see its stability / type summary here — factors of safety and bearing checks for a retaining
          wall, member checks for a culvert.
        </p>
      </div>
    )
  }

  if (runFailed) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-center">
        <p className="max-w-md text-base leading-relaxed text-neutral-400">
          No stability summary — the run did not complete.
        </p>
      </div>
    )
  }

  if (isRunning && !typeSummary) {
    return (
      <div data-testid="type-summary-loading" className="space-y-3 p-2">
        <div className="h-16 animate-pulse rounded-lg bg-neutral-800" />
        <div className="h-16 animate-pulse rounded-lg bg-neutral-800" />
        <div className="h-16 animate-pulse rounded-lg bg-neutral-800" />
        <p className="text-sm text-neutral-400">Computing stability checks…</p>
      </div>
    )
  }

  // A missing summary is informational, never an error — some components
  // (e.g. the culvert) may not publish a type_summary at all.
  if (!typeSummary || Object.keys(typeSummary).length === 0) {
    return (
      <div data-testid="type-summary-absent" className="flex h-full items-center justify-center p-8 text-center">
        <p className="max-w-md text-base leading-relaxed text-neutral-400">
          This component type does not publish a stability summary. See the Calc Sheet and Proof-Check tabs for its
          member checks and verdict.
        </p>
      </div>
    )
  }

  const consumed = new Set<string>()
  const fosRows: React.ReactNode[] = []
  const comparisonRows: React.ReactNode[] = []

  // Factor-of-safety rows.
  for (const [key, desc] of Object.entries(FOS_DESCRIPTORS)) {
    const value = asNumber(typeSummary[key])
    if (value == null) continue
    consumed.add(key)
    const pass = value >= desc.requiredMin
    fosRows.push(
      <MetricRow
        key={key}
        testid={`type-summary-${key}`}
        label={desc.label}
        value={fmt(value)}
        requirement={desc.requiredLabel}
        pass={pass}
      />,
    )
  }

  // Value-vs-limit comparison rows (bearing).
  for (const desc of COMPARISON_DESCRIPTORS) {
    const value = asNumber(typeSummary[desc.valueKey])
    const limit = asNumber(typeSummary[desc.limitKey])
    if (value == null || limit == null) continue
    consumed.add(desc.valueKey)
    consumed.add(desc.limitKey)
    if (desc.okKey) consumed.add(desc.okKey)
    const okFlag = desc.okKey != null && typeof typeSummary[desc.okKey] === 'boolean'
      ? (typeSummary[desc.okKey] as boolean)
      : desc.passWhen === 'lte'
        ? value <= limit
        : value >= limit
    comparisonRows.push(
      <MetricRow
        key={desc.key}
        testid={`type-summary-${desc.key}`}
        label={desc.label}
        value={`${fmt(value)} / ${fmt(limit)} ${desc.unit}`}
        requirement={`${desc.limitLabel} ${fmt(limit)} ${desc.unit}${desc.passWhen === 'lte' ? ' (max)' : ' (min)'}`}
        pass={okFlag}
      />,
    )
  }

  // Fallback rows for any unrecognised summary fields — a new component's
  // extra metrics still render (labelled value), no code change required.
  const fallbackRows = Object.entries(typeSummary)
    .filter(([key]) => !consumed.has(key))
    .map(([key, raw]) => {
      const value =
        typeof raw === 'boolean' ? (raw ? 'Yes' : 'No') : typeof raw === 'number' ? fmt(raw) : String(raw)
      return (
        <div
          key={key}
          data-testid={`type-summary-extra-${key}`}
          className="flex items-center justify-between gap-4 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3"
        >
          <span className="text-sm font-semibold text-slate-700">{key.replace(/_/g, ' ')}</span>
          <span className="text-base font-bold tabular-nums text-slate-800">{value}</span>
        </div>
      )
    })

  return (
    <div data-testid="type-summary-panel" data-component-type={componentType ?? ''} className="space-y-4 p-1">
      <div>
        <h3 className="text-lg font-bold text-neutral-100">Stability summary</h3>
        <p className="text-sm text-neutral-400">
          Deterministic stability checks{componentType ? ` — ${componentType.replace(/_/g, ' ')}` : ''}.
        </p>
      </div>

      {fosRows.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Factors of safety</p>
          {fosRows}
        </div>
      )}

      {comparisonRows.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Capacity checks</p>
          {comparisonRows}
        </div>
      )}

      {fallbackRows.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Other</p>
          {fallbackRows}
        </div>
      )}
    </div>
  )
}
