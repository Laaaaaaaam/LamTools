<template>
  <div class="composer-root">
    <form
      class="floating-composer"
      :class="{ dragover: dragOver }"
      @submit.prevent="$emit('submit')"
      @dragover.prevent="dragOver = true"
      @dragleave="dragOver = false"
      @drop.prevent="$emit('drop', $event); dragOver = false"
    >
      <slot name="preamble" />
      <textarea
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        rows="1"
        @input="$emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
        @keydown.enter.exact.prevent="$emit('submit')"
      />
      <div class="composer-bottom">
        <div class="tool-row">
          <slot name="attach-button" />
          <slot name="tools" />
        </div>
        <button
          class="send"
          type="submit"
          :disabled="disabled || !(modelValue || '').trim()"
          title="发送"
          aria-label="发送"
        >↑</button>
      </div>
      <div class="drop-hint">拖拽到这里上传</div>
    </form>
    <slot name="extras" />
  </div>
</template>

<script setup lang="ts">
/**
 * ComposerBar — floating composer bar (composer layer in the four-layer system)
 *
 * Renders a floating textarea with toolbar and send button.
 * Drag-and-drop support via slots and events.
 */
import { ref } from 'vue'

defineProps<{
  modelValue: string
  placeholder?: string
  disabled?: boolean
}>()

defineEmits<{
  'update:modelValue': [value: string]
  submit: []
  drop: [event: DragEvent]
}>()

const dragOver = ref(false)
</script>
