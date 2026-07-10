import type {
  ArtefactEvent,
  ClarificationEvent,
  DoneEvent,
  NarrationEvent,
  RunErrorEvent,
  RunSnapshot,
  StepEvent,
  TokensEvent,
  WarningEvent,
} from './types'

export interface RunEventHandlers {
  onSnapshot?: (snapshot: RunSnapshot) => void
  onStep?: (event: StepEvent) => void
  onNarration?: (event: NarrationEvent) => void
  onWarning?: (event: WarningEvent) => void
  onClarification?: (event: ClarificationEvent) => void
  onArtefact?: (event: ArtefactEvent) => void
  onTokens?: (event: TokensEvent) => void
  onDone?: (event: DoneEvent) => void
  onRunError?: (event: RunErrorEvent) => void
  /** Transport-level drop (not a run failure). EventSource retries automatically. */
  onConnectionDrop?: () => void
  /** Fired when the stream re-opens after a drop. */
  onReconnected?: () => void
}

export interface RunSubscription {
  close: () => void
}

function parse<T>(raw: MessageEvent): T | null {
  try {
    return JSON.parse(raw.data) as T
  } catch {
    return null
  }
}

/**
 * Subscribes to a run's SSE stream. The server replays a `snapshot` on every
 * (re)connect and closes the stream after `done`/`error` — we close the
 * EventSource on those terminal events so it does not reconnect forever.
 */
export function subscribeToRun(eventsUrl: string, handlers: RunEventHandlers): RunSubscription {
  const source = new EventSource(eventsUrl)
  let dropped = false
  let closed = false

  const close = () => {
    if (!closed) {
      closed = true
      source.close()
    }
  }

  source.onopen = () => {
    if (dropped) {
      dropped = false
      handlers.onReconnected?.()
    }
  }

  // The api.md run-failure event is named `error`, which shares its DOM event
  // type with the EventSource transport error. A server-sent `error` arrives as
  // a MessageEvent carrying `data`; a transport drop carries none — that is the
  // only reliable way to tell them apart, so both flow through one listener.
  source.addEventListener('error', raw => {
    if (closed) return
    const data = (raw as MessageEvent).data as string | undefined
    if (data !== undefined) {
      const payload = parse<RunErrorEvent>(raw as MessageEvent)
      if (payload !== null) handlers.onRunError?.(payload)
      close()
      return
    }
    dropped = true
    handlers.onConnectionDrop?.()
  })

  const on = <T>(name: string, handler: ((event: T) => void) | undefined, terminal = false) => {
    source.addEventListener(name, raw => {
      const payload = parse<T>(raw as MessageEvent)
      if (payload !== null) handler?.(payload)
      if (terminal) close()
    })
  }

  on<RunSnapshot>('snapshot', handlers.onSnapshot)
  on<StepEvent>('step', handlers.onStep)
  on<NarrationEvent>('narration', handlers.onNarration)
  on<WarningEvent>('warning', handlers.onWarning)
  on<ClarificationEvent>('clarification', handlers.onClarification)
  on<ArtefactEvent>('artefact', handlers.onArtefact)
  on<TokensEvent>('tokens', handlers.onTokens)
  on<DoneEvent>('done', handlers.onDone, true)

  return { close }
}
