/**
 * Shared theme presets.
 *
 * Built-in presets are intentionally pure-color only. Users can still create
 * gradients from the advanced editor, but presets must stay predictable.
 */

import type { ThemePreset, ThemeData } from '../helpers/theme'

const _ = (overrides: Partial<ThemeData>): Partial<ThemeData> => overrides
const solidStops = (color: string) => [
  { color, position: 0 },
  { color, position: 100 },
]

export const THEME_PRESETS: ThemePreset[] = [
  {
    id: 'solid-ink',
    group: 'solid',
    name: '墨黑',
    note: '主界面近黑，外侧深灰。',
    method: '全部区域使用纯色，靠明度差建立层级。',
    rationale: '长时间工作时减少视觉干扰，主内容优先。',
    theme: _({
      backdropStops: solidStops('#202020'),
      backdropAngle: 180,
      backdropText: '#f2efeb',
      mainStops: solidStops('#111111'),
      mainAngle: 180,
      mainText: '#f2efeb',
      mainOpacity: 1,
      composerStops: solidStops('#2c2c2b'),
      composerAngle: 180,
      composerText: '#f2efeb',
      composerOpacity: 1,
      controlStops: solidStops('#3a3835'),
      controlAngle: 180,
      controlText: '#f3eee8',
      controlOpacity: 1,
    }),
  },
  {
    id: 'solid-carbon',
    group: 'solid',
    name: '炭灰',
    note: '整体深灰，层级更柔和。',
    method: '全部区域使用纯色，主区比外壳更暗。',
    rationale: '适合写作、整理、复盘类任务。',
    theme: _({
      backdropStops: solidStops('#242424'),
      backdropAngle: 180,
      backdropText: '#f0ebe5',
      mainStops: solidStops('#151515'),
      mainAngle: 180,
      mainText: '#f2efeb',
      mainOpacity: 1,
      composerStops: solidStops('#303030'),
      composerAngle: 180,
      composerText: '#f2efeb',
      composerOpacity: 1,
      controlStops: solidStops('#3d3d3d'),
      controlAngle: 180,
      controlText: '#f2efeb',
      controlOpacity: 1,
    }),
  },
  {
    id: 'solid-paper',
    group: 'solid',
    name: '纸白',
    note: '浅色纯色，适合白天。',
    method: '全部区域使用纯色，避免渐变造成脏灰。',
    rationale: '白天环境需要更高整体亮度，同时保留清晰层级。',
    theme: _({
      backdropStops: solidStops('#dfdfdf'),
      backdropAngle: 180,
      backdropText: '#1f1f1f',
      mainStops: solidStops('#f8f8ef'),
      mainAngle: 180,
      mainText: '#1f1f1f',
      mainOpacity: 1,
      composerStops: solidStops('#efefef'),
      composerAngle: 180,
      composerText: '#1f1f1f',
      composerOpacity: 1,
      controlStops: solidStops('#d8d8d8'),
      controlAngle: 180,
      controlText: '#1f1f1f',
      controlOpacity: 1,
    }),
  },
  {
    id: 'solid-review',
    group: 'solid',
    name: '审阅灰',
    note: '中性灰阶，适合 diff 和报告。',
    method: '全部区域使用纯色，突出红绿状态色。',
    rationale: '审阅场景需要低刺激、高可读。',
    theme: _({
      backdropStops: solidStops('#d5d2cc'),
      backdropAngle: 180,
      backdropText: '#2a2926',
      mainStops: solidStops('#ebe8e2'),
      mainAngle: 180,
      mainText: '#20201e',
      mainOpacity: 1,
      composerStops: solidStops('#d9d5ce'),
      composerAngle: 180,
      composerText: '#20201e',
      composerOpacity: 1,
      controlStops: solidStops('#343331'),
      controlAngle: 180,
      controlText: '#f1eee8',
      controlOpacity: 1,
    }),
  },
]

export const THEME_PRESET_GROUPS: Array<{
  id: ThemePreset['group']
  label: string
}> = [
  { id: 'solid', label: '纯色' },
]
