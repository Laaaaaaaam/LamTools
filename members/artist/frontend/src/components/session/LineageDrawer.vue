<template>
  <Transition name="drawer-slide">
    <div v-if="visible" class="lineage-overlay" @click.self="$emit('close')">
      <div class="lineage-drawer">
        <div class="lineage-header">
          <div class="lineage-header-left">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/></svg>
            <span class="lineage-title">谱系图</span>
          </div>
          <button class="lineage-close" @click="$emit('close')">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>

        <div v-if="loading" class="lineage-status">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="icon-spin"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
          <span>加载中...</span>
        </div>

        <div v-else-if="error" class="lineage-status error">
          <span>{{ error }}</span>
          <button class="btn-retry" @click="fetchTree">重试</button>
        </div>

        <div v-else-if="!tree || Object.keys(tree.nodes).length === 0" class="lineage-status">
          <span>本会话暂无图片</span>
        </div>

        <template v-else>
          <div class="lineage-canvas-wrap" ref="canvasWrap">
            <canvas ref="canvasRef" @wheel.prevent="onWheel" @mousedown="onMouseDown" @click="onClick" />
          </div>

          <Transition name="fade">
            <div v-if="detailVisible" class="detail-overlay" @click.self="closeDetail">
              <div class="detail-card">
                <div class="detail-img">
                  <img v-if="detailUrl" :src="detailUrl" alt="" />
                  <span v-else>图片预览</span>
                  <span class="detail-badge" :style="{ background: modeColor(detailLineageNode?.generation_mode || 'generate') }">
                    {{ modeLabel(detailLineageNode?.generation_mode || 'generate') }}
                  </span>
                </div>
                <div class="detail-body">
                  <div class="detail-title">
                    {{ detailLineageNode ? truncate(detailLineageNode.prompt, 30) : '' }}
                    <span v-if="detailUrl === tree!.head_url" class="detail-head-tag" :style="{ background: modeColor(detailLineageNode?.generation_mode || 'generate') + '22', color: modeColor(detailLineageNode?.generation_mode || 'generate') }">HEAD</span>
                  </div>
                  <div class="detail-row">
                    <span class="detail-label">Prompt</span>
                    <span class="detail-value">{{ detailLineageNode?.prompt || '-' }}</span>
                  </div>
                  <div class="detail-row">
                    <span class="detail-label">时间</span>
                    <span class="detail-value">{{ detailLineageNode ? formatTime(detailLineageNode.created_at) : '' }}</span>
                  </div>
                  <div class="detail-row">
                    <span class="detail-label">模式</span>
                    <span class="detail-value" :style="{ color: modeColor(detailLineageNode?.generation_mode || 'generate') }">{{ detailLineageNode?.generation_mode || '-' }}</span>
                  </div>
                  <div v-if="detailLineageNode && detailLineageNode.source_image_urls.length" class="detail-row">
                    <span class="detail-label">参考图</span>
                    <div class="detail-refs">
                      <img v-for="refUrl in detailLineageNode!.source_image_urls" :key="refUrl" :src="refUrl" class="detail-ref-thumb" @click="$emit('select-image', refUrl)" />
                    </div>
                  </div>
                </div>
                <button class="detail-close-btn" @click="closeDetail">关闭</button>
              </div>
            </div>
          </Transition>

          <div class="lineage-footer">
            <div class="footer-left">
              <select v-if="branchNames.length > 1" class="branch-select" :value="selectedBranch" @change="onBranchChange">
                <option v-for="name in branchNames" :key="name" :value="name">{{ name }} ({{ tree!.branches[name].node_urls.length }})</option>
              </select>
              <div class="legend">
                <span class="legend-item"><span class="legend-dot" :style="{ background: modeColor('generate') }"></span>generate</span>
                <span class="legend-item"><span class="legend-dot" :style="{ background: modeColor('variation') }"></span>variation</span>
                <span class="legend-item"><span class="legend-dot" :style="{ background: modeColor('refine') }"></span>refine</span>
              </div>
            </div>
            <div class="footer-right">
              <button class="zoom-btn" @click="doZoomOut" title="缩小">−</button>
              <span class="zoom-val">{{ Math.round(viewZoom * 100) }}%</span>
              <button class="zoom-btn" @click="doZoomIn" title="放大">+</button>
              <button class="zoom-btn" @click="fitToView" title="适应画布">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/></svg>
              </button>
            </div>
          </div>
        </template>
      </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { ref, watch, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { sessionApi } from '../../api/session'
import type { LineageTree, LineageNode } from '../../types'

const props = defineProps<{
  visible: boolean
  sessionId: string
}>()

const emit = defineEmits<{
  close: []
  'select-image': [url: string]
}>()

const MODE_COLORS: Record<string, string> = {
  new_generation: '#d8d3ca', generate: '#d8d3ca',
  edit_target: '#b9b1a7', variation: '#b9b1a7',
  style_reference: '#a8adb0', batch_edit: '#c2b8ad',
  skill: '#c8c0b6', refine: '#9fa7a2',
}
const MODE_LABELS: Record<string, string> = {
  generate: '生成', new_generation: '生成', variation: '变体',
  edit_target: '编辑', refine: '精修', style_reference: '风格参考',
  batch_edit: '批量编辑', skill: '技能',
}

function modeColor(mode: string): string { return MODE_COLORS[mode] || '#d8d3ca' }
function modeLabel(mode: string): string { return MODE_LABELS[mode] || mode }
function truncate(s: string | null | undefined, max: number): string {
  if (!s) return '-'
  return s.length > max ? s.slice(0, max) + '...' : s
}
function formatTime(iso: string): string {
  if (!iso) return ''
  try { return new Date(iso).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) }
  catch { return iso }
}

