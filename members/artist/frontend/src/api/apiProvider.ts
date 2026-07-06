import api from './client'
import type { ApiProvider, ApiProviderCreate, ApiProviderUpdate, ApiVendor, ApiVendorCreate, ApiVendorUpdate } from '../types'

export const vendorApi = {
  list: () =>
    api.get<ApiVendor[]>('/vendors'),

  get: (id: string) =>
    api.get<ApiVendor>(`/vendors/${id}`),

  create: (data: ApiVendorCreate) =>
    api.post<ApiVendor>('/vendors', data),

  update: (id: string, data: ApiVendorUpdate) =>
    api.put<ApiVendor>(`/vendors/${id}`, data),

  delete: (id: string) =>
    api.delete(`/vendors/${id}`),

  test: (id: string) =>
    api.post<{ success: boolean; message: string }>(`/vendors/${id}/test`),

  listModels: (vendorId: string) =>
    api.get<ApiProvider[]>(`/vendors/${vendorId}/models`),

  createModel: (vendorId: string, data: ApiProviderCreate) =>
    api.post<ApiProvider>(`/vendors/${vendorId}/models`, data),

  updateModel: (vendorId: string, modelId: string, data: ApiProviderUpdate) =>
    api.put<ApiProvider>(`/vendors/${vendorId}/models/${modelId}`, data),

  deleteModel: (vendorId: string, modelId: string) =>
    api.delete(`/vendors/${vendorId}/models/${modelId}`),
}

export const providerApi = {
  list: (providerType?: string, vendorId?: string) =>
    api.get<ApiProvider[]>('/providers', { params: { provider_type: providerType, vendor_id: vendorId } }),

  get: (id: string) =>
    api.get<ApiProvider>(`/providers/${id}`),

  create: (data: ApiProviderCreate) =>
    api.post<ApiProvider>('/providers', data),

  update: (id: string, data: ApiProviderUpdate) =>
    api.put<ApiProvider>(`/providers/${id}`, data),

  delete: (id: string) =>
    api.delete(`/providers/${id}`),

  test: (id: string) =>
    api.post<{ success: boolean; message: string }>(`/providers/${id}/test`),
}
