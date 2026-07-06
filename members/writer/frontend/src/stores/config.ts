// ============================================================
// Config Store — manages LLM providers, models, and runtime settings
// ============================================================

import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as api from '@/api'
import type {
  Provider,
  ProviderCreate,
  ProviderUpdate,
  Model,
  ModelCreate,
  ModelUpdate,
  ResolvedConfig,
  RuntimeCapabilities,
  AppSetting,
  AdapterProfile,
  SubAgentDefinition,
  SubAgentDefinitionUpdate,
} from '@/types'

const MASKED_PATTERN = /^\*{4,}$/

/**
 * Returns true if the api_key value looks like a masked key
 * (e.g., "abcd...efgh", "********", or empty).
 * In these cases the key hasn't been changed by the user.
 */
function isKeyMasked(key: string | undefined): boolean {
  if (!key) return true
  if (key === '') return true
  if (MASKED_PATTERN.test(key)) return true
  // Provider api_key is masked as first4...last4, but if user types a full key
  // it won't contain "..." — unless it genuinely has "..." in it.
  // We check: if it has 4 chars + "..." + 4 chars pattern like "abcd...efgh"
  if (/^[a-zA-Z0-9]{2,8}\.\.\.[a-zA-Z0-9]{2,8}$/.test(key)) return true
  return false
}

export const useConfigStore = defineStore('config', () => {
  // --- State ---

  const providers = ref<Provider[]>([])
  const models = ref<Model[]>([])
  const resolvedConfig = ref<ResolvedConfig | null>(null)
  const runtimeCapabilities = ref<RuntimeCapabilities | null>(null)
  const adapterProfiles = ref<AdapterProfile[]>([])
  const loading = ref(false)

  // --- Provider Actions ---

  async function fetchProviders() {
    loading.value = true
    try {
      providers.value = await api.listProviders()
    } finally {
      loading.value = false
    }
  }

  async function createProvider(data: ProviderCreate): Promise<Provider> {
    const provider = await api.createProvider(data)
    providers.value.unshift(provider)
    return provider
  }

  /**
   * Update a provider. If api_key is masked (not changed by user),
   * we strip it from the payload so the backend keeps the existing key.
   */
  async function updateProvider(id: string, data: ProviderUpdate): Promise<Provider> {
    const payload: ProviderUpdate = { ...data }

    // Check if api_key should be sent
    if (isKeyMasked(payload.api_key)) {
      delete payload.api_key
    }

    const provider = await api.updateProvider(id, payload)
    const idx = providers.value.findIndex((p) => p.id === id)
    if (idx !== -1) providers.value[idx] = provider
    return provider
  }

  async function deleteProvider(id: string) {
    await api.deleteProvider(id)
    providers.value = providers.value.filter((p) => p.id !== id)
  }

  async function importEnvConfig() {
    const result = await api.importEnvConfig()
    await Promise.all([fetchProviders(), fetchModels(), fetchResolvedConfig('writer')])
    return result
  }

  // --- Model Actions ---

  async function fetchModels(providerId?: string) {
    loading.value = true
    try {
      models.value = await api.listModels(providerId)
    } finally {
      loading.value = false
    }
  }

  async function createModel(data: ModelCreate): Promise<Model> {
    const model = await api.createModel(data)
    models.value.unshift(model)
    return model
  }

  async function updateModel(id: string, data: ModelUpdate): Promise<Model> {
    const model = await api.updateModel(id, data)
    const idx = models.value.findIndex((m) => m.id === id)
    if (idx !== -1) models.value[idx] = model
    return model
  }

  async function deleteModel(id: string) {
    await api.deleteModel(id)
    models.value = models.value.filter((m) => m.id !== id)
  }

  async function fetchResolvedConfig(taskType: string = 'default') {
    resolvedConfig.value = await api.getResolvedConfig(taskType)
  }

  async function fetchRuntimeCapabilities(workRoot?: string) {
    runtimeCapabilities.value = await api.getRuntimeCapabilities(workRoot)
    return runtimeCapabilities.value
  }

  async function fetchAdapterProfiles() {
    adapterProfiles.value = await api.listAdapterProfiles()
    return adapterProfiles.value
  }

  async function fetchAppSetting(namespace: string): Promise<AppSetting> {
    return api.getAppSetting(namespace)
  }

  async function saveAppSetting(namespace: string, value: Record<string, unknown>): Promise<AppSetting> {
    return api.putAppSetting(namespace, value)
  }

  async function saveProjectSubAgent(workRoot: string, agent: SubAgentDefinitionUpdate): Promise<SubAgentDefinition> {
    const saved = await api.saveProjectSubAgent(workRoot, agent)
    await fetchRuntimeCapabilities(workRoot)
    return saved
  }

  async function deleteProjectSubAgent(workRoot: string, name: string): Promise<void> {
    await api.deleteProjectSubAgent(workRoot, name)
    await fetchRuntimeCapabilities(workRoot)
  }

  return {
    providers,
    models,
    resolvedConfig,
    runtimeCapabilities,
    adapterProfiles,
    loading,
    fetchProviders,
    createProvider,
    updateProvider,
    deleteProvider,
    importEnvConfig,
    fetchModels,
    createModel,
    updateModel,
    deleteModel,
    fetchResolvedConfig,
    fetchRuntimeCapabilities,
    fetchAdapterProfiles,
    fetchAppSetting,
    saveAppSetting,
    saveProjectSubAgent,
    deleteProjectSubAgent,
  }
})
