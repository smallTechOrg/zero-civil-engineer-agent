'use client'

export type StageId = 'overview' | 'define' | 'design' | 'review' | 'simulate' | 'test' | 'approve'

/** Live-run progress for the three functional stages (never forces a switch). */
export type StageProgress = 'pending' | 'active' | 'done'

interface StageDef {
  id: StageId
  numeral: string
  label: string
  /** true = visibly-coming, non-functional stub stage. */
  coming: boolean
}

const STAGES: StageDef[] = [
  { id: 'overview', numeral: '', label: 'Overview', coming: false },
  { id: 'define', numeral: '①', label: 'Define', coming: false },
  { id: 'design', numeral: '②', label: 'Design', coming: false },
  { id: 'review', numeral: '③', label: 'Review', coming: false },
  { id: 'simulate', numeral: '④', label: 'Simulate', coming: true },
  { id: 'test', numeral: '⑤', label: 'Test', coming: true },
  { id: 'approve', numeral: '⑥', label: 'Approve', coming: true },
]

interface StageRailProps {
  active: StageId
  onSelect: (id: StageId) => void
  /** Live progress for define / design / review — lights the rail without switching. */
  progress: Record<'define' | 'design' | 'review', StageProgress>
}

function progressFor(id: StageId, progress: StageRailProps['progress']): StageProgress | null {
  if (id === 'define' || id === 'design' || id === 'review') return progress[id]
  return null
}

export default function StageRail({ active, onSelect, progress }: StageRailProps) {
  return (
    <nav
      aria-label="Design lifecycle stages"
      data-testid="stage-rail"
      className="flex flex-wrap items-stretch gap-1.5 rounded-xl border border-neutral-800 bg-neutral-900/70 p-1.5"
    >
      {STAGES.map(stage => {
        const isActive = stage.id === active
        const prog = progressFor(stage.id, progress)
        return (
          <button
            key={stage.id}
            type="button"
            data-testid={`stage-tab-${stage.id}`}
            data-active={isActive ? 'true' : 'false'}
            data-coming={stage.coming ? 'true' : 'false'}
            data-progress={prog ?? ''}
            aria-current={isActive ? 'step' : undefined}
            onClick={() => onSelect(stage.id)}
            className={`group relative inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-semibold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-400 ${
              isActive
                ? 'bg-indigo-600 text-white shadow-sm'
                : stage.coming
                  ? 'text-neutral-500 hover:bg-neutral-800/60'
                  : 'text-neutral-300 hover:bg-neutral-800 hover:text-neutral-100'
            }`}
          >
            {stage.numeral && (
              <span className={`text-base leading-none ${isActive ? 'text-white' : 'text-neutral-500'}`}>
                {stage.numeral}
              </span>
            )}
            <span>{stage.label}</span>
            {/* Live progress dot for the functional stages. */}
            {prog === 'active' && (
              <span
                aria-hidden="true"
                className="h-2 w-2 animate-pulse rounded-full bg-amber-400"
                title="In progress"
              />
            )}
            {prog === 'done' && (
              <span aria-hidden="true" className="text-emerald-400" title="Complete">
                ✓
              </span>
            )}
            {/* Coming-stage marker — clearly a stub, never a bug. */}
            {stage.coming && (
              <span
                aria-hidden="true"
                title="Coming in a later release"
                className="rounded-full border border-dashed border-neutral-600 px-1.5 text-[11px] font-medium text-neutral-500"
              >
                ⊘
              </span>
            )}
          </button>
        )
      })}
    </nav>
  )
}
