'use client'

import { useCallback, useEffect, useState } from 'react'
import { ApiError, listPresets, updatePreset } from '@/lib/api'
import type { Preset } from '@/lib/types'

// The editable non-critical defaults (spec/data.md CulvertParams). Thickness
// overrides are deliberately absent — they are per-design, not preset values.
const GRADE_FIELDS = [
  { key: 'concrete_grade', label: 'Concrete grade', options: ['M25', 'M30', 'M35'] },
  { key: 'steel_grade', label: 'Steel grade', options: ['Fe415', 'Fe500'] },
] as const

const NUMERIC_FIELDS = [
  { key: 'clear_cover_mm', label: 'Clear cover (mm)', step: '1' },
  { key: 'soil_unit_weight_kn_m3', label: 'Soil unit weight (kN/m³)', step: '0.5' },
  { key: 'angle_of_friction_deg', label: 'Angle of internal friction (°)', step: '1' },
  { key: 'formation_width_m', label: 'Formation width (m)', step: '0.05' },
  { key: 'side_slope_h_per_v', label: 'Side slope (H per V)', step: '0.5' },
  { key: 'haunch_mm', label: 'Haunch (mm)', step: '25' },
] as const

interface FormState {
  name: string
  fields: Record<string, string>
}

function formFromPreset(preset: Preset): FormState {
  const fields: Record<string, string> = {}
  for (const f of [...GRADE_FIELDS, ...NUMERIC_FIELDS]) {
    const value = preset.values[f.key]
    fields[f.key] = value == null ? '' : String(value)
  }
  return { name: preset.name, fields }
}

const inputClass =
  'w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-base text-slate-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200 disabled:bg-slate-100 disabled:text-slate-500'
const labelClass = 'block text-sm font-semibold text-slate-600'

