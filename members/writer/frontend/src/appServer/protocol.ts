export const WRITER_APP_SERVER_PROTOCOL_VERSION = 'writer.app_server.v1'

export interface WriterAppEvent {
  event_id: string
  protocol_version?: typeof WRITER_APP_SERVER_PROTOCOL_VERSION
  seq: number
  thread_id: string
  method: string
  payload: Record<string, unknown>
  created_at: string
  turn_id?: string | null
  item_id?: string | null
  parent_item_id?: string | null
  client_message_id?: string | null
}

export interface WriterAppSnapshot {
  thread_id: string
  snapshot_seq: number
  seen_event_ids?: string[]
  turns?: Record<string, WriterAppTurn>
  items?: Record<string, WriterAppItem>
  item_order?: string[]
  queue?: WriterAppQueueItem[]
  requests?: Record<string, WriterAppRequestState>
  artifacts?: Record<string, Record<string, unknown>>
  core?: WriterCoreSnapshot
  status?: WriterAppThreadStatus
}

export type WriterAppThreadStatus = 'idle' | 'running' | 'waiting' | 'completed' | 'failed'

export interface WriterTextInputItem {
  type: 'text'
  text: string
}

export interface WriterAttachmentInputItem {
  type: 'attachment'
  attachment_id: string
  filename?: string
  mime_type?: string
  preview_type?: string
  size?: number
}

export interface WriterSkillInputItem {
  type: 'skill'
  name: string
  source_text?: string
}

export type WriterInputItem = WriterTextInputItem | WriterAttachmentInputItem | WriterSkillInputItem

export interface WriterCommandCatalogItem {
  name: string
  title?: string
  description?: string
  icon?: string
  source?: 'core' | 'member' | string
  action?: 'insert_token' | 'run_action' | 'expand_on_send' | string
  accepts_args?: boolean
}

export interface WriterAppTurn {
  turn_id: string
  status: string
  seq?: number
  items: string[]
  input?: WriterInputItem[] | unknown
  [key: string]: unknown
}

export interface WriterAppItem {
  item_id: string
  turn_id?: string | null
  parent_item_id?: string | null
  type?: string
  status?: string
  content?: string
  deltas?: unknown[]
  seq?: number
  last_seq?: number
  last_method?: string
  tool_name?: string
  arguments?: unknown
  request_id?: string
  [key: string]: unknown
}

export interface WriterAppQueueItem {
  queue_item_id: string
  status?: string
  mode?: string
  input?: WriterInputItem[] | unknown
  seq?: number
  last_method?: string
  [key: string]: unknown
}

export interface WriterAppRequestState {
  request_id: string
  status: string
  item_id?: string | null
  turn_id?: string | null
  decision?: string | null
  guidance?: string | null
  [key: string]: unknown
}

export interface WriterCoreSnapshot {
  thread_id: string
  snapshot_seq: number
  seen_event_ids?: string[]
  turns?: Record<string, WriterCoreTurn>
  items?: Record<string, WriterCoreItem>
  item_order?: string[]
  requests?: Record<string, WriterAppRequestState>
  artifacts?: Record<string, Record<string, unknown>>
  status?: WriterAppThreadStatus
}

export interface WriterCoreTurn {
  turn_id: string
  status: string
  items?: string[]
  usage?: Record<string, unknown>
  [key: string]: unknown
}

export interface WriterCoreItem {
  item_id: string
  turn_id?: string | null
  parent_item_id?: string | null
  kind?: string
  last_kind?: string
  status?: string
  content?: string
  deltas?: unknown[]
  payload?: Record<string, unknown>
  artifacts?: Record<string, unknown>[]
  usage?: Record<string, unknown>
  [key: string]: unknown
}
