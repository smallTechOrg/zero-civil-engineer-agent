'use client'

import { useState } from 'react'
import type { Assumption, CalcLine, CalcSheetData, TrailInput, TrailStep } from '@/lib/types'

interface CalcSheetProps {
  sheet: CalcSheetData | null
  isRunning: boolean
  /** True while the run is mid-Analyse/Check — the sheet is being composed. */
  composing: boolean
  runFailed: boolean
  hasRun: boolean
}

/** Engineering-friendly number formatting: 5 significant figures, no noise. */
function formatValue(value: number | string | null | undefined): string {
  if (value == null) return '—'
  if (typeof value === 'number') return Number(value.toPrecision(5)).toString()
  return String(value)
}

const SOURCE_BADGE: Record<string, { label: string; className: string }> = {
  user: { label: 'User', className: 'bg-indigo-100 text-indigo-800' },
  preset: { label: 'Preset', className: 'bg-sky-100 text-sky-800' },
  engine_default: { label: 'Engine default', className: 'bg-slate-200 text-slate-700' },
}

function SourceBadge({ source }: { source: string }) {
  const badge = SOURCE_BADGE[source] ?? { label: source, className: 'bg-slate-200 text-slate-700' }
  return (
    <span className={`shrink-0 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold ${badge.className}`}>
      {badge.label}
    </span>
  )
}

