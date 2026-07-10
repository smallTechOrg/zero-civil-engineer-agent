'use client'

import { useEffect, useState } from 'react'
import PresetsEditor from './PresetsEditor'
import { ApiError, listDesigns, listSessions } from '@/lib/api'
import type { DesignListing, RunListItem, RunStatus, SessionSummary } from '@/lib/types'

const PAGE_SIZE = 10

interface LibraryPanelProps {
  onSelectRun: (runId: string) => void
  selectionDisabled: boolean
  activeRunId: string | null
  /** Bumped by the studio when a run starts/finishes so the list refreshes live. */
  refreshKey: number
}

function VerdictChip({ verdict, status }: { verdict: string | null; status: RunStatus }) {
  if (verdict === 'recommended_for_approval') {
    return (
      <span
        data-testid="library-verdict"
        data-verdict="recommended_for_approval"
        className="whitespace-nowrap rounded-full bg-emerald-100 px-2.5 py-0.5 text-sm font-semibold text-emerald-800"
      >
        Recommended
      </span>
    )
  }
  if (verdict === 'return_for_revision') {
    return (
      <span
        data-testid="library-verdict"
        data-verdict="return_for_revision"
        className="whitespace-nowrap rounded-full bg-red-100 px-2.5 py-0.5 text-sm font-semibold text-red-800"
      >
        Return for revision
      </span>
    )
  }
  const label: Record<RunStatus, string> = {
    running: 'Running',
    completed: 'No verdict',
    needs_input: 'Needs input',
    out_of_scope: 'Out of scope',
    failed: 'Failed',
  }
  return (
    <span
      data-testid="library-verdict"
      data-verdict="none"
      className="whitespace-nowrap rounded-full bg-slate-100 px-2.5 py-0.5 text-sm font-semibold text-slate-600"
    >
      {label[status] ?? '—'}
    </span>
  )
}

