'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import AppShell, { type DesignRecordSummary } from '@/components/AppShell'
import CalcSheet from '@/components/CalcSheet'
import ComponentPicker from '@/components/ComponentPicker'
import DetectedTypeChip from '@/components/DetectedTypeChip'
import DrawingViewer from '@/components/DrawingViewer'
import Model3DViewer from '@/components/Model3DViewer'
import OverviewPanel from '@/components/OverviewPanel'
import ProofCheckPanel from '@/components/ProofCheckPanel'
import PromptPanel, { CANONICAL_PROMPT, type PromptMode } from '@/components/PromptPanel'
import StageRail, { type StageId, type StageProgress } from '@/components/StageRail'
import StageStub from '@/components/StageStub'
import StatusLine from '@/components/StatusLine'
import StepTracker from '@/components/StepTracker'
import SuggestionChips from '@/components/SuggestionChips'
import {
  ApiError,
  createSession,
  fetchArtefactJson,
  fetchArtefactText,
  getRunSnapshot,
  listComponents,
  listDesigns,
  runEventsUrl,
  submitDesign,
} from '@/lib/api'
import { subscribeToRun, type RunSubscription } from '@/lib/sse'
import {
  STEP_NAMES,
  type ArtefactRecord,
  type CalcSheetData,
  type ComplianceData,
  type ComponentCard,
  type RunListItem,
  type RunSnapshot,
  type RunStatus,
  type StepName,
  type StepState,
  type TypeSummary,
  type Verdict,
} from '@/lib/types'

const SESSION_STORAGE_KEY = 'culvert.session_id'

type DesignPanel = 'drawing' | 'calc' | '3d'

interface RunView {
  runId: string
  prompt: string
  status: RunStatus
  componentType: string | null
  typeSummary: TypeSummary | null
  steps: Record<StepName, StepState>
  narration: string
  warnings: string[]
  clarificationQuestion: string | null
  svgMarkup: string | null
  dxfUrl: string | null
  calcSheet: CalcSheetData | null
  compliance: ComplianceData | null
  memoMarkdown: string | null
  bmdSvg: string | null
  sfdSvg: string | null
  glbUrl: string | null
  stepUrl: string | null
  suggestions: string[]
  verdict: Verdict | null
  runTokens: number
  runCostUsd: number
  errorMessage: string | null
  startedAt: string | null
  durationMs: number | null
}

function initialSteps(): Record<StepName, StepState> {
  return Object.fromEntries(
    STEP_NAMES.map(name => [name, { name, status: 'pending', detail: null }]),
  ) as Record<StepName, StepState>
}

function stepsFromSnapshot(snap: RunSnapshot): Record<StepName, StepState> {
  const steps = initialSteps()
  for (const s of snap.steps ?? []) {
    if (!(s.name in steps)) continue
    steps[s.name] = {
      name: s.name,
      status: s.status,
      detail: s.status === 'skipped' ? 'Skipped for this run' : (s.detail ?? null),
    }
  }
  return steps
}

function terminalNarration(status: RunStatus): string | null {
  switch (status) {
    case 'completed':
      return 'Design complete — the drawing, calculation sheet and proof-check verdict are ready across the stages.'
    case 'needs_input':
      return 'The agent needs one more detail — answer the question in the Define stage.'
    case 'out_of_scope':
      return 'This request is outside the demonstrator’s scope — the agent’s reply is in the Define stage.'
    default:
      return null
  }
}

function complianceFromSnapshot(snap: RunSnapshot): ComplianceData | null {
  if (!snap.checklist || snap.checklist.length === 0) return null
  return { items: snap.checklist, verdict: snap.verdict, fe_agreement_pct: null }
}

