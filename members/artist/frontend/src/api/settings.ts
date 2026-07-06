import api from './client'
import type { DefaultModelsConfig } from '../types'

export const settingsApi = {
  getDefaultModels: () => api.get<DefaultModelsConfig>('/settings/default-models'),

  setDefaultModels: (data: DefaultModelsConfig) => api.put<DefaultModelsConfig>('/settings/default-models', data),

  getSetting: (key: string) => api.get(`/settings/${key}`),

  setSetting: (key: string, value: Record<string, unknown>) => api.put(`/settings/${key}`, value),
}
