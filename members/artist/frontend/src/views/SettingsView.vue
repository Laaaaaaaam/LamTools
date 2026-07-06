<template>
  <div class="settings-page" :style="settingsThemeStyle">
    <aside class="settings-sidebar">
      <div class="settings-brand">
        <strong>设置</strong>
        <button class="icon-btn" title="返回" @click="goWorkbench">×</button>
      </div>

      <nav class="settings-nav">
        <button
          v-for="section in sections"
          :key="section.id"
          :class="{ active: activeSection === section.id }"
          @click="activeSection = section.id"
        >
          <span>{{ section.icon }}</span>
          <span>{{ section.label }}</span>
        </button>
      </nav>

      <button class="settings-entry" @click="goWorkbench">
        <span>←</span>
        <span>返回主界面</span>
      </button>
    </aside>

    <main class="settings-main">
      <div v-if="saveMsg" class="settings-notice" :class="saveMsgType">{{ saveMsg }}</div>

      <section v-if="activeSection === 'model-api'" class="settings-content">
        <div class="settings-title">
          <h1>模型与 API</h1>
          <p>统一管理 Artist 主运行模型、图像生成模型、供应商和连接测试。</p>
        </div>
        <div class="settings-panel">
          <div class="setting-card">
            <div class="subhead">
              <strong>默认用途</strong>
            </div>
            <div class="route-purpose-list">
              <div class="route-purpose-row">
                <div>
                  <strong>Artist Runtime</strong>
                  <span>理解、规划、验收和回复</span>
                </div>
                <UiSelect
                  v-model="runtimeProviderId"
                  :options="[{ value: '', label: '未设置' }, ...llmProviderOptions]"
                  @update:model-value="saveDefaultModels"
                />
              </div>
              <div class="route-purpose-row">
                <div>
                  <strong>图像生成</strong>
                  <span>会话中的生图和改图</span>
                </div>
                <UiSelect
                  v-model="imageProviderId"
                  :options="[{ value: '', label: '未设置' }, ...imageProviderOptions]"
                  @update:model-value="saveDefaultModels"
                />
              </div>
            </div>
          </div>
          <div class="setting-card api-manage-card">
            <ApiManage />
          </div>
        </div>
      </section>

      <section v-else-if="activeSection === 'artist'" class="settings-content">
        <div class="settings-title">
          <h1>Artist 行为</h1>
          <p>控制默认生成规格和会话自动处理方式。</p>
        </div>
        <div class="settings-panel">
          <div class="setting-card">
            <label class="field">默认图像尺寸
              <div class="size-row">
                <input
                  v-model.number="defaultModels.default_image_width"
                  type="number"
                  min="64"
                  step="64"
                  @change="saveDefaultModels"
                />
                <span class="size-sep">×</span>
                <input
                  v-model.number="defaultModels.default_image_height"
                  type="number"
                  min="64"
                  step="64"
                  @change="saveDefaultModels"
                />
              </div>
              <span class="hint">具体限制取决于所使用的生图 API</span>
            </label>
          </div>
          <div class="setting-card">
            <label class="field">最大并发任务数
              <input v-model.number="defaultModels.max_concurrent" type="number" min="1" max="20" @change="saveDefaultModels" />
              <span class="hint">影响一批多图任务的同时执行上限</span>
            </label>
          </div>
        </div>
      </section>

      <section v-else-if="activeSection === 'workspace'" class="settings-content">
        <div class="settings-title">
          <h1>工作区</h1>
          <p>管理图片落地目录和本地会话辅助配置。</p>
        </div>
        <div class="settings-panel">
          <div class="setting-card">
            <label class="field">图片下载目录
              <input v-model="downloadDir" type="text" :placeholder="'留空则保存到: ' + defaultDownloadPath" @change="saveDownloadDir" />
              <span class="hint">设置后图片将直接保存到此目录</span>
            </label>
          </div>
        </div>
      </section>

      <section v-else-if="activeSection === 'tools'" class="settings-content">
        <div class="settings-title">
          <h1>工具</h1>
          <p>查看 Artist 当前依赖的外部能力，具体模型分配在“模型与 API”里配置。</p>
        </div>
        <div class="settings-panel">
          <div class="setting-card">
            <h3>运行能力</h3>
            <div class="tool-list">
              <label class="tool-toggle">
                <span class="tool-dot"></span>
                <strong>图像生成</strong>
                <span>根据本轮任务生成或修改图片</span>
              </label>
              <label class="tool-toggle">
                <span class="tool-dot"></span>
                <strong>视觉理解</strong>
                <span>读取上传图、参考图和生成结果</span>
              </label>
              <label class="tool-toggle">
                <span class="tool-dot"></span>
                <strong>外部调研</strong>
                <span>需要联网资料时用于趋势和事实补充</span>
              </label>
            </div>
          </div>
        </div>
      </section>

      <section v-else-if="activeSection === 'ui-system'" class="settings-content">
        <div class="settings-title">
          <h1>界面</h1>
          <p>控制界面密度、内容宽度和运行侧栏显示。</p>
        </div>
        <div class="settings-panel">
          <div class="setting-card">
            <h3>界面</h3>
            <label class="field">密度
              <UiSelect v-model="uiSystem.density" :options="densityOptions" @update:model-value="saveUiSystem" />
            </label>
            <label class="field width-field">
              <span>内容宽度 <em>{{ contentWidthText }}</em></span>
              <div class="width-control">
                <input v-model.number="uiSystem.contentWidth" type="range" min="560" max="1120" step="20" @change="saveUiSystem" />
                <input v-model.number="uiSystem.contentWidth" type="number" min="560" max="1120" step="20" @change="saveUiSystem" />
              </div>
            </label>
          </div>
          <div class="setting-card">
            <div class="subhead">
              <strong>主题</strong>
              <button class="small-btn" type="button" @click="resetTheme">恢复默认</button>
            </div>
            <div class="theme-preview" :style="themePreviewStyle">
              <aside>
                <strong>lamartist</strong>
                <span>背景板</span>
              </aside>
              <main :style="themePreviewMainStyle">
                <strong>主界面</strong>
                <span>会话 / 图片 / 状态</span>
                <div :style="themePreviewComposerStyle">输入栏</div>
                <button type="button" :style="themePreviewControlStyle">控件</button>
              </main>
            </div>
            <div class="theme-presets">
              <section v-for="group in visibleThemePresetGroups" :key="group.id" class="theme-preset-group">
                <h4>{{ group.label }}</h4>
                <div class="theme-preset-list">
                  <button
                    v-for="preset in presetsByGroup(group.id)"
                    :key="preset.id"
                    class="theme-preset"
                    type="button"
                    @click="applyThemePreset(preset)"
                  >
                    <span
                      class="preset-swatch"
                      :style="{ background: gradientFromStops(preset.theme.backdropAngle, preset.theme.backdropStops, 1) }"
                    >
                      <i :style="{ background: gradientFromStops(preset.theme.mainAngle, preset.theme.mainStops, preset.theme.mainOpacity) }"></i>
                      <b :style="{ background: gradientFromStops(preset.theme.composerAngle, preset.theme.composerStops, preset.theme.composerOpacity) }"></b>
                    </span>
                    <strong>{{ preset.name }}</strong>
                    <small>{{ preset.note }}</small>
                  </button>
                </div>
              </section>
            </div>
            <details class="theme-advanced">
              <summary>
                <span>高级自定义</span>
                <small>颜色节点、角度、透明度和文字颜色</small>
              </summary>
            <div class="theme-settings-grid">
              <section class="theme-area-card">
                <h4>背景板 / 侧边栏</h4>
                <div class="gradient-stop-list">
                  <div v-for="(stop, index) in uiSystem.theme.backdropStops" :key="`backdrop-${index}`" class="gradient-stop-row">
                    <span>{{ index + 1 }}</span>
                    <input v-model="stop.color" type="color" @change="saveUiSystem" />
                    <input v-model="stop.color" @change="saveUiSystem" />
                    <input v-model.number="stop.position" type="number" min="0" max="100" step="1" @change="sortGradientStops('backdrop')" />
                    <button type="button" :disabled="uiSystem.theme.backdropStops.length <= 2" @click="removeGradientStop('backdrop', index)">删</button>
                  </div>
                  <button class="small-btn" type="button" :disabled="uiSystem.theme.backdropStops.length >= 8" @click="addGradientStop('backdrop')">+ 添加节点</button>
                </div>
                <label class="field width-field">
                  <span>渐变角度 <em>{{ uiSystem.theme.backdropAngle }}deg</em></span>
                  <div class="width-control">
                    <input v-model.number="uiSystem.theme.backdropAngle" type="range" min="0" max="360" step="5" @change="saveUiSystem" />
                    <input v-model.number="uiSystem.theme.backdropAngle" type="number" min="0" max="360" step="5" @change="saveUiSystem" />
                  </div>
                </label>
                <label class="field color-field">文本颜色
                  <span><input v-model="uiSystem.theme.backdropText" type="color" @change="saveUiSystem" /><input v-model="uiSystem.theme.backdropText" @change="saveUiSystem" /></span>
                </label>
              </section>

              <section class="theme-area-card">
                <h4>主界面</h4>
                <div class="gradient-stop-list">
                  <div v-for="(stop, index) in uiSystem.theme.mainStops" :key="`main-${index}`" class="gradient-stop-row">
                    <span>{{ index + 1 }}</span>
                    <input v-model="stop.color" type="color" @change="saveUiSystem" />
                    <input v-model="stop.color" @change="saveUiSystem" />
                    <input v-model.number="stop.position" type="number" min="0" max="100" step="1" @change="sortGradientStops('main')" />
                    <button type="button" :disabled="uiSystem.theme.mainStops.length <= 2" @click="removeGradientStop('main', index)">删</button>
                  </div>
                  <button class="small-btn" type="button" :disabled="uiSystem.theme.mainStops.length >= 8" @click="addGradientStop('main')">+ 添加节点</button>
                </div>
                <label class="field width-field">
                  <span>渐变角度 <em>{{ uiSystem.theme.mainAngle }}deg</em></span>
                  <div class="width-control">
                    <input v-model.number="uiSystem.theme.mainAngle" type="range" min="0" max="360" step="5" @change="saveUiSystem" />
                    <input v-model.number="uiSystem.theme.mainAngle" type="number" min="0" max="360" step="5" @change="saveUiSystem" />
                  </div>
                </label>
                <label class="field width-field">
                  <span>透明度 <em>{{ mainOpacityText }}</em></span>
                  <div class="width-control">
                    <input v-model.number="uiSystem.theme.mainOpacity" type="range" min="0.1" max="1" step="0.05" @change="saveUiSystem" />
                    <input v-model.number="uiSystem.theme.mainOpacity" type="number" min="0.1" max="1" step="0.05" @change="saveUiSystem" />
                  </div>
                </label>
                <label class="field color-field">文本颜色
                  <span><input v-model="uiSystem.theme.mainText" type="color" @change="saveUiSystem" /><input v-model="uiSystem.theme.mainText" @change="saveUiSystem" /></span>
                </label>
              </section>

              <section class="theme-area-card">
                <h4>输入栏</h4>
                <div class="gradient-stop-list">
                  <div v-for="(stop, index) in uiSystem.theme.composerStops" :key="`composer-${index}`" class="gradient-stop-row">
                    <span>{{ index + 1 }}</span>
                    <input v-model="stop.color" type="color" @change="saveUiSystem" />
                    <input v-model="stop.color" @change="saveUiSystem" />
                    <input v-model.number="stop.position" type="number" min="0" max="100" step="1" @change="sortGradientStops('composer')" />
                    <button type="button" :disabled="uiSystem.theme.composerStops.length <= 2" @click="removeGradientStop('composer', index)">删</button>
                  </div>
                  <button class="small-btn" type="button" :disabled="uiSystem.theme.composerStops.length >= 8" @click="addGradientStop('composer')">+ 添加节点</button>
                </div>
                <label class="field width-field">
                  <span>渐变角度 <em>{{ uiSystem.theme.composerAngle }}deg</em></span>
                  <div class="width-control">
                    <input v-model.number="uiSystem.theme.composerAngle" type="range" min="0" max="360" step="5" @change="saveUiSystem" />
                    <input v-model.number="uiSystem.theme.composerAngle" type="number" min="0" max="360" step="5" @change="saveUiSystem" />
                  </div>
                </label>
                <label class="field width-field">
                  <span>透明度 <em>{{ composerOpacityText }}</em></span>
                  <div class="width-control">
                    <input v-model.number="uiSystem.theme.composerOpacity" type="range" min="0.1" max="1" step="0.05" @change="saveUiSystem" />
                    <input v-model.number="uiSystem.theme.composerOpacity" type="number" min="0.1" max="1" step="0.05" @change="saveUiSystem" />
                  </div>
                </label>
                <label class="field color-field">文本颜色
                  <span><input v-model="uiSystem.theme.composerText" type="color" @change="saveUiSystem" /><input v-model="uiSystem.theme.composerText" @change="saveUiSystem" /></span>
                </label>
              </section>

              <section class="theme-area-card">
                <h4>控件</h4>
                <div class="gradient-stop-list">
                  <div v-for="(stop, index) in uiSystem.theme.controlStops" :key="`control-${index}`" class="gradient-stop-row">
                    <span>{{ index + 1 }}</span>
                    <input v-model="stop.color" type="color" @change="saveUiSystem" />
                    <input v-model="stop.color" @change="saveUiSystem" />
                    <input v-model.number="stop.position" type="number" min="0" max="100" step="1" @change="sortGradientStops('control')" />
                    <button type="button" :disabled="uiSystem.theme.controlStops.length <= 2" @click="removeGradientStop('control', index)">删</button>
                  </div>
                  <button class="small-btn" type="button" :disabled="uiSystem.theme.controlStops.length >= 8" @click="addGradientStop('control')">+ 添加节点</button>
                </div>
                <label class="field width-field">
                  <span>渐变角度 <em>{{ uiSystem.theme.controlAngle }}deg</em></span>
                  <div class="width-control">
                    <input v-model.number="uiSystem.theme.controlAngle" type="range" min="0" max="360" step="5" @change="saveUiSystem" />
                    <input v-model.number="uiSystem.theme.controlAngle" type="number" min="0" max="360" step="5" @change="saveUiSystem" />
                  </div>
                </label>
                <label class="field width-field">
                  <span>透明度 <em>{{ controlOpacityText }}</em></span>
                  <div class="width-control">
                    <input v-model.number="uiSystem.theme.controlOpacity" type="range" min="0.1" max="1" step="0.05" @change="saveUiSystem" />
                    <input v-model.number="uiSystem.theme.controlOpacity" type="number" min="0.1" max="1" step="0.05" @change="saveUiSystem" />
                  </div>
                </label>
                <label class="field color-field">文本颜色
                  <span><input v-model="uiSystem.theme.controlText" type="color" @change="saveUiSystem" /><input v-model="uiSystem.theme.controlText" @change="saveUiSystem" /></span>
                </label>
              </section>
            </div>
            </details>
          </div>
          <div class="setting-card">
            <h3>运行面板</h3>
            <label class="toggle-line"><input v-model="uiSystem.showRuntime" type="checkbox" @change="saveUiSystem" /> 显示运行状态</label>
            <label class="toggle-line"><input v-model="uiSystem.showRecentImages" type="checkbox" @change="saveUiSystem" /> 显示最近图片</label>
          </div>
        </div>
      </section>

      <section v-else class="settings-content">
        <div class="settings-title">
          <h1>数据管理</h1>
          <p>本地缓存。</p>
        </div>
        <div class="settings-panel">
          <div class="setting-card">
            <div class="subhead">
              <strong>本地数据</strong>
            </div>
            <div class="data-actions">
              <button class="small-btn danger" @click="clearCache">清除缓存</button>
            </div>
          </div>
        </div>
      </section>
    </main>
    <ConfirmDialog />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import UiSelect from '../components/UiSelect.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import { useProviderStore } from '../stores/provider'