const loading = ref(false)
const error = ref('')
const tree = ref<LineageTree | null>(null)
const selectedBranch = ref('')

const canvasWrap = ref<HTMLElement | null>(null)
const canvasRef = ref<HTMLCanvasElement | null>(null)
let ctx: CanvasRenderingContext2D | null = null
const dpr = window.devicePixelRatio || 1

let viewX = 0, viewY = 0
const viewZoom = ref(1)
let isDragging = false, dragLastX = 0, dragLastY = 0
let hoveredNode: string | null = null
let selectedNodeUrl: string | null = null
const detailVisible = ref(false)
const detailUrl = ref<string | null>(null)
let positions = new Map<string, { x: number; y: number }>()
let animFrame = 0

const NODE_W = 130, NODE_H = 52

const branchNames = computed(() => tree.value ? Object.keys(tree.value.branches) : [])
const detailLineageNode = computed<LineageNode | null>(() => {
  if (!detailUrl.value || !tree.value) return null
  return tree.value.nodes[detailUrl.value] || null
})

function layoutGraph() {
  if (!tree.value) return
  const nodes = tree.value.nodes

  const parentMap = new Map<string, string>()
  const childMap = new Map<string, string[]>()
  Object.entries(nodes).forEach(([url, node]) => {
    node.source_image_urls.forEach(parentUrl => {
      if (nodes[parentUrl]) {
        parentMap.set(url, parentUrl)
        if (!childMap.has(parentUrl)) childMap.set(parentUrl, [])
        childMap.get(parentUrl)!.push(url)
      }
    })
  })

  const genMap = new Map<string, number>()
  function getGen(url: string): number {
    if (genMap.has(url)) return genMap.get(url)!
    const parent = parentMap.get(url)
    if (!parent) { genMap.set(url, 0); return 0 }
    const g = getGen(parent) + 1
    genMap.set(url, g)
    return g
  }
  Object.keys(nodes).forEach(url => getGen(url))

  const genGroups = new Map<number, string[]>()
  Object.keys(nodes).forEach(url => {
    const g = genMap.get(url)!
    if (!genGroups.has(g)) genGroups.set(g, [])
    genGroups.get(g)!.push(url)
  })

  const hOrder = new Map<string, number>()
  let hIdx = 0
  function dfs(url: string) {
    hOrder.set(url, hIdx++)
    for (const child of (childMap.get(url) || [])) dfs(child)
  }
  const roots = tree.value.root_urls.length ? tree.value.root_urls : Object.keys(nodes).filter(u => !parentMap.has(u))
  roots.forEach(url => dfs(url))

  const H_GAP = 20, V_GAP = 70
  positions.clear()
  const maxGen = genGroups.size > 0 ? Math.max(...genGroups.keys()) : 0

  for (let g = 0; g <= maxGen; g++) {
    const ids = (genGroups.get(g) || []).sort((a, b) => (hOrder.get(a) ?? 0) - (hOrder.get(b) ?? 0))
    const totalW = ids.length * NODE_W + (ids.length - 1) * H_GAP
    const startX = -totalW / 2 + NODE_W / 2
    ids.forEach((url, i) => {
      positions.set(url, { x: startX + i * (NODE_W + H_GAP), y: g * (NODE_H + V_GAP) })
    })
  }
}

