'use client'

import { useState } from 'react'
import type { ConcreteGrade, M00004Params, SteelGrade } from '@/lib/types'

// ---------------------------------------------------------------------------
// M-00004 Standard Box Culvert (RDSO) parameter form. Shown in place of the NL
// prompt box when the M-00004 card is picked (the component is params-direct —
// intake bypasses the LLM). Fields, defaults and hard ranges mirror
// `M00004Params` (spec/capabilities/m00004-box-culvert.md § Inputs) so a bad
// value is caught client-side before submit; a server 422 PARAMS_INVALID is
// still surfaced (rare — the ranges match).
// ---------------------------------------------------------------------------

interface NumericField {
  key: keyof M00004Params
  label: string
  unit: string
  required: boolean
  min: number
  max: number
  step: number
  /** Initial value as a string; '' for a required field with no default. */
  initial: string
  help: string
}

const NUMERIC_FIELDS: NumericField[] = [
  {
    key: 'clear_span_m',
    label: 'Clear span',
    unit: 'm',
    required: true,
    min: 1.0,
    max: 8.0,
    step: 0.1,
    initial: '',
    help: 'Selects the standard config (catalogue 2–6 m; outside → PROVISIONAL nearest).',
  },
  {
    key: 'clear_height_m',
    label: 'Clear height',
    unit: 'm',
    required: true,
    min: 1.0,
    max: 8.0,
    step: 0.1,
    initial: '',
    help: 'Selects the standard config.',
  },
  {
    key: 'cushion_m',
    label: 'Cushion / earth fill',
    unit: 'm',
    required: true,
    min: 0.0,
    max: 6.0,
    step: 0.1,
    initial: '',
    help: 'Earth fill over the top slab (catalogue 0/1/2 m; > 2 → PROVISIONAL).',
  },
  {
    key: 'surcharge_kn_m2',
    label: 'Surcharge',
    unit: 'kN/m²',
    required: false,
    min: 0,
    max: 50,
    step: 1,
    initial: '0',
    help: 'Digitized subset is surcharge = 0; any value > 0 adds a PROVISIONAL flag.',
  },
  {
    key: 'formation_width_m',
    label: 'Formation width',
    unit: 'm',
    required: false,
    min: 0.1,
    max: 50,
    step: 0.05,
    initial: '6.85',
    help: 'BG single-line formation width; drives barrel length.',
  },
  {
    key: 'side_slope_h_per_v',
    label: 'Side slope (H:V)',
    unit: '',
    required: false,
    min: 0,
    max: 10,
    step: 0.1,
    initial: '2',
    help: 'Embankment side slope H:V; drives barrel length.',
  },
]

const CONCRETE_GRADES: ConcreteGrade[] = ['M25', 'M30', 'M35']
const STEEL_GRADES: SteelGrade[] = ['Fe415', 'Fe500']

type NumericKey = NumericField['key']

function initialNumericState(): Record<string, string> {
  return Object.fromEntries(NUMERIC_FIELDS.map(f => [f.key, f.initial]))
}

interface M00004ParamFormProps {
  componentName: string
  onSubmit: (params: M00004Params) => void
  disabled: boolean
  disabledReason: string | null
  submitting: boolean
  /** A server-side 422 PARAMS_INVALID / PARAMS_REQUIRED message, if any. */
  serverError: string | null
}