import { settingsApi } from '../api/settings'
import api from '../api/client'
import type { ApiProvider, DefaultModelsConfig } from '../types'
import { dialog } from '../composables/useDialog'
import ApiManage from './ApiManage.vue'

type SettingsSection = 'model-api' | 'artist' | 'workspace' | 'tools' | 'ui-system' | 'data'
type UiDensity = 'compact' | 'standard' | 'loose'
type ThemeStop = {
  color: string
  position: number
}
type ThemeArea = 'backdrop' | 'main' | 'composer' | 'control'
type ThemePreset = {
  id: string
  group: 'solid'
  name: string
  note: string
  theme: typeof defaultTheme
}

const providerStore = useProviderStore()
const router = useRouter()
const activeSection = ref<SettingsSection>('model-api')
const saveMsg = ref('')
const saveMsgType = ref<'success' | 'error'>('success')

const defaultModels = reactive<DefaultModelsConfig>({
  default_artist_runtime_provider_id: null,
  default_image_provider_id: null,
  default_image_width: 1024,
  default_image_height: 1024,
  max_concurrent: 5,
})
const searchRetryCount = ref(3)
const downloadDir = ref('')
const defaultDownloadPath = ref('')
const uiSystemStorageKey = 'lamartist.ui'
const defaultTheme = {
  backdropAngle: 180,
  backdropStops: [
    { color: '#000000', position: 0 },
    { color: '#000000', position: 100 },
  ],
  backdropText: '#f5f5f5',
  mainAngle: 180,
  mainStops: [
    { color: '#202020', position: 0 },
    { color: '#202020', position: 100 },
  ],
  mainText: '#f5f5f5',
  mainOpacity: 1,
  composerAngle: 180,
  composerStops: [
    { color: '#404040', position: 0 },
    { color: '#404040', position: 100 },
  ],
  composerText: '#f5f5f5',
  composerOpacity: 1,
  controlAngle: 180,
  controlStops: [
    { color: '#404040', position: 0 },
    { color: '#404040', position: 100 },
  ],
  controlText: '#f5f5f5',
  controlOpacity: 1,
}

