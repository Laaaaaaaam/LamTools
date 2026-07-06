<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

type SelectOption = {
  value: string
  label: string
  disabled?: boolean
}

const props = defineProps<{
  modelValue: string
  options: SelectOption[]
  placeholder?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const open = ref(false)
const root = ref<HTMLElement | null>(null)

const selectedLabel = computed(() => {
  const option = props.options.find((item) => item.value === props.modelValue)
  return option?.label || props.placeholder || '未指定'
})

function toggle() {
  open.value = !open.value
}

function selectOption(option: SelectOption) {
  if (option.disabled) return
  emit('update:modelValue', option.value)
  open.value = false
}

function onPointerDown(event: PointerEvent) {
  const target = event.target as Node | null
  if (!target || !root.value || root.value.contains(target)) return
  open.value = false
}

onMounted(() => {
  document.addEventListener('pointerdown', onPointerDown)
})

onUnmounted(() => {
  document.removeEventListener('pointerdown', onPointerDown)
})
</script>

<template>
  <div ref="root" class="ui-select" :class="{ open }">
    <button class="ui-select-trigger" type="button" @click="toggle">
      <span>{{ selectedLabel }}</span>
      <span class="ui-select-arrow"></span>
    </button>
    <div v-if="open" class="ui-select-menu">
      <button
        v-for="option in options"
        :key="option.value"
        class="ui-select-option"
        :class="{ active: option.value === modelValue, disabled: option.disabled }"
        type="button"
        @click="selectOption(option)"
      >
        {{ option.label }}
      </button>
    </div>
  </div>
</template>
