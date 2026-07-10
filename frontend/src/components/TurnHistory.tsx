import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { RunListItem, RunStatus } from '@/lib/types'

export interface TurnDetail {
  scopeMessage: string | null
  clarificationQuestion: string | null
}

interface TurnHistoryProps {
  turns: RunListItem[]
  details: Record<string, TurnDetail>
  selectedRunId: string | null
  onSelect: (runId: string) => void
  selectionDisabled: boolean
}

const CHIP: Record<RunStatus, { label: string; className: string }> = {
  running: { label: 'Running', className: 'bg-indigo-100 text-indigo-800 motion-safe:animate-pulse' },
  completed: { label: 'Completed', className: 'bg-emerald-100 text-emerald-800' },
  needs_input: { label: 'Needs input', className: 'bg-amber-100 text-amber-900' },
  out_of_scope: { label: 'Out of scope', className: 'bg-sky-100 text-sky-900' },
  failed: { label: 'Failed', className: 'bg-red-100 text-red-800' },
}

export default function TurnHistory({ turns, details, selectedRunId, onSelect, selectionDisabled }: TurnHistoryProps) {
  if (turns.length === 0) {
    return (
      <p className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-5 text-base leading-relaxed text-slate-600">
        Your design turns appear here — each prompt with its outcome. Run your first design to start the session.
      </p>
    )
  }

  return (
    <ol className="space-y-2" aria-label="Turn history">
      {turns.map(turn => {
        const chip = CHIP[turn.status] ?? CHIP.failed
        const detail = details[turn.run_id]
        const selected = turn.run_id === selectedRunId
        return (
          <li
            key={turn.run_id}
            data-testid="turn-item"
            data-run-id={turn.run_id}
            className={`rounded-lg border transition-colors ${
              selected ? 'border-indigo-400 bg-indigo-50' : 'border-slate-200 bg-white hover:border-indigo-300'
            }`}
          >
            <button
              type="button"
              onClick={() => onSelect(turn.run_id)}
              disabled={selectionDisabled}
              aria-current={selected ? 'true' : undefined}
              title="Load this run into the tracker and tabs"
              className="w-full rounded-lg px-3.5 py-3 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 disabled:cursor-not-allowed"
            >
              <span className="flex items-start justify-between gap-2">
                <span className="line-clamp-2 text-base leading-snug text-slate-800">{turn.prompt}</span>
                <span
                  className={`shrink-0 whitespace-nowrap rounded-full px-2.5 py-0.5 text-sm font-semibold ${chip.className}`}
                >
                  {chip.label}
                </span>
              </span>
              {turn.params_summary && <span className="mt-1 block text-sm text-slate-500">{turn.params_summary}</span>}
            </button>
            {detail?.scopeMessage && turn.status === 'out_of_scope' && (
              <div
                data-testid="scope-statement"
                className="mx-3.5 mb-3 rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-base leading-relaxed text-sky-950 [&_p]:m-0"
              >
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{detail.scopeMessage}</ReactMarkdown>
              </div>
            )}
            {detail?.clarificationQuestion && turn.status === 'needs_input' && (
              <p className="mx-3.5 mb-3 text-base italic leading-relaxed text-amber-900">
                “{detail.clarificationQuestion}”
              </p>
            )}
          </li>
        )
      })}
    </ol>
  )
}
