import { DesignStatusChip, type DesignChipTone } from '@/lib/types'

interface StatusChipProps {
  status: string
  verdict: string | null
}

const TONE_CLASS: Record<DesignChipTone, string> = {
  draft: 'border-studio-border-strong bg-studio-panel-2 text-studio-text-dim',
  reviewed: 'border-transparent bg-emerald-500/15 text-emerald-300',
  needs_revision: 'border-transparent bg-red-500/15 text-red-300',
}

/**
 * Status-at-a-glance chip for a design record. The Draft / Reviewed ✓ /
 * Needs revision ✗ derivation lives in `DesignStatusChip` (lib/types); this
 * component only renders it.
 */
export default function StatusChip({ status, verdict }: StatusChipProps) {
  const { tone, label } = DesignStatusChip(status, verdict)
  return (
    <span
      data-testid="status-chip"
      data-tone={tone}
      className={`inline-flex shrink-0 items-center whitespace-nowrap rounded-full border px-2.5 py-0.5 text-sm font-semibold ${TONE_CLASS[tone]}`}
    >
      {label}
    </span>
  )
}
