import type { DesignListing, Preset, RunSnapshot, SessionInfo, SessionSummary, SubmitDesignResponse } from './types'

// All paths are root-relative on purpose: the app is served by FastAPI at /app,
// and a relative path would be corrupted by the basePath.

export class ApiError extends Error {
  readonly code: string
  readonly status: number

  constructor(code: string, message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    })
  } catch {
    throw new ApiError('NETWORK', 'Could not reach the server — is it running on localhost:8001?', 0)
  }

  let body: unknown = null
  try {
    body = await res.json()
  } catch {
    // non-JSON body handled below
  }

  if (!res.ok) {
    const detail = (body as { detail?: { code?: string; message?: string } } | null)?.detail
    throw new ApiError(
      detail?.code ?? 'HTTP_ERROR',
      detail?.message ?? `Request failed with status ${res.status}`,
      res.status,
    )
  }

  return (body as { data: T }).data
}

export function createSession(title?: string): Promise<SessionInfo> {
  return apiFetch<SessionInfo>('/api/sessions', {
    method: 'POST',
    body: JSON.stringify(title ? { title } : {}),
  })
}

export function submitDesign(sessionId: string, prompt: string): Promise<SubmitDesignResponse> {
  return apiFetch<SubmitDesignResponse>(`/api/sessions/${sessionId}/designs`, {
    method: 'POST',
    body: JSON.stringify({ prompt }),
  })
}

export function getRunSnapshot(runId: string): Promise<RunSnapshot> {
  return apiFetch<RunSnapshot>(`/api/designs/${runId}`)
}

export interface ListDesignsOptions {
  sessionId?: string
  limit?: number
  offset?: number
}

export function listDesigns(options: ListDesignsOptions = {}): Promise<DesignListing> {
  const query = new URLSearchParams()
  if (options.sessionId) query.set('session_id', options.sessionId)
  if (options.limit != null) query.set('limit', String(options.limit))
  if (options.offset != null) query.set('offset', String(options.offset))
  const qs = query.toString()
  return apiFetch<DesignListing>(`/api/designs${qs ? `?${qs}` : ''}`)
}

export function listSessions(): Promise<{ sessions: SessionSummary[] }> {
  return apiFetch<{ sessions: SessionSummary[] }>('/api/sessions')
}

export function listPresets(): Promise<{ presets: Preset[] }> {
  return apiFetch<{ presets: Preset[] }>('/api/presets')
}

export function updatePreset(
  presetId: string,
  body: { name?: string; values?: Record<string, string | number> },
): Promise<Preset> {
  return apiFetch<Preset>(`/api/presets/${presetId}`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
}

export function runEventsUrl(runId: string): string {
  return `/api/designs/${runId}/events`
}

export async function fetchArtefactText(url: string): Promise<string> {
  const res = await fetch(url)
  if (!res.ok) {
    throw new ApiError('ARTEFACT_FETCH', `Could not load artefact (${res.status})`, res.status)
  }
  return res.text()
}

export async function fetchArtefactJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) {
    throw new ApiError('ARTEFACT_FETCH', `Could not load artefact (${res.status})`, res.status)
  }
  return (await res.json()) as T
}
