'use client'

import StatusChip from './StatusChip'
import ProjectsStub from './ProjectsStub'
import type { DesignRecordSummary } from './AppShell'

export interface DesignRecordsRailProps {
  records: DesignRecordSummary[]
  activeRecordId: string | null
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
            const active = record.id === activeRecordId
            return (
              <li key={record.id}>
                <button
                  type="button"
                  data-testid="record-item"
                  data-run-id={record.id}
                  data-active={active ? 'true' : 'false'}
                  aria-current={active ? 'true' : undefined}
                  onClick={() => onSelectRecord(record.id)}
                  className="studio-card block w-full rounded-lg px-3.5 py-3 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-studio-accent"
                >
                  <span className="flex items-start justify-between gap-2">
                    <span className="line-clamp-2 text-base leading-snug text-studio-text">
                      {record.promptSummary}
                    </span>
                    <StatusChip status={record.status} verdict={record.verdict} />
                  </span>
                  <span className="mt-1.5 flex items-center justify-between gap-2 text-sm text-studio-text-dim">
                    <span>{record.componentLabel}</span>
                    <span className="tabular-nums">${record.cost.toFixed(2)}</span>
                  </span>
                </button>
              </li>
            )
          })}
        </ol>
      )}
    </nav>
  )
}
