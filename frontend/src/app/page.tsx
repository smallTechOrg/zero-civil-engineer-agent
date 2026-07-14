'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ArtefactTabs, { type TabId } from '@/components/ArtefactTabs'
import ComponentPicker from '@/components/ComponentPicker'
import DetectedTypeChip from '@/components/DetectedTypeChip'
import M00004ParamForm from '@/components/M00004ParamForm'
import PromptPanel, { CANONICAL_PROMPT, type PromptMode } from '@/components/PromptPanel'
import StatusLine from '@/components/StatusLine'
import StepTracker from '@/components/StepTracker'
import SuggestionChips from '@/components/SuggestionChips'
import TokenCostBadge from '@/components/TokenCostBadge'
import TurnHistory, { type TurnDetail } from '@/components/TurnHistory'
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
  isParamsDirectComponent,
  type ArtefactRecord,
  type CalcSheetData,
  type ComplianceData,
  type ComponentCard,
  type M00004Params,
  type RunListItem,
  type RunSnapshot,
  type RunStatus,
  type StepName,
  type StepState,
  type TypeSummary,
  type Verdict,
} from '@/lib/types'

const SESSION_STORAGE_KEY = 'culvert.session_id'

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
  m00004SheetUrl: string | null
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
      // Replayed skipped steps always show a neutral tag: stored details from
      // early-phase runs carried roadmap copy that must never render now.
      detail: s.status === 'skipped' ? 'Skipped for this run' : (s.detail ?? null),
    }
  }
  return steps
}

function terminalNarration(status: RunStatus): string | null {
  switch (status) {
    case 'completed':
      return 'Design complete — the drawing, calculation sheet and proof-check verdict are ready in the artefact tabs.'
    case 'needs_input':
      return 'The agent needs one more detail — answer the question in the session panel.'
    case 'out_of_scope':
      return 'This request is outside the demonstrator’s scope — the agent’s reply is in the session panel.'
    default:
      return null
  }
}

// The snapshot's checklist[] mirrors compliance.json items — use it as an
// instant fallback so a reload paints the matrix before the artefact fetch
// (which then overrides with the full compliance.json incl. fe_agreement_pct).
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
    m00004SheetUrl: snap.artefacts?.find(a => a.kind === 'm00004_sheet')?.url ?? null,
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
  }
}