function getPathToRoot(url: string): Set<string> {
  const path = new Set<string>()
  let cur: string | undefined = url
  while (cur && tree.value?.nodes[cur]) {
    path.add(cur)
    cur = tree.value.nodes[cur].source_image_urls[0]
  }
  return path
}

function worldToScreen(wx: number, wy: number) {
  const wrap = canvasWrap.value
  if (!wrap) return { x: 0, y: 0 }
  const cw = wrap.clientWidth, ch = wrap.clientHeight
  return { x: (wx * viewZoom.value + viewX + cw / 2) * dpr, y: (wy * viewZoom.value + viewY + ch / 2) * dpr }
}

function screenToWorld(sx: number, sy: number) {
  const wrap = canvasWrap.value
  if (!wrap) return { x: 0, y: 0 }
  const cw = wrap.clientWidth, ch = wrap.clientHeight
  return { x: (sx - cw / 2 - viewX) / viewZoom.value, y: (sy - ch / 2 - viewY) / viewZoom.value }
}

function render() {
  const canvas = canvasRef.value
  const wrap = canvasWrap.value
  if (!canvas || !wrap || !ctx || !tree.value) { animFrame = requestAnimationFrame(render); return }

  const rect = wrap.getBoundingClientRect()
  const targetW = Math.round(rect.width * dpr)
  const targetH = Math.round(rect.height * dpr)
  if (canvas.width !== targetW || canvas.height !== targetH) {
    canvas.width = targetW
    canvas.height = targetH
    canvas.style.width = rect.width + 'px'
    canvas.style.height = rect.height + 'px'
  }

  ctx.clearRect(0, 0, canvas.width, canvas.height)

  const s = viewZoom.value * dpr
  const headPath = getPathToRoot(tree.value.head_url)
  const selectedPath = selectedNodeUrl ? getPathToRoot(selectedNodeUrl) : null
  const highlightPath = selectedPath || headPath
  const nodes = tree.value.nodes

  Object.entries(nodes).forEach(([url, node]) => {
    node.source_image_urls.forEach(parentUrl => {
      if (!nodes[parentUrl]) return
      const fp = positions.get(parentUrl), tp = positions.get(url)
      if (!fp || !tp) return
      const fromP = worldToScreen(fp.x, fp.y)
      const toP = worldToScreen(tp.x, tp.y)
      const isHL = highlightPath.has(parentUrl) && highlightPath.has(url)

      ctx!.globalAlpha = isHL ? 1 : (selectedNodeUrl ? 0.25 : 1)
      ctx!.strokeStyle = isHL ? modeColor(node.generation_mode) : '#e5e5e5'
      ctx!.lineWidth = isHL ? 2.5 : 1

      const midY = (fromP.y + toP.y) / 2
      ctx!.beginPath()
      ctx!.moveTo(fromP.x, fromP.y + NODE_H / 2 * s)
      ctx!.bezierCurveTo(fromP.x, midY, toP.x, midY, toP.x, toP.y - NODE_H / 2 * s)
      ctx!.stroke()
      ctx!.globalAlpha = 1
    })
  })

  Object.entries(nodes).forEach(([url, node]) => {
    const pos = positions.get(url)
    if (!pos) return
    const p = worldToScreen(pos.x, pos.y)
    const onPath = !selectedNodeUrl || highlightPath.has(url)
    drawNodeCard(p.x, p.y, url, node, s, onPath ? 1 : 0.25)
  })

  animFrame = requestAnimationFrame(render)
}

