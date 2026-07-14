'use client'

import { useEffect, useState } from 'react'
import { TransformComponent, TransformWrapper, useControls } from 'react-zoom-pan-pinch'

interface DrawingViewerProps {
  svgMarkup: string | null
  dxfUrl: string | null
  /** M-00004 standard PDF sheet URL, when the run emitted the `m00004_sheet` kind. */
  m00004SheetUrl?: string | null
  isRunning: boolean
  drawActive: boolean
  runFailed: boolean
  hasRun: boolean
}

function ZoomControls() {
  const { zoomIn, zoomOut, resetTransform } = useControls()
  const buttonClass =
    'rounded-md border border-slate-300 bg-white px-3 py-1.5 text-base font-semibold text-slate-700 shadow-sm hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600'
  return (
    <div className="flex items-center gap-1.5" role="group" aria-label="Drawing zoom controls">
      <button type="button" className={buttonClass} onClick={() => zoomIn()} aria-label="Zoom in">
        +
      </button>
      <button type="button" className={buttonClass} onClick={() => zoomOut()} aria-label="Zoom out">
        −
      </button>
      <button type="button" className={buttonClass} onClick={() => resetTransform()}>
        Reset view
      </button>
    </div>
  )
}

function DownloadDxfButton({ dxfUrl }: { dxfUrl: string | null }) {
  if (!dxfUrl) {
    return (
      <button
        type="button"
        data-testid="download-dxf"
        disabled
        title="The DXF is produced at the end of the Draw step"
        className="cursor-not-allowed rounded-md bg-slate-300 px-4 py-1.5 text-base font-semibold text-slate-500"
      >
        Download DXF
      </button>
    )
  }
  return (
    <a
      data-testid="download-dxf"
      href={dxfUrl}
      download="ga.dxf"
      title="Opens in AutoCAD and free viewers"
      className="rounded-md bg-indigo-600 px-4 py-1.5 text-base font-semibold text-white shadow-sm hover:bg-indigo-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600"
    >
      Download DXF
    </a>
  )
}

// Opens the M-00004 standard PDF sheet inline in a new tab (the server serves it
// with `Content-Disposition: inline`), and offers a direct download. Absent for
// components that don't emit the PDF — never a broken/empty control (spec/ui.md).
function M00004SheetButtons({ url }: { url: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <a
        data-testid="open-m00004-pdf"
        href={url}
        target="_blank"
        rel="noreferrer"
        title="Opens the RDSO/M-00004 standard sheet (dimensioned section, a1..h reinforcement, schedule, notes) — every catalogue value marked PROVISIONAL"
        className="rounded-md bg-emerald-700 px-4 py-1.5 text-base font-semibold text-white shadow-sm hover:bg-emerald-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700"
      >
        Open M-00004 sheet (PDF)
      </a>
      <a
        data-testid="download-m00004-pdf"
        href={url}
        download="m00004_sheet.pdf"
        title="Download the M-00004 PDF sheet"
        className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-base font-semibold text-slate-700 shadow-sm hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600"
      >
        Download
      </a>
    </span>
  )
}

function FullscreenButton({
  isFullscreen,
  onToggle,
}: {
  isFullscreen: boolean
  onToggle: () => void
}) {
  return (
    <button
      type="button"
      data-testid="drawing-fullscreen-toggle"
      onClick={onToggle}
      aria-pressed={isFullscreen}
      title={isFullscreen ? 'Exit full screen (Esc)' : 'Expand drawing to full screen'}
      className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-base font-semibold text-slate-700 shadow-sm hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600"
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        {isFullscreen ? (
          <path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5" strokeLinecap="round" strokeLinejoin="round" />
        ) : (
          <path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" strokeLinecap="round" strokeLinejoin="round" />
        )}
      </svg>
      {isFullscreen ? 'Exit full screen' : 'Full screen'}
    </button>
  )
}

