'use client'

import { useState } from 'react'
import DesignRecordsRail from './DesignRecordsRail'

export type TokenCostState = {
  runTokens: number
  runCost: number // this run
  sessionTokens: number
  sessionCost: number // session/day running total
}

export type DesignRecordVersion = {
  runId: string // this version's run_id
  label: string // "v1", "v2", … (oldest = v1)
  status: string // raw backend run status
  verdict: string | null // raw backend verdict or null
}

export type DesignRecordSummary = {
  id: string // effective record id (root_run_id ?? run_id) — grouping + active key
  latestRunId: string // newest version's run_id — what a card click opens
  promptSummary: string // latest version's prompt
  componentLabel: string // e.g. "Box Culvert" (latest version)
  cost: number // latest version's cost (USD)
  status: string // latest version's raw backend run status
  verdict: string | null // latest version's raw backend verdict or null
  versions: DesignRecordVersion[] // every version, NEWEST first
}

export type AppShellProps = {
  tokens: TokenCostState
  records: DesignRecordSummary[]
  activeRecordId: string | null // group root of the open run — highlights the card
  activeRunId: string | null // the open version's run_id — highlights the version chip
  onSelectRecord: (id: string) => void
  onNewDesign: () => void
  children: React.ReactNode // the workspace (StageRail + active stage content)
}

function formatTokenCount(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return `${n}`
}

/**
 * Zer0 Rail Agent brand mark — rail-based: two rails receding to a vanishing
 * point over sleepers, inside a rounded badge. Inline SVG so it always renders.
 */
function RailAgentLogo() {
  return (
    <span
      aria-hidden
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-studio-panel-2 ring-1 ring-studio-border"
    >
      <svg viewBox="0 0 32 32" className="h-6 w-6 text-studio-accent" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
        {/* rails converging upward (perspective) */}
        <path d="M10.5 28 L14 5.5" />
        <path d="M21.5 28 L18 5.5" />
        {/* sleepers / ties, foreshortened toward the vanishing point */}
        <path d="M8.6 26.5 L23.4 26.5" />
        <path d="M10 21 L22 21" />
        <path d="M11.2 16 L20.8 16" />
        <path d="M12.3 11.2 L19.7 11.2" />
        <path d="M13.2 7 L18.8 7" />
      </svg>
    </span>
  )
}

/**
 * smallTech mark — a compact monogram beside the name. Inline SVG (renders with
 * no external asset). Swap the glyph for the official mark when available.
 */
function SmallTechLogo() {
  return (
    <svg aria-hidden viewBox="0 0 20 20" className="h-4 w-4 shrink-0 text-studio-text-dim">
      <rect x="1" y="1" width="18" height="18" rx="5" fill="currentColor" />
      <text
        x="10"
        y="14.2"
        textAnchor="middle"
        fontSize="10"
        fontWeight="700"
        fontFamily="ui-sans-serif, system-ui, sans-serif"
        fill="#0b0b0d"
      >
        sT
      </text>
    </svg>
  )
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
  activeRunId,
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
          <span className="flex items-center gap-2.5">
            <RailAgentLogo />
            <span className="flex items-baseline gap-2.5">
              <span className="text-lg font-semibold tracking-tight text-studio-text">Zer0 Rail Agent</span>
              <a
                href="https://smalltech.in"
                target="_blank"
                rel="noopener noreferrer"
                title="smalltech.in"
                className="flex items-center gap-1.5 text-xs font-medium text-studio-text-faint transition-colors hover:text-studio-text-dim"
              >
                <span className="text-studio-text-faint">by</span>
                <SmallTechLogo />
                <span>smallTech</span>
              </a>
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
              activeRunId={activeRunId}
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
