<template>
  <div class="lightbox-overlay" v-if="visible" @click.self="$emit('close')">
    <div class="lightbox-content">
      <button class="lightbox-close" @click="$emit('close')">
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
      <img :src="imageUrl" class="lightbox-img" @click.stop />
      <div class="lightbox-actions">
        <button class="small-btn" @click="$emit('download', imageUrl)">下载</button>
        <button class="small-btn" @click="openInNewTab(imageUrl)">新窗口打开</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  visible: boolean
  imageUrl: string
}>()

defineEmits<{
  close: []
  download: [url: string]
}>()

function openInNewTab(url: string) {
  window.open(url, '_blank')
}
</script>

<style scoped>
.lightbox-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.85);
  z-index: 300;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.lightbox-content {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  cursor: default;
}

.lightbox-close {
  position: absolute;
  top: -40px;
  right: 0;
  background: none;
  border: none;
  color: #fff;
  cursor: pointer;
  padding: 4px;
  opacity: 0.7;
  transition: opacity 0.15s;
}

.lightbox-close:hover {
  opacity: 1;
}

.lightbox-img {
  max-width: 90vw;
  max-height: 80vh;
  border-radius: 4px;
  object-fit: contain;
}

.lightbox-actions {
  margin-top: 12px;
  display: flex;
  gap: 8px;
}
</style>