const uiSystem = reactive({
  density: 'compact' as UiDensity,
  contentWidth: 780,
  showRuntime: true,
  showRecentImages: true,
  theme: { ...defaultTheme },
})

const sections: { id: SettingsSection; label: string; icon: string }[] = [
  { id: 'model-api', label: '模型与 API', icon: '◇' },
  { id: 'artist', label: 'Artist 行为', icon: '◉' },
  { id: 'workspace', label: '工作区', icon: '⌂' },
  { id: 'tools', label: '工具', icon: '✦' },
  { id: 'ui-system', label: '界面', icon: '▯' },
  { id: 'data', label: '数据管理', icon: '≡' },
]

const densityOptions: { value: UiDensity; label: string }[] = [
  { value: 'compact', label: '紧凑' },
  { value: 'standard', label: '标准' },
  { value: 'loose', label: '宽松' },
]

const themePresets: ThemePreset[] = [
  {
    id: 'artist-default-dark',
    group: 'solid',
    name: '默认暗色',
    note: '通用黑灰层级，适合夜间。',
    theme: {
      ...defaultTheme,
      backdropAngle: 180,
      backdropStops: [
        { color: '#000000', position: 0 },
        { color: '#000000', position: 100 },
      ],
      backdropText: '#f5f5f5',
      mainStops: [
        { color: '#202020', position: 0 },
        { color: '#202020', position: 100 },
      ],
      mainText: '#f5f5f5',
      composerStops: [
        { color: '#404040', position: 0 },
        { color: '#404040', position: 100 },
      ],
      composerText: '#f5f5f5',
      controlStops: [
        { color: '#404040', position: 0 },
        { color: '#404040', position: 100 },
      ],
      controlText: '#f5f5f5',
    },
  },
  {
    id: 'artist-default-light',
    group: 'solid',
    name: '默认亮色',
    note: '通用灰白层级，适合日间。',
    theme: {
      ...defaultTheme,
      backdropStops: [
        { color: '#dfdfdf', position: 0 },
        { color: '#dfdfdf', position: 100 },
      ],
      backdropText: '#1f1f1f',
      mainStops: [
        { color: '#ffffff', position: 0 },
        { color: '#ffffff', position: 100 },
      ],
      mainText: '#1f1f1f',
      composerStops: [
        { color: '#dfdfdf', position: 0 },
        { color: '#dfdfdf', position: 100 },
      ],
      composerText: '#1f1f1f',
      controlStops: [
        { color: '#bfbfbf', position: 0 },
        { color: '#bfbfbf', position: 100 },
      ],
      controlText: '#1f1f1f',
    },
  },
]

