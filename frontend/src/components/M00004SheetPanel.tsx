'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchArtefactText } from '@/lib/api'
import {
  M00004_BUNDLE_FILENAME,
  M00004_BUNDLE_KIND,
  M00004_DIAGRAMS,
  M00004_GA_SHEET_FILENAME,
  M00004_GA_SHEET_KIND,
  M00004_STEP_PARTS,
  type ArtefactRecord,
} from '@/lib/types'

// The full RDSO/M-00004 GA sheet surface (Phase 2). It lists and downloads every
// per-diagram drawing (SVG inline + DXF), the genuinely-3D STEP parts, the
// composed PDF sheet (inline) and the .zip bundle — driven ENTIRELY by the run's
// artefact list (kind → label), so an artefact that isn't present for a run
// (e.g. a STEP that the non-fatal 3D step didn't produce) is simply omitted,
// never rendered as a broken/empty control (spec/ui.md stub rules). Everything is
// stamped PROVISIONAL so nothing reads as a bug.

interface M00004SheetPanelProps {
  runId: string | null
  artefacts: ArtefactRecord[]
  isRunning: boolean
  hasRun: boolean
}

const PROVISIONAL = 'PROVISIONAL — NOT FOR CONSTRUCTION — verify every value against RDSO/M-00004'

function ProvisionalBanner() {
  return (
    <div
      data-testid="m00004-sheet-provisional"
      className="rounded-lg border border-amber-500/50 bg-amber-950/30 px-4 py-2.5 text-sm font-semibold text-amber-200"
    >
      {PROVISIONAL}
    </div>
  )
}

/** Fetch the SVG text for each present diagram once; cache by kind:url. */
function useDiagramSvgs(diagrams: { svgKind: string; url: string }[]) {
  const [svgs, setSvgs] = useState<Record<string, string>>({})
  const fetchedRef = useRef<Set<string>>(new Set())
  const signature = diagrams.map(d => `${d.svgKind}:${d.url}`).join('|')

  useEffect(() => {
    let cancelled = false
    for (const d of diagrams) {
      const cacheKey = `${d.svgKind}:${d.url}`
      if (fetchedRef.current.has(cacheKey)) continue
      fetchedRef.current.add(cacheKey)
      fetchArtefactText(d.url)
        .then(text => {
          if (!cancelled) setSvgs(prev => ({ ...prev, [d.svgKind]: text }))
        })
        .catch(() => {
          // Allow a later retry if the fetch failed transiently.
          fetchedRef.current.delete(cacheKey)
        })
    }
    return () => {
      cancelled = true
    }
    // signature captures the set of present diagrams + their urls
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature])

  return svgs
}

