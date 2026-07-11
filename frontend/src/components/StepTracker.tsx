import { STEP_NAMES, type StepName, type StepState } from '@/lib/types'

interface StepTrackerProps {
  steps: Record<StepName, StepState>
  runId: string | null
  elapsedMs: number
  isRunning: boolean
}

function formatElapsed(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000)
  if (totalSeconds < 60) return `${totalSeconds}s`
  return `${Math.floor(totalSeconds / 60)}m ${totalSeconds % 60}s`
}

function StepIcon({ status }: { status: StepState['status'] }) {
  switch (status) {
    case 'done':
      return (
        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-emerald-600 text-white">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" aria-hidden="true">
            <path d="m5 13 4.5 4.5L19 8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      )
    case 'active':
      return (
        <span className="flex h-9 w-9 items-center justify-center rounded-full border-4 border-indigo-200 bg-white">
          <span className="h-5 w-5 rounded-full border-[3px] border-indigo-600 border-t-transparent motion-safe:animate-spin motion-reduce:bg-indigo-600" />
        </span>
      )
    case 'failed':
      return (
        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-red-600 text-white">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" aria-hidden="true">
            <path d="M6 6l12 12M18 6 6 18" strokeLinecap="round" />
          </svg>
        </span>
      )
    case 'skipped':
      return <span className="flex h-9 w-9 items-center justify-center rounded-full border-2 border-dashed border-slate-300 bg-slate-50" />
    default:
      return <span className="flex h-9 w-9 items-center justify-center rounded-full border-2 border-slate-300 bg-white" />
  }
}

export default function StepTracker({ steps, runId, elapsedMs, isRunning }: StepTrackerProps) {
  return (
    <div data-testid="step-tracker" data-run-id={runId ?? ''} className="flex flex-wrap items-start gap-x-2 gap-y-4">
      <ol className="flex min-w-0 flex-1 flex-wrap items-start gap-x-1 gap-y-3">
        {STEP_NAMES.map((name, i) => {
          const step = steps[name]
          return (
            <li key={name} className="flex items-start">
              <div
                data-testid={`step-${name}`}
                data-status={step.status}
                className="flex min-w-[6.5rem] flex-col items-center gap-1.5 px-1 text-center"
              >
                <StepIcon status={step.status} />
                <span
                  className={`text-base font-semibold ${
                    step.status === 'active'
                      ? 'text-indigo-300 motion-safe:animate-pulse'
                      : step.status === 'done'
                        ? 'text-neutral-100'
                        : step.status === 'failed'
                          ? 'text-red-400'
                          : 'text-neutral-500'
                  }`}
                >
                  {name}
                </span>
                {step.status === 'skipped' && (
                  <span className="rounded-full bg-slate-200 px-2.5 py-0.5 text-xs font-medium text-slate-600">
                    {step.detail || 'Skipped'}
                  </span>
                )}
              </div>
              {i < STEP_NAMES.length - 1 && (
                <span aria-hidden="true" className="mt-4 hidden h-0.5 w-6 shrink-0 rounded bg-slate-300 xl:block" />
              )}
            </li>
          )
        })}
      </ol>
      <div
        data-testid="elapsed-time"
        className={`flex items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-1.5 text-lg font-semibold tabular-nums ${
          isRunning ? 'bg-indigo-50 text-indigo-800' : 'bg-slate-100 text-slate-700'
        }`}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <circle cx="12" cy="13" r="8" />
          <path d="M12 9v4l2.5 2.5M9 2.5h6" strokeLinecap="round" />
        </svg>
        {formatElapsed(elapsedMs)}
      </div>
    </div>
  )
}
