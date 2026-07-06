import { defineStore } from 'pinia'
import { ref } from 'vue'
import { providerApi, vendorApi } from '../api/apiProvider'
import type { ApiProvider, ApiProviderCreate, ApiProviderUpdate, ApiVendor, ApiVendorCreate, ApiVendorUpdate } from '../types'

export const useProviderStore = defineStore('provider', () => {
  const providers = ref<ApiProvider[]>([])
  const vendors = ref<ApiVendor[]>([])
  const loading = ref(false)
  const currentProvider = ref<ApiProvider | null>(null)

  async function fetchProviders(providerType?: string) {
    loading.value = true
    try {
      const { data } = await providerApi.list(providerType)
      providers.value = data
    } catch (e) {
      console.error('Failed to fetch providers:', e)
    } finally {
      loading.value = false
    }
  }

  async function createProvider(data: ApiProviderCreate) {
    try {
      const { data: result } = await providerApi.create(data)
      providers.value.unshift(result)
      return result
    } catch (e) {
      console.error('Failed to create provider:', e)
      throw e
    }
  }

  async function updateProvider(id: string, data: ApiProviderUpdate) {
    try {
      const { data: result } = await providerApi.update(id, data)
      const idx = providers.value.findIndex((p) => p.id === id)
      if (idx !== -1) providers.value[idx] = result
      return result
    } catch (e) {
      console.error('Failed to update provider:', e)
      throw e
    }
  }

  async function deleteProvider(id: string) {
    try {
      await providerApi.delete(id)
      providers.value = providers.value.filter((p) => p.id !== id)
    } catch (e) {
      console.error('Failed to delete provider:', e)
      throw e
    }
  }

  async function testConnection(id: string) {
    try {
      const { data } = await providerApi.test(id)
      return data
    } catch (e) {
      console.error('Failed to test connection:', e)
      throw e
    }
  }

  async function fetchVendors() {
    loading.value = true
    try {
      const { data } = await vendorApi.list()
      vendors.value = data
    } catch (e) {
      console.error('Failed to fetch vendors:', e)
    } finally {
      loading.value = false
    }
  }

  async function createVendor(data: ApiVendorCreate) {
    const { data: result } = await vendorApi.create(data)
    vendors.value.unshift(result)
    return result
  }

  async function updateVendor(id: string, data: ApiVendorUpdate) {
    const { data: result } = await vendorApi.update(id, data)
    const idx = vendors.value.findIndex((v) => v.id === id)
    if (idx !== -1) vendors.value[idx] = result
    return result
  }

  async function deleteVendor(id: string) {
    await vendorApi.delete(id)
    vendors.value = vendors.value.filter((v) => v.id !== id)
  }

  async function testVendor(id: string) {
    const { data } = await vendorApi.test(id)
    return data
  }

  return {
    providers, vendors, loading, currentProvider,
    fetchProviders, createProvider, updateProvider, deleteProvider, testConnection,
    fetchVendors, createVendor, updateVendor, deleteVendor, testVendor,
  }
})