export default function PresetsEditor() {
  const [presets, setPresets] = useState<Preset[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [retryNonce, setRetryNonce] = useState(0)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [form, setForm] = useState<FormState | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setPresets(null)
    setLoadError(null)
    listPresets()
      .then(({ presets: loaded }) => {
        if (cancelled) return
        setPresets(loaded)
        const initial = loaded.find(p => p.is_default) ?? loaded[0] ?? null
        if (initial) {
          setSelectedId(initial.preset_id)
          setForm(formFromPreset(initial))
        }
      })
      .catch(error => {
        if (cancelled) return
        setLoadError(error instanceof ApiError ? error.message : 'Could not load the presets — try again.')
      })
    return () => {
      cancelled = true
    }
  }, [retryNonce])

  const selectPreset = useCallback(
    (presetId: string) => {
      const preset = presets?.find(p => p.preset_id === presetId)
      if (!preset) return
      setSelectedId(presetId)
      setForm(formFromPreset(preset))
      setSaveError(null)
      setSaveSuccess(null)
    },
    [presets],
  )

  const setField = (key: string, value: string) => {
    setForm(prev => (prev ? { ...prev, fields: { ...prev.fields, [key]: value } } : prev))
    setSaveError(null)
    setSaveSuccess(null)
  }

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    const preset = presets?.find(p => p.preset_id === selectedId)
    if (!preset || !form || saving) return
    setSaving(true)
    setSaveError(null)
    setSaveSuccess(null)
    // Keep any values beyond the form's fields intact; the API validates
    // fields and ranges and its 422 message is surfaced verbatim below.
    const values: Record<string, string | number> = { ...preset.values }
    for (const f of GRADE_FIELDS) values[f.key] = form.fields[f.key]
    for (const f of NUMERIC_FIELDS) {
      const raw = form.fields[f.key].trim()
      const parsed = Number(raw)
      values[f.key] = raw !== '' && Number.isFinite(parsed) ? parsed : raw
    }
    try {
      const updated = await updatePreset(preset.preset_id, { name: form.name, values })
      setPresets(prev => (prev ? prev.map(p => (p.preset_id === updated.preset_id ? updated : p)) : prev))
      setForm(formFromPreset(updated))
      setSaveSuccess('Preset saved — new runs pick up these defaults; past runs keep the values they used.')
    } catch (error) {
      setSaveError(error instanceof ApiError ? error.message : 'Could not save the preset — try again.')
    } finally {
      setSaving(false)
    }
  }

  if (loadError) {
    return (
      <div data-testid="preset-load-error" className="rounded-xl border border-red-200 bg-red-50 p-5">
        <p className="text-base font-semibold text-red-800">Could not load the presets</p>
        <p className="mt-1 text-base text-red-900">{loadError}</p>
        <button
          type="button"
          onClick={() => setRetryNonce(n => n + 1)}
          className="mt-3 rounded-lg bg-red-700 px-4 py-2 text-base font-semibold text-white hover:bg-red-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-700"
        >
          Try again
        </button>
      </div>
    )
  }

  if (presets === null) {
    return (
      <div data-testid="preset-loading" className="space-y-3 rounded-xl border border-slate-200 bg-white p-5">
        <div className="h-6 w-48 rounded bg-slate-100 motion-safe:animate-pulse" aria-hidden="true" />
        <div className="h-24 w-full rounded bg-slate-100 motion-safe:animate-pulse" aria-hidden="true" />
        <p className="text-base text-slate-500" role="status">
          Loading presets…
        </p>
      </div>
    )
  }

  if (presets.length === 0 || !form || !selectedId) {
    return (
      <p className="rounded-xl border border-slate-200 bg-slate-50 p-5 text-base text-slate-600">
        No presets found — the default preset is seeded by the database migration (`uv run alembic upgrade head`).
      </p>
    )
  }

  const selected = presets.find(p => p.preset_id === selectedId)

  return (
    <form data-testid="preset-editor" onSubmit={handleSave} className="space-y-5 rounded-xl border border-slate-200 bg-white p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-base leading-relaxed text-slate-600">
          Defaults applied when a prompt leaves a non-critical parameter unstated. Every applied default is recorded
          as an assumption in the calc sheet; editing here never rewrites past runs.
        </p>
      </div>

      {presets.length > 1 && (
        <div className="max-w-sm space-y-1.5">
          <label htmlFor="preset-select" className={labelClass}>
            Preset
          </label>
          <select
            id="preset-select"
            data-testid="preset-select"
            value={selectedId}
            onChange={e => selectPreset(e.target.value)}
            disabled={saving}
            className={inputClass}
          >
            {presets.map(p => (
              <option key={p.preset_id} value={p.preset_id}>
                {p.name}
                {p.is_default ? ' (default)' : ''}
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div className="space-y-1.5 sm:col-span-2 lg:col-span-3">
          <label htmlFor="preset-name" className={labelClass}>
            Preset name
            {selected?.is_default && (
              <span className="ml-2 rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-semibold text-indigo-800">
                Default preset
              </span>
            )}
          </label>
          <input
            id="preset-name"
            data-testid="preset-name"
            type="text"
            value={form.name}
            onChange={e => {
              const name = e.target.value
              setForm(prev => (prev ? { ...prev, name } : prev))
              setSaveError(null)
              setSaveSuccess(null)
            }}
            disabled={saving}
            className={`${inputClass} max-w-md`}
          />
        </div>

        {GRADE_FIELDS.map(f => (
          <div key={f.key} className="space-y-1.5">
            <label htmlFor={`preset-${f.key}`} className={labelClass}>
              {f.label}
            </label>
            <select
              id={`preset-${f.key}`}
              data-testid={`preset-field-${f.key}`}
              value={form.fields[f.key]}
              onChange={e => setField(f.key, e.target.value)}
              disabled={saving}
              className={inputClass}
            >
              {f.options.map(option => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
        ))}

        {NUMERIC_FIELDS.map(f => (
          <div key={f.key} className="space-y-1.5">
            <label htmlFor={`preset-${f.key}`} className={labelClass}>
              {f.label}
            </label>
            <input
              id={`preset-${f.key}`}
              data-testid={`preset-field-${f.key}`}
              type="number"
              step={f.step}
              value={form.fields[f.key]}
              onChange={e => setField(f.key, e.target.value)}
              disabled={saving}
              className={inputClass}
            />
          </div>
        ))}
      </div>

      {saveError && (
        <p data-testid="preset-save-error" role="alert" className="text-base font-medium text-red-700">
          {saveError}
        </p>
      )}
      {saveSuccess && (
        <p data-testid="preset-save-success" role="status" className="text-base font-medium text-emerald-700">
          {saveSuccess}
        </p>
      )}

      <button
        type="submit"
        data-testid="preset-save"
        disabled={saving}
        className="rounded-lg bg-indigo-600 px-5 py-2.5 text-base font-semibold text-white shadow-sm transition-colors hover:bg-indigo-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 disabled:cursor-not-allowed disabled:bg-slate-400"
      >
        {saving ? 'Saving…' : 'Save preset'}
      </button>
    </form>
  )
}