function viewFromSnapshot(snap: RunSnapshot): RunView {
  const tokens = snap.tokens ?? { prompt_tokens: 0, completion_tokens: 0, cost_usd: 0 }
  return {
    runId: snap.run_id,
    prompt: snap.prompt,
    status: snap.status,
    componentType: snap.component_type ?? null,
    typeSummary: snap.type_summary ?? null,
    steps: stepsFromSnapshot(snap),
    narration: terminalNarration(snap.status) ?? snap.plan_text ?? '',
    warnings: snap.warnings ?? [],
    clarificationQuestion: snap.clarification_question,
    svgMarkup: null,
    dxfUrl: snap.artefacts?.find(a => a.kind === 'ga_dxf')?.url ?? null,
    calcSheet: null,
    compliance: complianceFromSnapshot(snap),
    memoMarkdown: null,
    bmdSvg: null,
    sfdSvg: null,
    glbUrl: snap.artefacts?.find(a => a.kind === 'model_glb')?.url ?? null,
    stepUrl: snap.artefacts?.find(a => a.kind === 'model_step')?.url ?? null,
    suggestions: snap.suggestions ?? [],
    verdict: snap.verdict,
    runTokens: (tokens.prompt_tokens ?? 0) + (tokens.completion_tokens ?? 0),
    runCostUsd: tokens.cost_usd ?? 0,
    errorMessage: snap.error_message,
    startedAt: snap.started_at,
    durationMs: snap.duration_ms,
  }
}

// Live-run progress for a stage — driven by the six pipeline steps, WITHOUT
// forcing a stage switch (spec/ui.md "Tab / stage focus rule").
function stageProgress(steps: Record<StepName, StepState>, names: StepName[]): StageProgress {
  const statuses = names.map(n => steps[n]?.status ?? 'pending')
  if (statuses.every(s => s === 'done' || s === 'skipped') && statuses.some(s => s === 'done')) return 'done'
  if (statuses.some(s => s === 'active')) return 'active'
  if (statuses.some(s => s === 'done' || s === 'skipped')) return 'active'
  return 'pending'
}

