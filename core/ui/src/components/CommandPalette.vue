<template>
  <div v-if="commands.length" class="command-palette" role="listbox" aria-label="命令">
    <div class="command-list">
      <button
        v-for="(command, index) in commands"
        :key="command.name"
        class="command-item"
        :class="{ active: index === activeIndex }"
        type="button"
        role="option"
        :aria-selected="index === activeIndex"
        :aria-label="commandLabel(command)"
        :data-command-name="command.name"
        @mousedown.prevent="$emit('select', command)"
        @click.prevent="$emit('select', command)"
      >
        <span
          class="command-icon"
          :data-command-kind="command.action === 'insert_token' ? 'skill' : 'action'"
          aria-hidden="true"
        >{{ iconLabel(command.icon, command.action) }}</span>
        <span class="command-copy">
          <span class="command-title-row">
            <strong>/{{ command.name }}</strong>
            <span class="command-kind">{{ kindLabel(command.action) }}</span>
          </span>
          <small>{{ command.description || command.title }}</small>
        </span>
      </button>
    </div>
    <div class="command-footer" aria-hidden="true">
      <span><kbd>↑↓</kbd> Move</span>
      <span><kbd>Enter</kbd> Select</span>
      <span><kbd>Esc</kbd> Close</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { CoreCommandCatalogItem } from '../types'

defineProps<{
  commands: CoreCommandCatalogItem[]
  activeIndex: number
}>()

defineEmits<{
  select: [command: CoreCommandCatalogItem]
}>()

function commandLabel(command: CoreCommandCatalogItem): string {
  const detail = command.description || command.title || kindLabel(command.action)
  return `/${command.name}: ${detail}`
}

function kindLabel(action: CoreCommandCatalogItem['action']): string {
  return action === 'insert_token' ? 'Skill' : 'Action'
}

function iconLabel(icon: string, action: CoreCommandCatalogItem['action']): string {
  if (icon === 'git-branch') return '↱'
  if (icon === 'archive') return '↓'
  if (icon === 'sparkles' || action === 'insert_token') return '✦'
  return '/'
}
</script>

<style scoped>
.command-palette {
  position: absolute;
  left: 0;
  width: min(520px, 100%);
  bottom: calc(100% + 8px);
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--theme-composer-text, currentColor) 13%, transparent);
  border-radius: 10px;
  background: color-mix(in srgb, var(--theme-composer-background, #111) 98%, var(--theme-composer-text, white) 2%);
  box-shadow: 0 8px 14px rgba(0, 0, 0, 0.18);
  z-index: 20;
}

.command-list {
  max-height: min(320px, calc(100vh - 180px));
  overflow-y: auto;
  padding: 5px;
}

.command-item {
  width: 100%;
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  border: 0;
  border-radius: 7px;
  min-height: 48px;
  padding: 6px 8px;
  background: transparent;
  color: var(--theme-composer-text, currentColor);
  text-align: left;
  cursor: default;
}

.command-item.active,
.command-item:hover {
  background: color-mix(in srgb, var(--theme-composer-text, currentColor) 9%, transparent);
}

.command-icon {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  background: color-mix(in srgb, var(--theme-composer-text, currentColor) 7%, transparent);
  color: color-mix(in srgb, var(--theme-composer-text, currentColor) 76%, transparent);
  font-size: 13px;
  font-weight: 700;
  line-height: 1;
}

.command-icon[data-command-kind="skill"] {
  background: color-mix(in srgb, #8ecbff 16%, transparent);
  color: #8ecbff;
}

.command-copy {
  min-width: 0;
  display: grid;
  gap: 3px;
}

.command-title-row {
  min-width: 0;
  display: flex;
  gap: 8px;
  align-items: baseline;
}

.command-copy strong,
.command-copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.command-copy strong {
  min-width: 0;
  color: var(--theme-composer-text, currentColor);
  font-size: 14px;
  font-weight: 650;
}

.command-copy small {
  color: color-mix(in srgb, var(--theme-composer-text, currentColor) 68%, transparent);
  font-size: 12px;
  line-height: 1.25;
}

.command-kind {
  flex: 0 0 auto;
  color: color-mix(in srgb, var(--theme-composer-text, currentColor) 52%, transparent);
  font-size: 11px;
  line-height: 1;
}

.command-footer {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  border-top: 1px solid color-mix(in srgb, var(--theme-composer-text, currentColor) 9%, transparent);
  padding: 6px 10px 7px;
  color: color-mix(in srgb, var(--theme-composer-text, currentColor) 52%, transparent);
  font-size: 11px;
}

.command-footer span {
  display: inline-flex;
  gap: 4px;
  align-items: center;
}

.command-footer kbd {
  min-width: 18px;
  border: 1px solid color-mix(in srgb, var(--theme-composer-text, currentColor) 14%, transparent);
  border-radius: 4px;
  padding: 1px 4px;
  background: color-mix(in srgb, var(--theme-composer-text, currentColor) 5%, transparent);
  color: color-mix(in srgb, var(--theme-composer-text, currentColor) 72%, transparent);
  font: inherit;
  line-height: 1.25;
  text-align: center;
}

@media (max-width: 560px) {
  .command-palette {
    width: 100%;
  }

  .command-footer {
    gap: 8px;
  }
}
</style>