function drawNodeCard(cx: number, cy: number, url: string, node: LineageNode, s: number, alpha: number) {
  if (!ctx) return
  const w = NODE_W * s, h = NODE_H * s, r = 6 * s
  const isHovered = hoveredNode === url
  const isSelected = selectedNodeUrl === url
  const isHead = url === tree.value?.head_url
  const mc = modeColor(node.generation_mode)

  ctx.globalAlpha = alpha

  ctx.fillStyle = isHead ? '#eeeef6' : isSelected ? '#f0f0f0' : isHovered ? '#f5f5f5' : '#fafafa'
  ctx.strokeStyle = isHead ? mc : isHovered ? '#ccc' : '#e5e5e5'
  ctx.lineWidth = isHead ? 2 : isHovered ? 1.5 : 0.5
  ctx.beginPath()
  ctx.roundRect(cx - w/2, cy - h/2, w, h, r)
  ctx.fill()
  ctx.stroke()

  if (isSelected) {
    ctx.fillStyle = mc
    ctx.beginPath()
    ctx.roundRect(cx - w/2, cy - h/2, 3 * s, h, [r, 0, 0, r])
    ctx.fill()
  }

  const tw = 28 * s, th = 28 * s
  ctx.fillStyle = '#f0f0f0'
  ctx.strokeStyle = '#e5e5e5'
  ctx.lineWidth = 0.5
  ctx.beginPath()
  ctx.roundRect(cx - w/2 + 6*s, cy - h/2 + (h-th)/2, tw, th, 3*s)
  ctx.fill()
  ctx.stroke()

  ctx.fillStyle = mc
  ctx.beginPath()
  ctx.arc(cx - w/2 + 10*s, cy - h/2 + 7*s, 2*s, 0, Math.PI*2)
  ctx.fill()

  ctx.fillStyle = alpha > 0.5 ? '#1a1a1a' : '#999'
  ctx.font = `500 ${9*s}px -apple-system, "PingFang SC", sans-serif`
  ctx.textAlign = 'left'
  ctx.fillText(modeLabel(node.generation_mode), cx - w/2 + 40*s, cy - 4*s)

  ctx.fillStyle = '#999'
  ctx.font = `${7.5*s}px -apple-system, sans-serif`
  ctx.fillText(formatTime(node.created_at), cx - w/2 + 40*s, cy + 8*s)

  if (isHead) {
    ctx.fillStyle = mc
    ctx.beginPath()
    ctx.arc(cx + w/2 - 8*s, cy - h/2 + 8*s, 3*s, 0, Math.PI*2)
    ctx.fill()
    ctx.font = `600 ${7*s}px -apple-system, sans-serif`
    ctx.textAlign = 'right'
    ctx.fillText('HEAD', cx + w/2 - 3*s, cy - h/2 + 11*s)
  }

  ctx.globalAlpha = 1
}

function hitTest(sx: number, sy: number): string | null {
  if (!tree.value) return null
  const wp = screenToWorld(sx, sy)
  let hit: string | null = null
  Object.keys(tree.value.nodes).forEach(url => {
    const pos = positions.get(url)
    if (!pos) return
    if (Math.abs(wp.x - pos.x) < NODE_W / 2 && Math.abs(wp.y - pos.y) < NODE_H / 2) hit = url
  })
  return hit
}

function onMouseDown(e: MouseEvent) {
  if (e.ctrlKey || e.metaKey) {
    isDragging = true
    dragLastX = e.clientX
    dragLastY = e.clientY
    if (canvasRef.value) canvasRef.value.style.cursor = 'grabbing'
    e.preventDefault()
  }
}

function onGlobalMouseMove(e: MouseEvent) {
  if (isDragging) {
    viewX += (e.clientX - dragLastX) * viewZoom.value
    viewY += (e.clientY - dragLastY) * viewZoom.value
    dragLastX = e.clientX
    dragLastY = e.clientY
    return
  }
  const rect = canvasWrap.value?.getBoundingClientRect()
  if (!rect) return
  hoveredNode = hitTest(e.clientX - rect.left, e.clientY - rect.top)
  if (canvasRef.value) canvasRef.value.style.cursor = (e.ctrlKey || e.metaKey) ? 'grab' : hoveredNode ? 'pointer' : 'default'
}

function onGlobalMouseUp() {
  isDragging = false
  if (canvasRef.value) canvasRef.value.style.cursor = hoveredNode ? 'pointer' : 'default'
}

function onClick(e: MouseEvent) {
  if (e.ctrlKey || e.metaKey) return
  const rect = canvasWrap.value?.getBoundingClientRect()
  if (!rect) return
  const hit = hitTest(e.clientX - rect.left, e.clientY - rect.top)
  if (hit) {
    if (selectedNodeUrl === hit) openDetail(hit)
    else selectedNodeUrl = hit
  } else {
    selectedNodeUrl = null
    closeDetail()
  }
}

