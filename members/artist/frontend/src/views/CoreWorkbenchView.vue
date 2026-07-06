<script setup lang="ts">
/**
 * CoreWorkbenchView — lamartist powered by @lamtools/ui WorkspaceShell
 *
 * Uses the four-layer WorkspaceShell. Sessions are grouped by user-created
 * groups (stored in localStorage) — no backend project concept like Writer,
 * but the same two-level sidebar structure for consistency.
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  WorkspaceShell,
  SessionSidebar,
  ChatThread,
  RuntimePanel,
  useCoreWorkbenchController,
  type CoreWorkbenchApi,
  type ProjectGroup,
  type SessionItem,
} from '@lamtools/ui'
import {
  listCoreSessions,
  createCoreSession,
  getCoreMessages,
  startCoreArtistTurn,
  getCoreEvents,
  listCoreProviders,
  getCoreUsageTotal,
} from '@/api/core'
import { sessionApi } from '@/api/session'

const router = useRouter()

// ---------------------------------------------------------------------------
// Session groups (frontend-only, localStorage backed)
// ---------------------------------------------------------------------------

interface SessionGroup {
  id: string
  name: string
  sessionIds: string[]
}

const STORAGE_KEY = 'lamartist.session-groups'

function loadGroups(): SessionGroup[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    return JSON.parse(raw) as SessionGroup[]
  } catch {
    return []
  }
}

function saveGroups(groups: SessionGroup[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(groups))
}

const sessionGroups = ref<SessionGroup[]>(loadGroups())

// Ensure default group always exists
function ensureDefaultGroup() {
  if (sessionGroups.value.length === 0) {
    sessionGroups.value = [{ id: 'default', name: 'Artist 工作台', sessionIds: [] }]
    saveGroups(sessionGroups.value)
  }
}
ensureDefaultGroup()

// ---------------------------------------------------------------------------
// Product adapter
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Core controller
// ---------------------------------------------------------------------------

const usageTotal = ref<number | null>(null)
const usageCurrency = ref('CNY')

const api: CoreWorkbenchApi = {
  listSessions: listCoreSessions,
  createSession: createCoreSession,
  getMessages: getCoreMessages,
  createMessage: startCoreArtistTurn,
  getEvents: getCoreEvents,
  listProviders: async () => (await listCoreProviders()).data,
}

const {
  sessions,
  activeSessionId,
  messages,
  composerText,
  loading,
  providerCount,
  stepGroups,
  selectSession,
  newSession: coreNewSession,
  sendMessage,
  loadInitialData,
} = useCoreWorkbenchController({
  api,
  onMountedExtra: async () => {
    try {
      const usageRes = await getCoreUsageTotal()
      if (usageRes.data) {
        usageTotal.value = usageRes.data.total_cost
        usageCurrency.value = usageRes.data.currency
      }
    } catch (err) {
      console.error('Failed to load usage:', err)
    }
  },
})

// ---------------------------------------------------------------------------
// Build ProjectGroup[] from sessions + sessionGroups
// ---------------------------------------------------------------------------

function sessionToItem(s: {
  id: string
  title: string
  status?: string
  created_at?: string
  updated_at?: string
  createdAt?: string
  updatedAt?: string
}): SessionItem {
  return {
    id: s.id,
    title: s.title,
    status: s.status,
    createdAt: (s as any).created_at || s.createdAt,
    updatedAt: (s as any).updated_at || s.updatedAt,
  }
}

const projectGroups = computed<ProjectGroup[]>(() => {
  const assigned = new Set<string>()
  const result: ProjectGroup[] = []

  for (const group of sessionGroups.value) {
    const groupSessions = sessions.value
      .filter((s) => group.sessionIds.includes(s.id))
      .map(sessionToItem)
    for (const s of groupSessions) assigned.add(s.id)
    result.push({
      id: group.id,
      name: group.name,
      sessions: groupSessions,
    })
  }

  // Ungrouped sessions → auto-assign to default group
  const ungrouped = sessions.value.filter((s) => !assigned.has(s.id))
  if (ungrouped.length > 0 && result.length > 0) {
    const defaultGroup = result[0]
    for (const s of ungrouped) {
      defaultGroup.sessions.push(sessionToItem(s))
      sessionGroups.value[0].sessionIds.push(s.id)
    }
    saveGroups(sessionGroups.value)
  }

  return result
})

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

function handleNewSession(groupId: string) {
  // Assign the new session to this group once created
  const group = sessionGroups.value.find((g) => g.id === groupId)
  if (!group) return

  // We need to intercept the session creation to assign group
  // useCoreWorkbenchController.newSession creates and selects in one step
  coreNewSession().then(() => {
    // After creation, the new session is first in sessions array
    const newSession = sessions.value[0]
    if (newSession && !group.sessionIds.includes(newSession.id)) {
      group.sessionIds.push(newSession.id)
      saveGroups(sessionGroups.value)
    }
  })
}

async function handleRenameSession(sessionId: string, title: string) {
  const cleaned = title.trim()
  if (!cleaned) return
  try {
    const { data } = await sessionApi.update(sessionId, { title: cleaned })
    sessions.value = sessions.value.map((session) =>
      session.id === sessionId
        ? {
            ...session,
            title: data.title || cleaned,
            updatedAt: data.updated_at || session.updatedAt,
          }
        : session,
    )
  } catch (err) {
    console.error('Failed to rename session:', err)
  }
}

function handleCreateGroup() {
  const name = window.prompt('新分组名称：')
  if (!name?.trim()) return
  const group: SessionGroup = {
    id: `group-${Date.now()}`,
    name: name.trim(),
    sessionIds: [],
  }
  sessionGroups.value.push(group)
  saveGroups(sessionGroups.value)
}

function handleDeleteGroup(groupId: string) {
  if (sessionGroups.value.length <= 1) {
    alert('至少保留一个分组。')
    return
  }
  const group = sessionGroups.value.find((g) => g.id === groupId)
  if (!group) return
  const confirmed = window.confirm(`确定删除分组「${group.name}」？其中的会话会移至默认分组。`)
  if (!confirmed) return
  // Move sessions to default group
  const defaultGroup = sessionGroups.value[0]
  defaultGroup.sessionIds.push(...group.sessionIds)
  sessionGroups.value = sessionGroups.value.filter((g) => g.id !== groupId)
  saveGroups(sessionGroups.value)
}

// ---------------------------------------------------------------------------
// Right panel
// ---------------------------------------------------------------------------

const usageLabel = computed(() =>
  usageTotal.value !== null
    ? `${usageTotal.value.toFixed(2)} ${usageCurrency.value}`
    : '-',
)

const activeSession = computed(() =>
  sessions.value.find((s) => s.id === activeSessionId.value) ?? null,
)

const rightPanelGroups = computed(() => {
  const gs: Array<{ id: string; label: string; items: { label: string; value: string }[] }> = []
  if (activeSession.value) {
    gs.push({
      id: 'session',
      label: 'Session',
      items: [
        { label: '当前会话', value: activeSession.value.title },
        { label: '会话编号', value: `#${activeSession.value.id.slice(0, 8)}` },
        { label: '消息数', value: String(messages.value.length) },
      ],
    })
  }
  if (usageTotal.value !== null) {
    gs.push({
      id: 'billing',
      label: 'Billing',
      items: [{ label: '累计费用', value: usageLabel.value }],
    })
  }
  gs.push({
    id: 'status',
    label: 'Status',
    items: [
      { label: 'Providers', value: String(providerCount.value) },
      { label: '分组数', value: String(sessionGroups.value.length) },
    ],
  })
  return gs
})

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

onMounted(() => {
  loadInitialData()
})
</script>

<template>
  <WorkspaceShell
    product-name="lamartist"
    storage-key="lamartist.ui"
    density="compact"
    :composer-placeholder="'输入生图指令...'"
    :composer-disabled="loading || !composerText.trim()"
    @settings="router.push('/settings')"
    @composer-submit="sendMessage"
  >
    <!-- Sidebar footer: create group -->
    <template #sidebar-footer>
      <button
        class="settings-entry"
        style="margin-top:6px"
        @click="handleCreateGroup"
      >
        <span>+</span>
        <span>新建分组</span>
      </button>
    </template>

    <!-- Left sidebar body -->
    <template #sidebar-body>
      <SessionSidebar
        :project-groups="projectGroups"
        :active-session-id="activeSessionId ?? undefined"
        :project-session-limit="0"
        :allow-project-delete="true"
        :allow-project-new-session="true"
        :allow-rename="true"
        @select-session="selectSession"
        @new-session="handleNewSession"
        @delete-project="handleDeleteGroup"
        @select-project="() => {}"
        @rename-session="handleRenameSession"
      />
    </template>

    <!-- Main header -->
    <template #main-header>
      <div v-if="activeSession" class="thread-header">
        <div>
          <h1>{{ activeSession.title }}</h1>
          <span>#{{ activeSession.id.slice(0, 8) }}</span>
          <span v-if="activeSession.status !== 'idle'" class="run-status running">
            {{ activeSession.status }}
          </span>
          <span v-else class="run-status">空闲</span>
        </div>
      </div>
    </template>

    <!-- Main content -->
    <template #thread-content>
      <template v-if="!activeSessionId">
        <div class="sidebar-empty" style="flex:1;display:flex;align-items:center;justify-content:center">
          选择或创建一个会话开始。
        </div>
      </template>
      <template v-else>
        <ChatThread :messages="messages" assistant-label="Artist" />
      </template>
    </template>

    <!-- Composer tools -->
    <template #composer-textarea>
      <textarea
        v-model="composerText"
        placeholder="输入生图指令..."
        rows="1"
        @keydown.enter.exact.prevent="sendMessage"
      />
    </template>

    <template #composer-tools>
      <span v-if="providerCount > 0" style="color:var(--muted);font-size:12px">
        {{ providerCount }} provider(s) &middot; {{ usageLabel }}
      </span>
    </template>

    <!-- Right panel -->
    <template #right-panel>
      <RuntimePanel
        :panel-groups="rightPanelGroups"
        :step-groups="stepGroups"
      />
    </template>
  </WorkspaceShell>
</template>

