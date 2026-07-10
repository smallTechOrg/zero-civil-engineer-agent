'use client'

import { useEffect, useRef, useState } from 'react'

// The model-viewer element exposes a `loaded` property — used to catch the
// case where the model finished loading before our listener attached.
interface ModelViewerElement extends HTMLElement {
  loaded?: boolean
}

interface Model3DViewerProps {
  glbUrl: string | null
  stepUrl: string | null
  isRunning: boolean
  runFailed: boolean
  hasRun: boolean
}

type ModelState = 'loading' | 'loaded' | 'error'

function CubeIcon() {
  return (
    <svg width="72" height="72" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M12 2.5 21 7v10l-9 4.5L3 17V7l9-4.5Z" />
      <path d="M12 11.5 21 7M12 11.5 3 7M12 11.5v10" />
    </svg>
  )
}

function DownloadStepButton({ stepUrl }: { stepUrl: string | null }) {
  if (!stepUrl) {
    return (
      <button
        type="button"
        data-testid="download-step"
        disabled
        title="The STEP file is produced with the 3D model — it appears when the export completes"
        className="cursor-not-allowed rounded-md bg-slate-300 px-4 py-1.5 text-base font-semibold text-slate-500"
      >
        Download STEP
      </button>
    )
  }
  return (
    <a
      data-testid="download-step"
      href={stepUrl}
      download="model.step"
      title="Opens in FreeCAD — free"
      className="rounded-md bg-indigo-600 px-4 py-1.5 text-base font-semibold text-white shadow-sm hover:bg-indigo-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600"
    >
      Download STEP
    </a>
  )
}

export default function Model3DViewer({ glbUrl, stepUrl, isRunning, runFailed, hasRun }: Model3DViewerProps) {
  // The custom element registers browser-side only (this is a static export):
  // the library is imported inside useEffect, never during prerender.
  const [viewerReady, setViewerReady] = useState(false)
  const [modelState, setModelState] = useState<ModelState>('loading')
  const hostRef = useRef<ModelViewerElement | null>(null)

  useEffect(() => {
    if (!glbUrl) return
    let cancelled = false
    import('@google/model-viewer')
      .then(() => {
        if (!cancelled) setViewerReady(true)
      })
      .catch(() => {
        if (!cancelled) setModelState('error')
      })
    return () => {
      cancelled = true
    }
  }, [glbUrl])

  // A new GLB (refinement / replayed run) restarts the loading state.
  useEffect(() => {
    setModelState('loading')
  }, [glbUrl])

  useEffect(() => {
    const el = hostRef.current
    if (!el) return
    if (el.loaded) {
      setModelState('loaded')
      return
    }
    const onLoad = () => setModelState('loaded')
    const onError = () => setModelState('error')
    el.addEventListener('load', onLoad)
    el.addEventListener('error', onError)
    return () => {
      el.removeEventListener('load', onLoad)
      el.removeEventListener('error', onError)
    }
  }, [viewerReady, glbUrl])

  if (!glbUrl) {
    if (isRunning) {
      return (
        <div
          data-testid="model3d-loading"
          className="flex h-full min-h-[24rem] flex-col items-center justify-center gap-4 rounded-xl border border-slate-200 bg-white p-8"
        >
          <div className="h-48 w-full max-w-xl rounded-lg bg-slate-100 motion-safe:animate-pulse" aria-hidden="true" />
          <p className="text-lg text-slate-600">
            Building the 3D solid — it appears here once the model exports.
          </p>
        </div>
      )
    }
    if (runFailed) {
      return (
        <div className="flex h-full min-h-[24rem] items-center justify-center rounded-xl border border-slate-200 bg-white p-8">
          <p className="max-w-md text-center text-lg leading-relaxed text-slate-600">
            The run failed before a 3D model was produced — the details are in the red banner above. Fix the request
            and try again.
          </p>
        </div>
      )
    }
    if (hasRun) {
      // Non-fatal model3d failure (or a run that produced no model): a
      // designed state, never an infinite skeleton and never an error page.
      return (
        <div
          data-testid="model3d-unavailable"
          className="flex h-full min-h-[24rem] flex-col items-center justify-center gap-4 rounded-xl border border-slate-200 bg-slate-50 p-8 text-center"
        >
          <div className="text-slate-400">
            <CubeIcon />
          </div>
          <p className="text-xl font-semibold text-slate-700">3D model unavailable for this run</p>
          <p className="max-w-md text-base leading-relaxed text-slate-600">
            This run produced no 3D export — the drawing, calc sheet and proof-check stand on their own. Run a new
            design or select a run with a model in the Library.
          </p>
        </div>
      )
    }
    return (
      <div
        data-testid="model3d-empty"
        className="flex h-full min-h-[24rem] flex-col items-center justify-center gap-4 rounded-xl border border-slate-200 bg-white p-8 text-center"
      >
        <div className="text-slate-300">
          <CubeIcon />
        </div>
        <p className="max-w-md text-lg leading-relaxed text-slate-600">
          The interactive 3D culvert appears here — orbit and zoom it in the browser, and download the STEP solid
          that opens in FreeCAD (free).
        </p>
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-[24rem] flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-500">Drag to orbit · wheel to zoom · right-drag to pan</p>
        <DownloadStepButton stepUrl={stepUrl} />
      </div>

      {modelState === 'error' ? (
        <div
          data-testid="model3d-error"
          className="flex min-h-0 flex-1 flex-col items-center justify-center gap-4 rounded-xl border border-red-200 bg-red-50 p-8 text-center"
        >
          <p className="text-xl font-semibold text-red-800">The 3D model could not be displayed</p>
          <p className="max-w-md text-base leading-relaxed text-red-900">
            The viewer failed to load the model file in this browser. The STEP download above still contains the full
            solid — open it in FreeCAD (free).
          </p>
        </div>
      ) : (
        <div
          data-testid="model3d-viewer"
          data-model-loaded={modelState === 'loaded' ? 'true' : 'false'}
          className="relative min-h-0 flex-1 overflow-hidden rounded-xl border border-slate-300 bg-white shadow-inner"
        >
          {viewerReady && (
            <model-viewer
              ref={hostRef}
              src={glbUrl}
              alt="Interactive 3D model of the designed box culvert"
              camera-controls=""
              exposure="0.9"
              shadow-intensity="0.6"
              interaction-prompt="none"
              touch-action="pan-y"
              style={{ width: '100%', height: '100%', display: 'block' }}
            />
          )}
          {modelState === 'loading' && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 bg-white/90 p-8">
              <div className="h-40 w-full max-w-lg rounded-lg bg-slate-100 motion-safe:animate-pulse" aria-hidden="true" />
              <p className="text-lg text-slate-600" role="status">
                Loading the 3D model…
              </p>
            </div>
          )}
        </div>
      )}

      <p data-testid="model3d-caption" className="text-sm text-slate-500">
        Generated from the same BoxGeometry as the drawing and calc sheet.
      </p>
    </div>
  )
}
