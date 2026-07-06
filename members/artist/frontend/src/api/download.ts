import api from './client'

export interface DownloadResult {
  success: boolean
  path: string
  size: number
  error?: string
}

export const downloadApi = {
  downloadImage: (url: string, filename: string) =>
    api.post<DownloadResult>('/download/image', { url, filename }),

  getDefaultPath: () =>
    api.get<{ path: string }>('/download/default-path'),
}
