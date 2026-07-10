'use client'

interface DetectedTypeChipProps {
  /** Human-readable name of the auto-detected component (null = not yet classified). */
  displayName: string | null
  /** Enables the "switch" affordance — hidden while a run is active. */
  onSwitch: () => void
  disabled: boolean
}

/**
 * Auto-detect surfacing (spec/ui.md → "Auto-detect surfacing"). When no
 * component was explicitly picked, after the `understand` step the classified
 * type shows as a chip above the tabs: "Detected: Retaining Wall — switch".
 * Switching lets the user re-pick and re-run — making both selection paths
 * (auto + explicit) visible and non-magical.
 */
export default function DetectedTypeChip({ displayName, onSwitch, disabled }: DetectedTypeChipProps) {
  if (!displayName) return null
  return (
    <div
      data-testid="detected-type-chip"
      data-detected={displayName}
      className="inline-flex items-center gap-2 self-start rounded-full border border-indigo-200 bg-indigo-50 px-3.5 py-1.5 text-sm font-medium text-indigo-900"
    >
      <span className="inline-block h-2 w-2 rounded-full bg-indigo-500" aria-hidden />
      <span>
        Detected: <span className="font-semibold">{displayName}</span>
      </span>
      <button
        type="button"
        data-testid="detected-type-switch"
        onClick={onSwitch}
        disabled={disabled}
        className="rounded-full px-2 py-0.5 text-sm font-semibold text-indigo-700 underline decoration-indigo-300 underline-offset-2 hover:text-indigo-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 disabled:cursor-not-allowed disabled:opacity-50"
      >
        switch
      </button>
    </div>
  )
}
