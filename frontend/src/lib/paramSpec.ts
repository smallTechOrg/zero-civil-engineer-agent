// Component-neutral formatter for a run's gathered/merged parameters.
//
// `formatParamSpec(params)` turns the component-specific `params` dict (e.g.
// {clear_span_m, clear_height_m, cushion_m, loading_standard} for a culvert, or
// {span_m, steel_grade} for a slab/T-beam) into a legible `{label, value}[]`
// definition list — WITHOUT any per-component hardcoding. Snake_case keys become
// Title Case labels; a recognised unit suffix is stripped from the label and
// appended to the value (so "clear_span_m": 4 → { label: "Clear Span", value:
// "4 m" }). Null / empty values are skipped.

export interface ParamSpecEntry {
  label: string
  value: string
}

// Longest suffixes first — `_kn_m2` must win over `_kn_m`, which must win over
// `_m`. Each renders the already-formatted scalar with its unit.
const UNIT_SUFFIXES: { suffix: string; render: (v: string) => string }[] = [
  { suffix: '_kn_m2', render: v => `${v} kN/m²` },
  { suffix: '_kn_m', render: v => `${v} kN·m` },
  { suffix: '_kn', render: v => `${v} kN` },
  { suffix: '_mpa', render: v => `${v} MPa` },
  { suffix: '_mm', render: v => `${v} mm` },
  { suffix: '_m2', render: v => `${v} m²` },
  { suffix: '_m', render: v => `${v} m` },
  { suffix: '_deg', render: v => `${v}°` },
  { suffix: '_pct', render: v => `${v}%` },
]

function titleCase(key: string): string {
  return key
    .split('_')
    .filter(Boolean)
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

/** A scalar → display string: trim redundant decimals, booleans as Yes/No. */
function formatScalar(value: unknown): string {
  if (typeof value === 'number') {
    if (Number.isInteger(value)) return String(value)
    return String(parseFloat(value.toFixed(3)))
  }
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  return String(value)
}

function splitKey(key: string): { label: string; render: (v: string) => string } {
  for (const { suffix, render } of UNIT_SUFFIXES) {
    if (key.endsWith(suffix)) {
      return { label: titleCase(key.slice(0, -suffix.length)), render }
    }
  }
  return { label: titleCase(key), render: v => v }
}

export function formatParamSpec(
  params: Record<string, unknown> | null | undefined,
): ParamSpecEntry[] {
  if (!params) return []
  const entries: ParamSpecEntry[] = []
  for (const [key, raw] of Object.entries(params)) {
    if (raw === null || raw === undefined || raw === '') continue
    if (Array.isArray(raw)) {
      if (raw.length === 0) continue
    } else if (typeof raw === 'object') {
      // Skip nested objects — the spec grid is flat label:value pairs.
      continue
    }
    const { label, render } = splitKey(key)
    const valueStr = Array.isArray(raw) ? raw.map(formatScalar).join(', ') : formatScalar(raw)
    entries.push({ label, value: render(valueStr) })
  }
  return entries
}
