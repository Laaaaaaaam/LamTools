/**
 * Type declarations for @lamtools/ui components.
 * Bridges the gap for vue-tsc to resolve .vue files
 * from the external Core UI source directory.
 * Aligned with core/ui/src (Phase 5A+ contract).
 */
declare module '@lamtools/ui' {
  import type { DefineComponent } from 'vue'

  // ---------------------------------------------------------------------------
  // Product adapter
  // ---------------------------------------------------------------------------

  /** Opaque feature identifier declared by a product adapter. */
  export type ProductFeatureId = string

  /** Minimal product identity and capability descriptor. */
  export interface ProductAdapter {
    id: string
    displayName: string
    version?: string
    sessionGroups?: CoreSessionGroup[]
    supportedFeatures?: ProductFeatureId[]
    metadata?: Record<string, unknown>
  }

  // ---------------------------------------------------------------------------
  // Session grouping
  // ---------------------------------------------------------------------------

  /** A named group of sessions displayed in the sidebar. */
  export interface CoreSessionGroup {
    id: string
    label: string
    sessionIds?: string[]
    description?: string
    metadata?: Record<string, unknown>
  }

  // ---------------------------------------------------------------------------
  // Runtime steps
  // ---------------------------------------------------------------------------

  export type CoreRuntimeStepStatus =
    | 'pending'
    | 'running'
    | 'completed'
    | 'failed'
    | 'skipped'

  /** A single step in a runtime process. */
  export interface CoreRuntimeStep {
    id: string
    title: string
    status: CoreRuntimeStepStatus
    kind?: string
    detail?: string
    timestamp?: string
    metadata?: Record<string, unknown>
  }

  /** A named group of runtime steps. */
  export interface CoreRuntimeStepGroup {
    id: string
    label: string
    status: CoreRuntimeStepStatus
    steps: CoreRuntimeStep[]
    description?: string
    metadata?: Record<string, unknown>
  }

  // ---------------------------------------------------------------------------
  // Core data types
  // ---------------------------------------------------------------------------

  export interface CoreSessionListItem {
    id: string
    title: string
    createdAt: string
    updatedAt?: string
    groupId?: string
    status?: string
    metadata?: Record<string, unknown>
  }

  // ---------------------------------------------------------------------------
  // Sidebar data types (used by SessionSidebar)
  // ---------------------------------------------------------------------------

  export interface SessionItem {
    id: string
    title: string
    createdAt?: string
    updatedAt?: string
    status?: string
    meta?: string
    metadata?: Record<string, unknown>
  }

  export interface ProjectGroup {
    id: string
    name: string
    workRoot?: string
    sessions: SessionItem[]
  }

  // ---------------------------------------------------------------------------
  // Message parts — typed content blocks within a message
  // ---------------------------------------------------------------------------

  export type MessagePartType =
    | 'text'
    | 'reasoning'
    | 'tool_call'
    | 'tool_result'
    | 'file_diff'
    | 'command_output'
    | 'plan'
    | 'todo_update'
    | 'error'
    | 'decision'
    | 'agent_summary'

  export type MessagePartStatus = 'pending' | 'running' | 'completed' | 'error'

  export interface MessagePart {
    id: string
    partType: MessagePartType
    status: MessagePartStatus
    content: string
    label?: string
    detail?: string
    toolName?: string
    toolArgs?: Record<string, unknown>
    toolResult?: string
    toolError?: string
    startedAt?: string
    completedAt?: string
    metadata?: Record<string, unknown>
  }

  export interface CoreMessage {
    id: string
    role: 'user' | 'assistant' | 'system'
    content: string
    timestamp: string
    /** Optional typed parts for rich rendering. When present, the renderer
     *  should prefer parts over the flat `content` field. */
    parts?: MessagePart[]
    metadata?: Record<string, unknown>
  }

  export interface CoreRuntimeEvent {
    id: string
    type: string
    timestamp: string
    data?: unknown
  }

  export interface CoreComposerPayload {
    content: string
    attachments?: unknown[]
  }