const themePresetGroups: Array<{ id: ThemePreset['group']; label: string }> = [
  { id: 'solid', label: '默认' },
]

const visibleThemePresetGroups = computed(() => (
  themePresetGroups.filter((group) => themePresets.some((preset) => preset.group === group.id))
))

const runtimeProviderId = computed({
  get: () => defaultModels.default_artist_runtime_provider_id || '',
  set: (value: string) => {
    defaultModels.default_artist_runtime_provider_id = value || null
  },
})

const imageProviderId = computed({
  get: () => defaultModels.default_image_provider_id || '',
  set: (value: string) => {
    defaultModels.default_image_provider_id = value || null
  },
})

const llmProviderOptions = computed(() => providerStore.providers
  .filter((provider) => provider.provider_type === 'llm' && provider.is_active)
  .map(providerOption))
const imageProviderOptions = computed(() => providerStore.providers
  .filter((provider) => provider.provider_type === 'image_gen' && provider.is_active)
  .map(providerOption))
const settingsThemeStyle = computed(() => ({
  '--settings-backdrop-background': gradientFromStops(uiSystem.theme.backdropAngle, uiSystem.theme.backdropStops, 1),
  '--settings-backdrop-text': uiSystem.theme.backdropText,
  '--settings-main-background': gradientFromStops(uiSystem.theme.mainAngle, uiSystem.theme.mainStops, uiSystem.theme.mainOpacity),
  '--settings-main-text': uiSystem.theme.mainText,
}))
const contentWidthText = computed(() => `${uiSystem.contentWidth}px`)
const mainOpacityText = computed(() => `${Math.round(uiSystem.theme.mainOpacity * 100)}%`)
const composerOpacityText = computed(() => `${Math.round(uiSystem.theme.composerOpacity * 100)}%`)
const controlOpacityText = computed(() => `${Math.round(uiSystem.theme.controlOpacity * 100)}%`)
const themePreviewStyle = computed(() => ({
  background: gradientFromStops(uiSystem.theme.backdropAngle, uiSystem.theme.backdropStops, 1),
  color: uiSystem.theme.backdropText,
}))
const themePreviewMainStyle = computed(() => ({
  background: gradientFromStops(uiSystem.theme.mainAngle, uiSystem.theme.mainStops, uiSystem.theme.mainOpacity),
  color: uiSystem.theme.mainText,
}))
const themePreviewComposerStyle = computed(() => ({
  background: gradientFromStops(uiSystem.theme.composerAngle, uiSystem.theme.composerStops, uiSystem.theme.composerOpacity),
  color: uiSystem.theme.composerText,
}))
const themePreviewControlStyle = computed(() => ({
  background: gradientFromStops(uiSystem.theme.controlAngle, uiSystem.theme.controlStops, uiSystem.theme.controlOpacity),
  color: uiSystem.theme.controlText,
}))