export default function DesignStudio() {
  const [booting, setBooting] = useState(true)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [components, setComponents] = useState<ComponentCard[]>([])
  const [selectedComponent, setSelectedComponent] = useState<string | null>(null)
  const [turns, setTurns] = useState<RunListItem[]>([])
  const [run, setRun] = useState<RunView | null>(null)
  const [elapsedMs, setElapsedMs] = useState(0)
  const [sessionCostUsd, setSessionCostUsd] = useState(0)
  const [sessionTokens, setSessionTokens] = useState(0)
  const [promptValue, setPromptValue] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  // Workspace view state — active lifecycle stage + inner Design panel.
  const [stage, setStage] = useState<StageId>('overview')
  const [designPanel, setDesignPanel] = useState<DesignPanel>('drawing')

  const subscriptionRef = useRef<RunSubscription | null>(null)
  const elapsedBaseRef = useRef({ baseMs: 0, wallStart: Date.now() })
  const runStatusRef = useRef<RunStatus | null>(null)
  runStatusRef.current = run?.status ?? null
  // Committed per-session token total (runs finalized this session), keyed so a
  // run is never double-counted.
  const committedTokensRef = useRef(0)
  const countedRunsRef = useRef<Set<string>>(new Set())

  const isRunning = run?.status === 'running'

  const persistSession = useCallback((sid: string) => {
    setSessionId(sid)
    try {
      localStorage.setItem(SESSION_STORAGE_KEY, sid)
    } catch {
      // private mode — session survives in memory only
    }
  }, [])

  const applyArtefact = useCallback((runId: string, kind: string, url: string) => {
    const patch = (fields: Partial<RunView>) =>
      setRun(prev => (prev && prev.runId === runId ? { ...prev, ...fields } : prev))
    switch (kind) {
      case 'ga_svg':
        fetchArtefactText(url)
          .then(svg => patch({ svgMarkup: svg }))
          .catch(() => {})
        break
      case 'ga_dxf':
        patch({ dxfUrl: url })
        break
      case 'calc_sheet':
        fetchArtefactJson<CalcSheetData>(url)
          .then(sheet => patch({ calcSheet: sheet }))
          .catch(() => {})
        break
      case 'compliance':
        fetchArtefactJson<ComplianceData>(url)
          .then(compliance => patch({ compliance }))
          .catch(() => {})
        break
      case 'proof_memo':
        fetchArtefactText(url)
          .then(memo => patch({ memoMarkdown: memo }))
          .catch(() => {})
        break
      case 'bmd_svg':
        fetchArtefactText(url)
          .then(svg => patch({ bmdSvg: svg }))
          .catch(() => {})
        break
      case 'sfd_svg':
        fetchArtefactText(url)
          .then(svg => patch({ sfdSvg: svg }))
          .catch(() => {})
        break
      case 'model_glb':
        patch({ glbUrl: url })
        break
      case 'model_step':
        patch({ stepUrl: url })
        break
      default:
        break
    }
  }, [])

  const loadRunArtefacts = useCallback(
    (runId: string, artefacts: ArtefactRecord[] | null | undefined) => {
      for (const artefact of artefacts ?? []) applyArtefact(runId, artefact.kind, artefact.url)
    },
    [applyArtefact],
  )

  const refreshTurns = useCallback(async (sid: string) => {
    try {
      const listing = await listDesigns({ sessionId: sid })
      setTurns(listing.runs)
    } catch {
      // listing refresh is cosmetic — the live view already has the run
    }
  }, [])

  const commitSessionTokens = useCallback((runId: string, tokens: number) => {
    if (countedRunsRef.current.has(runId)) return
    countedRunsRef.current.add(runId)
    committedTokensRef.current += tokens
    setSessionTokens(committedTokensRef.current)
  }, [])

  const finalizeRun = useCallback(
    async (runId: string, sid: string) => {
      try {
        const snap = await getRunSnapshot(runId)
        setRun(prev => {
          if (!prev || prev.runId !== runId) return prev
          const final = viewFromSnapshot(snap)
          return {
            ...final,
            componentType: final.componentType ?? prev.componentType ?? null,
            typeSummary: final.typeSummary ?? prev.typeSummary ?? null,
            svgMarkup: prev.svgMarkup,
            calcSheet: prev.calcSheet ?? final.calcSheet,
            compliance: prev.compliance ?? final.compliance,
            memoMarkdown: prev.memoMarkdown,
            bmdSvg: prev.bmdSvg,
            sfdSvg: prev.sfdSvg,
            glbUrl: prev.glbUrl ?? final.glbUrl,
            stepUrl: prev.stepUrl ?? final.stepUrl,
            verdict: final.verdict ?? prev.verdict,
            narration: terminalNarration(snap.status) ?? prev.narration,
          }
        })
        if (snap.duration_ms != null) setElapsedMs(snap.duration_ms)
        const snapTokens =
          (snap.tokens?.prompt_tokens ?? 0) + (snap.tokens?.completion_tokens ?? 0)
        if (snapTokens > 0) commitSessionTokens(runId, snapTokens)
        loadRunArtefacts(runId, snap.artefacts)
      } catch {
        // snapshot fetch failure — the SSE-built state stands
      }
      await refreshTurns(sid)
    },
    [commitSessionTokens, loadRunArtefacts, refreshTurns],
  )

  const applyLiveSnapshot = useCallback(
    (snap: RunSnapshot) => {
      setRun(prev => {
        if (prev && prev.runId !== snap.run_id) return prev
        const next = viewFromSnapshot(snap)
        return {
          ...next,
          componentType: next.componentType ?? prev?.componentType ?? null,
          typeSummary: next.typeSummary ?? prev?.typeSummary ?? null,
          svgMarkup: prev?.svgMarkup ?? null,
          calcSheet: prev?.calcSheet ?? next.calcSheet,
          compliance: prev?.compliance ?? next.compliance,
          memoMarkdown: prev?.memoMarkdown ?? null,
          bmdSvg: prev?.bmdSvg ?? null,
          sfdSvg: prev?.sfdSvg ?? null,
          glbUrl: prev?.glbUrl ?? next.glbUrl,
          stepUrl: prev?.stepUrl ?? next.stepUrl,
          verdict: next.verdict ?? prev?.verdict ?? null,
          narration: prev?.narration || next.narration,
        }
      })
      loadRunArtefacts(snap.run_id, snap.artefacts)
    },
    [loadRunArtefacts],
  )

  const openStream = useCallback(
    (runId: string, sid: string) => {
      subscriptionRef.current?.close()
      subscriptionRef.current = subscribeToRun(runEventsUrl(runId), {
        onSnapshot: applyLiveSnapshot,
        onStep: event => {
          elapsedBaseRef.current = { baseMs: event.elapsed_ms, wallStart: Date.now() }
          setRun(prev => {
            if (!prev || prev.runId !== runId) return prev
            const current = prev.steps[event.step]
            if (
              current &&
              (current.status === 'done' || current.status === 'failed') &&
              event.status !== 'done' &&
              event.status !== 'failed'
            ) {
              return prev
            }
            const steps = {
              ...prev.steps,
              [event.step]: { name: event.step, status: event.status, detail: event.detail ?? null },
            }
            return { ...prev, steps }
          })
        },
        onNarration: event => {
          setRun(prev => (prev && prev.runId === runId ? { ...prev, narration: event.text } : prev))
        },
        onWarning: event => {
          setRun(prev =>
            prev && prev.runId === runId ? { ...prev, warnings: [...prev.warnings, event.message] } : prev,
          )
        },
        onClarification: event => {
          setRun(prev => (prev && prev.runId === runId ? { ...prev, clarificationQuestion: event.question } : prev))
        },
        onArtefact: event => {
          applyArtefact(runId, event.kind, event.url)
        },
        onTokens: event => {
          setRun(prev =>
            prev && prev.runId === runId
              ? {
                  ...prev,
                  runTokens: (event.prompt_tokens ?? 0) + (event.completion_tokens ?? 0),
                  runCostUsd: event.cost_usd ?? 0,
                }
              : prev,
          )
          setSessionCostUsd(event.session_total_cost_usd ?? 0)
        },
        onDone: event => {
          setRun(prev =>
            prev && prev.runId === runId
              ? {
                  ...prev,
                  status: event.status,
                  verdict: event.verdict ?? prev.verdict,
                  narration: terminalNarration(event.status) ?? prev.narration,
                }
              : prev,
          )
          void finalizeRun(runId, sid)
        },
        onRunError: event => {
          setRun(prev =>
            prev && prev.runId === runId ? { ...prev, status: 'failed', errorMessage: event.message } : prev,
          )
          void finalizeRun(runId, sid)
        },
        onConnectionDrop: () => {
          if (runStatusRef.current !== 'running') return
          getRunSnapshot(runId)
            .then(snap => {
              applyLiveSnapshot(snap)
              if (snap.status !== 'running') {
                subscriptionRef.current?.close()
                void finalizeRun(runId, sid)
              }
            })
            .catch(() => {
              // server unreachable — EventSource keeps retrying
            })
        },
        onReconnected: () => setToast('Reconnected — live updates resumed'),
      })
    },
    [applyArtefact, applyLiveSnapshot, finalizeRun],
  )

  const beginLiveRun = useCallback(
    (runId: string, sid: string, prompt: string, componentType: string | null) => {
      elapsedBaseRef.current = { baseMs: 0, wallStart: Date.now() }
      setElapsedMs(0)
      // NOTE (tab-yank fix, spec/ui.md "Tab / stage focus rule"): we deliberately
      // do NOT reset the active stage/panel here. A refine run leaves the user on
      // whatever stage/panel they were watching; the Stage Rail lights its
      // progress indicators from run.steps instead.
      setRun({
        runId,
        prompt,
        status: 'running',
        componentType,
        typeSummary: null,
        steps: initialSteps(),
        narration: '',
        warnings: [],
        clarificationQuestion: null,
        svgMarkup: null,
        dxfUrl: null,
        calcSheet: null,
        compliance: null,
        memoMarkdown: null,
        bmdSvg: null,
        sfdSvg: null,
        glbUrl: null,
        stepUrl: null,
        suggestions: [],
        verdict: null,
        runTokens: 0,
        runCostUsd: 0,
        errorMessage: null,
        startedAt: new Date().toISOString(),
        durationMs: null,
      })
      setTurns(prev => [
        {
          run_id: runId,
          session_id: sid,
          prompt,
          status: 'running',
          verdict: null,
          params_summary: null,
          cost_usd: null,
          started_at: new Date().toISOString(),
          duration_ms: null,
        },
        ...prev,
      ])
      openStream(runId, sid)
    },
    [openStream],
  )

  const submitPrompt = useCallback(
    async (rawPrompt: string) => {
      const prompt = rawPrompt.trim()
      if (!prompt) {
        setFormError('Type a design request first — the placeholder shows a complete example.')
        return
      }
      if (submitting || runStatusRef.current === 'running') return
      setSubmitting(true)
      setFormError(null)
      // Documented, non-jarring transition: submitting from the New-design entry
      // or the Define stage advances to Overview once artefacts begin. This is an
      // explicit user action, never a mid-watch reset.
      const wasEntry = run === null
      try {
        let sid = sessionId
        if (!sid) {
          sid = (await createSession()).session_id
          persistSession(sid)
        }
        const pickedType = selectedComponent
        let response
        try {
          response = await submitDesign(sid, prompt, pickedType)
        } catch (error) {
          if (error instanceof ApiError && error.status === 404) {
            sid = (await createSession()).session_id
            persistSession(sid)
            setTurns([])
            setSessionCostUsd(0)
            response = await submitDesign(sid, prompt, pickedType)
          } else {
            throw error
          }
        }
        setPromptValue('')
        if (wasEntry) setStage('overview')
        beginLiveRun(response.run_id, sid, prompt, pickedType)
      } catch (error) {
        if (error instanceof ApiError) {
          if (error.code === 'RUN_ACTIVE') {
            setFormError('A run is already in progress in this session — wait for it to finish.')
          } else if (error.code === 'EMPTY_PROMPT') {
            setFormError('Type a design request first — the placeholder shows a complete example.')
          } else if (error.code === 'UNKNOWN_COMPONENT') {
            setFormError('That component is not available yet — pick an available one or let the agent decide.')
          } else {
            setFormError(error.message)
          }
        } else {
          setFormError('Something went wrong submitting the request — try again.')
        }
      } finally {
        setSubmitting(false)
      }
    },
    [beginLiveRun, persistSession, run, selectedComponent, sessionId, submitting],
  )

  const loadPastRun = useCallback(
    async (runId: string) => {
      if (runStatusRef.current === 'running') return
      try {
        const snap = await getRunSnapshot(runId)
        setRun(viewFromSnapshot(snap))
        setElapsedMs(snap.duration_ms ?? 0)
        // Opening a record is an explicit user action — land on the Overview.
        setStage('overview')
        loadRunArtefacts(runId, snap.artefacts)
      } catch {
        setToast('Could not load that run — try again')
      }
    },
    [loadRunArtefacts],
  )

  const handleNewDesign = useCallback(() => {
    if (runStatusRef.current === 'running') return
    setRun(null)
    setStage('overview')
    setDesignPanel('drawing')
    setSelectedComponent(null)
    setPromptValue('')
    setFormError(null)
  }, [])

  useEffect(() => {
    let cancelled = false
    async function rehydrate() {
      let sid: string | null = null
      try {
        sid = localStorage.getItem(SESSION_STORAGE_KEY)
      } catch {
        sid = null
      }
      if (!sid) {
        setBooting(false)
        return
      }
      try {
        const listing = await listDesigns({ sessionId: sid })
        if (cancelled) return
        setSessionId(sid)
        setTurns(listing.runs)
        setSessionCostUsd(listing.runs.reduce((sum, r) => sum + (r.cost_usd ?? 0), 0))
        const latest = listing.runs[0]
        if (latest) {
          const snap = await getRunSnapshot(latest.run_id)
          if (cancelled) return
          setRun(viewFromSnapshot(snap))
          loadRunArtefacts(snap.run_id, snap.artefacts)
          if (snap.status === 'running') {
            const startedMs = snap.started_at ? Date.now() - Date.parse(snap.started_at) : 0
            elapsedBaseRef.current = { baseMs: Math.max(startedMs, 0), wallStart: Date.now() }
            openStream(snap.run_id, sid)
          } else {
            setElapsedMs(snap.duration_ms ?? 0)
          }
        }
      } catch {
        try {
          localStorage.removeItem(SESSION_STORAGE_KEY)
        } catch {
          // ignore
        }
      } finally {
        if (!cancelled) setBooting(false)
      }
    }
    void rehydrate()
    return () => {
      cancelled = true
      subscriptionRef.current?.close()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!isRunning) return
    const id = setInterval(() => {
      const base = elapsedBaseRef.current
      setElapsedMs(base.baseMs + (Date.now() - base.wallStart))
    }, 500)
    return () => clearInterval(id)
  }, [isRunning, run?.runId])

  useEffect(() => {
    if (!toast) return
    const id = setTimeout(() => setToast(null), 4000)
    return () => clearTimeout(id)
  }, [toast])

  useEffect(() => {
    let cancelled = false
    listComponents()
      .then(cat => {
        if (!cancelled) setComponents(cat.components)
      })
      .catch(() => {
        // catalogue unavailable — picker stays hidden, auto-detect remains
      })
    return () => {
      cancelled = true
    }
  }, [])

  const componentsById = useMemo(
    () => Object.fromEntries(components.map(c => [c.type_id, c])) as Record<string, ComponentCard>,
    [components],
  )
  const selectedCard = selectedComponent ? componentsById[selectedComponent] ?? null : null

  const detectedDisplayName =
    selectedComponent === null &&
    run?.componentType &&
    (run.steps.Understand.status === 'active' || run.steps.Understand.status === 'done')
      ? componentsById[run.componentType]?.display_name ?? run.componentType.replace(/_/g, ' ')
      : null

  const latestTurn = turns[0] ?? null
  const runIsLatest = !latestTurn || run?.runId === latestTurn.run_id

  const pendingQuestion = (() => {
    if (run?.status === 'needs_input' && run.clarificationQuestion && runIsLatest) return run.clarificationQuestion
    return null
  })()

  const promptMode: PromptMode = pendingQuestion
    ? 'answer'
    : run?.status === 'completed' || turns.some(t => t.status === 'completed')
      ? 'refine'
      : 'design'

  const promptDisabled = submitting || isRunning

  // Records for the AppShell left rail (TurnHistory + Library merged & elevated).
  const records: DesignRecordSummary[] = useMemo(
    () =>
      turns.map(t => ({
        id: t.run_id,
        promptSummary: t.prompt,
        componentLabel: t.params_summary ?? 'Design',
        cost: t.cost_usd ?? 0,
        status: t.status,
        verdict: t.verdict ?? null,
      })),
    [turns],
  )

  const suggestions = run?.status === 'completed' ? run.suggestions : []

  const handleTryAgain = () => {
    if (run) setPromptValue(run.prompt)
    document.getElementById('prompt-input')?.focus()
  }

  const handleSuggestionPick = (text: string) => {
    setPromptValue(text)
    setFormError(null)
    document.getElementById('prompt-input')?.focus()
  }

  const progress: Record<'define' | 'design' | 'review', StageProgress> = run
    ? {
        define: stageProgress(run.steps, ['Understand', 'Extract']),
        design: stageProgress(run.steps, ['Analyse', 'Check', 'Draw']),
        review: stageProgress(run.steps, ['Review']),
      }
    : { define: 'pending', design: 'pending', review: 'pending' }

  // ------------------------------------------------------------------ Define
  const defineStage = (
    <div className="space-y-4">
      {components.length > 0 && (
        <div className="rounded-2xl border border-neutral-800 bg-neutral-950 p-5">
          <ComponentPicker
            components={components}
            activeTypeId={selectedComponent}
            onSelect={setSelectedComponent}
            disabled={promptDisabled}
          />
        </div>
      )}
      <DetectedTypeChip
        displayName={detectedDisplayName}
        onSwitch={() => setStage('define')}
        disabled={isRunning}
      />
      <SuggestionChips suggestions={suggestions} onPick={handleSuggestionPick} disabled={promptDisabled} />
      <div className="rounded-2xl border border-neutral-800 bg-neutral-950 p-5">
        <PromptPanel
          value={promptValue}
          onChange={value => {
            setPromptValue(value)
            if (formError) setFormError(null)
          }}
          onSubmit={() => void submitPrompt(promptValue)}
          mode={promptMode}
          disabled={promptDisabled}
          disabledReason={isRunning ? 'A design run is in progress — the prompt re-opens when it finishes.' : null}
          formError={formError}
          clarificationQuestion={pendingQuestion}
          placeholder={selectedCard?.example_prompt || CANONICAL_PROMPT}
          hint={
            selectedCard
              ? `Designing a ${selectedCard.display_name}. ${selectedCard.summary}`
              : 'The agent auto-detects the component — or pick one above.'
          }
        />
      </div>
    </div>
  )

  // ------------------------------------------------------------------ Design
  const DESIGN_PANELS: { id: DesignPanel; label: string }[] = [
    { id: 'drawing', label: 'Drawing' },
    { id: 'calc', label: 'Calc Sheet' },
    { id: '3d', label: '3D Model' },
  ]
  const designStage = (
    <div className="flex min-h-[28rem] flex-1 flex-col gap-4">
      <div role="tablist" aria-label="Design artefacts" className="inline-flex gap-1 self-start rounded-lg border border-neutral-800 bg-neutral-900 p-1">
        {DESIGN_PANELS.map(p => {
          const active = p.id === designPanel
          return (
            <button
              key={p.id}
              type="button"
              role="tab"
              data-testid={`design-panel-${p.id}`}
              aria-selected={active}
              onClick={() => setDesignPanel(p.id)}
              className={`rounded-md px-4 py-2 text-sm font-semibold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-400 ${
                active ? 'bg-indigo-600 text-white' : 'text-neutral-300 hover:bg-neutral-800 hover:text-neutral-100'
              }`}
            >
              {p.label}
            </button>
          )
        })}
      </div>
      <div className="min-h-0 flex-1 rounded-xl bg-white p-4 shadow-sm">
        {designPanel === 'drawing' && (
          <DrawingViewer
            svgMarkup={run?.svgMarkup ?? null}
            dxfUrl={run?.dxfUrl ?? null}
            isRunning={isRunning}
            drawActive={run?.steps.Draw.status === 'active'}
            runFailed={run?.status === 'failed'}
            hasRun={!!run}
          />
        )}
        {designPanel === 'calc' && (
          <CalcSheet
            sheet={run?.calcSheet ?? null}
            isRunning={isRunning}
            composing={run?.steps.Analyse.status === 'active' || run?.steps.Check.status === 'active'}
            runFailed={run?.status === 'failed'}
            hasRun={!!run}
          />
        )}
        {designPanel === '3d' && (
          <Model3DViewer
            glbUrl={run?.glbUrl ?? null}
            stepUrl={run?.stepUrl ?? null}
            isRunning={isRunning}
            runFailed={run?.status === 'failed'}
            hasRun={!!run}
          />
        )}
      </div>
    </div>
  )

  // ------------------------------------------------------------------ Review
  const reviewStage = (
    <div className="rounded-xl bg-white p-5 shadow-sm">
      <ProofCheckPanel
        compliance={run?.compliance ?? null}
        memoMarkdown={run?.memoMarkdown ?? null}
        bmdSvg={run?.bmdSvg ?? null}
        sfdSvg={run?.sfdSvg ?? null}
        verdict={run?.verdict ?? null}
        isRunning={isRunning}
        reviewActive={run?.steps.Review.status === 'active'}
        runFailed={run?.status === 'failed'}
        hasRun={!!run}
      />
    </div>
  )

  // ---------------------------------------------------------------- Overview
  const overviewStage = (
    <OverviewPanel
      verdict={run?.verdict ?? null}
      componentType={run?.componentType ?? null}
      componentDisplayName={run?.componentType ? componentsById[run.componentType]?.display_name ?? null : null}
      codes={run?.componentType ? componentsById[run.componentType]?.codes ?? [] : []}
      typeSummary={run?.typeSummary ?? null}
      svgMarkup={run?.svgMarkup ?? null}
      onOpenDrawing={() => {
        setDesignPanel('drawing')
        setStage('design')
      }}
      runTokens={run?.runTokens ?? 0}
      runCostUsd={run?.runCostUsd ?? 0}
      createdAt={run?.startedAt ?? null}
      durationMs={run?.durationMs ?? null}
      hasRun={!!run}
      isRunning={isRunning}
    />
  )

  const stageContent = (() => {
    switch (stage) {
      case 'overview':
        return overviewStage
      case 'define':
        return defineStage
      case 'design':
        return designStage
      case 'review':
        return reviewStage
      case 'simulate':
        return <StageStub stage="simulate" />
      case 'test':
        return <StageStub stage="test" />
      case 'approve':
        return <StageStub stage="approve" />
      default:
        return overviewStage
    }
  })()

  // --------------------------------------------------------------- Workspace
  const newDesignEntry = (
    <section className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-8 py-6">
      <div className="space-y-3 text-center">
        <h2 className="text-3xl font-bold leading-tight text-neutral-100">
          Describe the component you need — the platform designs and proof-checks it
        </h2>
        <p className="mx-auto max-w-2xl text-lg leading-relaxed text-neutral-400">
          Describe the crossing or member in one sentence. The platform plans, extracts the parameters, runs the full IR
          load checks, drafts a dimensioned GA drawing (download as genuine DXF), builds an interactive 3D model with a
          STEP download, and proof-checks its own work with a clause-cited memo and verdict.
        </p>
      </div>

      <div className="rounded-2xl border border-neutral-800 bg-neutral-950 p-6">
        <PromptPanel
          value={promptValue}
          onChange={value => {
            setPromptValue(value)
            if (formError) setFormError(null)
          }}
          onSubmit={() => void submitPrompt(promptValue)}
          mode="design"
          disabled={submitting}
          disabledReason={null}
          formError={formError}
          clarificationQuestion={null}
          placeholder={selectedCard?.example_prompt || CANONICAL_PROMPT}
          hint={
            selectedCard
              ? `Designing a ${selectedCard.display_name}. ${selectedCard.summary}`
              : 'The agent auto-detects the component — or pick one from the gallery below.'
          }
        />
        <button
          type="button"
          data-testid="hero-starter"
          onClick={() => void submitPrompt(CANONICAL_PROMPT)}
          disabled={submitting}
          className="mt-4 w-full rounded-xl border border-indigo-500/40 bg-indigo-950/30 px-5 py-4 text-left transition-colors hover:border-indigo-400 hover:bg-indigo-900/30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-400 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <span className="block text-xs font-semibold uppercase tracking-wide text-indigo-300">
            Run the canonical example
          </span>
          <span className="mt-1.5 block font-mono text-base leading-relaxed text-neutral-200">{CANONICAL_PROMPT}</span>
        </button>
      </div>

      {components.length > 0 && (
        <div className="rounded-2xl border border-neutral-800 bg-neutral-950 p-6">
          <ComponentPicker
            components={components}
            activeTypeId={selectedComponent}
            onSelect={setSelectedComponent}
            disabled={submitting}
          />
        </div>
      )}
    </section>
  )

  const openWorkspace = (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <StageRail active={stage} onSelect={setStage} progress={progress} />

      {run?.status === 'failed' && (
        <div
          data-testid="error-banner"
          role="alert"
          className="rounded-xl border border-red-600 bg-red-950/40 px-5 py-4"
        >
          <p className="text-lg font-semibold text-red-300">The run failed</p>
          <p className="mt-1 text-base leading-relaxed text-red-200">
            {run.errorMessage ?? 'The agent stopped before completing the design.'}
          </p>
          <button
            type="button"
            onClick={handleTryAgain}
            className="mt-3 rounded-lg bg-red-700 px-4 py-2 text-base font-semibold text-white hover:bg-red-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-500"
          >
            Try again
          </button>
        </div>
      )}

      {/* Live run progress band — always visible while a design is open so
          feedback never depends on the active stage (never yanks focus). */}
      {run && (
        <section
          aria-label="Run progress"
          className="space-y-3 rounded-xl border border-neutral-800 bg-neutral-900 p-4"
        >
          <StepTracker steps={run.steps} runId={run.runId} elapsedMs={elapsedMs} isRunning={isRunning} />
          {(run.narration || run.warnings.length > 0) && (
            <StatusLine text={run.narration} warnings={run.warnings} />
          )}
        </section>
      )}

      <div className="flex min-h-0 flex-1 flex-col">{stageContent}</div>
    </div>
  )

  const workspace = booting ? (
    <div className="flex flex-1 items-center justify-center">
      <p className="text-lg text-neutral-400">Restoring session…</p>
    </div>
  ) : run ? (
    openWorkspace
  ) : (
    newDesignEntry
  )

  return (
    <>
      <AppShell
        tokens={{
          runTokens: run?.runTokens ?? 0,
          runCost: run?.runCostUsd ?? 0,
          sessionTokens: sessionTokens + (isRunning ? run?.runTokens ?? 0 : 0),
          sessionCost: sessionCostUsd,
        }}
        records={records}
        activeRecordId={run?.runId ?? null}
        onSelectRecord={runId => void loadPastRun(runId)}
        onNewDesign={handleNewDesign}
      >
        {workspace}
      </AppShell>

      {toast && (
        <div
          role="status"
          className="fixed bottom-6 right-6 rounded-lg bg-neutral-800 px-4 py-2.5 text-base text-neutral-100 shadow-lg"
        >
          {toast}
        </div>
      )}
    </>
  )
}
