'use client'

import StatusChip from './StatusChip'
import ProjectsStub from './ProjectsStub'
import type { DesignRecordSummary } from './AppShell'

export interface DesignRecordsRailProps {
  records: DesignRecordSummary[]
  /** Effective record id (group root) of the currently open run — highlights the card. */
  activeRecordId: string | null
  /** run_id of the currently open version — highlights the exact version chip. */
  activeRunId: string | null
  onSelectRecord: (id: string) => void
  onNewDesign: () => void
}

/**
 * The left rail: `[+ New design]` action, the Projects `⊘ coming` stub, then
 * the Records list (newest first, as given). This is today's TurnHistory +
 * LibraryPanel merged and elevated into one persistent, first-class surface.
 */
export default function DesignRecordsRail({
  records,
  activeRecordId,
  activeRunId,
  onSelectRecord,
  onNewDesign,
}: DesignRecordsRailProps) {
  return (
    <nav aria-label="Design records" className="flex h-full flex-col gap-4 p-4">
      <button
        type="button"
        onClick={onNewDesign}
        data-testid="new-design"
        className="w-full rounded-lg bg-studio-accent-strong px-4 py-2.5 text-base font-semibold text-white shadow-sm transition-colors hover:bg-studio-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-studio-accent"
      >
        + New design
      </button>

      <ProjectsStub />

      <div className="flex items-center gap-3 px-1 pt-1">
        <span className="text-xs font-semibold uppercase tracking-wider text-studio-text-faint">Records</span>
        <span className="h-px flex-1 bg-studio-border" aria-hidden />
      </div>

      {records.length === 0 ? (
        <p
          data-testid="records-empty"
          className="rounded-lg border border-studio-border bg-studio-panel px-4 py-5 text-base leading-relaxed text-studio-text-dim"
        >
          Every design you run is stored here — run your first design.
        </p>
      ) : (
        <ol className="flex-1 space-y-2 overflow-y-auto" aria-label="Design records list">
          {records.map(record => {
            // Active when the currently open run belongs to THIS record group —
            // matched by group root (record.id), not only the card's run_id.
            const active = record.id === activeRecordId
            const hasVersions = record.versions.length > 1
            const latestLabel = record.versions[0]?.label ?? 'v1'
            return (
              <li
                key={record.id}
                data-testid="record-item"
                data-record-id={record.id}
                data-active={active ? 'true' : 'false'}
                className={`rounded-lg ${active ? 'ring-1 ring-studio-accent' : ''}`}
              >
                <button
                  type="button"
                  data-testid="record-card"
                  data-run-id={record.latestRunId}
                  aria-current={active ? 'true' : undefined}
                  onClick={() => onSelectRecord(record.latestRunId)}
                  className="studio-card block w-full rounded-lg px-3.5 py-3 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-studio-accent"
                >
                  <span className="flex items-start justify-between gap-2">
                    <span className="line-clamp-2 text-base leading-snug text-studio-text">
                      {record.promptSummary}
                    </span>
                    <span className="flex shrink-0 items-center gap-1.5">
                      {hasVersions && (
                        <span
                          data-testid="record-version-badge"
                          title={`${record.versions.length} versions — latest ${latestLabel}`}
                          className="rounded-full border border-studio-border bg-studio-panel-2 px-1.5 py-0.5 text-xs font-semibold tabular-nums text-studio-text-dim"
                        >
                          {latestLabel}
                        </span>
                      )}
                      <StatusChip status={record.status} verdict={record.verdict} />
                    </span>
                  </span>
                  <span className="mt-1.5 flex items-center justify-between gap-2 text-sm text-studio-text-dim">
                    <span>{record.componentLabel}</span>
                    <span className="tabular-nums">${record.cost.toFixed(2)}</span>
                  </span>
                </button>

                {hasVersions && (
                  <div
                    data-testid="record-versions"
                    className="flex flex-wrap items-center gap-1 px-3.5 pb-2.5 pt-1"
                    aria-label="Earlier versions — click to replay"
                  >
                    {record.versions.map((version, index) => {
                      const isActiveVersion = version.runId === activeRunId
                      return (
                        <span key={version.runId} className="flex items-center">
                          {index > 0 && <span aria-hidden className="px-1 text-studio-text-faint">·</span>}
                          <button
                            type="button"
                            data-testid="record-version"
                            data-run-id={version.runId}
                            data-version-label={version.label}
                            title={`Replay ${version.label}`}
                            onClick={() => onSelectRecord(version.runId)}
                            className={`rounded px-1.5 py-0.5 text-xs font-semibold tabular-nums transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-studio-accent ${
                              isActiveVersion
                                ? 'bg-studio-accent-strong text-white'
                                : 'text-studio-text-dim hover:bg-studio-panel-2 hover:text-studio-text'
                            }`}
                          >
                            {version.label}
                          </button>
                        </span>
                      )
                    })}
                  </div>
                )}
              </li>
            )
          })}
        </ol>
      )}
    </nav>
  )
}
