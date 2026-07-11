'use client'

import type { ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { ComplianceData, ComplianceItem, ComplianceSeverity, Verdict } from '@/lib/types'

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
  PASS: { label: 'PASS', className: 'border border-emerald-800/60 bg-emerald-950/50 text-emerald-300' },
  OBSERVATION: { label: 'Observation', className: 'border border-amber-800/60 bg-amber-950/40 text-amber-300' },
  NON_CONFORMITY_MINOR: { label: 'Non-conformity · minor', className: 'border border-red-800/60 bg-red-950/40 text-red-300' },
  NON_CONFORMITY_MAJOR: { label: 'NON-CONFORMITY · MAJOR', className: 'bg-red-600 text-white' },
}

const SEVERITY_ROW: Record<ComplianceSeverity, string> = {
  PASS: 'border-l-4 border-emerald-800/60',
  OBSERVATION: 'border-l-4 border-amber-500 bg-amber-950/20',
  NON_CONFORMITY_MINOR: 'border-l-4 border-red-700 bg-red-950/20',
  NON_CONFORMITY_MAJOR: 'border-l-4 border-red-500 bg-red-950/40',
}

function SeverityChip({ severity }: { severity: ComplianceSeverity }) {
  const chip = SEVERITY_CHIP[severity] ?? SEVERITY_CHIP.OBSERVATION
  return (
    <span className={`inline-block whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-bold ${chip.className}`}>
      {chip.label}
    </span>
  )
}

/** A numbered report section with a consistent heading rule. */
function ReportSection({
  numeral,
  title,
  aside,
  children,
}: {
  numeral: string
  title: string
  aside?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-neutral-800 pb-1.5">
        <h3 className="flex items-baseline gap-2 text-base font-bold text-neutral-100">
          <span className="font-mono text-sm text-neutral-500">{numeral}</span>
          {title}
        </h3>
        {aside}
      </div>
      {children}
    </section>
  )
}

function BlockSkeleton({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-neutral-800 bg-neutral-900 p-6">
      <div className="h-6 w-2/3 max-w-md rounded-lg bg-neutral-800 motion-safe:animate-pulse" aria-hidden="true" />
      <div className="h-6 w-full max-w-lg rounded-lg bg-neutral-800 motion-safe:animate-pulse" aria-hidden="true" />
      <p className="text-base text-neutral-400">{label}</p>
    </div>
  )
}

/** Report masthead — frames the whole panel as a formal proof-check document. */
function ReportHeader({ verdict, compliance }: { verdict: Verdict | null; compliance: ComplianceData | null }) {
  const approved = verdict === 'recommended_for_approval'
  const feAgreement = compliance?.fe_agreement_pct ?? null
  return (
    <header className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-neutral-500">Engineering proof-check report</p>
          <h2 className="mt-0.5 text-xl font-bold text-neutral-100">Independent design verification</h2>
        </div>
        <p className="text-sm text-neutral-500">
          IRS checklist · independent FE cross-check
          {feAgreement != null && <> · FE agreement {Number(feAgreement.toPrecision(3))}%</>}
        </p>
      </div>
      {verdict && (
        <div
          data-testid="verdict-banner"
          data-verdict={verdict}
          role="status"
          className={`flex flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-xl border-2 px-5 py-4 ${
            approved ? 'border-emerald-500 bg-emerald-950/40' : 'border-red-600 bg-red-950/40'
          }`}
        >
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-neutral-400">Verdict</p>
            <p className={`text-2xl font-bold ${approved ? 'text-emerald-300' : 'text-red-300'}`}>
              {approved ? 'Recommended for approval' : 'Return for revision'}
            </p>
          </div>
          <p className={`max-w-sm text-sm ${approved ? 'text-emerald-200/80' : 'text-red-200/80'}`}>
            {approved
              ? 'All checklist items cleared, with an independent FE cross-check confirming the closed-form analysis.'
              : 'One or more non-conformities were found — see the compliance checklist below.'}
          </p>
        </div>
      )}
    </header>
  )
}

