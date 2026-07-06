import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import { sessionApi } from '../api/session'
import type {
  Message,
  RuntimeEvent,
  RuntimeProgressArtifact,
  RuntimeProgressState,
  RuntimeProgressStep,
  SessionInfo,
  TaskUpdateEvent,
} from '../types'

const ACTION_LABELS: Record<string, string> = {
  chat_only: '回复用户',
  ask_clarification: '等待补充',
  generate_anchor: '生成基准图',
  generate_image: '生成图片',
  generate_pack: '生成套图',
  edit_image: '修改图片',
  review_image: '检查图片',
  self_critique: '自检结果',
  delegate_to_agent: '委托子任务',
}

const LEGACY_NODE_LABELS: Record<string, string> = {
  intent: '理解需求',
  context: '整理上下文',
  planner: '规划步骤',
  prompt_builder: '准备提示词',
  executor: '调用工具',
  critic: '检查结果',
  decision: '决定下一步',
}

export type RuntimeActivity = {
  id: string
  session_id: string
  group: 'plan' | 'tool' | 'verify' | 'reply' | 'decision' | 'system'
  status: 'running' | 'completed' | 'failed' | 'paused'
  label: string
  detail: string
  raw_detail: string
  created_at: number
}

function createRuntimeProgress(sessionId: string, title = 'Artist Runtime'): RuntimeProgressState {
  return {
    sessionId,
    status: 'thinking',
    title,
    message: '准备中',
    content: '',
    steps: [],
    artifacts: [],
    totalSteps: 0,
    completedSteps: 0,
    failedSteps: 0,
    cost: null,
    phase: '',
    taskRunId: '',
    startedAt: Date.now(),
    updatedAt: Date.now(),
  }
}

function normalizeArtifact(raw: unknown, fallbackLabel = ''): RuntimeProgressArtifact | null {
  if (!raw || typeof raw !== 'object') return null
  const obj = raw as Record<string, unknown>
  const url = obj.url
  if (typeof url !== 'string' || (!url.startsWith('http') && !url.startsWith('data:'))) return null
  const meta = (obj.metadata && typeof obj.metadata === 'object')
    ? obj.metadata as Record<string, unknown>
    : {}
  return {
    url,
    type: (obj.type as string) || (meta.artifact_type as string) || 'image',
    label: (obj.label as string) || (obj.branch_name as string) || fallbackLabel,
    meta: { ...meta, ...obj },
  }
}

function artifactFromUrl(url: string, label = ''): RuntimeProgressArtifact | null {
  if (!url || (!url.startsWith('http') && !url.startsWith('data:'))) return null
  return { url, type: 'image', label }
}

function stepKindFromLegacyNode(node: string): RuntimeProgressStep['kind'] {
  if (node === 'executor') return 'tool'
  if (node === 'critic') return 'review'
  if (node === 'decision') return 'done'
  if (node === 'intent' || node === 'context') return 'observe'
  return 'decide'
}

