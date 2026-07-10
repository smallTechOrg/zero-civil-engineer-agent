'use client'

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { ComplianceData, ComplianceSeverity, Verdict } from '@/lib/types'

interface ProofCheckPanelProps {
  compliance: ComplianceData | null
  memoMarkdown: string | null
  bmdSvg: string | null
  sfdSvg: string | null
  verdict: Verdict | null
  isRunning: boolean
  /** True while the run is mid-Review — the proof-check is executing. */
  reviewActive: boolean
  runFailed: boolean
  hasRun: boolean
}

const SEVERITY_CHIP: Record<ComplianceSeverity, { label: string; className: string }> = {
  PASS: { label: 'PASS', className: 'bg-emerald-100 text-emerald-800' },
  OBSERVATION: { label: 'Observation', className: 'bg-amber-100 text-amber-900' },
  NON_CONFORMITY_MINOR: { label: 'Non-conformity · minor', className: 'border border-red-300 bg-red-50 text-red-800' },
  NON_CONFORMITY_MAJOR: { label: 'NON-CONFORMITY · MAJOR', className: 'bg-red-600 text-white' },
}

const SEVERITY_ROW: Record<ComplianceSeverity, string> = {
  PASS: 'border-l-4 border-emerald-200',
  OBSERVATION: 'border-l-4 border-amber-400 bg-amber-50',
  NON_CONFORMITY_MINOR: 'border-l-4 border-red-300 bg-red-50',
  NON_CONFORMITY_MAJOR: 'border-l-4 border-red-600 bg-red-100',
}

function SeverityChip({ severity }: { severity: ComplianceSeverity }) {
  const chip = SEVERITY_CHIP[severity] ?? SEVERITY_CHIP.OBSERVATION
  return (
    <span className={`inline-block whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-bold ${chip.className}`}>
      {chip.label}
    </span>
  )
}

function BlockSkeleton({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-slate-200 bg-white p-6">
      <div className="h-6 w-2/3 max-w-md rounded-lg bg-slate-100 motion-safe:animate-pulse" aria-hidden="true" />
      <div className="h-6 w-full max-w-lg rounded-lg bg-slate-100 motion-safe:animate-pulse" aria-hidden="true" />
      <p className="text-base text-slate-500">{label}</p>
    </div>
  )
}

function VerdictBanner({ verdict }: { verdict: Verdict }) {
  const approved = verdict === 'recommended_for_approval'
  return (
    <div
      data-testid="verdict-banner"
      data-verdict={verdict}
      role="status"
      className={`rounded-xl border-2 px-5 py-4 ${
        approved ? 'border-emerald-500 bg-emerald-50' : 'border-red-600 bg-red-50'
      }`}
    >
      <p className={`text-2xl font-bold ${approved ? 'text-emerald-800' : 'text-red-800'}`}>
        {approved ? 'Recommended for approval' : 'Return for revision'}
      </p>
      <p className={`mt-1 text-base ${approved ? 'text-emerald-900' : 'text-red-900'}`}>
        Automatic proof-check verdict — 12-item IRS checklist with an independent FE cross-check.
      </p>
    </div>
  )
}

