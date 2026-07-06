import type { RuntimeEvent, TaskUpdateEvent } from '../types'
import { API_BASE } from '../api/client'

let lastEventId: string | null = null

type RuntimeSseEvent = Record<string, unknown> & {
  data?: unknown
  payload?: unknown
  type?: string
  event_type?: string
  event_id?: string
  id?: string
  timestamp?: number
  created_at?: string
  correlation_id?: string
  run_id?: string
}

function eventPayload(event: RuntimeSseEvent): Record<string, unknown> {
  if (event.type === 'snapshot' && event.data && typeof event.data === 'object' && !Array.isArray(event.data)) {
    return {}
  }
  if (event.data && typeof event.data === 'object' && !Array.isArray(event.data)) {
    return event.data as Record<string, unknown>
  }
  if (event.payload && typeof event.payload === 'object' && !Array.isArray(event.payload)) {
    return event.payload as Record<string, unknown>
  }
  return {}
}

function eventType(event: RuntimeSseEvent, payload: Record<string, unknown>): string {
  return String(event.type || event.event_type || payload.type || '')
}

function normalizeRuntimeEvent(event: RuntimeSseEvent): RuntimeEvent {
  const payload = eventPayload(event)
  const type = eventType(event, payload)
  const timestamp = typeof event.timestamp === 'number' ? event.timestamp : Date.parse(String(event.created_at || ''))
  return {
    id: String(event.id || event.event_id || ''),
    timestamp: Number.isFinite(timestamp) ? timestamp : Date.now(),
    created_at: typeof event.created_at === 'string' ? event.created_at : undefined,
    type,
    run_id: String(event.run_id || event.correlation_id || ''),
    data: {
      ...payload,
      type: String(payload.type || type),
      session_id: String(payload.session_id || event.session_id || ''),
    } as RuntimeEvent['data'],
  }
}

export function useSessionEvents(
  onTaskUpdate: (event: TaskUpdateEvent) => void,
  onSnapshot: (tasks: Record<string, { status: string; progress: number; total: number; message: string }>) => void,
  onRuntimeEvent?: (event: RuntimeEvent) => void,
) {
  let abortController: AbortController | null = null
  let retryTimer: ReturnType<typeof setTimeout> | null = null
  let retryCount = 0
  const BASE_DELAY = 1000
  let currentSessionId: string | null = null

  function getRetryDelay(): number {
    const delay = Math.min(BASE_DELAY * Math.pow(2, retryCount), 30000)
    retryCount++
    return delay
  }

  function resetRetry() {
    retryCount = 0
  }

  function clearRetryTimer() {
    if (retryTimer !== null) {
      clearTimeout(retryTimer)
      retryTimer = null
    }
  }

  async function connect(sessionId?: string) {
    if (sessionId !== undefined) currentSessionId = sessionId
    console.log('[SSE] connecting, session_id:', currentSessionId)

    if (abortController) {
      abortController.abort()
    }
    abortController = new AbortController()

    try {
      const headers: Record<string, string> = {}
      if (lastEventId) {
        headers['Last-Event-ID'] = lastEventId
      }

      const url = currentSessionId
        ? `${API_BASE}/core/sessions/${encodeURIComponent(currentSessionId)}/events/live`
        : `${API_BASE}/core/events/live`

      const response = await fetch(url, {
        headers,
        signal: abortController.signal,
      })

      if (!response.ok || !response.body) {
        console.warn('[SSE] connect failed, status=', response.status, 'retrying...')
        retryTimer = setTimeout(() => connect(), getRetryDelay())
        return
      }

      console.log('[SSE] connected', currentSessionId ? `session=${currentSessionId}` : '(global)')
      resetRetry()

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('id: ')) {
            lastEventId = line.substring(4).trim()
          } else if (line.startsWith('data: ')) {
            const jsonStr = line.substring(6)
            try {
              const raw = JSON.parse(jsonStr) as RuntimeSseEvent
              const payload = eventPayload(raw)
              const type = eventType(raw, payload)
              const event = normalizeRuntimeEvent(raw)
              console.log('[SSE] recv:', type, payload.type, String(payload.session_id || '').slice(0, 8))

              if (type === 'task_progress' && payload.type === 'task_progress') {
                onTaskUpdate({
                  session_id: String(payload.session_id || ''),
                  status: String(payload.status || ''),
                  progress: Number(payload.progress || 0),
                  total: Number(payload.total || 0),
                  message: String(payload.message || ''),
                  task_type: typeof payload.task_type === 'string' ? payload.task_type : undefined,
                  strategy: typeof payload.strategy === 'string' ? payload.strategy : undefined,
                })
              } else if (type === 'snapshot') {
                onSnapshot(raw.data as Record<string, { status: string; progress: number; total: number; message: string }>)
              } else if (
                ['task_started', 'task_progress', 'checkpoint_required', 'task_completed', 'task_failed'].includes(type) &&
                onRuntimeEvent
              ) {
                onRuntimeEvent(event)
              } else if (
                onRuntimeEvent &&
                payload.type &&
                typeof payload.type === 'string' &&
                payload.type.startsWith('artist_')
              ) {
                onRuntimeEvent(event)
              }
            } catch {
              /* ignore parse errors */
            }
          }
        }
      }

      console.log('[SSE] disconnected (stream ended), reconnecting...')
      retryTimer = setTimeout(() => connect(), getRetryDelay())
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === 'AbortError') {
        console.log('[SSE] disconnected (aborted)')
      } else {
        console.warn('[SSE] disconnected reason:', e instanceof Error ? e.message : e, 'reconnecting...')
        retryTimer = setTimeout(() => connect(), getRetryDelay())
      }
    }
  }

  function disconnect() {
    clearRetryTimer()
    abortController?.abort()
    abortController = null
  }

  return { connect, disconnect }
}
