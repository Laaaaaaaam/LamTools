<template>
  <WorkspaceShell product-name="LamTools Demo">
    <template #sidebar-body>
      <SessionSidebar
        :project-groups="projectGroups"
        :active-session-id="activeSessionId"
        @select-session="handleSelectSession"
      />
    </template>

    <template #main-content>
      <ChatThread :messages="activeMessages" />
    </template>

    <template #composer-textarea>
      <ComposerBar
        v-model="composerText"
        placeholder="Type a message..."
        @submit="handleSubmit"
      />
    </template>

    <template #right-panel>
      <RuntimePanel :events="runtimeEvents" />
    </template>
  </WorkspaceShell>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import type { CoreSessionListItem, CoreMessage, CoreRuntimeEvent } from '../types';

import WorkspaceShell from '../components/WorkspaceShell.vue';
import SessionSidebar from '../components/SessionSidebar.vue';
import ChatThread from '../components/ChatThread.vue';
import ComposerBar from '../components/ComposerBar.vue';
import RuntimePanel from '../components/RuntimePanel.vue';

// --- Neutral sample data ---
const sessions = ref<CoreSessionListItem[]>([
  { id: 's1', title: 'First session', createdAt: '2026-01-01T00:00:00Z', updatedAt: '2026-01-01T12:00:00Z' },
  { id: 's2', title: 'Second session', createdAt: '2026-02-01T00:00:00Z' },
  { id: 's3', title: 'Third session', createdAt: '2026-03-01T00:00:00Z', updatedAt: '2026-03-15T09:30:00Z' },
]);

const projectGroups = computed(() => [
  {
    id: 'demo',
    name: 'Demo Project',
    sessions: sessions.value,
  },
]);

const messagesBySession: Record<string, CoreMessage[]> = {
  s1: [
    { id: 'm1', role: 'user', content: 'Hello, this is a sample message.', timestamp: '2026-01-01T10:00:00Z' },
    { id: 'm2', role: 'assistant', content: 'This is a sample response.', timestamp: '2026-01-01T10:00:05Z' },
  ],
  s2: [
    { id: 'm3', role: 'user', content: 'Another session, another message.', timestamp: '2026-02-01T08:00:00Z' },
  ],
  s3: [
    { id: 'm4', role: 'user', content: 'Third session message.', timestamp: '2026-03-01T14:00:00Z' },
    { id: 'm5', role: 'assistant', content: 'Third session response.', timestamp: '2026-03-01T14:00:10Z' },
  ],
};

const runtimeEvents = ref<CoreRuntimeEvent[]>([
  { id: 'e1', type: 'start', timestamp: '2026-01-01T10:00:00Z' },
  { id: 'e2', type: 'tool_call', timestamp: '2026-01-01T10:00:02Z', data: { name: 'read_file' } },
  { id: 'e3', type: 'complete', timestamp: '2026-01-01T10:00:05Z' },
]);

const activeSessionId = ref('s1');
const composerText = ref('');

const activeMessages = computed(() => messagesBySession[activeSessionId.value] ?? []);

function handleSelectSession(id: string) {
  activeSessionId.value = id;
}

function handleSubmit() {
  if (!composerText.value.trim()) return;
  // In a real app, this would emit to a parent or store.
  // For demo, we just clear the input.
  composerText.value = '';
}
</script>

<style>
@import '../styles/base.css';
@import '../styles/workspace.css';
</style>