  export interface CoreMemberDescriptor {
    id: string
    name: string
    version?: string
  }

  // ---------------------------------------------------------------------------
  // API mapper helpers
  // ---------------------------------------------------------------------------

  export interface CoreSessionRawLike {
    id: string
    title: string
    created_at: string | null
    updated_at?: string | null
    status?: string
    metadata?: Record<string, unknown> | null
  }

  export interface CoreMessageRawLike {
    id: string
    role: string
    content: string
    created_at: string | null
    metadata?: Record<string, unknown> | null
  }

  export interface CoreApiMapper<Raw, Core> {
    toCore(raw: Raw): Core
    toRaw(core: Core): Raw
  }

  export interface CreateSessionMapperOptions {
    nullFallback?: boolean
  }

  export interface CreateMessageMapperOptions {
    nullFallback?: boolean
  }

  export function createSessionMapper(
    groupId: string,
    options?: CreateSessionMapperOptions,
  ): CoreApiMapper<CoreSessionRawLike, CoreSessionListItem>

  export function createMessageMapper(
    options?: CreateMessageMapperOptions,
  ): CoreApiMapper<CoreMessageRawLike, CoreMessage>

  export function createLoadingStepGroup(): CoreRuntimeStepGroup[]

  // ---------------------------------------------------------------------------
  // Workbench controller
  // ---------------------------------------------------------------------------

  export interface CoreWorkbenchApi {
    listSessions(): Promise<CoreSessionListItem[]>
    createSession(): Promise<CoreSessionListItem>
    getMessages?(sessionId: string): Promise<CoreMessage[]>
    createMessage?(sessionId: string, content: string, role?: string): Promise<CoreMessage>
    getEvents?(sessionId: string): Promise<CoreRuntimeEvent[]>
    listProviders?(): Promise<unknown[]>
  }

  export interface UseCoreWorkbenchControllerContext {
    sessions: CoreSessionListItem[]
    activeSessionId: string | null
    providerCount: number
  }

  export interface UseCoreWorkbenchControllerOptions {
    api: CoreWorkbenchApi
    onMountedExtra?: (ctx: UseCoreWorkbenchControllerContext) => Promise<void> | void
  }

  export function useCoreWorkbenchController(
    options: UseCoreWorkbenchControllerOptions,
  ): {
    sessions: import('vue').Ref<CoreSessionListItem[]>
    activeSessionId: import('vue').Ref<string | null>
    messages: import('vue').Ref<CoreMessage[]>
    events: import('vue').Ref<CoreRuntimeEvent[]>
    composerText: import('vue').Ref<string>
    loading: import('vue').Ref<boolean>
    providerCount: import('vue').Ref<number>
    stepGroups: import('vue').ComputedRef<CoreRuntimeStepGroup[]>
    selectSession: (id: string) => Promise<void>
    newSession: () => Promise<void>
    sendMessage: () => Promise<void>
    loadInitialData: () => Promise<void>
  }

  // ---------------------------------------------------------------------------
  // Components
  // ---------------------------------------------------------------------------

  export const WorkspaceShell: DefineComponent
  export const SessionSidebar: DefineComponent<{
    projectGroups: ProjectGroup[]
    activeSessionId?: string
    projectSessionLimit?: number
    allowRename?: boolean
    allowProjectNewSession?: boolean
    allowProjectDelete?: boolean
    allowProjectClick?: boolean
    allowProjectContextMenu?: boolean
  }>
  export const ChatThread: DefineComponent<{
    messages: CoreMessage[]
    assistantLabel?: string
    processExpandedIds?: Set<string>
  }>
  export const ComposerBar: DefineComponent<{
    modelValue: string
    placeholder?: string
    disabled?: boolean
  }>
  export const RuntimePanel: DefineComponent<{
    panelGroups?: Array<{
      id: string
      label: string
      items: Array<{ label: string; value: unknown }>
    }>
    events?: CoreRuntimeEvent[]
    stepGroups?: CoreRuntimeStepGroup[]
  }>
  export const SettingsShell: DefineComponent
}
