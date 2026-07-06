import { createSessionMapper, createMessageMapper, type CoreSessionRawLike, type CoreMessageRawLike, type CoreRuntimeEvent } from '@lamtools/ui'

const sessionMapper = createSessionMapper('__MEMBER_ID__-sessions')
const messageMapper = createMessageMapper()

const API_BASE = '/api'

async function request<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`)
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export async function listCoreSessions() {
  const raw = await request<CoreSessionRawLike[]>('/core/sessions')
  return raw.map(sessionMapper.toCore)
}

export async function createCoreSession(title?: string) {
  const res = await fetch(`${API_BASE}/core/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: title ?? 'New session' }),
  })
  const raw = await res.json()
  return sessionMapper.toCore(raw)
}

export async function getCoreMessages(sessionId: string) {
  const raw = await request<CoreMessageRawLike[]>(`/core/sessions/${sessionId}/messages`)
  return raw.map(messageMapper.toCore)
}

export async function createCoreMessage(sessionId: string, content: string) {
  const res = await fetch(`${API_BASE}/core/sessions/${sessionId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role: 'user', content }),
  })
  const raw = await res.json()
  return messageMapper.toCore(raw)
}

export async function getCoreEvents(sessionId: string): Promise<CoreRuntimeEvent[]> {
  return request<CoreRuntimeEvent[]>(`/core/sessions/${sessionId}/events`)
}