export default function DesignStudio() {
  const [booting, setBooting] = useState(true)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [components, setComponents] = useState<ComponentCard[]>([])
  // null = "Let the agent decide" (auto-detect). Otherwise a registry type_id.
  const [selectedComponent, setSelectedComponent] = useState<string | null>(null)
  const [turns, setTurns] = useState<RunListItem[]>([])
  const [turnDetails, setTurnDetails] = useState<Record<string, TurnDetail>>({})
  const [run, setRun] = useState<RunView | null>(null)
  const [elapsedMs, setElapsedMs] = useState(0)
  const [sessionCostUsd, setSessionCostUsd] = useState(0)
  const [promptValue, setPromptValue] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [activeTab, setActiveTab] = useState<TabId>('drawing')
  const [toast, setToast] = useState<string | null>(null)
  // Bumped when a run starts/finishes so an open Library tab refreshes live.
  const [libraryVersion, setLibraryVersion] = useState(0)
  // First-visit hero offers "browse the library" — that forces the tabs view.
  const [tabsForced, setTabsForced] = useState(false)

  const subscriptionRef = useRef<RunSubscription | null>(null)
  const elapsedBaseRef = useRef({ baseMs: 0, wallStart: Date.now() })
  const runStatusRef = useRef<RunStatus | null>(null)
  runStatusRef.current = run?.status ?? null

  const isRunning = run?.status === 'running'

  const persistSession = useCallback((sid: string) => {
    setSessionId(sid)
    try {
      localStorage.setItem(SESSION_STORAGE_KEY, sid)
    } catch {
      // private mode — session survives in memory only
    }
  }, [])

  const storeTurnDetail = useCallback((snap: RunSnapshot) => {
    setTurnDetails(prev => ({
      ...prev,
      [snap.run_id]: {
        scopeMessage: snap.scope_message,
        clarificationQuestion: snap.clarification_question,
      },
    }))
  }, [])

  // Applies one artefact (live SSE event or snapshot record) to the run view.
  // Fetch failures are non-fatal: the owning tab keeps its waiting state.
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
      case 'm00004_sheet':
        // The PDF is served inline by the backend — only the URL is stored;
        // the Drawing tab's "Open M-00004 sheet (PDF)" button links to it.
        patch({ m00004SheetUrl: url })
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
        // The viewer streams the GLB itself — only the URL is stored here.
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

  const finalizeRun = useCallback(
    async (runId: string, sid: string) => {
      try {
        const snap = await getRunSnapshot(runId)
        storeTurnDetail(snap)
        setRun(prev => {
          if (!prev || prev.runId !== runId) return prev
          const final = viewFromSnapshot(snap)
          return {
            ...final,
            componentType: final.componentType ?? prev.componentType ?? null,
            typeSummary: final.typeSummary ?? prev.typeSummary ?? null,
            // Keep artefacts already streamed in — loadRunArtefacts refreshes them.
            svgMarkup: prev.svgMarkup,
            m00004SheetUrl: prev.m00004SheetUrl ?? final.m00004SheetUrl,
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
        loadRunArtefacts(runId, snap.artefacts)
      } catch {
        // snapshot fetch failure — the SSE-built state stands
      }
      await refreshTurns(sid)
      setLibraryVersion(v => v + 1)
    },
    [loadRunArtefacts, refreshTurns, storeTurnDetail],
  )

  const applyLiveSnapshot = useCallback(
    (snap: RunSnapshot) => {
      storeTurnDetail(snap)
      setRun(prev => {
        if (prev && prev.runId !== snap.run_id) return prev
        const next = viewFromSnapshot(snap)
        return {
          ...next,
          componentType: next.componentType ?? prev?.componentType ?? null,
          typeSummary: next.typeSummary ?? prev?.typeSummary ?? null,
          svgMarkup: prev?.svgMarkup ?? null,
          m00004SheetUrl: prev?.m00004SheetUrl ?? next.m00004SheetUrl,
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
    [loadRunArtefacts, storeTurnDetail],
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
            // Mirror src/graph/steps.py: a step already done/failed is never
            // downgraded by a later skipped/pending/active event, whatever
            // order the publisher emits in (regression guard F1).
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
      setActiveTab('drawing')
      setRun({
        runId,
        prompt,
        status: 'running',
        // Explicit pick is known immediately; auto-detect fills in from the snapshot.
        componentType,
        typeSummary: null,
        steps: initialSteps(),
        narration: '',
        warnings: [],
        clarificationQuestion: null,
        svgMarkup: null,
        dxfUrl: null,
        m00004SheetUrl: null,
        calcSheet: null,
        compliance: null,
        memoMarkdown: null,
        bmdSvg: null,
        sfdSvg: null,
        glbUrl: null,
        stepUrl: null,
        // Chips from the previous run clear the moment a new run starts.
        suggestions: [],
        verdict: null,
        runTokens: 0,
        runCostUsd: 0,
        errorMessage: null,
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
      setLibraryVersion(v => v + 1)
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
            // Stored session no longer exists (fresh database) — start a new one.
            sid = (await createSession()).session_id
            persistSession(sid)
            setTurns([])
            setTurnDetails({})
            setSessionCostUsd(0)
            response = await submitDesign(sid, prompt, pickedType)
          } else {
            throw error
          }
        }
        setPromptValue('')
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
    [beginLiveRun, persistSession, selectedComponent, sessionId, submitting],
  )

  // Params-direct submit for a standard-driven component (M-00004): sends the
  // typed `params` object with `component_type`; the graph bypasses the LLM
  // intake nodes (spec/capabilities/m00004-box-culvert.md). A short synthetic
  // prompt is stored only for the audit-trail / library row.
  const submitParams = useCallback(
    async (componentType: string, params: M00004Params) => {
      if (submitting || runStatusRef.current === 'running') return
      setSubmitting(true)
      setFormError(null)
      const prompt = `M-00004 standard box culvert ${params.clear_span_m}×${params.clear_height_m} m, fill ${params.cushion_m} m, surcharge ${params.surcharge_kn_m2} kN/m²`
      try {
        let sid = sessionId
        if (!sid) {
          sid = (await createSession()).session_id
          persistSession(sid)
        }
        const paramsPayload = params as unknown as Record<string, unknown>
        let response
        try {
          response = await submitDesign(sid, prompt, componentType, paramsPayload)
        } catch (error) {
          if (error instanceof ApiError && error.status === 404) {
            // Stored session no longer exists (fresh database) — start a new one.
            sid = (await createSession()).session_id
            persistSession(sid)
            setTurns([])
            setTurnDetails({})
            setSessionCostUsd(0)
            response = await submitDesign(sid, prompt, componentType, paramsPayload)
          } else {
            throw error
          }
        }
        beginLiveRun(response.run_id, sid, prompt, componentType)
      } catch (error) {
        if (error instanceof ApiError) {
          if (error.code === 'RUN_ACTIVE') {
            setFormError('A run is already in progress in this session — wait for it to finish.')
          } else if (error.code === 'PARAMS_INVALID') {
            setFormError(error.message || 'One or more parameters are out of range — adjust the highlighted fields.')
          } else if (error.code === 'PARAMS_REQUIRED') {
            setFormError('This standard component needs its parameters — fill the form and submit again.')
          } else if (error.code === 'UNKNOWN_COMPONENT') {
            setFormError('That component is not available yet — pick an available one.')
          } else {
            setFormError(error.message)
          }
        } else {
          setFormError('Something went wrong submitting the parameters — try again.')
        }
      } finally {
        setSubmitting(false)
      }
    },
    [beginLiveRun, persistSession, sessionId, submitting],
  )

  const loadPastRun = useCallback(
    async (runId: string) => {
      if (runStatusRef.current === 'running') return
      try {
        const snap = await getRunSnapshot(runId)
        storeTurnDetail(snap)
        setRun(viewFromSnapshot(snap))
        setElapsedMs(snap.duration_ms ?? 0)
        setActiveTab('drawing')
        loadRunArtefacts(runId, snap.artefacts)
      } catch {
        setToast('Could not load that run — try again')
      }
    },
    [loadRunArtefacts, storeTurnDetail],
  )

  // Reload / SSE-drop rehydration: restore the stored session, its turn
  // history, and — if a run is still live — re-subscribe to its stream.
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
          storeTurnDetail(snap)
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
        // Stale session (e.g. reset database) — start clean.
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

  // Live elapsed-time ticker; freezes when the run leaves `running`.
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

  // Component catalogue for the picker (GET /api/components). A fetch failure
  // is non-fatal — the picker simply hides and auto-detect still works.
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
  // A standard-driven (params-direct) component is form-only: its typed
  // parameter form replaces the NL prompt box (spec/ui.md → "Parameter form").
  const showParamForm = isParamsDirectComponent(selectedCard)

  // Auto-detect chip: only when the user did NOT pick explicitly, the run
  // classified a component, and Understand has started.
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
    if (latestTurn?.status === 'needs_input') return turnDetails[latestTurn.run_id]?.clarificationQuestion ?? null
    return null
  })()

  const promptMode: PromptMode = pendingQuestion
    ? 'answer'
    : run?.status === 'completed' || turns.some(t => t.status === 'completed')
      ? 'refine'
      : 'design'

  const promptDisabled = submitting || isRunning
  // The hero's one-click starter runs the canonical culvert prompt — hide it when
  // a params-direct component is picked so it never contradicts the shown form.
  const showHero = !booting && turns.length === 0 && !run && !tabsForced && !showParamForm

  const handleTryAgain = () => {
    if (run) setPromptValue(run.prompt)
    document.getElementById('prompt-input')?.focus()
  }

  // A chip only fills the prompt box — the user still presses Refine.
  const handleSuggestionPick = (text: string) => {
    setPromptValue(text)
    setFormError(null)
    document.getElementById('prompt-input')?.focus()
  }

  const suggestions = run?.status === 'completed' ? run.suggestions : []

  return (
    <div className="flex h-screen flex-col bg-slate-100 text-slate-900">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-700 bg-slate-900 px-6 py-3.5">
        <h1 className="text-xl font-bold tracking-tight text-white">IR Box Culvert Design &amp; Proof-Check Agent</h1>
        <TokenCostBadge
          runTokens={run?.runTokens ?? 0}
          runCostUsd={run?.runCostUsd ?? 0}
          sessionCostUsd={sessionCostUsd}
        />
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[24rem_minmax(0,1fr)]">
        <aside className="flex min-h-0 flex-col border-r border-slate-200 bg-slate-50" aria-label="Session panel">
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
            <ComponentPicker
              components={components}
              activeTypeId={selectedComponent}
              onSelect={setSelectedComponent}
              disabled={promptDisabled}
            />
            {components.length > 0 && <div className="border-t border-slate-200" />}
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Session</h2>
            <TurnHistory
              turns={turns}
              details={turnDetails}
              selectedRunId={run?.runId ?? null}
              onSelect={runId => void loadPastRun(runId)}
              selectionDisabled={isRunning}
            />
          </div>
          <div className="space-y-3 border-t border-slate-200 bg-white p-4">
            {showParamForm && selectedCard ? (
              <M00004ParamForm
                componentName={selectedCard.display_name}
                onSubmit={params => void submitParams(selectedCard.type_id, params)}
                disabled={promptDisabled}
                disabledReason={
                  isRunning ? 'A design run is in progress — the form re-opens when it finishes.' : null
                }
                submitting={submitting}
                serverError={formError}
              />
            ) : (
              <>
                <SuggestionChips suggestions={suggestions} onPick={handleSuggestionPick} disabled={promptDisabled} />
                <PromptPanel
                  value={promptValue}
                  onChange={value => {
                    setPromptValue(value)
                    if (formError) setFormError(null)
                  }}
                  onSubmit={() => void submitPrompt(promptValue)}
                  mode={promptMode}
                  disabled={promptDisabled}
                  disabledReason={
                    isRunning ? 'A design run is in progress — the prompt re-opens when it finishes.' : null
                  }
                  formError={formError}
                  clarificationQuestion={pendingQuestion}
                  placeholder={selectedCard?.example_prompt || CANONICAL_PROMPT}
                  hint={
                    selectedCard
                      ? `Designing a ${selectedCard.display_name}. ${selectedCard.summary}`
                      : 'The agent auto-detects the component — or pick one above.'
                  }
                />
              </>
            )}
          </div>
        </aside>

        <main className="flex min-h-0 flex-col gap-4 overflow-y-auto p-5">
          {run?.status === 'failed' && (
            <div
              data-testid="error-banner"
              role="alert"
              className="rounded-xl border border-red-300 bg-red-50 px-5 py-4"
            >
              <p className="text-lg font-semibold text-red-800">The run failed</p>
              <p className="mt-1 text-base leading-relaxed text-red-900">
                {run.errorMessage ?? 'The agent stopped before completing the design.'}
              </p>
              <button
                type="button"
                onClick={handleTryAgain}
                className="mt-3 rounded-lg bg-red-700 px-4 py-2 text-base font-semibold text-white hover:bg-red-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-700"
              >
                Try again
              </button>
            </div>
          )}

          {showHero ? (
            <section className="mx-auto flex max-w-2xl flex-1 flex-col items-center justify-center gap-6 text-center">
              <h2 className="text-3xl font-bold leading-tight text-slate-900">
                Design a single-cell RCC box culvert from one sentence
              </h2>
              <p className="text-lg leading-relaxed text-slate-700">
                Describe the crossing — clear span, height, cushion, gauge, loading standard — and watch the agent
                plan, extract the parameters, run the full IRS load checks, draft a dimensioned GA drawing you can
                download as genuine DXF, build an interactive 3D model with a STEP download, and proof-check its own
                design with a clause-cited memo and verdict.
              </p>
              <button
                type="button"
                data-testid="hero-starter"
                onClick={() => void submitPrompt(CANONICAL_PROMPT)}
                disabled={submitting}
                className="w-full max-w-xl rounded-xl border border-indigo-200 bg-white px-6 py-5 text-left shadow-sm transition-colors hover:border-indigo-400 hover:bg-indigo-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <span className="block text-sm font-semibold uppercase tracking-wide text-indigo-600">
                  Run the canonical example
                </span>
                <span className="mt-2 block font-mono text-base leading-relaxed text-slate-800">
                  {CANONICAL_PROMPT}
                </span>
              </button>
              <p className="text-base text-slate-500">
                Every run is stored in the design library with its verdict, cost and artefacts — replay any past
                design or tune the standards presets there.
              </p>
              <button
                type="button"
                data-testid="hero-library-link"
                onClick={() => {
                  setTabsForced(true)
                  setActiveTab('library')
                }}
                className="text-base font-semibold text-indigo-700 underline decoration-indigo-300 underline-offset-4 hover:text-indigo-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600"
              >
                Browse the design library →
              </button>
            </section>
          ) : (
            <>
              <section
                aria-label="Run progress"
                className="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
              >
                {booting ? (
                  <p className="text-lg text-slate-500">Restoring session…</p>
                ) : (
                  <>
                    <StepTracker
                      steps={run?.steps ?? initialSteps()}
                      runId={run?.runId ?? null}
                      elapsedMs={elapsedMs}
                      isRunning={isRunning}
                    />
                    <StatusLine text={run?.narration ?? ''} warnings={run?.warnings ?? []} />
                  </>
                )}
              </section>

              <DetectedTypeChip
                displayName={detectedDisplayName}
                onSwitch={() => {
                  document
                    .querySelector('[data-testid="component-picker"]')
                    ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                }}
                disabled={isRunning}
              />

              <section className="flex min-h-[28rem] flex-1 flex-col rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <ArtefactTabs
                  activeTab={activeTab}
                  onTabChange={setActiveTab}
                  componentType={run?.componentType ?? null}
                  typeSummary={run?.typeSummary ?? null}
                  svgMarkup={run?.svgMarkup ?? null}
                  dxfUrl={run?.dxfUrl ?? null}
                  m00004SheetUrl={run?.m00004SheetUrl ?? null}
                  calcSheet={run?.calcSheet ?? null}
                  calcComposing={run?.steps.Analyse.status === 'active' || run?.steps.Check.status === 'active'}
                  compliance={run?.compliance ?? null}
                  memoMarkdown={run?.memoMarkdown ?? null}
                  bmdSvg={run?.bmdSvg ?? null}
                  sfdSvg={run?.sfdSvg ?? null}
                  verdict={run?.verdict ?? null}
                  reviewActive={run?.steps.Review.status === 'active'}
                  isRunning={isRunning}
                  drawActive={run?.steps.Draw.status === 'active'}
                  runFailed={run?.status === 'failed'}
                  hasRun={!!run}
                  glbUrl={run?.glbUrl ?? null}
                  stepUrl={run?.stepUrl ?? null}
                  onSelectRun={runId => void loadPastRun(runId)}
                  activeRunId={run?.runId ?? null}
                  libraryRefreshKey={libraryVersion}
                />
              </section>
            </>
          )}
        </main>
      </div>

      {toast && (
        <div
          role="status"
          className="fixed bottom-6 right-6 rounded-lg bg-slate-900 px-4 py-2.5 text-base text-white shadow-lg"
        >
          {toast}
        </div>
      )}
    </div>
  )
}
