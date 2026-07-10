'use client'

import { useMemo, useState } from 'react'
import type { ComponentCard } from '@/lib/types'

interface ComponentPickerProps {
  components: ComponentCard[]
  /** null = "Let the agent decide" (auto-detect from the prompt). */
  activeTypeId: string | null
  onSelect: (typeId: string | null) => void
  disabled: boolean
}

// Stable domain order: Civil first, Mechanical second, anything else after.
const DOMAIN_ORDER: Record<string, number> = { Civil: 0, Mechanical: 1 }

function groupByDomain(components: ComponentCard[]): [string, ComponentCard[]][] {
  const groups = new Map<string, ComponentCard[]>()
  for (const c of components) {
    const list = groups.get(c.domain) ?? []
    list.push(c)
    groups.set(c.domain, list)
  }
  return [...groups.entries()].sort(
    ([a], [b]) => (DOMAIN_ORDER[a] ?? 99) - (DOMAIN_ORDER[b] ?? 99) || a.localeCompare(b),
  )
}

/**
 * Component gallery (spec/ui.md → "Component picker / gallery", Expansion
 * Phase 1). Grouped by domain; `available` cards are selectable and show the
 * declared code set; `coming_soon` cards render greyed with a "Coming soon"
 * badge — clickable only to reveal what they will design, never an error.
 * A "Let the agent decide" option leaves it to auto-detect.
 */
export default function ComponentPicker({ components, activeTypeId, onSelect, disabled }: ComponentPickerProps) {
  const [expanded, setExpanded] = useState<string | null>(null)
  const grouped = useMemo(() => groupByDomain(components), [components])

  if (components.length === 0) return null

  return (
    <section data-testid="component-picker" aria-label="Component picker" className="space-y-3">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Component</h2>

      <button
        type="button"
        data-testid="component-auto"
        aria-pressed={activeTypeId === null}
        onClick={() => onSelect(null)}
        disabled={disabled}
        className={`w-full rounded-lg border px-3.5 py-2.5 text-left text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 disabled:cursor-not-allowed disabled:opacity-60 ${
          activeTypeId === null
            ? 'border-indigo-500 bg-indigo-50 text-indigo-900 ring-1 ring-indigo-300'
            : 'border-slate-300 bg-white text-slate-700 hover:border-slate-400 hover:bg-slate-50'
        }`}
      >
        <span className="block font-semibold">Let the agent decide</span>
        <span className="mt-0.5 block text-xs text-slate-500">Auto-detect the component type from your prompt.</span>
      </button>

      {grouped.map(([domain, cards]) => (
        <div key={domain} className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">{domain}</p>
          <div className="grid gap-2">
            {cards.map(card => {
              const isAvailable = card.status === 'available'
              const isActive = isAvailable && card.type_id === activeTypeId
              const isOpen = expanded === card.type_id
              return (
                <button
                  key={card.type_id}
                  type="button"
                  data-testid="component-card"
                  data-type-id={card.type_id}
                  data-status={card.status}
                  data-active={isActive ? 'true' : 'false'}
                  aria-pressed={isActive}
                  disabled={disabled}
                  onClick={() => {
                    if (isAvailable) {
                      onSelect(card.type_id)
                    } else {
                      // Greyed cards never select — clicking only reveals the roadmap.
                      setExpanded(prev => (prev === card.type_id ? null : card.type_id))
                    }
                  }}
                  className={`w-full rounded-lg border px-3.5 py-2.5 text-left transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 disabled:cursor-not-allowed disabled:opacity-60 ${
                    isAvailable
                      ? isActive
                        ? 'border-indigo-500 bg-indigo-50 ring-1 ring-indigo-300'
                        : 'border-slate-300 bg-white hover:border-indigo-400 hover:bg-indigo-50/40'
                      : 'border-dashed border-slate-300 bg-slate-100'
                  }`}
                >
                  <span className="flex items-center justify-between gap-2">
                    <span
                      className={`text-sm font-semibold ${isAvailable ? 'text-slate-900' : 'text-slate-500'}`}
                    >
                      {card.display_name}
                    </span>
                    {isAvailable ? (
                      isActive && (
                        <span
                          data-testid="component-selected-badge"
                          className="rounded-full bg-indigo-600 px-2 py-0.5 text-[11px] font-semibold text-white"
                        >
                          Selected
                        </span>
                      )
                    ) : (
                      <span
                        data-testid="coming-soon-badge"
                        className="rounded-full bg-slate-300 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-slate-600"
                      >
                        Coming soon
                      </span>
                    )}
                  </span>
                  <span className={`mt-1 block text-xs leading-snug ${isAvailable ? 'text-slate-600' : 'text-slate-500'}`}>
                    {card.summary}
                  </span>
                  {isAvailable && card.codes.length > 0 && (
                    <span className="mt-2 flex flex-wrap gap-1">
                      {card.codes.map(code => (
                        <span
                          key={code}
                          className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-600"
                        >
                          {code}
                        </span>
                      ))}
                    </span>
                  )}
                  {!isAvailable && isOpen && (
                    <span
                      data-testid="coming-soon-roadmap"
                      className="mt-2 block rounded-md bg-white/70 px-2.5 py-2 text-xs leading-relaxed text-slate-600"
                    >
                      On the roadmap: {card.summary}
                      {card.codes.length > 0 && <> Planned code set: {card.codes.join(', ')}.</>}
                    </span>
                  )}
                </button>
              )
            })}
          </div>
        </div>
      ))}
    </section>
  )
}
