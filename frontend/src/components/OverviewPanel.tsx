'use client'

import type { ReactNode } from 'react'
import TypeSummaryPanel from './TypeSummaryPanel'
import type { StageId } from './StageRail'
import type { TypeSummary, Verdict } from '@/lib/types'

interface OverviewPanelProps {
  verdict: Verdict | null
  componentType: string | null
  componentDisplayName: string | null
  /** One-line requirement summary: params_summary if present, else the request. */
  requirementSummary: string | null
  codes: string[]
  typeSummary: TypeSummary | null
  /** GA drawing markup for the non-interactive thumbnail (null while pending). */
  svgMarkup: string | null
  /** Jump to a lifecycle stage (reuses the page's stage-select callback). */
  onSelectStage: (id: StageId) => void
  /** Click-through: jump to the Design → Drawing panel. */
  onOpenDrawing: () => void
  /** Click-through: jump to the Design → Calc Sheet panel. */
  onOpenCalc: () => void
  /** Click-through: jump to the Design → 3D Model panel. */
  onOpen3d: () => void
  /** Artefact readiness — drives each card's one-line status. */
  drawingReady: boolean
  calcReady: boolean
  modelReady: boolean
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

/** A clickable dark process card that jumps to a lifecycle stage. */
function ProcessCard({
  testid,
  step,
  title,
  status,
  statusTone = 'neutral',
  onClick,
  children,
}: {
  testid: string
  step: string
  title: string
  status: string
  statusTone?: 'neutral' | 'good' | 'warn' | 'pending'
  onClick: () => void
  children?: ReactNode
}) {
  const statusCls = {
    good: 'text-emerald-300',
    warn: 'text-red-300',
    pending: 'text-amber-300',
    neutral: 'text-neutral-300',
  }[statusTone]
  return (
    <div
      data-testid={testid}
      className="flex flex-col rounded-xl border border-neutral-800 bg-neutral-900 p-4 transition-colors hover:border-indigo-500/60"
    >
      <button
        type="button"
        onClick={onClick}
        className="group flex flex-1 flex-col items-start text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-400"
      >
        <span className="text-xs font-semibold uppercase tracking-wide text-neutral-500">{step}</span>
        <span className="mt-1 flex items-center gap-2 text-lg font-bold text-neutral-100 group-hover:text-indigo-300">
          {title}
          <span aria-hidden="true" className="text-sm text-indigo-400 opacity-0 transition-opacity group-hover:opacity-100">
            →
          </span>
        </span>
        <span className={`mt-1 text-sm font-medium ${statusCls}`}>{status}</span>
      </button>
      {children}
    </div>
  )
}

export default function OverviewPanel({
  verdict,
  componentType,
  componentDisplayName,
  requirementSummary,
  codes,
  typeSummary,
  svgMarkup,
  onSelectStage,
  onOpenDrawing,
  onOpenCalc,
  onOpen3d,
  drawingReady,
  calcReady,
  modelReady,
  runTokens,
  runCostUsd,
  createdAt,
  durationMs,
  hasRun,
  isRunning,
}: OverviewPanelProps) {
  const typeLabel = componentDisplayName ?? (componentType ? componentType.replace(/_/g, ' ') : 'Auto-detecting…')

  const reviewStatus =
    verdict === 'recommended_for_approval'
      ? { text: 'Proof-check: Recommended for approval', tone: 'good' as const }
      : verdict === 'return_for_revision'
        ? { text: 'Proof-check: Return for revision', tone: 'warn' as const }
        : isRunning
          ? { text: 'Proof-check running…', tone: 'pending' as const }
          : { text: 'Not yet reviewed', tone: 'neutral' as const }

  const designStatus = drawingReady
    ? { text: 'Drawing ready', tone: 'good' as const }
    : isRunning
      ? { text: 'Drafting artefacts…', tone: 'pending' as const }
      : { text: 'No artefacts yet', tone: 'neutral' as const }

  const subLink =
    'rounded-md border border-neutral-700 px-2.5 py-1 text-xs font-semibold text-neutral-300 transition-colors hover:border-indigo-400 hover:text-indigo-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-400 disabled:cursor-not-allowed disabled:opacity-40'

  return (
    <div data-testid="overview-panel" className="space-y-5">
      <VerdictBanner verdict={verdict} />

      {/* Process dashboard — one clickable card per stage of the design. */}
      <section aria-label="Design process" className="grid gap-4 lg:grid-cols-3">
        <ProcessCard
          testid="overview-card-define"
          step="① Define / Refine"
          title={typeLabel}
          status={hasRun ? 'Inputs captured — click to refine' : 'Describe the component'}
          statusTone="neutral"
          onClick={() => onSelectStage('define')}
        >
          {requirementSummary && (
            <p
              data-testid="overview-requirement-summary"
              title={requirementSummary}
              className="mt-2 line-clamp-2 text-sm leading-snug text-neutral-300"
            >
              {requirementSummary}
            </p>
          )}
          <p className="mt-2 text-xs text-neutral-500">{codes.length > 0 ? codes.join(' · ') : 'Code set auto-selected'}</p>
        </ProcessCard>

        <ProcessCard
          testid="overview-card-design"
          step="② Design"
          title="Drawing · Calc · 3D"
          status={designStatus.text}
          statusTone={designStatus.tone}
          onClick={onOpenDrawing}
        >
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" className={subLink} onClick={onOpenDrawing} disabled={!drawingReady && !isRunning}>
              GA Drawing
            </button>
            <button type="button" className={subLink} onClick={onOpenCalc} disabled={!calcReady && !isRunning}>
              Calc Sheet
            </button>
            <button type="button" className={subLink} onClick={onOpen3d} disabled={!modelReady && !isRunning}>
              3D Model
            </button>
          </div>
        </ProcessCard>

        <ProcessCard
          testid="overview-card-review"
          step="③ Review"
          title="Proof-check"
          status={reviewStatus.text}
          statusTone={reviewStatus.tone}
          onClick={() => onSelectStage('review')}
        >
          <p className="mt-2 text-xs text-neutral-500">{fmtTokens(runTokens)} · {fmtCost(runCostUsd)}</p>
        </ProcessCard>
      </section>

      {/* General arrangement — large, full-width preview linking into Design → Drawing. */}
      <section aria-label="General arrangement" className="space-y-4">
        <div className="rounded-xl border border-neutral-800 bg-neutral-900 p-4">
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-400">General arrangement</h3>
          {svgMarkup ? (
            <button
              type="button"
              data-testid="overview-drawing-thumb"
              onClick={onOpenDrawing}
              title="Open the full drawing in the Design stage"
              className="group block w-full overflow-hidden rounded-lg border border-neutral-700 bg-white p-3 transition-colors hover:border-indigo-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-400"
            >
              <div
                aria-hidden="true"
                className="pointer-events-none flex h-[26rem] items-center justify-center overflow-hidden lg:h-[34rem] [&_svg]:h-full [&_svg]:w-full [&_svg]:max-w-full"
                dangerouslySetInnerHTML={{ __html: svgMarkup }}
              />
              <span className="mt-2 block text-center text-xs font-medium text-indigo-400 group-hover:text-indigo-300">
                Open full drawing →
              </span>
            </button>
          ) : (
            <div
              data-testid="overview-drawing-empty"
              className="flex h-[26rem] items-center justify-center rounded-lg border border-dashed border-neutral-700 bg-neutral-950 px-4 text-center text-sm text-neutral-500 lg:h-[34rem]"
            >
              {isRunning ? 'The GA drawing appears here once the Draw step runs.' : 'No drawing for this design yet.'}
            </div>
          )}
        </div>

        {/* Design metadata (full-width row below the drawing). */}
        <dl className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
          <div className="rounded-lg border border-neutral-800 bg-neutral-900 px-3 py-2">
            <dt className="text-xs font-semibold uppercase tracking-wide text-neutral-500">Created</dt>
            <dd className="mt-0.5 font-semibold text-neutral-100">{fmtCreated(createdAt)}</dd>
          </div>
          <div className="rounded-lg border border-neutral-800 bg-neutral-900 px-3 py-2">
            <dt className="text-xs font-semibold uppercase tracking-wide text-neutral-500">Duration</dt>
            <dd className="mt-0.5 font-semibold text-neutral-100">{fmtDuration(durationMs)}</dd>
          </div>
        </dl>
      </section>

      {/* Detailed key numbers — reachable, collapsible, no longer the hero. */}
      <details data-testid="overview-key-numbers" open className="rounded-xl border border-neutral-800 bg-neutral-900 p-4">
        <summary className="cursor-pointer select-none text-sm font-semibold uppercase tracking-wide text-neutral-400">
          Key numbers — stability &amp; capacity
        </summary>
        <div className="mt-3 rounded-lg bg-neutral-950 p-3">
          <TypeSummaryPanel
            componentType={componentType}
            typeSummary={typeSummary}
            isRunning={isRunning}
            runFailed={false}
            hasRun={hasRun}
          />
        </div>
      </details>
    </div>
  )
}