/** The interactive drawing surface — reused inline and inside the full-screen overlay. */
function DrawingSurface({
  svgMarkup,
  dxfUrl,
  m00004SheetUrl,
  isFullscreen,
  onToggleFullscreen,
}: {
  svgMarkup: string
  dxfUrl: string | null
  m00004SheetUrl?: string | null
  isFullscreen: boolean
  onToggleFullscreen: () => void
}) {
  return (
    <div className="flex h-full min-h-0 flex-1 flex-col gap-3">
      <TransformWrapper doubleClick={{ mode: 'reset' }} minScale={0.2} maxScale={20} limitToBounds={false}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <ZoomControls />
            <FullscreenButton isFullscreen={isFullscreen} onToggle={onToggleFullscreen} />
          </div>
          <p className={`text-sm ${isFullscreen ? 'text-neutral-400' : 'text-slate-500'}`}>
            Wheel to zoom · drag to pan · double-click to reset
          </p>
          <div className="flex flex-wrap items-center gap-2">
            {/* M-00004 standard PDF sheet affordance — only when the run emitted it. */}
            {m00004SheetUrl && <M00004SheetButtons url={m00004SheetUrl} />}
            <DownloadDxfButton dxfUrl={dxfUrl} />
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-hidden rounded-xl border border-slate-300 bg-white shadow-inner">
          <TransformComponent wrapperClass="!h-full !w-full" contentClass="!h-full !w-full">
            <div
              data-testid="drawing-svg"
              className="drawing-svg-host flex h-full w-full items-center justify-center p-4"
              // Trusted markup: the SVG is rendered server-side by our own
              // drawing engine from the DXF it wrote (single origin, no user HTML).
              dangerouslySetInnerHTML={{ __html: svgMarkup }}
            />
          </TransformComponent>
        </div>
      </TransformWrapper>
    </div>
  )
}

export default function DrawingViewer({
  svgMarkup,
  dxfUrl,
  m00004SheetUrl,
  isRunning,
  drawActive,
  runFailed,
  hasRun,
}: DrawingViewerProps) {
  const [isFullscreen, setIsFullscreen] = useState(false)

  useEffect(() => {
    if (!isFullscreen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setIsFullscreen(false)
    }
    window.addEventListener('keydown', onKey)
    // Prevent background scroll while the overlay is open.
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [isFullscreen])

  // Whenever the drawing disappears (e.g. a new run starts), leave full screen.
  useEffect(() => {
    if (!svgMarkup && isFullscreen) setIsFullscreen(false)
  }, [svgMarkup, isFullscreen])

  if (!svgMarkup) {
    if (isRunning) {
      return (
        <div className="flex h-full min-h-[24rem] flex-col items-center justify-center gap-4 rounded-xl border border-slate-200 bg-white p-8">
          <div className="h-48 w-full max-w-xl rounded-lg bg-slate-100 motion-safe:animate-pulse" aria-hidden="true" />
          <p className="text-lg text-slate-600">
            {drawActive ? 'Drawing the GA…' : 'The GA sheet appears here when the run reaches the Draw step.'}
          </p>
        </div>
      )
    }
    if (runFailed) {
      return (
        <div className="flex h-full min-h-[24rem] items-center justify-center rounded-xl border border-slate-200 bg-white p-8">
          <p className="max-w-md text-center text-lg leading-relaxed text-slate-600">
            The run failed before a drawing was produced — the details are in the red banner above. Fix the request and
            try again.
          </p>
        </div>
      )
    }
    return (
      <div className="flex h-full min-h-[24rem] items-center justify-center rounded-xl border border-slate-200 bg-white p-8">
        <p className="max-w-md text-center text-lg leading-relaxed text-slate-600">
          {hasRun
            ? 'This run produced no drawing — select a completed run in the session panel, or refine and run again.'
            : 'The dimensioned GA drawing appears here — plan, sections and title block, rendered from the same DXF you can download.'}
        </p>
      </div>
    )
  }

  return (
    <>
      <div className="flex h-full min-h-[24rem] flex-col">
        <DrawingSurface
          svgMarkup={svgMarkup}
          dxfUrl={dxfUrl}
          m00004SheetUrl={m00004SheetUrl}
          isFullscreen={false}
          onToggleFullscreen={() => setIsFullscreen(true)}
        />
      </div>

      {isFullscreen && (
        <div
          data-testid="drawing-fullscreen-overlay"
          role="dialog"
          aria-modal="true"
          aria-label="General arrangement drawing — full screen"
          className="fixed inset-0 z-50 flex flex-col bg-neutral-950/95 p-4 backdrop-blur-sm"
        >
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-neutral-100">General arrangement — full screen</h2>
            <button
              type="button"
              data-testid="drawing-fullscreen-close"
              onClick={() => setIsFullscreen(false)}
              aria-label="Close full screen"
              className="inline-flex items-center gap-1.5 rounded-md border border-neutral-700 bg-neutral-800 px-3 py-1.5 text-sm font-semibold text-neutral-200 hover:bg-neutral-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-400"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <path d="M6 6l12 12M18 6 6 18" strokeLinecap="round" />
              </svg>
              Close (Esc)
            </button>
          </div>
          <div className="min-h-0 flex-1">
            <DrawingSurface
              svgMarkup={svgMarkup}
              dxfUrl={dxfUrl}
              m00004SheetUrl={m00004SheetUrl}
              isFullscreen
              onToggleFullscreen={() => setIsFullscreen(false)}
            />
          </div>
        </div>
      )}
    </>
  )
}
