export interface ApiVendor {
  id: string
  name: string
  base_url: string
  api_key_masked: string
  is_active: boolean
  model_count: number
  created_at: string
  updated_at: string
}

export interface ApiVendorCreate {
  name: string
  base_url: string
  api_key: string
  is_active?: boolean
}

export interface ApiVendorUpdate {
  name?: string
  base_url?: string
  api_key?: string
  is_active?: boolean
}

export interface ApiProvider {
  id: string
  nickname: string
  base_url: string
  model_id: string
  vendor_id: string | null
  vendor_name: string
  api_key_masked: string
  provider_type: 'image_gen' | 'llm' | 'web_search'
  billing_type: 'per_call' | 'per_token'
  unit_price: number
  currency: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface ApiProviderCreate {
  nickname: string
  base_url?: string
  model_id: string
  vendor_id?: string | null
  api_key?: string
  provider_type: 'image_gen' | 'llm' | 'web_search'
  billing_type?: 'per_call' | 'per_token'
  unit_price?: number
  currency?: string
  is_active?: boolean
}

export interface ApiProviderUpdate {
  nickname?: string
  base_url?: string | null
  model_id?: string
  vendor_id?: string | null
  api_key?: string
  provider_type?: 'image_gen' | 'llm' | 'web_search'
  billing_type?: 'per_call' | 'per_token'
  unit_price?: number
  currency?: string
  is_active?: boolean
}

export interface BillingSummary {
  today: number
  month: number
  total: number
  currency: string
}

export interface BillingRecord {
  id: string
  session_id: string | null
  provider_id: string | null
  billing_type: string
  tokens_in: number
  tokens_out: number
  cost: number
  currency: string
  detail: Record<string, unknown>
  created_at: string
}

export interface BillingBreakdown {
  by_provider: Array<{
    provider_id: string
    nickname: string
    cost: number
    tokens: number
  }>
  by_type: Array<{
    type: string
    label: string
    cost: number
    tokens: number
    count: number
  }>
}

export interface ReferenceImage {
  id: string
  name: string
  file_path: string
  file_type: string
  file_size: number
  thumbnail: string
  is_global: boolean
  strength: number
  crop_config: Record<string, unknown>
  created_at: string
}

export interface PromptOptimizeResult {
  original: string
  optimized: string
  direction: string
}

export interface SessionInfo {
  id: string
  title: string
  status: 'idle' | 'generating' | 'optimizing' | 'planning' | 'error'
  created_at: string
  updated_at: string
  message_count: number
  cost: number
  tokens: number
}

export interface TaskHandle {
  sessionId: string
  type: 'generate' | 'optimize' | 'plan'
  status: 'running' | 'done' | 'error'
  progress: number
  total: number
  abortController: AbortController | null
  taskType?: string
  strategy?: string
}

export interface TaskUpdateEvent {
  session_id: string
  status: string
  progress: number
  total: number
  message: string
  task_type?: string
  strategy?: string
}

export interface Message {
  id: string
  session_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  message_type: 'text' | 'image' | 'plan' | 'optimization' | 'skill' | 'error' | 'agent' | 'agent_timeline' | 'artist'
  metadata: Record<string, unknown>
  created_at: string
}

export interface GenerateRequest {
  session_id?: string | null
  prompt: string
  model?: string
  image_urls?: string[]
  reference_image_ids?: string[]
  head_image_id?: string
  artist_pack_count?: number
  artist_model_mode?: string
  artist_anchor_first?: boolean
  negative_prompt?: string
  image_count?: number
  image_size?: string
  image_quality?: string
  reference_images?: string[]
  reference_labels?: { index: number; source: string; name: string }[]
  context_messages?: { role: string; content: string; image_urls?: string[] }[]
  plan_strategy?: string
  refine_mode?: boolean
  selected_image_url?: string
}

export interface PlanStep {
  prompt: string
  negative_prompt: string
  description: string
  image_count?: number
  image_size?: string
  /** @deprecated */
  reference_step_indices?: number[]
  checkpoint?: {
    enabled: boolean
    message: string
    auto_continue_seconds?: number
  }
}

export interface DefaultModelsConfig {
  default_artist_runtime_provider_id: string | null
  default_optimize_provider_id?: string | null
  default_image_provider_id: string | null
  default_image_width: number
  default_image_height: number
  max_concurrent: number
}

export interface RuntimeEventData {
  type: string
  session_id: string
  kind?: string
  content?: string
  metadata?: Record<string, unknown>
  elapsed_s?: number
  name?: string
  args?: Record<string, unknown>
  meta?: Record<string, unknown>
  error?: string
  reason?: string
  retry_count?: number
  tokens_in?: number
  tokens_out?: number
  cost?: number
  partial_output?: string
  tool_name?: string
  message?: string
  preview?: string
  status?: string
  progress?: number
  total?: number
  node?: string
  detail?: string | Record<string, unknown>
  artifacts?: Array<{ type: string; url: string }>
  step?: { description: string }
  artist_turn_id?: string
  action_type?: string
  action_id?: string
  phase?: string
  artifact?: Record<string, unknown>
  prompt?: string
  task_run_id?: string
  step_index?: number
  step_name?: string
  artifact_urls?: string[]
  total_steps?: number
  completed?: number
  failed?: number
  current_step_name?: string
  total_artifacts?: number
  total_tokens?: number
  total_cost?: number
}

export interface RuntimeEvent {
  id: string
  timestamp: number
  created_at?: string
  type: string
  run_id: string
  data: RuntimeEventData
}

export interface RuntimeProgressArtifact {
  url: string
  type?: string
  label?: string
  meta?: Record<string, unknown>
}

export interface RuntimeProgressStep {
  id: string
  kind: 'observe' | 'decide' | 'tool' | 'artifact' | 'review' | 'done'
  title: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
  detail?: string
  prompt?: string
  artifacts?: RuntimeProgressArtifact[]
  meta?: Record<string, unknown>
}

export interface RuntimeProgressState {
  sessionId: string
  status: 'thinking' | 'running' | 'paused' | 'completed' | 'failed' | 'cancelled'
  title: string
  message: string
  content: string
  steps: RuntimeProgressStep[]
  artifacts: RuntimeProgressArtifact[]
  totalSteps: number
  completedSteps: number
  failedSteps: number
  cost: number | null
  phase: string
  taskRunId: string
  startedAt: number | null
  updatedAt: number | null
}

export interface ContextImage {
  url: string
  source: 'upload' | 'context' | 'refine'
  name: string
  preview?: string
}

export interface Attachment {
  name: string
  type: string
  size: number
  preview?: string
  content?: string
}

export interface DialogToolCall {
  id: string
  name: string
  args: Record<string, unknown>
  content: string
  collapsed: boolean
}

export interface DialogMessage {
  id: number
  role: string
  content: string
  attachments?: Attachment[]
}

export interface LineageNode {
  image_url: string
  artifact_id?: string
  parent_artifact_id?: string
  root_artifact_id?: string
  source_image_urls: string[]
  generation_mode: string
  prompt: string
  artifact_type?: string
  created_at: string
  message_id: string | null
  branch: string
}

export interface LineageBranch {
  name: string
  head_url: string
  node_urls: string[]
}

export interface LineageTree {
  session_id: string
  nodes: Record<string, LineageNode>
  root_urls: string[]
  branches: Record<string, LineageBranch>
  head_branch: string
  head_url: string
}
