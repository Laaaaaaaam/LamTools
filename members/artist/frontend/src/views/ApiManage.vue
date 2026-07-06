<template>
  <div class="api-manage">
    <div v-if="!store.loading && !store.vendors.length" class="empty compact-empty">暂无供应商</div>

    <div v-for="v in store.vendors" :key="v.id" class="provider-card">
      <div class="provider-head">
        <div>
          <strong>{{ v.name }}</strong>
          <span>{{ v.is_active ? '启用' : '停用' }} · {{ v.model_count }} 个模型</span>
        </div>
        <div class="provider-actions">
          <button class="small-btn" @click="toggleVendor(v.id)">{{ isVendorExpanded(v.id) ? '收起' : '展开' }}</button>
          <button class="small-btn" @click="testVendorConn(v.id)">测试</button>
          <button class="small-btn" @click="openVendorDrawer(v)">编辑</button>
          <button class="small-btn danger" @click="removeVendor(v.id)">删除</button>
        </div>
      </div>

      <div v-if="isVendorExpanded(v.id)" class="provider-body">
        <div class="api-fields">
          <div class="api-field"><span>API Key</span><code>{{ v.api_key_masked || '未配置' }}</code></div>
          <div class="api-field"><span>Base URL</span><code>{{ v.base_url }}</code></div>
        </div>

        <div class="subhead">
          <strong>Models</strong>
          <button class="small-btn" @click="openModelDrawer(v)">+ 新增 model</button>
        </div>

        <div class="model-list">
          <div v-if="getVendorModels(v.id).length === 0" class="empty compact-empty">暂无模型</div>
          <div v-for="m in getVendorModels(v.id)" :key="m.id" class="model-row">
            <div>
              <strong>{{ m.nickname || m.model_id }}</strong>
              <div class="model-params">
                <span class="param">{{ providerTypeLabel(m.provider_type) }}</span>
                <span class="param">{{ m.model_id }}</span>
                <span class="param">{{ m.billing_type === 'per_call' ? '按次' : '按 Token' }} {{ m.unit_price }} {{ m.currency }}</span>
                <span class="param">{{ m.is_active ? '启用' : '停用' }}</span>
              </div>
            </div>
            <div class="row-actions">
              <button class="small-btn" @click="testConn(m.id)">测试</button>
              <button class="small-btn" @click="openModelDrawer(v, m)">参数</button>
              <button class="small-btn danger" @click="removeProvider(m.id)">删除</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <button class="add-row" @click="() => openVendorDrawer()">+ 新增 provider</button>

    <!-- Vendor Modal -->
    <div v-if="vendorDrawerOpen" class="modal-overlay" @click.self="vendorDrawerOpen = false">
      <div class="modal-card">
        <h2>{{ editingVendor ? '编辑供应商' : '添加供应商' }}</h2>
        <div class="form-grid">
          <label class="field">名称
            <input v-model="vendorForm.name" type="text" placeholder="供应商名称" />
          </label>
          <label class="field">接口地址
            <input v-model="vendorForm.base_url" type="url" placeholder="https://api.openai.com" />
          </label>
          <label class="field">API 密钥
            <input v-model="vendorForm.api_key" type="password" :placeholder="editingVendor ? '留空保持不变' : 'sk-...'" />
          </label>
          <label class="toggle-line"><input v-model="vendorForm.is_active" type="checkbox" /> 启用</label>
        </div>
        <div v-if="testResult" class="test-result" :class="testResult.success ? 'success' : 'error'">
          {{ testResult.message }}
        </div>
        <div class="modal-actions">
          <button @click="vendorDrawerOpen = false">取消</button>
          <button class="btn-primary" @click="saveVendor">{{ editingVendor ? '更新' : '创建' }}</button>
        </div>
      </div>
    </div>

    <!-- Model Modal -->
    <div v-if="modelDrawerOpen" class="modal-overlay" @click.self="modelDrawerOpen = false">
      <div class="modal-card">
        <h2>{{ editingModel ? '编辑模型' : '添加模型' }} - {{ modelVendor?.name }}</h2>
        <div class="form-grid">
          <label class="field">名称
            <input v-model="modelForm.nickname" type="text" placeholder="显示名称" />
          </label>
          <label class="field">模型 ID
            <input v-model="modelForm.model_id" type="text" placeholder="gpt-4o" />
          </label>
          <label class="field">类型
            <select v-model="modelForm.provider_type">
              <option value="llm">LLM</option>
              <option value="image_gen">图像生成</option>
              <option value="web_search">联网搜索</option>
            </select>
          </label>
          <label class="field">计费方式
            <select v-model="modelForm.billing_type">
              <option value="per_call">按次计费</option>
              <option value="per_token">按 Token 计费</option>
            </select>
          </label>
          <label class="field">单价
            <input v-model.number="modelForm.unit_price" type="number" step="0.000001" min="0" />
          </label>
          <label class="field">货币
            <select v-model="modelForm.currency">
              <option value="CNY">CNY</option>
              <option value="USD">USD</option>
            </select>
          </label>
          <label class="toggle-line"><input v-model="modelForm.is_active" type="checkbox" /> 启用</label>
        </div>
        <div v-if="testResult" class="test-result" :class="testResult.success ? 'success' : 'error'">
          {{ testResult.message }}
        </div>
        <div class="modal-actions">
          <button @click="modelDrawerOpen = false">取消</button>
          <button class="btn-primary" @click="saveModel">{{ editingModel ? '更新' : '创建' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue'
import { useProviderStore } from '../stores/provider'
import type { ApiProvider, ApiVendor } from '../types'
import { dialog } from '../composables/useDialog'

const store = useProviderStore()
const testResult = ref<{ success: boolean; message: string } | null>(null)
const expandedVendors = ref<Set<string>>(new Set())

// Vendor form state
const vendorDrawerOpen = ref(false)
const editingVendor = ref<ApiVendor | null>(null)

const vendorForm = reactive({
  name: '',
  base_url: '',
  api_key: '',
  is_active: true,
})

// Model form state
const modelDrawerOpen = ref(false)
const modelVendor = ref<ApiVendor | null>(null)
const editingModel = ref<ApiProvider | null>(null)

const modelForm = reactive({
  nickname: '',
  model_id: '',
  provider_type: 'llm' as 'llm' | 'image_gen' | 'web_search',
  billing_type: 'per_call' as 'per_call' | 'per_token',
  unit_price: 0,
  currency: 'CNY',
  is_active: true,
})

onMounted(async () => {
  await store.fetchVendors()
  await store.fetchProviders()
})

function getVendorModels(vendorId: string): ApiProvider[] {
  return store.providers.filter(p => p.vendor_id === vendorId)
}

function providerTypeLabel(type: ApiProvider['provider_type']) {
  if (type === 'llm') return 'LLM'
  if (type === 'web_search') return '联网搜索'
  return '图像生成'
}

function isVendorExpanded(id: string) {
  return expandedVendors.value.has(id)
}

function toggleVendor(id: string) {
  const next = new Set(expandedVendors.value)
  if (next.has(id)) {
    next.delete(id)
  } else {
    next.add(id)
  }
  expandedVendors.value = next
}

function openVendorDrawer(vendor?: ApiVendor) {
  editingVendor.value = vendor || null
  testResult.value = null
  if (vendor) {
    Object.assign(vendorForm, {
      name: vendor.name,
      base_url: vendor.base_url,
      api_key: '',
      is_active: vendor.is_active,
    })
  } else {
    Object.assign(vendorForm, {
      name: '', base_url: '', api_key: '', is_active: true,
    })
  }
  vendorDrawerOpen.value = true
}

async function saveVendor() {
  try {
    if (editingVendor.value) {
      const data: Record<string, unknown> = { ...vendorForm }
      if (!vendorForm.api_key) delete data.api_key
      await store.updateVendor(editingVendor.value.id, data)
    } else {
      await store.createVendor({ ...vendorForm })
    }
    vendorDrawerOpen.value = false
  } catch (e: any) {
    dialog.showAlert(e.response?.data?.detail || e.message || '操作失败')
  }
}

async function testVendorConn(id: string) {
  testResult.value = null
  try {
    const result = await store.testVendor(id)
    testResult.value = result as any
  } catch (e: any) {
    testResult.value = { success: false, message: e.message || '测试失败' }
  }
}

async function removeVendor(id: string) {
  if (await dialog.showConfirm('确定删除此供应商及其所有模型？')) {
    await store.deleteVendor(id)
    await store.fetchProviders()
  }
}

function openModelDrawer(vendor: ApiVendor, model?: ApiProvider) {
  modelVendor.value = vendor
  editingModel.value = model || null
  testResult.value = null
  if (model) {
    Object.assign(modelForm, {
      nickname: model.nickname || model.model_id,
      model_id: model.model_id,
      provider_type: model.provider_type,
      billing_type: model.billing_type,
      unit_price: model.unit_price,
      currency: model.currency,
      is_active: model.is_active,
    })
  } else {
    Object.assign(modelForm, {
      nickname: '', model_id: '',
      provider_type: 'llm', billing_type: 'per_call', unit_price: 0, currency: 'CNY', is_active: true,
    })
  }
  modelDrawerOpen.value = true
}

async function saveModel() {
  if (!modelVendor.value) return
  try {
    if (editingModel.value) {
      await store.updateProvider(editingModel.value.id, { ...modelForm })
    } else {
      await store.createProvider({
        ...modelForm,
        vendor_id: modelVendor.value.id,
      })
    }
    await store.fetchProviders()
    await store.fetchVendors()
    modelDrawerOpen.value = false
  } catch (e: any) {
    dialog.showAlert(e.response?.data?.detail || e.message || '操作失败')
  }
}

async function testConn(id: string) {
  testResult.value = null
  try {
    const result = await store.testConnection(id)
    testResult.value = result as any
  } catch (e: any) {
    testResult.value = { success: false, message: e.message || '测试失败' }
  }
}

async function removeProvider(id: string) {
  if (await dialog.showConfirm('确定删除此模型？')) {
    await store.deleteProvider(id)
    await store.fetchVendors()
  }
}
</script>

<style scoped>
.test-result {
  margin-top: 12px;
  padding: 8px 12px;
  border-radius: var(--radius);
  font-size: 13px;
}
.field select {
  width: 100%;
  min-height: 38px;
  border: 1px solid color-mix(in srgb, var(--settings-main-text, var(--text)) 12%, transparent);
  border-radius: 10px;
  background: color-mix(in srgb, var(--settings-main-text, var(--text)) 4%, transparent);
  color: var(--settings-main-text, var(--text));
  padding: 0 10px;
  outline: none;
}
.field select:focus {
  border-color: color-mix(in srgb, var(--settings-main-text, var(--text)) 28%, transparent);
}
.test-result.success {
  background: color-mix(in srgb, var(--settings-main-text, var(--text)) 8%, transparent);
  color: color-mix(in srgb, var(--settings-main-text, var(--text)) 78%, transparent);
}
.test-result.error {
  background: rgba(239,68,68,0.1);
  color: #ef4444;
}
</style>