function providerOption(provider: ApiProvider) {
  return {
    value: provider.id,
    label: `${provider.vendor_name ? `${provider.vendor_name} / ` : ''}${provider.nickname || provider.model_id}`,
  }
}

function goWorkbench() {
  router.push('/')
}

onMounted(async () => {
  loadUiSystem()
  await providerStore.fetchProviders()
  try {
    const { data } = await settingsApi.getDefaultModels()
    defaultModels.default_artist_runtime_provider_id = data.default_artist_runtime_provider_id || data.default_optimize_provider_id || null
    defaultModels.default_image_provider_id = data.default_image_provider_id
    if (data.default_image_width) defaultModels.default_image_width = data.default_image_width
    if (data.default_image_height) defaultModels.default_image_height = data.default_image_height
    if (data.max_concurrent) defaultModels.max_concurrent = data.max_concurrent
    try {
      const retryRes = await settingsApi.getSetting('search_retry_count')
      if (retryRes.data && retryRes.data.value != null) searchRetryCount.value = retryRes.data.value
    } catch { /* ignore */ }
    try {
      const dirRes = await settingsApi.getSetting('download_directory')
      if (dirRes.data && dirRes.data.value) downloadDir.value = dirRes.data.value
    } catch { /* ignore */ }
    try {
      const defRes = await api.get('/download/default-path')
      if (defRes.data?.path) defaultDownloadPath.value = defRes.data.path
    } catch { /* ignore */ }
  } catch { /* ignore */ }
})

