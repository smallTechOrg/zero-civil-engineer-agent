'use client'

import { useState } from 'react'
import DesignRecordsRail from './DesignRecordsRail'

export type TokenCostState = {
  runTokens: number
  runCost: number // this run
  sessionTokens: number
  sessionCost: number // session/day running total
}

export type DesignRecordSummary = {
  id: string // run_id
  promptSummary: string // short prompt text
  componentLabel: string // e.g. "Box Culvert"
  cost: number // this design's cost (USD)
  status: string // raw backend run status
  verdict: string | null // raw backend verdict or null
}

export type AppShellProps = {
  tokens: TokenCostState
  records: DesignRecordSummary[]
  activeRecordId: string | null
  onSelectRecord: (id: string) => void
  onNewDesign: () => void
  children: React.ReactNode // the workspace (StageRail + active stage content)
}

function formatTokenCount(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return `${n}`
}

/** Top-bar token/cost badge: `12.4k tok · $0.19 run · $0.83 session`. */
function TokenCostBadge({ tokens }: { tokens: TokenCostState }) {
  return (
    <span
      data-testid="token-cost-badge"
      title="Tokens and cost for the current run, plus the session running total"
      className="rounded-lg border border-studio-border bg-studio-panel-2 px-3.5 py-1.5 text-base font-medium tabular-nums text-studio-text"
    >
      {formatTokenCount(tokens.runTokens)} tok · ${tokens.runCost.toFixed(2)} run · ${tokens.sessionCost.toFixed(2)}{' '}
      session
    </span>
  )
}

/**
 * The global shell: a persistent TOP BAR (wordmark + token/cost badge), a
 * collapsible LEFT RAIL (DesignRecordsRail), and the WORKSPACE slot (`children`,
 * rendered by page.tsx). The dark-studio base bg/text live on html/body
 * (layout.tsx + globals.css) so both slices share the palette.
 */
export default function AppShell({
  tokens,
  records,
  activeRecordId,
  onSelectRecord,
  onNewDesign,
  children,
}: AppShellProps) {
  const [railOpen, setRailOpen] = useState(true)

  return (
    <div className="flex min-h-screen flex-col bg-studio-base text-studio-text">
      <header className="sticky top-0 z-20 border-b border-studio-border bg-studio-panel/95 backdrop-blur">
        <div className="flex items-center gap-3 px-4 py-3">
          <button
            type="button"
            onClick={() => setRailOpen(o => !o)}
            aria-label={railOpen ? 'Collapse design records' : 'Expand design records'}
            aria-expanded={railOpen}
            className="rounded-md border border-studio-border px-2.5 py-1.5 text-studio-text-dim transition-colors hover:border-studio-border-strong hover:text-studio-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-studio-accent"
          >
            <span aria-hidden>☰</span>
          </button>
          <span className="flex items-center gap-2">
            <span aria-hidden className="text-lg text-studio-accent">
              ◈
            </span>
            <span className="text-lg font-semibold tracking-tight text-studio-text">
              IR Engineering Design &amp; Proof-Check Platform
            </span>
          </span>
          <span className="ml-auto">
            <TokenCostBadge tokens={tokens} />
          </span>
        </div>
        <div className="h-px w-full bg-gradient-to-r from-studio-accent/60 via-studio-accent/10 to-transparent" aria-hidden />
      </header>

      <div className="flex flex-1 overflow-hidden">
        {railOpen && (
          <aside
            data-testid="design-records-rail"
            className="w-80 shrink-0 overflow-y-auto border-r border-studio-border bg-studio-panel"
          >
            <DesignRecordsRail
              records={records}
              activeRecordId={activeRecordId}
              onSelectRecord={onSelectRecord}
              onNewDesign={onNewDesign}
            />
          </aside>
        )}
        <main data-testid="workspace" className="flex-1 overflow-y-auto bg-studio-base">
          {children}
        </main>
      </div>
    </div>
  )
}