/** Compact "10 pass · 1 observation · 1 non-conformity" tally for the checklist heading. */
function ChecklistTally({ items }: { items: ComplianceItem[] }) {
  const pass = items.filter(i => i.severity === 'PASS').length
  const obs = items.filter(i => i.severity === 'OBSERVATION').length
  const nc = items.filter(i => i.severity === 'NON_CONFORMITY_MINOR' || i.severity === 'NON_CONFORMITY_MAJOR').length
  return (
    <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm font-medium">
      <span className="text-emerald-300">{pass} pass</span>
      {obs > 0 && <span className="text-amber-300">· {obs} observation{obs === 1 ? '' : 's'}</span>}
      {nc > 0 && <span className="text-red-300">· {nc} non-conformit{nc === 1 ? 'y' : 'ies'}</span>}
      <span className="text-neutral-500">· {items.length} checks</span>
    </p>
  )
}

function ComplianceMatrix({ compliance }: { compliance: ComplianceData }) {
  return (
    <div className="overflow-hidden rounded-xl border border-neutral-800 bg-neutral-950">
      {/* table-fixed + colgroup: columns keep sane widths and cells WRAP instead of
          forcing a horizontal scroll — reads as a report table at any panel width. */}
      <table data-testid="compliance-matrix" className="w-full table-fixed border-collapse text-left">
        <colgroup>
          <col className="w-[28%]" />
          <col className="w-[38%]" />
          <col className="w-[20%]" />
          <col className="w-[14%]" />
        </colgroup>
        <thead>
          <tr className="border-b border-neutral-800 bg-neutral-900 text-xs font-semibold uppercase tracking-wide text-neutral-400">
            <th scope="col" className="px-3 py-2">Clause</th>
            <th scope="col" className="px-3 py-2">Check &amp; requirement</th>
            <th scope="col" className="px-3 py-2">Result</th>
            <th scope="col" className="px-3 py-2">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-neutral-800">
          {compliance.items.map(item => (
            <tr
              key={item.item}
              data-testid="compliance-row"
              data-severity={item.severity}
              className={SEVERITY_ROW[item.severity] ?? ''}
            >
              <td className="break-words px-3 py-3 align-top text-sm text-neutral-400">{item.clause}</td>
              <td className="px-3 py-3 align-top">
                <span className="block text-sm font-semibold leading-snug text-neutral-100">
                  {item.item}. {item.title}
                </span>
                <span className="mt-1 block break-words text-sm leading-snug text-neutral-300">{item.requirement}</span>
                {item.detail && (
                  <span className="mt-1 block break-words text-xs leading-snug text-neutral-500">{item.detail}</span>
                )}
              </td>
              <td className="px-3 py-3 align-top">
                <span className="block break-words font-mono text-sm font-semibold text-neutral-100">{item.computed}</span>
                <span className="mt-0.5 block break-words font-mono text-xs text-neutral-500">limit {item.limit}</span>
              </td>
              <td className="px-3 py-3 align-top">
                <SeverityChip severity={item.severity} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Diagrams({
  bmdSvg,
  sfdSvg,
}: {
  bmdSvg: string | null
  sfdSvg: string | null
}) {
  const host = 'rounded-lg border border-neutral-700 bg-white p-4 [&_svg]:h-auto [&_svg]:w-full [&_svg]:max-w-full'
  return (
    // Stacked so each figure spans the full width of its (left) column.
    <div className="grid gap-6">
      {bmdSvg && (
        <figure data-testid="bmd-svg" className="space-y-1.5">
          {/* Trusted markup: rendered server-side by our own FE cross-check. */}
          <div className={host} dangerouslySetInnerHTML={{ __html: bmdSvg }} />
          <figcaption className="text-sm text-neutral-400">Bending-moment diagram (independent FE re-solve)</figcaption>
        </figure>
      )}
      {sfdSvg && (
        <figure data-testid="sfd-svg" className="space-y-1.5">
          {/* Trusted markup: rendered server-side by our own FE cross-check. */}
          <div className={host} dangerouslySetInnerHTML={{ __html: sfdSvg }} />
          <figcaption className="text-sm text-neutral-400">Shear-force diagram (independent FE re-solve)</figcaption>
        </figure>
      )}
    </div>
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
          className="flex h-full min-h-[24rem] flex-col items-center justify-center gap-4 rounded-xl border border-neutral-800 bg-neutral-900 p-8"
        >
          <div className="w-full max-w-xl space-y-3" aria-hidden="true">
            <div className="h-10 w-full rounded-lg bg-neutral-800 motion-safe:animate-pulse" />
            <div className="h-5 w-5/6 rounded-lg bg-neutral-800 motion-safe:animate-pulse" />
            <div className="h-5 w-full rounded-lg bg-neutral-800 motion-safe:animate-pulse" />
          </div>
          <p className="text-lg text-neutral-400">
            {reviewActive
              ? 'Running the independent proof-check…'
              : 'The proof-check runs automatically once the design and drawing are complete.'}
          </p>
        </div>
      )
    }
    if (runFailed) {
      return (
        <div className="flex h-full min-h-[24rem] items-center justify-center rounded-xl border border-neutral-800 bg-neutral-900 p-8">
          <p className="max-w-md text-center text-lg leading-relaxed text-neutral-400">
            The run failed before the proof-check completed — the details are in the red banner above. Fix the request
            and try again.
          </p>
        </div>
      )
    }
    return (
      <div className="flex h-full min-h-[24rem] items-center justify-center rounded-xl border border-neutral-800 bg-neutral-900 p-8">
        <p className="max-w-md text-center text-lg leading-relaxed text-neutral-400">
          {hasRun
            ? 'This run has no proof-check — select a completed design in the session panel, or run a new design.'
            : 'Every completed design is proof-checked automatically — verdict, severity-graded memo, 12-item compliance matrix and independent FE cross-check appear here.'}
        </p>
      </div>
    )
  }

  // Each section stays whole within a single column. Deterministic split so the
  // reading order is: Assessment (1) + FE cross-check (3) down the LEFT column,
  // Compliance checklist (2) down the RIGHT column. The verdict header spans the
  // full width across the top. Stacks to one column below lg.
  const assessmentSection = memoMarkdown ? (
    <ReportSection numeral="1" title="Assessment">
      <div
        data-testid="memo"
        aria-label="Proof-check memo"
        className="text-[0.95rem] leading-relaxed text-neutral-200 [&_a]:text-indigo-300 [&_a]:underline [&_code]:font-mono [&_code]:rounded [&_code]:bg-neutral-950 [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-sm [&_code]:text-neutral-100 [&_h1]:text-xl [&_h1]:font-bold [&_h1]:text-neutral-100 [&_h2]:mt-5 [&_h2]:text-lg [&_h2]:font-bold [&_h2]:text-neutral-100 [&_h3]:mt-4 [&_h3]:text-base [&_h3]:font-semibold [&_h3]:text-neutral-100 [&_li]:mt-1 [&_ol]:mt-2 [&_ol]:list-decimal [&_ol]:pl-6 [&_p]:mt-2.5 [&_strong]:font-semibold [&_strong]:text-neutral-100 [&_table]:mt-3 [&_table]:w-full [&_table]:border-collapse [&_td]:border [&_td]:border-neutral-700 [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_th]:border-neutral-700 [&_th]:bg-neutral-950 [&_th]:px-2 [&_th]:py-1 [&_th]:text-neutral-100 [&_ul]:mt-2 [&_ul]:list-disc [&_ul]:pl-6"
      >
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{memoMarkdown}</ReactMarkdown>
      </div>
    </ReportSection>
  ) : (
    isRunning && <BlockSkeleton label="Drafting the proof-check memo…" />
  )

  const feSection =
    bmdSvg || sfdSvg ? (
      <ReportSection
        numeral="3"
        title="Independent FE cross-check"
        aside={
          compliance?.fe_agreement_pct != null ? (
            <p data-testid="fe-agreement" className="text-sm text-neutral-400">
              Agrees within {Number(compliance.fe_agreement_pct.toPrecision(3))}% of the closed-form analysis
            </p>
          ) : undefined
        }
      >
        <Diagrams bmdSvg={bmdSvg} sfdSvg={sfdSvg} />
      </ReportSection>
    ) : (
      isRunning && <BlockSkeleton label="Re-solving the frame with the independent FE model…" />
    )

  const complianceSection = compliance ? (
    <ReportSection numeral="2" title="Compliance checklist" aside={<ChecklistTally items={compliance.items} />}>
      <ComplianceMatrix compliance={compliance} />
    </ReportSection>
  ) : (
    isRunning && <BlockSkeleton label="Evaluating the 12-item checklist…" />
  )

  return (
    <article data-testid="proof-check-content" className="w-full space-y-8">
      {verdict ? (
        <ReportHeader verdict={verdict} compliance={compliance} />
      ) : (
        isRunning && <BlockSkeleton label="Computing the verdict…" />
      )}

      <div className="grid gap-8 lg:grid-cols-2 lg:items-start">
        <div className="space-y-8">
          {assessmentSection}
          {feSection}
        </div>
        <div className="space-y-8">{complianceSection}</div>
      </div>
    </article>
  )
}