export const useSessionStore = defineStore('session', () => {
  const sessions = ref<SessionInfo[]>([])
  const currentSessionId = ref<string | null>(null)
  const messages = ref<Message[]>([])
  const loading = ref(false)
  const runtimeProgressStates = reactive(new Map<string, RuntimeProgressState>())
  const runtimeActivityFeed = ref<RuntimeActivity[]>([])
  const lineageDrawerVisible = ref(false)
  const lineageDrawerSessionId = ref('')
  let fetchSeq = 0

  function getRuntimeProgress(sessionId: string): RuntimeProgressState | undefined {
    return runtimeProgressStates.get(sessionId)
  }

  function ensureRuntimeProgress(sessionId: string, title = 'Artist Runtime'): RuntimeProgressState {
    let state = runtimeProgressStates.get(sessionId)
    if (!state) {
      state = createRuntimeProgress(sessionId, title)
      runtimeProgressStates.set(sessionId, state)
    } else if (title && state.title !== title) {
      state.title = title
    }
    state.updatedAt = Date.now()
    return state
  }

  function clearRuntimeProgress(sessionId: string) {
    runtimeProgressStates.delete(sessionId)
  }

  function isRuntimeBusy(sessionId: string): boolean {
    const state = runtimeProgressStates.get(sessionId)
    return !!state && ['thinking', 'running', 'paused'].includes(state.status)
  }

  function upsertRuntimeStep(state: RuntimeProgressState, step: RuntimeProgressStep) {
    const existing = state.steps.find(s => s.id === step.id)
    if (existing) Object.assign(existing, step)
    else state.steps.push(step)
    state.updatedAt = Date.now()
  }

  function pushRuntimeActivity(activity: Omit<RuntimeActivity, 'id' | 'created_at'> & { id?: string }) {
    const item: RuntimeActivity = {
      id: activity.id || `${activity.session_id}-${Date.now()}-${runtimeActivityFeed.value.length}`,
      created_at: Date.now(),
      ...activity,
    }
    runtimeActivityFeed.value.push(item)
    if (runtimeActivityFeed.value.length > 400) {
      runtimeActivityFeed.value = runtimeActivityFeed.value.slice(-300)
    }
  }

  function completeRunningToolStep(state: RuntimeProgressState, artifact: RuntimeProgressArtifact | null) {
    const step = [...state.steps].reverse().find(s => s.status === 'running' && (s.kind === 'tool' || s.kind === 'artifact'))
    if (step) {
      step.status = 'completed'
      if (artifact) step.artifacts = [...(step.artifacts || []), artifact]
    } else if (artifact) {
      state.steps.push({
        id: `artifact-${state.steps.length}-${Date.now()}`,
        kind: 'artifact',
        title: '接收产出',
        status: 'completed',
        artifacts: [artifact],
      })
    }
    if (artifact) state.artifacts.push(artifact)
    state.completedSteps = state.steps.filter(s => s.status === 'completed').length
    state.message = artifact ? '已产出图片' : state.message
    state.status = 'running'
    state.updatedAt = Date.now()
  }

  function runtimeActivityGroupForDisplay(kind: string): RuntimeActivity['group'] {
    if (kind === 'reply') return 'reply'
    if (kind === 'tool_start' || kind === 'tool_end' || kind === 'artifact') return 'tool'
    if (kind === 'verify') return 'verify'
    if (kind === 'waiting') return 'decision'
    return 'system'
  }

  function handleCoreDisplayEvent(sessionId: string, event: RuntimeEvent, payload: RuntimeEvent['data']): boolean {
    const kind = typeof payload.kind === 'string' ? payload.kind : ''
    if (!kind) return false

    const state = ensureRuntimeProgress(sessionId, 'Artist Runtime')
    const content = typeof payload.content === 'string' ? payload.content : ''
    const detail = typeof payload.detail === 'string' ? payload.detail : ''
    const metadata = payload.metadata && typeof payload.metadata === 'object'
      ? payload.metadata as Record<string, unknown>
      : {}
    const callId = String(metadata.call_id || event.id || `${kind}-${Date.now()}`)
    const stepIndex = metadata.step_index != null ? String(metadata.step_index) : String(state.steps.length)
    let label = content || detail || kind

    if (kind === 'started') {
      state.status = 'thinking'
      state.message = '理解任务中'
      state.phase = ''
      label = '接收任务'
      upsertRuntimeStep(state, {
        id: `core-start-${event.id}`,
        kind: 'observe',
        title: '接收任务',
        status: 'completed',
        detail: content,
      })
    } else if (kind === 'reply') {
      state.status = 'thinking'
      state.message = '组织回复'
      label = '组织回复'
      if (content) {
        state.content = metadata.delta === true ? `${state.content}${content}` : content
      }
    } else if (kind === 'tool_start') {
      state.status = 'running'
      state.message = ACTION_LABELS[content] || content || '调用工具'
      label = state.message
      upsertRuntimeStep(state, {
        id: `core-tool-${callId}`,
        kind: 'tool',
        title: ACTION_LABELS[content] || content || '调用工具',
        status: 'running',
        detail,
        meta: { ...metadata, display_kind: kind },
      })
    } else if (kind === 'tool_end') {
      const failed = String(metadata.status || '').toLowerCase() === 'failed'
      upsertRuntimeStep(state, {
        id: `core-tool-${callId}`,
        kind: 'tool',
        title: ACTION_LABELS[content] || content || '工具完成',
        status: failed ? 'failed' : 'completed',
        detail,
        meta: { ...metadata, display_kind: kind },
      })
      state.status = failed ? 'failed' : 'running'
      state.message = failed ? '工具执行失败' : '工具完成'
      label = state.message
    } else if (kind === 'verify') {
      const passed = metadata.passed !== false
      label = content || '验收结果'
      upsertRuntimeStep(state, {
        id: `core-verify-${stepIndex}`,
        kind: 'review',
        title: label,
        status: passed ? 'completed' : 'failed',
        detail,
        meta: { ...metadata, display_kind: kind },
      })
      if (!passed) state.status = 'failed'
      state.message = content || (passed ? '验收通过' : '验收失败')
    } else if (kind === 'waiting') {
      state.status = 'paused'
      state.message = content || '等待补充'
      label = '等待补充'
      upsertRuntimeStep(state, {
        id: `core-waiting-${event.id}`,
        kind: 'decide',
        title: '等待补充',
        status: 'running',
        detail: content || detail,
      })
    } else if (kind === 'done') {
      for (const step of state.steps) {
        if (step.status === 'running') step.status = 'completed'
      }
      state.status = 'completed'
      state.message = content || '完成'
      label = '完成'
      upsertRuntimeStep(state, {
        id: `core-done-${event.id}`,
        kind: 'done',
        title: '完成',
        status: 'completed',
        detail: content || detail,
      })
    } else if (kind === 'failed') {
      for (const step of state.steps) {
        if (step.status === 'running') step.status = 'failed'
      }
      state.status = 'failed'
      state.message = content || '执行失败'
      label = '执行失败'
      upsertRuntimeStep(state, {
        id: `core-failed-${event.id}`,
        kind: 'done',
        title: '执行失败',
        status: 'failed',
        detail: content || detail,
      })
    } else if (kind === 'part') {
      const partType = String(metadata.part_type || '')
      if (partType === 'text' || partType === 'tool_call' || partType === 'tool_result') return true
      state.status = 'running'
      state.message = label
    } else if (kind === 'artifact') {
      const artifact = normalizeArtifact(metadata.artifact, content || '产出')
      completeRunningToolStep(state, artifact)
      state.message = content || state.message
      label = content || '接收产出'
    } else {
      state.status = state.status === 'completed' || state.status === 'failed' ? state.status : 'running'
      state.message = label
    }

    state.completedSteps = state.steps.filter(s => s.status === 'completed').length
    state.failedSteps = state.steps.filter(s => s.status === 'failed').length
    state.updatedAt = Date.now()
    pushRuntimeActivity({
      session_id: sessionId,
      group: runtimeActivityGroupForDisplay(kind),
      status: state.status === 'failed' ? 'failed' : (kind === 'done' ? 'completed' : 'running'),
      label: label.slice(0, 80) || kind,
      detail: detail || (kind === 'reply' ? content.slice(0, 100) : ''),
      raw_detail: JSON.stringify(payload),
    })
    return true
  }

  function handleRuntimeTaskUpdate(event: TaskUpdateEvent) {
    if (!event.session_id) return
    const state = ensureRuntimeProgress(event.session_id)
    state.status = event.status === 'error' ? 'failed' : 'running'
    state.message = event.message || state.message
    state.completedSteps = event.progress ?? state.completedSteps
    state.totalSteps = event.total ?? state.totalSteps
    state.updatedAt = Date.now()
  }

  function handleRuntimeEvent(sessionId: string, event: RuntimeEvent) {
    if (!sessionId) return
    const payload = event.data || {}
    const type = payload.type || event.type

    if (type === 'task_started') {
      const state = ensureRuntimeProgress(sessionId)
      state.status = 'thinking'
      state.message = '接收任务'
      pushRuntimeActivity({
        session_id: sessionId,
        group: 'system',
        status: 'running',
        label: '接收任务',
        detail: '',
        raw_detail: JSON.stringify(payload),
      })
      return
    }

    if (handleCoreDisplayEvent(sessionId, event, payload)) {
      return
    }

    if (type === 'artist_thinking' || type === 'artist_reasoning_delta') {
      const state = ensureRuntimeProgress(sessionId, 'Artist Runtime')
      state.status = 'thinking'
      state.message = (payload.content as string) || '思考下一步'
      pushRuntimeActivity({
        session_id: sessionId,
        group: 'plan',
        status: 'running',
        label: '思考下一步',
        detail: String(payload.content || '').slice(0, 100),
        raw_detail: String(payload.content || ''),
      })
      return
    }

    if (type === 'artist_image_ready') {
      const state = ensureRuntimeProgress(sessionId, 'Artist Runtime')
      const artifact = normalizeArtifact(payload.artifact, '生成图片')
      completeRunningToolStep(state, artifact)
      pushRuntimeActivity({
        session_id: sessionId,
        group: 'tool',
        status: 'completed',
        label: '接收图片',
        detail: artifact?.label || artifact?.url || '',
        raw_detail: JSON.stringify(payload),
      })
      return
    }

    if (type === 'long_task_created') {
      const state = ensureRuntimeProgress(sessionId, (payload.name as string) || 'Runtime Task')
      state.status = 'running'
      state.message = '开始执行'
      state.taskRunId = (payload.task_run_id as string) || ''
      state.totalSteps = Number(payload.total_steps || payload.total || 0)
      state.completedSteps = 0
      state.failedSteps = 0
      state.steps = []
      state.artifacts = []
      state.updatedAt = Date.now()
      pushRuntimeActivity({
        session_id: sessionId,
        group: 'system',
        status: 'running',
        label: '开始长任务',
        detail: state.message,
        raw_detail: JSON.stringify(payload),
      })
      return
    }

    if (type === 'long_task_step_started') {
      const state = ensureRuntimeProgress(sessionId)
      const index = Number(payload.step_index || 0)
      state.status = 'running'
      state.message = (payload.step_name as string) || `步骤 ${index + 1}`
      upsertRuntimeStep(state, {
        id: `long-${payload.task_run_id || state.taskRunId}-${index}`,
        kind: 'tool',
        title: (payload.step_name as string) || `步骤 ${index + 1}`,
        status: 'running',
        prompt: (payload.prompt as string) || '',
        meta: { step_index: index, task_run_id: payload.task_run_id },
      })
      pushRuntimeActivity({
        session_id: sessionId,
        group: 'tool',
        status: 'running',
        label: state.message,
        detail: (payload.prompt as string) || '',
        raw_detail: JSON.stringify(payload),
      })
      return
    }

    if (type === 'long_task_step_completed') {
      const state = ensureRuntimeProgress(sessionId)
      const index = Number(payload.step_index || 0)
      const artifacts = ((payload.artifact_urls as string[]) || [])
        .map((url, i) => artifactFromUrl(url, `步骤 ${index + 1}.${i + 1}`))
        .filter((a): a is RuntimeProgressArtifact => !!a)
      upsertRuntimeStep(state, {
        id: `long-${payload.task_run_id || state.taskRunId}-${index}`,
        kind: 'tool',
        title: `步骤 ${index + 1}`,
        status: 'completed',
        artifacts,
        meta: { step_index: index, tokens: payload.total_tokens, cost: payload.cost },
      })
      state.artifacts.push(...artifacts)
      state.completedSteps = Math.max(state.completedSteps, state.steps.filter(s => s.status === 'completed').length)
      if (typeof payload.cost === 'number') state.cost = (state.cost || 0) + payload.cost
      state.message = '步骤完成'
      state.updatedAt = Date.now()
      pushRuntimeActivity({
        session_id: sessionId,
        group: 'tool',
        status: 'completed',
        label: `步骤 ${index + 1} 完成`,
        detail: artifacts.length ? `${artifacts.length} 张图片` : '',
        raw_detail: JSON.stringify(payload),
      })
      return
    }

    if (type === 'long_task_step_failed') {
      const state = ensureRuntimeProgress(sessionId)
      const index = Number(payload.step_index || 0)
      upsertRuntimeStep(state, {
        id: `long-${payload.task_run_id || state.taskRunId}-${index}`,
        kind: 'tool',
        title: `步骤 ${index + 1}`,
        status: 'failed',
        detail: (payload.error as string) || '执行失败',
        meta: { step_index: index, retry_count: payload.retry_count },
      })
      state.failedSteps = Math.max(state.failedSteps, state.steps.filter(s => s.status === 'failed').length)
      state.status = 'running'
      state.message = '步骤失败，等待下一步'
      pushRuntimeActivity({
        session_id: sessionId,
        group: 'tool',
        status: 'failed',
        label: `步骤 ${index + 1} 失败`,
        detail: (payload.error as string) || '执行失败',
        raw_detail: JSON.stringify(payload),
      })
      return
    }

    if (type === 'long_task_progress') {
      const state = ensureRuntimeProgress(sessionId)
      state.completedSteps = Number(payload.completed ?? state.completedSteps)
      state.failedSteps = Number(payload.failed ?? state.failedSteps)
      state.totalSteps = Number(payload.total ?? state.totalSteps)
      state.message = (payload.current_step_name as string) || state.message
      state.status = 'running'
      state.updatedAt = Date.now()
      return
    }

    if (type === 'long_task_paused') {
      const state = ensureRuntimeProgress(sessionId)
      state.status = 'paused'
      state.message = '已暂停'
      pushRuntimeActivity({
        session_id: sessionId,
        group: 'decision',
        status: 'paused',
        label: '已暂停',
        detail: '',
        raw_detail: JSON.stringify(payload),
      })
      return
    }

    if (type === 'long_task_resumed') {
      const state = ensureRuntimeProgress(sessionId)
      state.status = 'running'
      state.message = '继续执行'
      pushRuntimeActivity({
        session_id: sessionId,
        group: 'system',
        status: 'running',
        label: '继续执行',
        detail: '',
        raw_detail: JSON.stringify(payload),
      })
      return
    }

    if (type === 'long_task_completed') {
      const state = ensureRuntimeProgress(sessionId)
      state.status = 'completed'
      state.message = '完成'
      state.completedSteps = state.totalSteps || state.completedSteps
      state.cost = typeof payload.total_cost === 'number' ? payload.total_cost : state.cost
      pushRuntimeActivity({
        session_id: sessionId,
        group: 'system',
        status: 'completed',
        label: '任务完成',
        detail: '',
        raw_detail: JSON.stringify(payload),
      })
      return
    }

    if (type === 'long_task_cancelled') {
      const state = ensureRuntimeProgress(sessionId)
      state.status = 'cancelled'
      state.message = (payload.reason as string) || '已取消'
      pushRuntimeActivity({
        session_id: sessionId,
        group: 'system',
        status: 'failed',
        label: '任务取消',
        detail: state.message,
        raw_detail: JSON.stringify(payload),
      })
      return
    }

    if (type === 'agent_node_progress') {
      const state = ensureRuntimeProgress(sessionId)
      const node = (payload.node as string) || 'runtime'
      const status = payload.status === 'running' ? 'running' : payload.status === 'error' ? 'failed' : 'completed'
      upsertRuntimeStep(state, {
        id: `legacy-${node}`,
        kind: stepKindFromLegacyNode(node),
        title: LEGACY_NODE_LABELS[node] || node,
        status,
        detail: (payload.content as string) || (payload.message as string) || '',
        meta: payload.detail && typeof payload.detail === 'object' ? payload.detail : {},
      })
      state.status = status === 'running' ? 'running' : state.status
      state.message = (payload.message as string) || state.message
      pushRuntimeActivity({
        session_id: sessionId,
        group: status === 'failed' ? 'system' : stepKindFromLegacyNode(node) === 'review' ? 'verify' : 'plan',
        status,
        label: LEGACY_NODE_LABELS[node] || node,
        detail: (payload.content as string) || (payload.message as string) || '',
        raw_detail: JSON.stringify(payload),
      })
      return
    }

    if (type === 'agent_error') {
      const state = ensureRuntimeProgress(sessionId)
      state.status = 'failed'
      state.message = (payload.error as string) || (payload.message as string) || '执行失败'
      pushRuntimeActivity({
        session_id: sessionId,
        group: 'system',
        status: 'failed',
        label: '执行失败',
        detail: state.message,
        raw_detail: JSON.stringify(payload),
      })
      return
    }

    if (event.type === 'checkpoint_required') {
      const state = ensureRuntimeProgress(sessionId)
      const artifacts = ((payload.artifacts as Array<{ type: string; url: string }>) || [])
        .map((a, i) => normalizeArtifact(a, `确认 ${i + 1}`))
        .filter((a): a is RuntimeProgressArtifact => !!a)
      state.status = 'paused'
      state.message = payload.message || '等待确认'
      upsertRuntimeStep(state, {
        id: `checkpoint-${event.id}`,
        kind: 'decide',
        title: '等待确认',
        status: 'running',
        detail: payload.step?.description || '',
        artifacts,
        meta: { tool_name: payload.tool_name },
      })
      pushRuntimeActivity({
        session_id: sessionId,
        group: 'decision',
        status: 'paused',
        label: '等待确认',
        detail: String(payload.message || ''),
        raw_detail: JSON.stringify(payload),
      })
    }
  }

  async function finalizeRuntimeProgress(sessionId: string, failed = false) {
    const state = runtimeProgressStates.get(sessionId)
    if (state) {
      state.status = failed ? 'failed' : 'completed'
      state.message = failed ? '执行失败' : '完成'
      pushRuntimeActivity({
        session_id: sessionId,
        group: 'system',
        status: failed ? 'failed' : 'completed',
        label: failed ? '执行失败' : '任务完成',
        detail: state.message,
        raw_detail: JSON.stringify({
          status: state.status,
          message: state.message,
          steps: state.steps.map(step => ({ id: step.id, title: step.title, status: step.status })),
        }),
      })
    }
    await fetchMessages(sessionId)
    await fetchSessions()
    runtimeProgressStates.delete(sessionId)
  }

  function handleTaskCompleted(sessionId: string) {
    if (sessionId && sessionId !== currentSessionId.value) {
      runtimeProgressStates.delete(sessionId)
    }
  }

  async function fetchSessions() {
    loading.value = true
    try {
      const { data } = await sessionApi.list()
      sessions.value = data
    } catch (e) {
      console.error('Failed to fetch sessions:', e)
    } finally {
      loading.value = false
    }
  }

  async function createSession(title: string = '新会话') {
    try {
      const { data } = await sessionApi.create(title)
      sessions.value.unshift(data)
      currentSessionId.value = data.id
      await fetchMessages(data.id)
      return data
    } catch (e) {
      console.error('Failed to create session:', e)
      throw e
    }
  }

  async function selectSession(id: string) {
    currentSessionId.value = id
    const seq = ++fetchSeq
    try {
      const { data } = await sessionApi.getMessages(id)
      if (seq === fetchSeq) messages.value = data
    } catch (e) {
      if (seq === fetchSeq) console.error('Failed to fetch messages:', e)
    }
  }

  async function fetchMessages(sessionId: string) {
    const seq = ++fetchSeq
    try {
      const { data } = await sessionApi.getMessages(sessionId)
      if (seq === fetchSeq) messages.value = data
    } catch (e) {
      if (seq === fetchSeq) console.error('Failed to fetch messages:', e)
    }
  }

  async function sendMessage(content: string, messageType: string = 'text', metadata: Record<string, unknown> = {}) {
    if (!currentSessionId.value) return
    try {
      await sessionApi.addMessage(currentSessionId.value, { content, message_type: messageType, metadata })
      await fetchMessages(currentSessionId.value)
    } catch (e) {
      console.error('Failed to send message:', e)
      throw e
    }
  }

  async function generate(sessionId: string, data: {
    prompt: string
    negative_prompt?: string
    image_count?: number
    image_size?: string | undefined
    image_quality?: string | undefined
    reference_images?: string[]
    reference_labels?: { index: number; source: string; name: string }[]
    context_messages?: { role: string; content: string; image_urls?: string[] }[]
    plan_strategy?: string
    refine_mode?: boolean
    selected_image_url?: string
  }) {
    const state = ensureRuntimeProgress(sessionId)
    state.status = 'thinking'
    state.message = '发送中'
    try {
      const { data: result } = await sessionApi.generate({
        ...data,
        session_id: sessionId,
      })
      if (sessionId === currentSessionId.value) await fetchMessages(sessionId)
      await fetchSessions()
      return result
    } catch (e) {
      const failedState = ensureRuntimeProgress(sessionId)
      failedState.status = 'failed'
      failedState.message = e instanceof Error ? e.message : '发送失败'
      pushRuntimeActivity({
        session_id: sessionId,
        group: 'system',
        status: 'failed',
        label: '发送失败',
        detail: failedState.message,
        raw_detail: e instanceof Error ? e.stack || e.message : String(e),
      })
      console.error('Failed to generate:', e)
      throw e
    }
  }

  async function deleteSession(id: string) {
    try {
      await sessionApi.delete(id)
      sessions.value = sessions.value.filter((s) => s.id !== id)
      runtimeProgressStates.delete(id)
      if (currentSessionId.value === id) {
        currentSessionId.value = sessions.value.length ? sessions.value[0].id : null
        if (currentSessionId.value) await fetchMessages(currentSessionId.value)
        else messages.value = []
      }
    } catch (e) {
      console.error('Failed to delete session:', e)
      throw e
    }
  }

  async function renameSession(id: string, title: string) {
    try {
      await sessionApi.update(id, { title })
      await fetchSessions()
    } catch (e) {
      console.error('Failed to rename session:', e)
      throw e
    }
  }

  function openLineageDrawer(sessionId: string) {
    lineageDrawerSessionId.value = sessionId
    lineageDrawerVisible.value = true
  }

  function closeLineageDrawer() {
    lineageDrawerVisible.value = false
    lineageDrawerSessionId.value = ''
  }

  return {
    sessions,
    currentSessionId,
    messages,
    loading,
    runtimeProgressStates,
    runtimeActivityFeed,
    lineageDrawerVisible,
    lineageDrawerSessionId,
    getRuntimeProgress,
    clearRuntimeProgress,
    isRuntimeBusy,
    handleRuntimeTaskUpdate,
    handleRuntimeEvent,
    finalizeRuntimeProgress,
    handleTaskCompleted,
    fetchSessions,
    createSession,
    selectSession,
    fetchMessages,
    sendMessage,
    generate,
    deleteSession,
    renameSession,
    openLineageDrawer,
    closeLineageDrawer,
  }
})
