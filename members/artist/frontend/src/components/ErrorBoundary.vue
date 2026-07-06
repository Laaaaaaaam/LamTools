<script setup lang="ts">
import { ref, onErrorCaptured } from 'vue'
import { AlertTriangle, RefreshCw } from '@lucide/vue'

const hasError = ref(false)
const errorMessage = ref('')

onErrorCaptured((err: Error) => {
  hasError.value = true
  errorMessage.value = err.message || 'Unknown error'
  return false
})

function retry() {
  hasError.value = false
  errorMessage.value = ''
}
</script>

<template>
  <div v-if="hasError" class="error-boundary">
    <AlertTriangle :size="24" />
    <p>组件渲染出错</p>
    <p class="error-detail">{{ errorMessage }}</p>
    <button class="small-btn" @click="retry">
      <RefreshCw :size="14" />
      重试
    </button>
  </div>
  <slot v-else />
</template>

<style scoped>
.error-boundary {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px;
  gap: 8px;
  color: #666;
}

.error-detail {
  font-size: 12px;
  color: #999;
  max-width: 400px;
  text-align: center;
}

.small-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 8px;
}
</style>
