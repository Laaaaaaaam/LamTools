<template>
  <WorkspaceShell>
    <template #sidebar-header>
      <div class="ltw-sidebar-header">
        <span class="ltw-sidebar-title">__DISPLAY_NAME__</span>
      </div>
    </template>

    <template #sidebar>
      <SessionSidebar
        :sessions="sessions"
        :active-id="activeSessionId ?? undefined"
        :groups="sessionGroups"
        @select="selectSession"
      />
    </template>

    <template #chat>
      <ChatThread :messages="messages" />
      <ComposerBar
        v-model="composerText"
        @submit="sendMessage"
      />
    </template>
  </WorkspaceShell>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import {
  WorkspaceShell,
  SessionSidebar,
  ChatThread,
  ComposerBar,
  useCoreWorkbenchController,
  type CoreWorkbenchApi,
} from '@lamtools/ui'
import { adapter, useSessionGroups } from '../api/adapter'
import {
  listCoreSessions,
  createCoreSession,
  getCoreMessages,
  createCoreMessage,
  getCoreEvents,
} from '../api/core'

const { sessionGroups } = useSessionGroups()

const api: CoreWorkbenchApi = {
  listSessions: listCoreSessions,
  createSession: createCoreSession,
  getMessages: getCoreMessages,
  createMessage: createCoreMessage,
  getEvents: getCoreEvents,
}

const {
  sessions, activeSessionId, messages,
  composerText,
  selectSession, sendMessage, loadInitialData,
} = useCoreWorkbenchController({ api })

onMounted(() => {
  loadInitialData()
})
</script>
