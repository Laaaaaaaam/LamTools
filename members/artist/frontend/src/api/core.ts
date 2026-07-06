/**
 * Core API client -- thin wrappers over /api/core endpoints.
 * Uses the shared axios instance from client.ts (baseURL '/api').
 *
 * Uses @lamtools/ui mappers for session/message transformation.
 */
import client from './client'
import type { CoreMessage, CoreRuntimeEvent } from '@lamtools/ui'
import {
  createSessionMapper,
  createMessageMapper,
  type CoreSessionRawLike,
  type CoreMessageRawLike,
} from '@lamtools/ui'

const sessionMapper = createSessionMapper('Artist-sessions')
const messageMapper = createMessageMapper()

export const listCoreSessions = () =>
  client.get<CoreSessionRawLike[]>('/core/sessions').then(res => res.data.map(sessionMapper.toCore))

export const createCoreSession = (title?: string) =>
  client.post<CoreSessionRawLike>('/core/sessions', { title: title ?? 'New Session' })
    .then(res => sessionMapper.toCore(res.data))

export const getCoreMessages = (sessionId: string) =>
  client.get<CoreMessageRawLike[]>(`/core/sessions/${sessionId}/messages`)
    .then(res => res.data.map(messageMapper.toCore))

export const createCoreMessage = (
  sessionId: string,
  content: string,
  role = 'user',
  message_type = 'text',
) =>
  client.post<CoreMessageRawLike>(`/core/sessions/${sessionId}/messages`, {
    content,
    role,
    message_type,
  }).then(res => messageMapper.toCore(res.data))

export const startCoreArtistTurn = (
  sessionId: string,
  content: string,
): Promise<CoreMessage> =>
  client.post(`/sessions/${sessionId}/artist-turn`, {
    session_id: sessionId,
    prompt: content,
    agent_persona: 'artist',
  }).then(() => ({
    id: `pending-${sessionId}-${Date.now()}`,
    role: 'user',
    content,
    timestamp: new Date().toISOString(),
    metadata: { pending: true },
  }))

// -- Events --

export const getCoreEvents = (sessionId: string) =>
  client.get<unknown[]>(`/core/sessions/${sessionId}/events`)
    .then(res => res.data.map((raw, i) => {
      const e = raw as Record<string, unknown>
      const timestamp = e.created_at != null ? String(e.created_at) : (
        typeof e.timestamp === 'number'
          ? new Date(e.timestamp).toISOString()
          : String(e.timestamp || new Date().toISOString())
      )
      return {
        id: e.id != null ? String(e.id) : `evt-${i}`,
        type: e.type != null ? String(e.type) : 'info',
        timestamp,
        data: e.data ?? raw,
      } as CoreRuntimeEvent
    }))

// -- Providers --

export interface CoreProvider {
  id: string
  kind: string | null
  name: string
  base_url: string | null
  default_model: string | null
  enabled: boolean
  billing_type: string | null
  unit_price: number | null
  currency: string | null
  vendor: { id: string; name: string } | null
  api_key_ref: string
}

export const listCoreProviders = () =>
  client.get<CoreProvider[]>('/core/providers')

// -- Usage (Artist product-side state) --

export interface CoreUsageTotal {
  total_cost: number
  currency: string
}

export const getCoreUsageTotal = (params?: {
  session_id?: string
  provider_id?: string
  currency?: string
}) => client.get<CoreUsageTotal>('/core/usage/total', { params })