function onWheel(e: WheelEvent) {
  const rect = canvasWrap.value?.getBoundingClientRect()
  if (!rect) return
  const mx = e.clientX - rect.left, my = e.clientY - rect.top
  const oldZoom = viewZoom.value
  viewZoom.value = Math.max(0.3, Math.min(2.5, viewZoom.value + (e.deltaY > 0 ? -0.08 : 0.08)))
  const wx = (mx - rect.width / 2 - viewX) / oldZoom
  const wy = (my - rect.height / 2 - viewY) / oldZoom
  viewX = mx - rect.width / 2 - wx * viewZoom.value
  viewY = my - rect.height / 2 - wy * viewZoom.value
}

function openDetail(url: string) { detailUrl.value = url; detailVisible.value = true }
function closeDetail() { detailVisible.value = false; detailUrl.value = null; selectedNodeUrl = null }

function onBranchChange(e: Event) {
  selectedBranch.value = (e.target as HTMLSelectElement).value
  selectedNodeUrl = null
  closeDetail()
  fitToView()
}

function doZoomIn() { viewZoom.value = Math.min(2.5, viewZoom.value + 0.15) }
function doZoomOut() { viewZoom.value = Math.max(0.3, viewZoom.value - 0.15) }

function fitToView() {
  const wrap = canvasWrap.value
  if (!wrap || positions.size === 0) return
  const cw = wrap.clientWidth, ch = wrap.clientHeight

  // 以 HEAD 节点居中
  const headUrl = tree.value?.head_url
  const headPos = headUrl ? positions.get(headUrl) : null
  if (headPos) {
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
    positions.forEach(p => {
      minX = Math.min(minX, p.x - NODE_W/2); maxX = Math.max(maxX, p.x + NODE_W/2)
      minY = Math.min(minY, p.y - NODE_H/2); maxY = Math.max(maxY, p.y + NODE_H/2)
    })
    viewZoom.value = Math.min(cw / (maxX - minX + 60), ch / (maxY - minY + 60), 1.5)
    // worldToScreen: sx = wx*zoom + viewX + cw/2, 要 sx=cw/2 → viewX = -wx*zoom
    viewX = -headPos.x * viewZoom.value
    viewY = -headPos.y * viewZoom.value
  } else {
    // 无 HEAD 时退回整棵树居中
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
    positions.forEach(p => {
      minX = Math.min(minX, p.x - NODE_W/2); maxX = Math.max(maxX, p.x + NODE_W/2)
      minY = Math.min(minY, p.y - NODE_H/2); maxY = Math.max(maxY, p.y + NODE_H/2)
    })
    viewZoom.value = Math.min(cw / (maxX - minX + 60), ch / (maxY - minY + 60), 1.5)
    // worldToScreen: sx = wx*zoom + viewX + cw/2, 中心 cx=(minX+maxX)/2 → viewX = -cx*zoom
    viewX = -(minX + maxX) / 2 * viewZoom.value
    viewY = -(minY + maxY) / 2 * viewZoom.value
  }
}

async function fetchTree() {
  if (!props.sessionId) return
  loading.value = true; error.value = ''
  try {
    const { data } = await sessionApi.getLineageTree(props.sessionId)
    tree.value = data
    selectedBranch.value = data.head_branch || Object.keys(data.branches)[0] || ''
    layoutGraph()
  } catch (e: any) { error.value = e?.message || '加载失败' }
  finally { loading.value = false }
  // ctx 初始化必须在 loading=false 之后，否则 canvas DOM 因 v-if/v-else 分支不存在
  await nextTick()
  if (canvasRef.value) ctx = canvasRef.value.getContext('2d')
  fitToView()
  render()
}

function onKeydown(e: KeyboardEvent) { if (e.key === 'Escape' && detailVisible.value) closeDetail() }

watch(() => props.visible, val => {
  if (val) fetchTree()
  else { tree.value = null; error.value = ''; selectedBranch.value = ''; selectedNodeUrl = null; closeDetail(); cancelAnimationFrame(animFrame) }
})

onMounted(() => {
  document.addEventListener('mousemove', onGlobalMouseMove)
  document.addEventListener('mouseup', onGlobalMouseUp)
  document.addEventListener('keydown', onKeydown)
  if (props.visible) fetchTree()
})

onUnmounted(() => {
  document.removeEventListener('mousemove', onGlobalMouseMove)
  document.removeEventListener('mouseup', onGlobalMouseUp)
  document.removeEventListener('keydown', onKeydown)
  cancelAnimationFrame(animFrame)
})
</script>