async function saveDefaultModels() {
  try {
    await settingsApi.setDefaultModels({
      ...defaultModels,
      default_optimize_provider_id: defaultModels.default_artist_runtime_provider_id,
    })
    showSaveMsg('设置已保存', 'success')
  } catch {
    showSaveMsg('保存失败', 'error')
  }
}

async function saveDownloadDir() {
  try {
    await settingsApi.setSetting('download_directory', { value: downloadDir.value || '' })
    showSaveMsg('已保存', 'success')
  } catch {
    showSaveMsg('保存失败', 'error')
  }
}

function clampNumber(value: unknown, min: number, max: number, fallback: number) {
  const numberValue = Number(value)
  if (!Number.isFinite(numberValue)) return fallback
  return Math.min(max, Math.max(min, numberValue))
}

function rgbaFromHex(color: string, opacity: number) {
  const normalized = /^#[0-9a-f]{6}$/i.test(color) ? color : '#121313'
  const value = Number.parseInt(normalized.slice(1), 16)
  const r = (value >> 16) & 255
  const g = (value >> 8) & 255
  const b = value & 255
  return `rgba(${r}, ${g}, ${b}, ${clampNumber(opacity, 0.1, 1, 1)})`
}

function gradientFromStops(angle: number, stops: Array<{ color: string; position: number }>, opacity: number) {
  const normalized = Array.isArray(stops) && stops.length >= 2 ? stops : defaultTheme.mainStops
  const parts = normalized
    .slice(0, 8)
    .sort((a, b) => a.position - b.position)
    .map((stop, index, source) => {
      const position = index === 0 ? 0 : index === source.length - 1 ? 100 : clampNumber(stop.position, 0, 100, 50)
      return `${rgbaFromHex(stop.color, opacity)} ${position}%`
    })
  return `linear-gradient(${clampNumber(angle, 0, 360, 180)}deg, ${parts.join(', ')})`
}

