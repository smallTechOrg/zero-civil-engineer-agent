interface TokenCostBadgeProps {
  runTokens: number
  runCostUsd: number
  sessionCostUsd: number
}

function formatTokenCount(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return `${n}`
}

export default function TokenCostBadge({ runTokens, runCostUsd, sessionCostUsd }: TokenCostBadgeProps) {
  return (
    <span
      data-testid="token-cost-badge"
      title="Tokens and cost for the current run, plus the session running total"
      className="rounded-lg bg-slate-800 px-3.5 py-1.5 text-base font-medium tabular-nums text-slate-100"
    >
      {formatTokenCount(runTokens)} tok · ${runCostUsd.toFixed(2)} run · ${sessionCostUsd.toFixed(2)} session
    </span>
  )
}