export default function M00004ParamForm({
  componentName,
  onSubmit,
  disabled,
  disabledReason,
  submitting,
  serverError,
}: M00004ParamFormProps) {
  const [numeric, setNumeric] = useState<Record<string, string>>(initialNumericState)
  const [concreteGrade, setConcreteGrade] = useState<ConcreteGrade>('M30')
  const [steelGrade, setSteelGrade] = useState<SteelGrade>('Fe500')
  const [errors, setErrors] = useState<Partial<Record<NumericKey, string>>>({})

  function setField(key: NumericKey, value: string) {
    setNumeric(prev => ({ ...prev, [key]: value }))
    if (errors[key]) setErrors(prev => ({ ...prev, [key]: undefined }))
  }

  function validate(): M00004Params | null {
    const nextErrors: Partial<Record<NumericKey, string>> = {}
    const values = {} as Record<NumericKey, number>

    for (const field of NUMERIC_FIELDS) {
      const raw = numeric[field.key].trim()
      if (raw === '') {
        if (field.required) {
          nextErrors[field.key] = `${field.label} is required.`
          continue
        }
        // Optional + blank → fall back to the documented default.
        values[field.key] = Number(field.initial)
        continue
      }
      const parsed = Number(raw)
      if (!Number.isFinite(parsed)) {
        nextErrors[field.key] = `${field.label} must be a number.`
        continue
      }
      if (parsed < field.min || parsed > field.max) {
        nextErrors[field.key] = `${field.label} must be between ${field.min} and ${field.max} ${field.unit}.`.trim()
        continue
      }
      values[field.key] = parsed
    }

    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors)
      return null
    }
    setErrors({})
    return {
      clear_span_m: values.clear_span_m,
      clear_height_m: values.clear_height_m,
      cushion_m: values.cushion_m,
      surcharge_kn_m2: values.surcharge_kn_m2,
      formation_width_m: values.formation_width_m,
      side_slope_h_per_v: values.side_slope_h_per_v,
      concrete_grade: concreteGrade,
      steel_grade: steelGrade,
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (disabled) return
    const params = validate()
    if (params) onSubmit(params)
  }

  const selectClass =
    'w-full rounded-lg border border-slate-300 bg-white p-2.5 text-base text-slate-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200 disabled:bg-slate-100 disabled:text-slate-500'

  return (
    <form data-testid="m00004-form" className="space-y-3" onSubmit={handleSubmit} noValidate>
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-slate-500">Standard parameters</p>
        <p className="mt-1 text-sm leading-snug text-slate-500">
          {componentName} is standard-driven — enter the box and site data; a deterministic catalogue lookup supplies
          thickness, haunch and reinforcement. Intake bypasses the LLM.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {NUMERIC_FIELDS.map(field => {
          const err = errors[field.key]
          const inputId = `m00004-${field.key}`
          return (
            <div key={field.key}>
              <label htmlFor={inputId} className="block text-sm font-semibold text-slate-700">
                {field.label}
                {field.unit && <span className="ml-1 font-normal text-slate-400">({field.unit})</span>}
                {field.required && <span className="ml-1 text-red-600" aria-hidden="true">*</span>}
              </label>
              <input
                id={inputId}
                data-testid={inputId}
                type="number"
                inputMode="decimal"
                step={field.step}
                min={field.min}
                max={field.max}
                required={field.required}
                value={numeric[field.key]}
                disabled={disabled}
                aria-invalid={err ? 'true' : undefined}
                aria-describedby={err ? `${inputId}-error` : undefined}
                onChange={e => setField(field.key, e.target.value)}
                className={`mt-1 w-full rounded-lg border bg-white p-2.5 text-base text-slate-900 shadow-sm focus:outline-none focus:ring-2 disabled:bg-slate-100 disabled:text-slate-500 ${
                  err
                    ? 'border-red-400 focus:border-red-500 focus:ring-red-200'
                    : 'border-slate-300 focus:border-indigo-500 focus:ring-indigo-200'
                }`}
              />
              {err ? (
                <p id={`${inputId}-error`} data-testid={`${inputId}-error`} role="alert" className="mt-1 text-sm font-medium text-red-700">
                  {err}
                </p>
              ) : (
                <p className="mt-1 text-xs leading-snug text-slate-400">{field.help}</p>
              )}
            </div>
          )
        })}
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="m00004-concrete_grade" className="block text-sm font-semibold text-slate-700">
            Concrete grade
          </label>
          <select
            id="m00004-concrete_grade"
            data-testid="m00004-concrete_grade"
            value={concreteGrade}
            disabled={disabled}
            onChange={e => setConcreteGrade(e.target.value as ConcreteGrade)}
            className={`mt-1 ${selectClass}`}
          >
            {CONCRETE_GRADES.map(g => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="m00004-steel_grade" className="block text-sm font-semibold text-slate-700">
            Steel grade
          </label>
          <select
            id="m00004-steel_grade"
            data-testid="m00004-steel_grade"
            value={steelGrade}
            disabled={disabled}
            onChange={e => setSteelGrade(e.target.value as SteelGrade)}
            className={`mt-1 ${selectClass}`}
          >
            {STEEL_GRADES.map(g => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </select>
        </div>
      </div>

      {serverError && (
        <p role="alert" data-testid="m00004-server-error" className="text-base font-medium text-red-700">
          {serverError}
        </p>
      )}

      <div className="space-y-2">
        <button
          type="submit"
          data-testid="m00004-submit"
          disabled={disabled}
          className="w-full rounded-lg bg-indigo-600 px-5 py-3 text-lg font-semibold text-white shadow-sm transition-colors hover:bg-indigo-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 disabled:cursor-not-allowed disabled:bg-slate-400"
        >
          {submitting ? 'Submitting…' : 'Design'}
        </button>
        {disabled && disabledReason && <p className="text-sm text-slate-600">{disabledReason}</p>}
        <p className="text-xs leading-snug text-slate-400">
          Thickness, haunch and the reinforcement schedule are reproduced from a digitized PROVISIONAL subset of the
          RDSO/M-00004 annexure — every such value is marked PROVISIONAL on the outputs.
        </p>
      </div>
    </form>
  )
}
