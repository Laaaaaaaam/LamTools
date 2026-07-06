<template>
  <div class="theme-editor-root">
    <!-- Live preview -->
    <div class="setting-card">
      <div class="subhead">
        <strong>主题</strong>
        <button class="small-btn" type="button" @click="$emit('reset-theme')">恢复默认</button>
      </div>
      <div class="theme-preview" :style="themePreviewStyle">
        <aside>
          <strong>{{ productName }}</strong>
          <span>背景板</span>
        </aside>
        <main :style="themePreviewMainStyle">
          <strong>主界面</strong>
          <span>{{ contentDescription }}</span>
          <div :style="themePreviewComposerStyle">输入栏</div>
          <button type="button" :style="themePreviewControlStyle">控件</button>
        </main>
      </div>
      <!-- Presets -->
      <div class="theme-presets">
        <section
          v-for="group in presetGroups"
          :key="group.id"
          class="theme-preset-group"
        >
          <h4>{{ group.label }}</h4>
          <div class="theme-preset-list">
            <button
              v-for="preset in presetsByGroup(group.id)"
              :key="preset.id"
              class="theme-preset"
              type="button"
              @click="$emit('apply-preset', preset)"
            >
              <span
                class="preset-swatch"
                :style="{
                  background: gradientFromStops(
                    (preset.theme as any).backdropAngle ?? defaultBackdropAngle,
                    (preset.theme as any).backdropStops ?? defaultBackdropStops,
                    1,
                  ),
                }"
              >
                <i
                  :style="{
                    background: gradientFromStops(
                      (preset.theme as any).mainAngle ?? defaultMainAngle,
                      (preset.theme as any).mainStops ?? defaultMainStops,
                      (preset.theme as any).mainOpacity ?? 1,
                    ),
                  }"
                />
                <b
                  :style="{
                    background: gradientFromStops(
                      (preset.theme as any).composerAngle ?? defaultComposerAngle,
                      (preset.theme as any).composerStops ?? defaultComposerStops,
                      (preset.theme as any).composerOpacity ?? 1,
                    ),
                  }"
                />
              </span>
              <strong>{{ preset.name }}</strong>
              <small>{{ preset.note }}</small>
            </button>
          </div>
        </section>
      </div>
    </div>

    <!-- Area editors -->
    <div class="theme-settings-grid">
      <ThemeAreaEditor
        v-for="area in areas"
        :key="area.key"
        :label="area.label"
        :stops="getStops(area.key)"
        :angle="getAngle(area.key)"
        :opacity="getOpacity(area.key)"
        :text-color="getTextColor(area.key)"
        :show-opacity="area.showOpacity"
        @update:stops="(s) => $emit('update-stops', area.key, s)"
        @update:angle="(a) => $emit('update-angle', area.key, a)"
        @update:opacity="(o) => $emit('update-opacity', area.key, o)"
        @update:text-color="(c) => $emit('update-text-color', area.key, c)"
        @add-stop="$emit('add-stop', area.key)"
        @remove-stop="(idx) => $emit('remove-stop', area.key, idx)"
        @sort-stops="$emit('sort-stops', area.key)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * ThemeEditor — four-area theme configuration panel
 *
 * Handles: live preview, preset selection, per-area gradient stop editing.
 * Parent provides theme data via props; mutations via emits.
 */
import ThemeAreaEditor from './ThemeAreaEditor.vue'
import { gradientFromStops, DEFAULT_THEME, type ThemeStop, type ThemeArea } from '../helpers/theme'
import type { ThemePreset } from '../helpers/theme'
import { THEME_PRESET_GROUPS } from '../data/theme-presets'

// ---- Props ----
defineProps<{
  productName?: string
  contentDescription?: string
  // area data
  getStops: (area: ThemeArea) => ThemeStop[]
  getAngle: (area: ThemeArea) => number
  getOpacity: (area: ThemeArea) => number
  getTextColor: (area: ThemeArea) => string
  // presets
  presets: ThemePreset[]
  presetsByGroup: (group: ThemePreset['group']) => ThemePreset[]
  // computed preview styles
  themePreviewStyle: Record<string, string>
  themePreviewMainStyle: Record<string, string>
  themePreviewComposerStyle: Record<string, string>
  themePreviewControlStyle: Record<string, string>
}>()

// ---- Emits ----
defineEmits<{
  'reset-theme': []
  'apply-preset': [preset: ThemePreset]
  'update-stops': [area: ThemeArea, stops: ThemeStop[]]
  'update-angle': [area: ThemeArea, angle: number]
  'update-opacity': [area: ThemeArea, opacity: number]
  'update-text-color': [area: ThemeArea, color: string]
  'add-stop': [area: ThemeArea]
  'remove-stop': [area: ThemeArea, index: number]
  'sort-stops': [area: ThemeArea]
}>()

// ---- Constants ----
const presetGroups = THEME_PRESET_GROUPS
const defaultBackdropAngle = DEFAULT_THEME.backdropAngle
const defaultBackdropStops = DEFAULT_THEME.backdropStops
const defaultMainAngle = DEFAULT_THEME.mainAngle
const defaultMainStops = DEFAULT_THEME.mainStops
const defaultComposerAngle = DEFAULT_THEME.composerAngle
const defaultComposerStops = DEFAULT_THEME.composerStops

// ---- Area config ----
interface AreaDef {
  key: ThemeArea
  label: string
  showOpacity: boolean
}

const areas: AreaDef[] = [
  { key: 'backdrop', label: '背景板 / 侧边栏', showOpacity: false },
  { key: 'main', label: '主界面', showOpacity: true },
  { key: 'composer', label: '输入栏', showOpacity: true },
  { key: 'control', label: '控件', showOpacity: true },
]
</script>