function formatWhen(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatDuration(ms: number | null): string {
  if (ms == null) return '—'
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`
  return `${Math.floor(ms / 60_000)}m ${Math.round((ms % 60_000) / 1000)}s`
}

function formatCost(cost: number | null): string {
  if (cost == null) return '—'
  return `$${cost.toFixed(2)}`
}

export default function LibraryPanel({ onSelectRun, selectionDisabled, activeRunId, refreshKey }: LibraryPanelProps) {
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [sessionFilter, setSessionFilter] = useState<string>('all')
  const [offset, setOffset] = useState(0)
  const [listing, setListing] = useState<DesignListing | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [retryNonce, setRetryNonce] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    Promise.all([
      listDesigns({
        sessionId: sessionFilter === 'all' ? undefined : sessionFilter,
        limit: PAGE_SIZE,
        offset,
      }),
      // Session titles are cosmetic for the filter — their failure never
      // blocks the run table.
      listSessions().catch(() => null),
    ])
      .then(([designs, sessionsResponse]) => {
        if (cancelled) return
        setListing(designs)
        if (sessionsResponse) setSessions(sessionsResponse.sessions)
      })
      .catch(err => {
        if (cancelled) return
        setError(err instanceof ApiError ? err.message : 'Could not load the design library — try again.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [sessionFilter, offset, refreshKey, retryNonce])

  const runs: RunListItem[] = listing?.runs ?? []
  const total = listing?.total ?? 0

  const rowClickable = !selectionDisabled

  return (
    <div data-testid="library-panel" className="flex flex-col gap-8">
      <section aria-labelledby="library-runs-heading" className="space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h3 id="library-runs-heading" className="text-xl font-bold text-slate-900">
              Design library
            </h3>
            <p className="mt-0.5 text-base text-slate-600">
              Every run is stored as an audit trail — click one to replay it in the tracker and tabs.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <label htmlFor="library-session-filter" className="text-sm font-semibold text-slate-600">
              Session
            </label>
            <select
              id="library-session-filter"
              data-testid="library-session-filter"
              value={sessionFilter}
              onChange={e => {
                setSessionFilter(e.target.value)
                setOffset(0)
              }}
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-base text-slate-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200"
            >
              <option value="all">All sessions</option>
              {sessions.map(s => (
                <option key={s.session_id} value={s.session_id}>
                  {s.title}
                </option>
              ))}
            </select>
          </div>
        </div>

        {error ? (
          <div data-testid="library-error" className="rounded-xl border border-red-200 bg-red-50 p-5">
            <p className="text-base font-semibold text-red-800">Could not load the design library</p>
            <p className="mt-1 text-base text-red-900">{error}</p>
            <button
              type="button"
              onClick={() => setRetryNonce(n => n + 1)}
              className="mt-3 rounded-lg bg-red-700 px-4 py-2 text-base font-semibold text-white hover:bg-red-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-700"
            >
              Try again
            </button>
          </div>
        ) : loading ? (
          <div data-testid="library-loading" className="space-y-2 rounded-xl border border-slate-200 bg-white p-5">
            {[0, 1, 2].map(i => (
              <div key={i} className="h-10 w-full rounded bg-slate-100 motion-safe:animate-pulse" aria-hidden="true" />
            ))}
            <p className="text-base text-slate-500" role="status">
              Loading the design library…
            </p>
          </div>
        ) : total === 0 ? (
          <div
            data-testid="library-empty"
            className="flex min-h-[12rem] flex-col items-center justify-center gap-3 rounded-xl border border-slate-200 bg-slate-50 p-8 text-center"
          >
            <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true" className="text-slate-300">
              <path d="M4 4.5h5l2 2.5h9v12.5H4V4.5Z" />
              <path d="M4 9.5h16" />
            </svg>
            <p className="max-w-md text-lg leading-relaxed text-slate-600">
              {sessionFilter === 'all'
                ? 'Every design you run is stored here — run your first design.'
                : 'No runs in this session yet — pick another session or run a design.'}
            </p>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto rounded-xl border border-slate-200">
              <table data-testid="library-table" className="w-full border-collapse text-left">
                <caption className="sr-only">
                  All design runs, newest first — click a row to replay that run in the tracker and artefact tabs
                </caption>
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 text-sm font-semibold uppercase tracking-wide text-slate-500">
                    <th scope="col" className="px-4 py-3">When</th>
                    <th scope="col" className="px-4 py-3">Prompt</th>
                    <th scope="col" className="px-4 py-3">Parameters</th>
                    <th scope="col" className="px-4 py-3">Verdict</th>
                    <th scope="col" className="px-4 py-3">Cost</th>
                    <th scope="col" className="px-4 py-3">Duration</th>
                    <th scope="col" className="px-4 py-3">
                      <span className="sr-only">Open</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map(run => {
                    const active = run.run_id === activeRunId
                    return (
                      <tr
                        key={run.run_id}
                        data-testid="library-row"
                        data-run-id={run.run_id}
                        onClick={() => {
                          if (rowClickable) onSelectRun(run.run_id)
                        }}
                        title={rowClickable ? 'Load this run into the tracker and tabs' : undefined}
                        className={`border-b border-slate-100 last:border-b-0 ${
                          active ? 'bg-indigo-50' : 'bg-white hover:bg-slate-50'
                        } ${rowClickable ? 'cursor-pointer' : ''}`}
                      >
                        <td className="whitespace-nowrap px-4 py-3 text-base text-slate-700">
                          {formatWhen(run.started_at)}
                        </td>
                        <td className="max-w-[18rem] px-4 py-3">
                          <span className="block truncate text-base text-slate-800" title={run.prompt}>
                            {run.prompt}
                          </span>
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-base text-slate-600">
                          {run.params_summary ?? '—'}
                        </td>
                        <td className="px-4 py-3">
                          <VerdictChip verdict={run.verdict} status={run.status} />
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-base tabular-nums text-slate-700">
                          {formatCost(run.cost_usd)}
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-base tabular-nums text-slate-700">
                          {formatDuration(run.duration_ms)}
                        </td>
                        <td className="px-4 py-3">
                          <button
                            type="button"
                            onClick={e => {
                              e.stopPropagation()
                              onSelectRun(run.run_id)
                            }}
                            disabled={selectionDisabled}
                            aria-label={`Open run: ${run.prompt.slice(0, 60)}`}
                            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-semibold text-slate-700 shadow-sm hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            Open
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3">
              <p data-testid="library-range" className="text-base text-slate-600">
                {offset + 1}–{offset + runs.length} of {total}
              </p>
              <div className="flex items-center gap-2" role="group" aria-label="Library pages">
                <button
                  type="button"
                  data-testid="library-prev"
                  onClick={() => setOffset(o => Math.max(0, o - PAGE_SIZE))}
                  disabled={offset === 0 || loading}
                  className="rounded-md border border-slate-300 bg-white px-4 py-1.5 text-base font-semibold text-slate-700 shadow-sm hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Previous
                </button>
                <button
                  type="button"
                  data-testid="library-next"
                  onClick={() => setOffset(o => o + PAGE_SIZE)}
                  disabled={offset + runs.length >= total || loading}
                  className="rounded-md border border-slate-300 bg-white px-4 py-1.5 text-base font-semibold text-slate-700 shadow-sm hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </section>

      <section aria-labelledby="preset-editor-heading" className="space-y-3">
        <h3 id="preset-editor-heading" className="text-xl font-bold text-slate-900">
          Presets
        </h3>
        <PresetsEditor />
      </section>
    </div>
  )
}
