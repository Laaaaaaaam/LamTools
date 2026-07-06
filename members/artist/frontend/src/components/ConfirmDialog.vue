<template>
  <Teleport to="body">
    <div v-if="visible" class="dialog-overlay" @click.self="cancel">
      <div class="dialog-panel">
        <div class="dialog-title" v-if="options.title">{{ options.title }}</div>
        <div class="dialog-body">{{ options.message }}</div>

        <div v-if="mode === 'prompt'" class="dialog-input-wrap">
          <label v-if="options.inputLabel" class="dialog-input-label">{{ options.inputLabel }}</label>
          <input
            v-model="inputValue"
            type="text"
            class="dialog-input"
            @keyup.enter="confirm"
            ref="inputRef"
          />
        </div>

        <div class="dialog-actions">
          <button v-if="mode !== 'alert'" class="small-btn" @click="cancel">取消</button>
          <button
            class="small-btn"
            :class="mode === 'confirm' ? 'danger' : 'primary'"
            @click="confirm"
          >
            {{ mode === 'confirm' ? '删除' : '确定' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { dialog } from '../composables/useDialog'

const {
  visible,
  options,
  mode,
  inputValue,
  confirm,
  cancel,
} = dialog

const inputRef = ref<HTMLInputElement | null>(null)

watch(visible, async (v) => {
  if (v) {
    await nextTick()
    inputRef.value?.focus()
  }
})
</script>

<style scoped>
.dialog-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
}

.dialog-panel {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 6px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.12);
  width: 380px;
  max-width: 90vw;
  padding: 24px;
}

.dialog-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 12px;
}

.dialog-body {
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.6;
  margin-bottom: 20px;
}

.dialog-input-wrap {
  margin-bottom: 20px;
}

.dialog-input-label {
  display: block;
  margin-bottom: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
}

.dialog-input {
  width: 100%;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--card);
  color: var(--text);
  font-size: 14px;
  outline: none;
  transition: border-color 0.15s;
}

.dialog-input:focus {
  border-color: var(--accent);
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.dialog-actions .small-btn.primary {
  color: var(--text);
  border-color: color-mix(in srgb, var(--text) 18%, transparent);
}
</style>
