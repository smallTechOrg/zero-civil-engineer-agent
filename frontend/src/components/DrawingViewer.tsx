'use client'

import { TransformComponent, TransformWrapper, useControls } from 'react-zoom-pan-pinch'

interface DrawingViewerProps {
  svgMarkup: string | null
  dxfUrl: string | null
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

export default function DrawingViewer({ svgMarkup, dxfUrl, isRunning, drawActive, runFailed, hasRun }: DrawingViewerProps) {
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
    <div className="flex h-full min-h-[24rem] flex-col gap-3">
      <TransformWrapper doubleClick={{ mode: 'reset' }} minScale={0.2} maxScale={20} limitToBounds={false}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <ZoomControls />
          <p className="text-sm text-slate-500">Wheel to zoom · drag to pan · double-click to reset</p>
          <DownloadDxfButton dxfUrl={dxfUrl} />
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
