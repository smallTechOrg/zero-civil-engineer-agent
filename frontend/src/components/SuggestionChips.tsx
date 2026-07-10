'use client'

interface SuggestionChipsProps {
  suggestions: string[]
  onPick: (text: string) => void
  disabled: boolean
}

/**
 * Post-run refinement suggestions (spec/capabilities/session-refinement.md):
 * clicking a chip fills the prompt box — the user still presses Refine to
 * submit. No suggestions → render nothing (suggestion failure is
 * invisible-degrading, never a placeholder).
 */
export default function SuggestionChips({ suggestions, onPick, disabled }: SuggestionChipsProps) {
  if (suggestions.length === 0) return null
  return (
    <div data-testid="suggestion-chips" className="space-y-2" aria-label="Refinement suggestions">
      <p className="text-sm font-semibold uppercase tracking-wide text-slate-500">Try a refinement</p>
      <div className="flex flex-wrap gap-2">
        {suggestions.map(text => (
          <button
            key={text}
            type="button"
            data-testid="suggestion-chip"
            onClick={() => onPick(text)}
            disabled={disabled}
            title="Fills the prompt box — press Refine to run it"
            className="rounded-full border border-indigo-200 bg-indigo-50 px-3.5 py-1.5 text-left text-sm font-medium leading-snug text-indigo-900 transition-colors hover:border-indigo-400 hover:bg-indigo-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {text}
          </button>
        ))}
      </div>
    </div>
  )
}