function AssumptionsBlock({ assumptions }: { assumptions: Assumption[] }) {
  return (
    <section
      data-testid="calc-assumptions"
      className="rounded-xl border border-slate-200 bg-slate-50 p-4"
      aria-label="Assumptions"
    >
      <h3 className="text-base font-bold uppercase tracking-wide text-slate-700">Assumptions</h3>
      <p className="mt-1 text-sm text-slate-500">
        Every value the engine did not receive from you, with its source — nothing implicit.
      </p>
      {assumptions.length === 0 ? (
        <p className="mt-3 text-base text-slate-600">
          No assumed values — every parameter was supplied in the request.
        </p>
      ) : (
        <ul className="mt-3 divide-y divide-slate-200">
          {assumptions.map((a, i) => (
            <li
              key={`${a.field}-${i}`}
              data-testid="calc-assumption"
              className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2"
            >
              <span className="font-mono text-sm text-slate-600">{a.field}</span>
              <span className="text-base font-semibold text-slate-900">{a.value}</span>
              <SourceBadge source={a.source} />
              {a.note && <span className="text-sm text-slate-500">{a.note}</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function isRefInput(input: TrailInput): input is { ref: string; value: number | string } {
  return typeof input === 'object' && input !== null && 'ref' in input
}

/**
 * One substituted input inside a trail step. A {ref, value} input links to
 * the step that computed it — expandable in place, recursively.
 */
function TrailInputRow({
  name,
  input,
  trailById,
  ancestors,
}: {
  name: string
  input: TrailInput
  trailById: Map<string, TrailStep>
  ancestors: ReadonlySet<string>
}) {
  const [open, setOpen] = useState(false)

  if (!isRefInput(input)) {
    return (
      <li data-testid="calc-trail-input" className="flex flex-wrap items-baseline gap-x-2">
        <span className="font-mono text-sm font-semibold text-slate-700">{name}</span>
        <span className="text-sm text-slate-500">=</span>
        <span className="font-mono text-sm text-slate-900">{formatValue(input)}</span>
      </li>
    )
  }

  const refStep = trailById.get(input.ref)
  const circular = ancestors.has(input.ref)
  const expandable = !!refStep && !circular

  return (
    <li data-testid="calc-trail-input" className="space-y-2">
      <span className="flex flex-wrap items-baseline gap-x-2">
        <span className="font-mono text-sm font-semibold text-slate-700">{name}</span>
        <span className="text-sm text-slate-500">=</span>
        <span className="font-mono text-sm text-slate-900">{formatValue(input.value)}</span>
        {expandable ? (
          <button
            type="button"
            data-testid="calc-trail-ref"
            aria-expanded={open}
            onClick={() => setOpen(v => !v)}
            className="inline-flex items-center gap-1 rounded-md border border-indigo-200 bg-white px-2 py-0.5 text-xs font-semibold text-indigo-700 hover:bg-indigo-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600"
          >
            <span aria-hidden="true">{open ? '▾' : '▸'}</span>
            from {input.ref}
          </button>
        ) : (
          <span className="text-xs font-medium text-slate-500">
            from {input.ref}
            {circular ? ' (already expanded above)' : ' (step not in trail)'}
          </span>
        )}
      </span>
      {open && expandable && (
        <TrailStepView step={refStep} trailById={trailById} ancestors={new Set([...ancestors, input.ref])} />
      )}
    </li>
  )
}

/** A CalcStep drill-down card: formula, substituted inputs, result, citation. */
function TrailStepView({
  step,
  trailById,
  ancestors,
}: {
  step: TrailStep
  trailById: Map<string, TrailStep>
  ancestors: ReadonlySet<string>
}) {
  return (
    <div data-testid="calc-trail-step" className="space-y-2 rounded-lg border border-indigo-200 bg-indigo-50/60 p-3">
      <p className="text-sm text-slate-600">
        <span className="font-mono font-semibold text-indigo-800">{step.step_id}</span>
        <span aria-hidden="true"> · </span>
        {step.description}
      </p>
      <p data-testid="calc-trail-formula" className="rounded-md bg-white px-3 py-2 font-mono text-sm text-slate-900">
        {step.formula}
      </p>
      <ul data-testid="calc-trail-inputs" className="space-y-1.5 pl-1" aria-label="Substituted inputs">
        {Object.entries(step.inputs).map(([name, input]) => (
          <TrailInputRow key={name} name={name} input={input} trailById={trailById} ancestors={ancestors} />
        ))}
      </ul>
      <p className="flex flex-wrap items-baseline gap-x-2 text-sm">
        <span className="text-slate-500">=</span>
        <span className="font-mono font-semibold text-slate-900">
          {formatValue(step.value)}
          {step.unit ? ` ${step.unit}` : ''}
        </span>
        {step.citation && <cite className="not-italic text-xs text-slate-500">{step.citation}</cite>}
      </p>
    </div>
  )
}

function StatusChip({ status }: { status: 'PASS' | 'FAIL' }) {
  if (status === 'FAIL') {
    return (
      <span className="shrink-0 rounded-full bg-red-600 px-2.5 py-0.5 text-xs font-bold uppercase tracking-wide text-white">
        FAIL
      </span>
    )
  }
  return (
    <span className="shrink-0 rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide text-emerald-800">
      PASS
    </span>
  )
}

function CalcRow({ line, trailById }: { line: CalcLine; trailById: Map<string, TrailStep> }) {
  const [expanded, setExpanded] = useState(false)
  const trailStep = line.trail_ref ? trailById.get(line.trail_ref) : undefined
  const expandable = !!trailStep
  const failed = line.status === 'FAIL'

  const rowBody = (
    <span className="flex w-full flex-wrap items-baseline gap-x-3 gap-y-1">
      {expandable && (
        <span aria-hidden="true" className="w-4 shrink-0 text-sm text-indigo-600">
          {expanded ? '▾' : '▸'}
        </span>
      )}
      <span className={`min-w-0 flex-1 text-base leading-snug ${failed ? 'font-semibold text-red-900' : 'text-slate-800'}`}>
        {line.description}
      </span>
      <span className="whitespace-nowrap font-mono text-base font-semibold text-slate-900">
        {formatValue(line.value)}
        {line.unit ? ` ${line.unit}` : ''}
      </span>
      {line.citation && (
        <cite data-testid="calc-citation" className="whitespace-nowrap not-italic text-sm text-slate-500">
          {line.citation}
        </cite>
      )}
      {(line.status === 'PASS' || line.status === 'FAIL') && <StatusChip status={line.status} />}
    </span>
  )

  return (
    <li
      data-testid="calc-row"
      data-status={line.status ?? ''}
      className={
        failed
          ? 'border-l-4 border-red-600 bg-red-50'
          : line.status === 'PASS'
            ? 'border-l-4 border-emerald-200'
            : 'border-l-4 border-transparent'
      }
    >
      {expandable ? (
        <button
          type="button"
          data-testid="calc-row-expand"
          aria-expanded={expanded}
          title="Expand the calc trail — formula and substituted inputs"
          onClick={() => setExpanded(v => !v)}
          className="w-full px-3 py-2.5 text-left hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-indigo-600"
        >
          {rowBody}
        </button>
      ) : (
        <div className="px-3 py-2.5">{rowBody}</div>
      )}
      {expanded && trailStep && line.trail_ref && (
        <div data-testid="calc-trail" className="px-3 pb-3 pl-9">
          <TrailStepView step={trailStep} trailById={trailById} ancestors={new Set([line.trail_ref])} />
        </div>
      )}
    </li>
  )
}

export default function CalcSheet({ sheet, isRunning, composing, runFailed, hasRun }: CalcSheetProps) {
  if (!sheet) {
    if (isRunning) {
      return (
        <div
          data-testid="calc-sheet-loading"
          className="flex h-full min-h-[24rem] flex-col items-center justify-center gap-4 rounded-xl border border-slate-200 bg-white p-8"
        >
          <div className="w-full max-w-xl space-y-3" aria-hidden="true">
            <div className="h-8 w-2/3 rounded-lg bg-slate-100 motion-safe:animate-pulse" />
            <div className="h-5 w-full rounded-lg bg-slate-100 motion-safe:animate-pulse" />
            <div className="h-5 w-5/6 rounded-lg bg-slate-100 motion-safe:animate-pulse" />
            <div className="h-5 w-full rounded-lg bg-slate-100 motion-safe:animate-pulse" />
          </div>
          <p className="text-lg text-slate-600">
            {composing
              ? 'Composing the calculation sheet…'
              : 'The clause-cited calculation sheet appears here as soon as the load checks complete.'}
          </p>
        </div>
      )
    }
    if (runFailed) {
      return (
        <div className="flex h-full min-h-[24rem] items-center justify-center rounded-xl border border-slate-200 bg-white p-8">
          <p className="max-w-md text-center text-lg leading-relaxed text-slate-600">
            The run failed before the calculation sheet was composed — the details are in the red banner above. Fix
            the request and try again.
          </p>
        </div>
      )
    }
    return (
      <div className="flex h-full min-h-[24rem] items-center justify-center rounded-xl border border-slate-200 bg-white p-8">
        <p className="max-w-md text-center text-lg leading-relaxed text-slate-600">
          {hasRun
            ? 'This run produced no calculation sheet — select a completed design in the session panel, or run a new design.'
            : 'The clause-cited calculation sheet appears here — design basis, EUDL + CDA loading, analysis and member checks, with drill-down to every formula.'}
        </p>
      </div>
    )
  }

  const trailById = new Map(sheet.trail.map(step => [step.step_id, step]))

  return (
    <div data-testid="calc-sheet-content" className="space-y-5">
      <AssumptionsBlock assumptions={sheet.assumptions} />

      {sheet.warnings.length > 0 && (
        <div className="space-y-2">
          {sheet.warnings.map((message, i) => (
            <div
              key={i}
              data-testid="calc-warning"
              role="status"
              className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-base text-amber-900"
            >
              <span className="font-semibold">Flagged: </span>
              {message}
            </div>
          ))}
        </div>
      )}

      {sheet.sections.map(section => (
        <section
          key={section.id}
          data-testid="calc-section"
          data-section-id={section.id}
          aria-label={section.title}
          className="overflow-hidden rounded-xl border border-slate-200"
        >
          <h3 className="border-b border-slate-200 bg-slate-100 px-4 py-2.5 text-base font-bold text-slate-800">
            {section.title}
          </h3>
          {section.lines.length === 0 ? (
            <p className="px-4 py-3 text-base text-slate-500">No lines in this section for this design.</p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {section.lines.map((line, i) => (
                <CalcRow key={`${section.id}-${i}`} line={line} trailById={trailById} />
              ))}
            </ul>
          )}
        </section>
      ))}
    </div>
  )
}