export default function M00004SheetPanel({ runId, artefacts, isRunning, hasRun }: M00004SheetPanelProps) {
  const byKind = useMemo(() => {
    const map = new Map<string, ArtefactRecord>()
    for (const a of artefacts) map.set(a.kind, a)
    return map
  }, [artefacts])

  const presentDiagrams = useMemo(
    () =>
      M00004_DIAGRAMS.map(d => ({
        ...d,
        svgUrl: byKind.get(d.svgKind)?.url ?? null,
        dxfUrl: byKind.get(d.dxfKind)?.url ?? null,
      })).filter(d => d.svgUrl),
    [byKind],
  )

  const stepParts = useMemo(
    () =>
      M00004_STEP_PARTS.map(p => ({ ...p, url: byKind.get(p.kind)?.url ?? null })).filter(
        (p): p is typeof p & { url: string } => p.url !== null,
      ),
    [byKind],
  )

  const gaSheetUrl = byKind.get(M00004_GA_SHEET_KIND)?.url ?? null
  const bundleUrl = byKind.get(M00004_BUNDLE_KIND)?.url ?? null

  const svgs = useDiagramSvgs(
    presentDiagrams
      .filter((d): d is typeof d & { svgUrl: string } => d.svgUrl !== null)
      .map(d => ({ svgKind: d.svgKind, url: d.svgUrl })),
  )

  const nothingYet =
    presentDiagrams.length === 0 && stepParts.length === 0 && !gaSheetUrl && !bundleUrl

  // ---- Empty / loading / no-artefact states (all four states, spec/ui-ux) ----
  if (nothingYet) {
    if (isRunning) {
      return (
        <div
          data-testid="m00004-sheet-panel"
          data-run-id={runId ?? ''}
          className="flex h-full min-h-[24rem] flex-col gap-4"
        >
          <ProvisionalBanner />
          <div className="flex flex-1 flex-col items-center justify-center gap-4 rounded-xl border border-neutral-800 bg-neutral-950 p-8">
            <div className="h-40 w-full max-w-xl rounded-lg bg-neutral-800 motion-safe:animate-pulse" aria-hidden="true" />
            <p className="text-lg text-neutral-400">
              Rendering the full RDSO/M-00004 GA sheet — the ten drawings, STEP parts and composed sheet appear here as
              they stream in.
            </p>
          </div>
        </div>
      )
    }
    return (
      <div
        data-testid="m00004-sheet-panel"
        data-run-id={runId ?? ''}
        className="flex h-full min-h-[24rem] flex-col gap-4"
      >
        <ProvisionalBanner />
        <div className="flex flex-1 items-center justify-center rounded-xl border border-neutral-800 bg-neutral-950 p-8">
          <p className="max-w-md text-center text-lg leading-relaxed text-neutral-400">
            {hasRun
              ? 'This run produced no full-sheet artefacts — the standard GA sheet, per-diagram drawings and STEP parts appear here once a design completes.'
              : 'The full RDSO/M-00004 GA sheet — all ten drawings, the STEP parts, the composed PDF sheet and a downloadable bundle — appears here after you run an M-00004 design.'}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div
      data-testid="m00004-sheet-panel"
      data-run-id={runId ?? ''}
      className="flex h-full min-h-[24rem] flex-col gap-4 overflow-y-auto"
    >
      <ProvisionalBanner />

      {/* Composed sheet + bundle affordances — the headline review/download row. */}
      <section
        aria-label="Composed sheet and bundle"
        className="flex flex-wrap items-center gap-3 rounded-xl border border-neutral-800 bg-neutral-950 p-4"
      >
        {gaSheetUrl ? (
          <a
            data-testid="open-m00004-ga-sheet"
            href={gaSheetUrl}
            target="_blank"
            rel="noreferrer"
            title="Opens the composed RDSO/M-00004 GA sheet — the six drawings laid out as on the real sheet, with notations, notes and title block. Every value PROVISIONAL."
            className="rounded-md bg-emerald-700 px-4 py-1.5 text-base font-semibold text-white shadow-sm hover:bg-emerald-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-600"
          >
            Open M-00004 GA sheet (PDF)
          </a>
        ) : (
          <span className="text-sm text-neutral-500">The composed GA sheet (PDF) appears here at Review.</span>
        )}
        {bundleUrl && (
          <a
            data-testid="download-m00004-bundle"
            href={bundleUrl}
            download={M00004_BUNDLE_FILENAME}
            title="Downloads a .zip of every per-diagram DXF and every STEP part produced for this run."
            className="rounded-md border border-neutral-700 bg-neutral-900 px-4 py-1.5 text-base font-semibold text-neutral-100 shadow-sm hover:bg-neutral-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-400"
          >
            Download bundle (.zip)
          </a>
        )}
        <span className="text-xs text-neutral-500">
          {M00004_GA_SHEET_FILENAME} · {M00004_BUNDLE_FILENAME}
        </span>
      </section>

      {/* STEP parts — the genuinely-3D solids, each a download. */}
      {stepParts.length > 0 && (
        <section
          aria-label="3D STEP parts"
          data-testid="m00004-step-parts"
          className="rounded-xl border border-neutral-800 bg-neutral-950 p-4"
        >
          <h3 className="text-sm font-semibold uppercase tracking-wide text-neutral-400">
            3D STEP parts <span className="font-normal text-neutral-500">(open in FreeCAD — free)</span>
          </h3>
          <ul className="mt-3 flex flex-wrap gap-2">
            {stepParts.map(p => (
              <li key={p.kind}>
                <a
                  data-testid={`m00004-step-${p.kind}`}
                  href={p.url}
                  download={p.filename}
                  title={`Download ${p.filename}`}
                  className="inline-flex items-center gap-2 rounded-md border border-neutral-700 bg-neutral-900 px-3 py-1.5 text-sm font-semibold text-neutral-100 hover:bg-neutral-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-400"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                    <path d="M12 2.5 21 7v10l-9 4.5L3 17V7l9-4.5Z" />
                  </svg>
                  {p.label}
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Per-diagram drawing gallery — SVG inline + DXF download for each. */}
      {presentDiagrams.length > 0 && (
        <section aria-label="M-00004 drawings" data-testid="m00004-drawings" className="grid gap-4 lg:grid-cols-2">
          {presentDiagrams.map(d => {
            const svg = svgs[d.svgKind]
            return (
              <figure
                key={d.key}
                data-testid={`m00004-diagram-${d.key}`}
                className="flex flex-col overflow-hidden rounded-xl border border-neutral-800 bg-neutral-950"
              >
                <figcaption className="flex flex-wrap items-center justify-between gap-2 border-b border-neutral-800 px-4 py-2.5">
                  <span className="text-base font-semibold text-neutral-100">{d.label}</span>
                  {d.dxfUrl && (
                    <a
                      data-testid={`m00004-diagram-dxf-${d.key}`}
                      href={d.dxfUrl}
                      download={d.dxfFilename}
                      title={`Download ${d.dxfFilename} — opens in AutoCAD and free viewers`}
                      className="rounded-md border border-neutral-700 bg-neutral-900 px-3 py-1 text-sm font-semibold text-neutral-200 hover:bg-neutral-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-400"
                    >
                      Download DXF
                    </a>
                  )}
                </figcaption>
                <div className="flex min-h-[16rem] flex-1 items-center justify-center bg-white p-3">
                  {svg ? (
                    <div
                      data-testid={`m00004-diagram-svg-${d.key}`}
                      className="drawing-svg-host flex h-full w-full items-center justify-center"
                      // Trusted markup: rendered server-side by our own drawing
                      // engine from the DXF it wrote (single origin, no user HTML).
                      dangerouslySetInnerHTML={{ __html: svg }}
                    />
                  ) : (
                    <div className="h-40 w-full rounded-lg bg-slate-100 motion-safe:animate-pulse" aria-hidden="true" />
                  )}
                </div>
              </figure>
            )
          })}
        </section>
      )}
    </div>
  )
}
