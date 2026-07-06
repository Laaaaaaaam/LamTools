import type { WriterAppEvent, WriterAppSnapshot } from './protocol.ts'

export interface JsonRpcRequest {
  id?: number | string
  method: string
  params?: Record<string, unknown>
}

export interface JsonRpcResponse {
  id?: number | string
  result?: Record<string, unknown>
  error?: { code: number; message: string; data?: unknown }
}

export interface JsonRpcClientResponse {
  id: number | string
  result: Record<string, unknown>
}

export interface WriterAppServerClientOptions {
  url: string
  clientInfo: { name: string; title?: string; version?: string }
  onEvent?: (event: WriterAppEvent) => void
  onSnapshot?: (snapshot: WriterAppSnapshot) => void
  onConnectionState?: (state: 'connecting' | 'open' | 'closed' | 'error') => void
}

export class WriterAppServerClosedError extends Error {
  constructor() {
    super('Writer App Server socket closed')
    this.name = 'AbortError'
  }
}

export class WriterAppServerClient {
  private socket: WebSocket | null = null
  private nextId = 1
  private pending = new Map<number | string, {
    resolve: (value: Record<string, unknown>) => void
    reject: (error: Error) => void
  }>()
  private serverRequestIds = new Map<string, number | string>()

  constructor(private readonly options: WriterAppServerClientOptions) {}

  async connect(params: { threadId?: string; lastSeenSeq?: number } = {}): Promise<void> {
    this.options.onConnectionState?.('connecting')
    this.socket = new WebSocket(this.options.url)
    await new Promise<void>((resolve, reject) => {
      if (!this.socket) {
        reject(new Error('WebSocket was not created'))
        return
      }
      this.socket.onopen = () => {
        this.options.onConnectionState?.('open')
        resolve()
      }
      this.socket.onerror = () => {
        this.options.onConnectionState?.('error')
        reject(new Error('Writer App Server socket failed'))
      }
      this.socket.onclose = () => {
        this.options.onConnectionState?.('closed')
      }
      this.socket.onmessage = (message) => this.handleMessage(message.data)
    })

    await this.request('initialize', {
      clientInfo: this.options.clientInfo,
      threadId: params.threadId,
      lastSeenSeq: params.lastSeenSeq,
    })
    this.notify('initialized', {})
  }

  close(): void {
    this.socket?.close()
    this.socket = null
    this.serverRequestIds.clear()
    for (const pending of this.pending.values()) {
      pending.reject(new WriterAppServerClosedError())
    }
    this.pending.clear()
  }

  request(method: string, params: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
    const id = this.nextId++
    const payload: JsonRpcRequest = { id, method, params }
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject })
      try {
        this.send(payload)
      } catch (error) {
        this.pending.delete(id)
        reject(error instanceof Error ? error : new Error(String(error)))
      }
    })
  }

  notify(method: string, params: Record<string, unknown> = {}): void {
    this.send({ method, params })
  }

  respondServerRequest(requestId: string, result: Record<string, unknown>): boolean {
    const rpcId = this.serverRequestIds.get(requestId)
    if (rpcId === undefined) return false
    this.serverRequestIds.delete(requestId)
    this.send({ id: rpcId, result })
    return true
  }

  private send(payload: JsonRpcRequest | JsonRpcClientResponse): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      throw new Error('Writer App Server socket is not open')
    }
    this.socket.send(JSON.stringify(payload))
  }

  private handleMessage(raw: string): void {
    const message = JSON.parse(raw) as JsonRpcResponse & { method?: string; params?: unknown }
    if (message.id !== undefined && typeof message.method === 'string') {
      if (message.params && typeof message.params === 'object') {
        const event = message.params as WriterAppEvent
        const requestId = typeof event.payload?.request_id === 'string' ? event.payload.request_id : String(message.id)
        this.serverRequestIds.set(requestId, message.id)
        this.options.onEvent?.(event)
      }
      return
    }

    if (message.id !== undefined) {
      const pending = this.pending.get(message.id)
      if (!pending) return
      this.pending.delete(message.id)
      if (message.error) {
        pending.reject(new Error(message.error.message))
      } else {
        pending.resolve(message.result ?? {})
      }
      return
    }

    if (typeof message.method === 'string' && message.params && typeof message.params === 'object') {
      if (message.method === 'thread/snapshot') {
        this.options.onSnapshot?.(message.params as WriterAppSnapshot)
        return
      }
      this.options.onEvent?.(message.params as WriterAppEvent)
    }
  }
}

export async function fetchAppServerToken(apiBase: string): Promise<string> {
  const response = await fetch(`${apiBase || ''}/api/app-server-token`)
  if (!response.ok) {
    throw new Error('Writer App Server token request failed')
  }
  const body = await response.json() as { token?: string }
  if (!body.token) {
    throw new Error('Writer App Server token response is missing token')
  }
  return body.token
}

export function appServerUrl(apiBase: string, token?: string): string {
  const base = apiBase || window.location.origin
  const url = new URL('/api/app-server', base)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  if (token) {
    url.searchParams.set('token', token)
  }
  return url.toString()
}