<style scoped>
.lineage-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.15); z-index: 400; display: flex; justify-content: flex-end; }
.lineage-drawer { width: 400px; max-width: 90vw; height: 100%; background: var(--card); border-left: 1px solid var(--border); display: flex; flex-direction: column; overflow: hidden; }

.lineage-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.lineage-header-left { display: flex; align-items: center; gap: 8px; color: var(--text); }
.lineage-title { font-size: 14px; font-weight: 600; }
.lineage-close { display: flex; align-items: center; justify-content: center; background: none; border: none; color: var(--text-secondary); cursor: pointer; padding: 4px; border-radius: var(--radius); }
.lineage-close:hover { background: var(--hover); color: var(--text); }

.lineage-status { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; padding: 48px 24px; color: var(--text-secondary); font-size: 13px; flex: 1; }
.lineage-status.error { color: var(--danger); }
.btn-retry { padding: 4px 12px; background: var(--hover); border: 1px solid var(--border); border-radius: var(--radius); cursor: pointer; font-size: 12px; color: var(--text); }
.btn-retry:hover { background: var(--active); }

.lineage-canvas-wrap { flex: 1; position: relative; overflow: hidden; cursor: default; }
.lineage-canvas-wrap canvas { width: 100%; height: 100%; display: block; }

.icon-spin { animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

.detail-overlay { position: absolute; inset: 0; background: rgba(0,0,0,0.3); z-index: 20; display: flex; align-items: center; justify-content: center; }
.detail-card { width: 300px; background: var(--card); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; box-shadow: var(--shadow); }
.detail-img { width: 100%; height: 180px; background: var(--hover); display: flex; align-items: center; justify-content: center; color: var(--text-tertiary); font-size: 13px; position: relative; overflow: hidden; }
.detail-img img { width: 100%; height: 100%; object-fit: cover; }
.detail-badge { position: absolute; top: 8px; left: 8px; padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: 600; color: #fff; }
.detail-body { padding: 14px; }
.detail-title { font-size: 13px; font-weight: 600; color: var(--text); margin-bottom: 10px; display: flex; align-items: center; gap: 6px; }
.detail-head-tag { display: inline-flex; align-items: center; padding: 1px 6px; border-radius: 3px; font-size: 9px; font-weight: 700; }
.detail-row { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 8px; }
.detail-label { font-size: 11px; color: var(--text-tertiary); min-width: 44px; flex-shrink: 0; padding-top: 1px; }
.detail-value { font-size: 12px; color: var(--text-secondary); line-height: 1.5; word-break: break-word; }
.detail-refs { display: flex; gap: 6px; margin-top: 4px; }
.detail-ref-thumb { width: 44px; height: 44px; border-radius: 5px; object-fit: cover; border: 1px solid var(--border); cursor: pointer; }
.detail-ref-thumb:hover { border-color: var(--accent); }
.detail-close-btn { width: 100%; padding: 10px; background: none; border: none; border-top: 1px solid var(--border); color: var(--text-tertiary); font-size: 12px; cursor: pointer; }
.detail-close-btn:hover { color: var(--text-secondary); background: var(--hover); }

.lineage-footer { padding: 8px 14px; border-top: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; font-size: 11px; color: var(--text-tertiary); }
.footer-left { display: flex; align-items: center; gap: 12px; }
.footer-right { display: flex; align-items: center; gap: 6px; }
.branch-select { padding: 3px 8px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--card); color: var(--text); font-size: 11px; outline: none; cursor: pointer; }
.branch-select:focus { border-color: var(--accent); }
.legend { display: flex; gap: 8px; }
.legend-item { display: flex; align-items: center; gap: 3px; }
.legend-dot { width: 7px; height: 7px; border-radius: 2px; display: inline-block; }
.zoom-btn { width: 24px; height: 24px; border-radius: 4px; background: var(--card); border: 1px solid var(--border); color: var(--text-secondary); cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 14px; }
.zoom-btn:hover { background: var(--hover); color: var(--text); }
.zoom-val { min-width: 32px; text-align: center; }

.drawer-slide-enter-active, .drawer-slide-leave-active { transition: opacity 0.2s ease; }
.drawer-slide-enter-from, .drawer-slide-leave-to { opacity: 0; }
.fade-enter-active, .fade-leave-active { transition: opacity 0.15s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