function ComplianceMatrix({ compliance }: { compliance: ComplianceData }) {
  return (
    <section aria-label="Compliance matrix" className="overflow-hidden rounded-xl border border-slate-200">
      <h3 className="border-b border-slate-200 bg-slate-100 px-4 py-2.5 text-base font-bold text-slate-800">
        Compliance matrix
      </h3>
      <div className="overflow-x-auto">
        <table data-testid="compliance-matrix" className="w-full border-collapse text-left">
          <thead>
            <tr className="border-b border-slate-200 text-sm font-semibold uppercase tracking-wide text-slate-500">
              <th scope="col" className="px-3 py-2">
                Clause
              </th>
              <th scope="col" className="px-3 py-2">
                Requirement
              </th>
              <th scope="col" className="px-3 py-2">
                Computed
              </th>
              <th scope="col" className="px-3 py-2">
                Limit
              </th>
              <th scope="col" className="px-3 py-2">
                Status
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {compliance.items.map(item => (
              <tr
                key={item.item}
                data-testid="compliance-row"
                data-severity={item.severity}
                className={SEVERITY_ROW[item.severity] ?? ''}
              >
                <td className="whitespace-nowrap px-3 py-2.5 align-top text-sm text-slate-600">{item.clause}</td>
                <td className="px-3 py-2.5 align-top">
                  <span className="block text-base font-semibold leading-snug text-slate-900">
                    {item.item}. {item.title}
                  </span>
                  <span className="mt-0.5 block text-sm leading-snug text-slate-600">{item.requirement}</span>
                  {item.detail && <span className="mt-0.5 block text-sm leading-snug text-slate-500">{item.detail}</span>}
                </td>
                <td className="px-3 py-2.5 align-top font-mono text-sm text-slate-900">{item.computed}</td>
                <td className="px-3 py-2.5 align-top font-mono text-sm text-slate-700">{item.limit}</td>
                <td className="px-3 py-2.5 align-top">
                  <SeverityChip severity={item.severity} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function Diagrams({
  bmdSvg,
  sfdSvg,
  feAgreementPct,
}: {
  bmdSvg: string | null
  sfdSvg: string | null
  feAgreementPct: number | null
}) {
  const host = 'rounded-lg border border-slate-200 bg-white p-2 [&_svg]:h-auto [&_svg]:w-full [&_svg]:max-w-full'
  return (
    <section aria-label="FE cross-check diagrams" className="space-y-3">
      <h3 className="text-base font-bold text-slate-800">Independent FE cross-check</h3>
      {feAgreementPct != null && (
        <p data-testid="fe-agreement" className="text-base text-slate-700">
          Independent FE re-solve agrees within {Number(feAgreementPct.toPrecision(3))}% of the closed-form analysis.
        </p>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        {bmdSvg && (
          <figure data-testid="bmd-svg" className="space-y-1.5">
            {/* Trusted markup: rendered server-side by our own FE cross-check. */}
            <div className={host} dangerouslySetInnerHTML={{ __html: bmdSvg }} />
            <figcaption className="text-sm text-slate-600">Bending-moment diagram (independent FE re-solve)</figcaption>
          </figure>
        )}
        {sfdSvg && (
          <figure data-testid="sfd-svg" className="space-y-1.5">
            {/* Trusted markup: rendered server-side by our own FE cross-check. */}
            <div className={host} dangerouslySetInnerHTML={{ __html: sfdSvg }} />
            <figcaption className="text-sm text-slate-600">Shear-force diagram (independent FE re-solve)</figcaption>
          </figure>
        )}
      </div>
    </section>
  )
}

export default function ProofCheckPanel({
  compliance,
  memoMarkdown,
  bmdSvg,
  sfdSvg,
  verdict,
  isRunning,
  reviewActive,
  runFailed,
  hasRun,
}: ProofCheckPanelProps) {
  const hasAnything = !!(verdict || compliance || memoMarkdown || bmdSvg || sfdSvg)

  if (!hasAnything) {
    if (isRunning) {
      return (
        <div
          data-testid="proof-check-loading"
          className="flex h-full min-h-[24rem] flex-col items-center justify-center gap-4 rounded-xl border border-slate-200 bg-white p-8"
        >
          <div className="w-full max-w-xl space-y-3" aria-hidden="true">
            <div className="h-10 w-full rounded-lg bg-slate-100 motion-safe:animate-pulse" />
            <div className="h-5 w-5/6 rounded-lg bg-slate-100 motion-safe:animate-pulse" />
            <div className="h-5 w-full rounded-lg bg-slate-100 motion-safe:animate-pulse" />
          </div>
          <p className="text-lg text-slate-600">
            {reviewActive
              ? 'Running the independent proof-check…'
              : 'The proof-check runs automatically once the design and drawing are complete.'}
          </p>
        </div>
      )
    }
    if (runFailed) {
      return (
        <div className="flex h-full min-h-[24rem] items-center justify-center rounded-xl border border-slate-200 bg-white p-8">
          <p className="max-w-md text-center text-lg leading-relaxed text-slate-600">
            The run failed before the proof-check completed — the details are in the red banner above. Fix the request
            and try again.
          </p>
        </div>
      )
    }
    return (
      <div className="flex h-full min-h-[24rem] items-center justify-center rounded-xl border border-slate-200 bg-white p-8">
        <p className="max-w-md text-center text-lg leading-relaxed text-slate-600">
          {hasRun
            ? 'This run has no proof-check — select a completed design in the session panel, or run a new design.'
            : 'Every completed design is proof-checked automatically — verdict, severity-graded memo, 12-item compliance matrix and independent FE cross-check appear here.'}
        </p>
      </div>
    )
  }

  return (
    <div data-testid="proof-check-content" className="space-y-5">
      {verdict ? (
        <VerdictBanner verdict={verdict} />
      ) : (
        isRunning && <BlockSkeleton label="Computing the verdict…" />
      )}

      {memoMarkdown ? (
        <article
          data-testid="memo"
          aria-label="Proof-check memo"
          className="rounded-xl border border-slate-200 bg-white p-5 text-base leading-relaxed text-slate-800 [&_code]:font-mono [&_code]:text-sm [&_h1]:text-2xl [&_h1]:font-bold [&_h2]:mt-4 [&_h2]:text-xl [&_h2]:font-bold [&_h3]:mt-3 [&_h3]:text-lg [&_h3]:font-semibold [&_li]:mt-1 [&_ol]:mt-2 [&_ol]:list-decimal [&_ol]:pl-6 [&_p]:mt-2 [&_strong]:font-semibold [&_table]:mt-3 [&_table]:w-full [&_table]:border-collapse [&_td]:border [&_td]:border-slate-300 [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_th]:border-slate-300 [&_th]:px-2 [&_th]:py-1 [&_ul]:mt-2 [&_ul]:list-disc [&_ul]:pl-6"
        >
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{memoMarkdown}</ReactMarkdown>
        </article>
      ) : (
        isRunning && <BlockSkeleton label="Drafting the proof-check memo…" />
      )}

      {compliance ? (
        <ComplianceMatrix compliance={compliance} />
      ) : (
        isRunning && <BlockSkeleton label="Evaluating the 12-item checklist…" />
      )}

      {bmdSvg || sfdSvg ? (
        <Diagrams bmdSvg={bmdSvg} sfdSvg={sfdSvg} feAgreementPct={compliance?.fe_agreement_pct ?? null} />
      ) : (
        isRunning && <BlockSkeleton label="Re-solving the frame with the independent FE model…" />
      )}
    </div>
  )
}
