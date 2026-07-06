import { ref } from 'vue'
import { settingsApi } from '../api/settings'

export interface DownloadTask {
  id: number
  url: string
  filename: string
  progress: number
  status: 'pending' | 'downloading' | 'done' | 'error'
  error?: string
  errorMsg?: string
  path?: string
}

export function generateFilename(url: string): string {
  try {
    const pathname = new URL(url, window.location.origin).pathname
    const name = pathname.split('/').pop() || 'image.png'
    if (/\.(png|jpg|jpeg|webp|gif|bmp)$/i.test(name)) return name
  } catch {}
  return 'image.png'
}

export function useDownload() {
  const downloadDir = ref('')
  let downloadTaskId = 0

  async function loadDownloadDir() {
    try {
      const res = await settingsApi.getSetting('download_directory')
      if (res.data && res.data.value) downloadDir.value = res.data.value
    } catch { /* ignore */ }
  }

  function triggerBlobDownload(blob: Blob, filename: string) {
    const blobUrl = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = blobUrl
    a.download = filename
    a.click()
    URL.revokeObjectURL(blobUrl)
  }

  function nextTaskId(): number {
    return ++downloadTaskId
  }

  return {
    downloadDir,
    loadDownloadDir,
    triggerBlobDownload,
    nextTaskId,
  }
}
