'use client'

import TypeSummaryPanel from './TypeSummaryPanel'
import type { TypeSummary, Verdict } from '@/lib/types'

interface OverviewPanelProps {
  verdict: Verdict | null
  componentType: string | null
  componentDisplayName: string | null
  codes: string[]
  typeSummary: TypeSummary | null
  /** GA drawing markup for the non-interactive thumbnail (null while pending). */
  svgMarkup: string | null
  /** Click-through: jump to the Design → Drawing panel. */
  onOpenDrawing: () => void
  runTokens: number
  runCostUsd: number
  createdAt: string | null
  durationMs: number | null
  hasRun: boolean
  isRunning: boolean
}

function VerdictBanner({ verdict }: { verdict: Verdict | null }) {
  const tone = verdict === 'recommended_for_approval' ? 'approved' : verdict === 'return_for_revision' ? 'revise' : 'draft'
  const map = {
    approved: {
      label: 'Recommended for approval',
      sub: 'The automatic proof-check passed the IRS checklist with an independent FE cross-check.',
      cls: 'border-emerald-500 bg-emerald-950/40',
      text: 'text-emerald-300',
      subText: 'text-emerald-200/80',
    },
    revise: {
      label: 'Return for revision',
      sub: 'The proof-check found one or more non-conformities — see the Review stage.',
      cls: 'border-red-600 bg-red-950/40',
      text: 'text-red-300',
      subText: 'text-red-200/80',
    },
    draft: {
      label: 'Draft — not yet reviewed',
      sub: 'No proof-check verdict yet. Run or refine the design to reach the Review stage.',
      cls: 'border-neutral-700 bg-neutral-900',
      text: 'text-neutral-200',
      subText: 'text-neutral-400',
    },
  }[tone]
  return (
    <div
      data-testid="overview-verdict-banner"
      data-verdict={verdict ?? 'none'}
      role="status"
      className={`rounded-xl border-2 px-5 py-4 ${map.cls}`}
    >
      <p className={`text-2xl font-bold ${map.text}`}>{map.label}</p>
      <p className={`mt-1 text-base ${map.subText}`}>{map.sub}</p>
    </div>
  )
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900 px-4 py-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-neutral-500">{label}</p>
      <p className="mt-1 text-base font-semibold text-neutral-100">{value}</p>
    </div>
  )
}

function fmtCost(usd: number): string {
  return `$${usd.toFixed(2)}`
}

function fmtTokens(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k tok` : `${n} tok`
}

function fmtCreated(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString()
}

function fmtDuration(ms: number | null): string {
  if (ms == null) return '—'
  const s = ms / 1000
  return s >= 60 ? `${Math.floor(s / 60)}m ${Math.round(s % 60)}s` : `${s.toFixed(1)}s`
}

export default function OverviewPanel({
  verdict,
  componentType,
  componentDisplayName,
  codes,
  typeSummary,
  svgMarkup,
  onOpenDrawing,
  runTokens,
  runCostUsd,
  createdAt,
  durationMs,
  hasRun,
  isRunning,
}: OverviewPanelProps) {
  const typeLabel = componentDisplayName ?? (componentType ? componentType.replace(/_/g, ' ') : 'Auto-detecting…')

  return (
    <div data-testid="overview-panel" className="space-y-5">
      <VerdictBanner verdict={verdict} />

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_18rem]">
        {/* Key numbers — generic type_summary renderer (no per-type code). */}
        <section aria-label="Key numbers" className="space-y-3">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-neutral-400">Key numbers</h3>
          <div className="rounded-xl bg-white p-4 shadow-sm">
            <TypeSummaryPanel
              componentType={componentType}
              typeSummary={typeSummary}
              isRunning={isRunning}
              runFailed={false}
              hasRun={hasRun}
            />
          </div>
        </section>

        {/* Drawing thumbnail (non-interactive) + cost. */}
        <div className="space-y-5">
          <section aria-label="Drawing preview" className="space-y-3">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-neutral-400">General arrangement</h3>
            {svgMarkup ? (
              <button
                type="button"
                data-testid="overview-drawing-thumb"
                onClick={onOpenDrawing}
                title="Open the full drawing in the Design stage"
                className="group block w-full overflow-hidden rounded-xl border border-neutral-700 bg-white p-2 transition-colors hover:border-indigo-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-400"
              >
                <div
                  aria-hidden="true"
                  className="pointer-events-none flex h-40 items-center justify-center overflow-hidden [&_svg]:h-full [&_svg]:w-full [&_svg]:max-w-full"
                  dangerouslySetInnerHTML={{ __html: svgMarkup }}
                />
                <span className="mt-1 block text-center text-xs font-medium text-indigo-400 group-hover:text-indigo-300">
                  Open drawing →
                </span>
              </button>
            ) : (
              <div
                data-testid="overview-drawing-empty"
                className="flex h-40 items-center justify-center rounded-xl border border-dashed border-neutral-700 bg-neutral-900 px-4 text-center text-sm text-neutral-500"
              >
                {isRunning ? 'The GA drawing appears here once the Draw step runs.' : 'No drawing for this design yet.'}
              </div>
            )}
          </section>

          <section aria-label="Cost" className="rounded-xl border border-neutral-800 bg-neutral-900 px-4 py-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-neutral-500">This design</p>
            <p className="mt-1 text-lg font-bold text-neutral-100">
              {fmtTokens(runTokens)} · {fmtCost(runCostUsd)}
            </p>
          </section>
        </div>
      </div>

      {/* Design metadata / code traceability. */}
      <section aria-label="Design metadata" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Meta label="Component type" value={typeLabel} />
        <Meta label="Code set" value={codes.length > 0 ? codes.join(', ') : '—'} />
        <Meta label="Created" value={fmtCreated(createdAt)} />
        <Meta label="Duration" value={fmtDuration(durationMs)} />
      </section>
    </div>
  )
}