function normalizeGradientStops(stops: ThemeStop[], fallbackStart: string, fallbackEnd: string): ThemeStop[] {
  const valid = stops
    .filter((stop) => /^#[0-9a-f]{6}$/i.test(stop.color))
    .map((stop) => ({ color: stop.color, position: clampNumber(stop.position, 0, 100, 50) }))
    .sort((a, b) => a.position - b.position)
    .slice(0, 8)
  if (valid.length >= 2) {
    valid[0].position = 0
    valid[valid.length - 1].position = 100
    return valid
  }
  return [
    { color: fallbackStart, position: 0 },
    { color: fallbackEnd, position: 100 },
  ]
}

function gradientStops(area: ThemeArea): ThemeStop[] {
  return uiSystem.theme[`${area}Stops` as const] as ThemeStop[]
}

function addGradientStop(area: ThemeArea) {
  const stops = gradientStops(area)
  if (stops.length >= 8) return
  const middle = Math.round((stops[0]?.position ?? 0) + ((stops[stops.length - 1]?.position ?? 100) - (stops[0]?.position ?? 0)) / 2)
  stops.push({
    color: stops[Math.floor(stops.length / 2)]?.color || '#222222',
    position: middle,
  })
  sortGradientStops(area)
}

function removeGradientStop(area: ThemeArea, index: number) {
  const stops = gradientStops(area)
  if (stops.length <= 2) return
  stops.splice(index, 1)
  sortGradientStops(area)
}

function sortGradientStops(area: ThemeArea) {
  const stops = gradientStops(area)
  const normalized = normalizeGradientStops(stops, stops[0]?.color || '#000000', stops[stops.length - 1]?.color || '#000000')
  stops.splice(0, stops.length, ...normalized)
  saveUiSystem()
}

function presetsByGroup(group: ThemePreset['group']) {
  return themePresets.filter((preset) => preset.group === group)
}

function loadUiSystem() {
  try {
    const raw = localStorage.getItem(uiSystemStorageKey)
    if (!raw) return
    const saved = JSON.parse(raw)
    if (saved.density) uiSystem.density = saved.density
    if (saved.contentWidth) uiSystem.contentWidth = saved.contentWidth
    if (typeof saved.showRuntime === 'boolean') uiSystem.showRuntime = saved.showRuntime
    if (typeof saved.showRecentImages === 'boolean') uiSystem.showRecentImages = saved.showRecentImages
    if (saved.theme) uiSystem.theme = { ...defaultTheme, ...saved.theme }
  } catch { /* ignore */ }
}

function saveUiSystem() {
  localStorage.setItem(uiSystemStorageKey, JSON.stringify(uiSystem))
  showSaveMsg('界面设置已保存', 'success')
}

function resetTheme() {
  uiSystem.theme = { ...defaultTheme }
  saveUiSystem()
}

function applyThemePreset(preset: ThemePreset) {
  uiSystem.theme = { ...defaultTheme, ...preset.theme }
  saveUiSystem()
}

function showSaveMsg(msg: string, type: 'success' | 'error') {
  saveMsg.value = msg
  saveMsgType.value = type
  setTimeout(() => { saveMsg.value = '' }, 2000)
}

async function clearCache() {
  if (await dialog.showConfirm('确定清除所有缓存数据？')) {
    localStorage.clear()
    showSaveMsg('缓存已清除', 'success')
  }
}

</script>

<style scoped>
.settings-notice.error {
  color: #ff9a9f;
}

.settings-panel {
  max-width: 1120px;
}

.api-manage-card {
  padding: 0;
  overflow: hidden;
}

.route-purpose-list,
.tool-list {
  display: grid;
  gap: 10px;
}

.route-purpose-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: 16px;
  align-items: center;
  padding: 12px;
  border-radius: 10px;
  border: 1px solid rgba(255,255,255,.08);
  background: rgba(255,255,255,.035);
}

.route-purpose-row div {
  display: grid;
  gap: 4px;
}

.route-purpose-row strong,
.tool-toggle strong {
  font-size: 13px;
  color: #f2efeb;
}

.route-purpose-row span,
.tool-toggle span:last-child,
.hint {
  font-size: 12px;
  color: #a7a29b;
}

.field {
  display: grid;
  gap: 8px;
  font-size: 13px;
  color: #f2efeb;
}

.field > span {
  font-weight: 650;
}

.size-row,
.width-control {
  display: flex;
  align-items: center;
  gap: 8px;
}

.size-row input {
  width: 120px;
  text-align: center;
}

.size-sep {
  color: #817c75;
}

.toggle-line {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  font-size: 13px;
  color: #c9c4bd;
}

.tool-toggle {
  display: grid;
  grid-template-columns: auto 130px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  padding: 12px;
  border-radius: 10px;
  border: 1px solid rgba(255,255,255,.08);
  background: rgba(255,255,255,.035);
}

.tool-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #79bcff;
}

.data-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

@media (max-width: 820px) {
  .route-purpose-row {
    grid-template-columns: 1fr;
  }
}
</style>
