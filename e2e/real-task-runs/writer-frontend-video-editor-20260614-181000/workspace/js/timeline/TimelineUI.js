import { eventBus } from '../utils/EventBus.js';
import { timeToPx, pxToTime, clamp, formatTimeShort } from '../utils/TimeUtils.js';

/**
 * 时间线UI - 管理时间线区域的交互与渲染
 */
export class TimelineUI {
  constructor(project, commandManager, container) {
    this.project = project;
    this.cmdManager = commandManager;
    this.container = container;

    // 状态
    this._zoom = 100;           // 像素/秒
    this._scrollX = 0;         // 水平滚动偏移
    this._trackHeight = 60;    // 轨道高度
    this._headerWidth = 120;   // 轨道头宽度
    this._selectedClipId = null;
    this._dragState = null;

    // DOM引用
    this._el = null;
    this._rulerEl = null;
    this._tracksEl = null;
    this._playheadEl = null;
    this._trackRenderers = [];

    this._build();
    this._bindEvents();
  }

  get zoom() { return this._zoom; }
  get scrollX() { return this._scrollX; }
  get headerWidth() { return this._headerWidth; }
  get trackHeight() { return this._trackHeight; }
  get selectedClipId() { return this._selectedClipId; }

  set zoom(v) {
    this._zoom = Math.max(10, Math.min(500, v));
    this.render();
  }

  /** 构建DOM结构 */
  _build() {
    this._el = document.createElement('div');
    this._el.className = 'timeline';
    this._el.innerHTML = `
      <div class="timeline-ruler" data-part="ruler">
        <div class="timeline-ruler-spacer" style="width:${this._headerWidth}px"></div>
        <div class="timeline-ruler-canvas" data-part="ruler-canvas"></div>
      </div>
      <div class="timeline-body" data-part="body">
        <div class="timeline-tracks" data-part="tracks"></div>
        <div class="timeline-playhead" data-part="playhead"></div>
      </div>
    `;

    this._rulerEl = this._el.querySelector('[data-part="ruler-canvas"]');
    this._bodyEl = this._el.querySelector('[data-part="body"]');
    this._tracksEl = this._el.querySelector('[data-part="tracks"]');
    this._playheadEl = this._el.querySelector('[data-part="playhead"]');

    this.container.appendChild(this._el);
  }

  /** 绑定交互事件 */
  _bindEvents() {
    // 滚动
    this._bodyEl.addEventListener('scroll', () => {
      this._scrollX = this._bodyEl.scrollLeft;
      this._updatePlayhead();
    });

    // 点击时间线空白区域 -> 移动播放头
    this._bodyEl.addEventListener('mousedown', (e) => {
      if (e.target.closest('.clip-block')) return;
      const rect = this._bodyEl.getBoundingClientRect();
      const x = e.clientX - rect.left + this._scrollX - this._headerWidth;
      const time = pxToTime(x, this._zoom);
      eventBus.emit('seekRequest', Math.max(0, time));
    });

    // 缩放
    this._bodyEl.addEventListener('wheel', (e) => {
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        const delta = e.deltaY > 0 ? 0.9 : 1.1;
        this.zoom = this._zoom * delta;
      }
    }, { passive: false });

    // 事件监听
    eventBus.on('playbackTick', (time) => this._updatePlayheadPosition(time));
    eventBus.on('playbackSeeked', (time) => this._updatePlayheadPosition(time));
    eventBus.on('stateChanged', () => this.render());
    eventBus.on('clipSelected', (clipId) => {
      this._selectedClipId = clipId;
      this.render();
    });
  }

  /** 更新播放头位置 */
  _updatePlayheadPosition(time) {
    if (!this._playheadEl) return;
    const x = timeToPx(time, this._zoom);
    this._playheadEl.style.left = `${this._headerWidth + x}px`;
  }

  _updatePlayhead() {
    // 同步ruler滚动
  }

  /** 完整渲染 */
  render() {
    this._renderRuler();
    this._renderTracks();
    this._updateTotalWidth();
  }

  /** 渲染时间刻度尺 */
  _renderRuler() {
    const canvas = this._rulerEl;
    const totalWidth = Math.max(timeToPx(this.project.duration + 10, this._zoom), canvas.parentElement.clientWidth);
    canvas.style.width = `${totalWidth}px`;
    canvas.width = totalWidth * (window.devicePixelRatio || 1);
    canvas.height = 30 * (window.devicePixelRatio || 1);

    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, totalWidth, 30);

    // 计算刻度间隔
    let interval = 1;
    if (this._zoom < 20) interval = 10;
    else if (this._zoom < 50) interval = 5;
    else if (this._zoom < 100) interval = 2;
    else if (this._zoom > 200) interval = 0.5;

    ctx.fillStyle = '#888';
    ctx.font = '10px monospace';
    ctx.textAlign = 'left';

    for (let t = 0; t * this._zoom < totalWidth; t += interval) {
      const x = timeToPx(t, this._zoom);
      ctx.fillStyle = '#555';
      ctx.fillRect(x, 20, 1, 10);
      ctx.fillStyle = '#888';
      ctx.fillText(formatTimeShort(t), x + 2, 15);
    }
  }

  /** 渲染轨道列表 */
  _renderTracks() {
    this._tracksEl.innerHTML = '';
    this._trackRenderers = [];

    for (const track of this.project.tracks) {
      const renderer = new TrackRenderer(this, track, this._tracksEl);
      this._trackRenderers.push(renderer);
    }
  }

  /** 更新总宽度 */
  _updateTotalWidth() {
    const totalWidth = timeToPx(this.project.duration + 10, this._zoom);
    this._tracksEl.style.width = `${totalWidth + this._headerWidth}px`;
  }

  /** 获取clip的DOM位置信息 */
  getClipRect(clip) {
    const x = timeToPx(clip.trackStart, this._zoom);
    const w = timeToPx(clip.duration, this._zoom);
    return { x, w };
  }

  /** 选中clip */
  selectClip(clipId) {
    this._selectedClipId = clipId;
    eventBus.emit('clipSelected', clipId);
    this.render();
  }

  /** 取消选中 */
  deselectAll() {
    this._selectedClipId = null;
    eventBus.emit('clipSelected', null);
    this.render();
  }

  destroy() {
    this._el.remove();
  }
}

/**
 * 轨道渲染器
 */
class TrackRenderer {
  constructor(timelineUI, track, container) {
    this.timeline = timelineUI;
    this.track = track;
    this._el = null;
    this._clipRenderers = [];
    this._build(container);
  }

  _build(container) {
    this._el = document.createElement('div');
    this._el.className = `track track-${this.track.type}`;
    this._el.dataset.trackId = this.track.id;

    // 轨道头
    const header = document.createElement('div');
    header.className = 'track-header';
    header.innerHTML = `
      <span class="track-name">${this.track.name}</span>
      <button class="track-mute-btn ${this.track.muted ? 'muted' : ''}" title="Mute/Unmute">
        ${this.track.muted ? '🔇' : '🔊'}
      </button>
    `;

    header.querySelector('.track-mute-btn').addEventListener('click', () => {
      eventBus.emit('toggleMuteTrack', this.track.id);
    });

    // 轨道内容区
    const content = document.createElement('div');
    content.className = 'track-content';
    content.style.height = `${this.timeline.trackHeight}px`;

    // 渲染clips
    for (const clip of this.track.clips) {
      const clipRenderer = new ClipRenderer(this.timeline, this.track, clip, content);
      this._clipRenderers.push(clipRenderer);
    }

    this._el.appendChild(header);
    this._el.appendChild(content);
    container.appendChild(this._el);
  }
}

/**
 * 片段块渲染器
 */
class ClipRenderer {
  constructor(timelineUI, track, clip, container) {
    this.timeline = timelineUI;
    this.track = track;
    this.clip = clip;
    this._el = null;
    this._dragState = null;
    this._build(container);
  }

  _build(container) {
    const { x, w } = this.timeline.getClipRect(this.clip);
    const isSelected = this.timeline.selectedClipId === this.clip.id;

    this._el = document.createElement('div');
    this._el.className = `clip-block clip-${this.track.type}${isSelected ? ' selected' : ''}`;
    this._el.dataset.clipId = this.clip.id;
    this._el.style.left = `${x}px`;
    this._el.style.width = `${Math.max(w, 4)}px`;
    this._el.style.height = `${this.timeline.trackHeight - 4}px`;

    // 片段名称
    const label = document.createElement('span');
    label.className = 'clip-label';
    label.textContent = this._getClipName();
    this._el.appendChild(label);

    // 左裁剪手柄
    const leftHandle = document.createElement('div');
    leftHandle.className = 'clip-handle clip-handle-left';
    this._el.appendChild(leftHandle);

    // 右裁剪手柄
    const rightHandle = document.createElement('div');
    rightHandle.className = 'clip-handle clip-handle-right';
    this._el.appendChild(rightHandle);

    // 转场指示器
    if (this.clip.transitions.length > 0) {
      const transIndicator = document.createElement('div');
      transIndicator.className = 'clip-transition-indicator';
      transIndicator.textContent = '✦';
      this._el.appendChild(transIndicator);
    }

    // 文字叠加指示器
    if (this.clip.textOverlays.length > 0) {
      const txtIndicator = document.createElement('div');
      txtIndicator.className = 'clip-text-indicator';
      txtIndicator.textContent = 'T';
      this._el.appendChild(txtIndicator);
    }

    // 交互事件
    this._el.addEventListener('mousedown', (e) => this._onMouseDown(e));
    this._el.addEventListener('click', (e) => {
      e.stopPropagation();
      this.timeline.selectClip(this.clip.id);
    });

    container.appendChild(this._el);
  }

  _getClipName() {
    // 简化：用mediaId的前8个字符
    return this.clip.mediaId ? this.clip.mediaId.substring(0, 12) : 'Clip';
  }

  _onMouseDown(e) {
    e.stopPropagation();
    const target = e.target;

    if (target.classList.contains('clip-handle-left')) {
      this._startTrimLeft(e);
    } else if (target.classList.contains('clip-handle-right')) {
      this._startTrimRight(e);
    } else {
      this._startMove(e);
    }
  }

  _startMove(e) {
    const startX = e.clientX;
    const startTrackStart = this.clip.trackStart;

    const onMouseMove = (e2) => {
      const dx = e2.clientX - startX;
      const dt = pxToTime(dx, this.timeline.zoom);
      const newTrackStart = Math.max(0, startTrackStart + dt);
      this.clip.trackStart = newTrackStart;
      // 更新视觉位置
      const { x } = this.timeline.getClipRect(this.clip);
      this._el.style.left = `${x}px`;
    };

    const onMouseUp = () => {
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
      // 发出移动命令
      if (this.clip.trackStart !== startTrackStart) {
        const { MoveClipCommand } = await_import_clip_commands();
        // 简化：直接更新，后续可通过command
        eventBus.emit('stateChanged');
      }
    };

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  }

  _startTrimLeft(e) {
    const startX = e.clientX;
    const startInPoint = this.clip.inPoint;
    const startTrackStart = this.clip.trackStart;

    const onMouseMove = (e2) => {
      const dx = e2.clientX - startX;
      const dt = pxToTime(dx, this.timeline.zoom);
      const newInPoint = Math.max(0, startInPoint + dt);
      const newTrackStart = startTrackStart + (newInPoint - startInPoint);
      if (newInPoint < this.clip.outPoint - 0.1) {
        this.clip.inPoint = newInPoint;
        this.clip.trackStart = newTrackStart;
        const { x, w } = this.timeline.getClipRect(this.clip);
        this._el.style.left = `${x}px`;
        this._el.style.width = `${Math.max(w, 4)}px`;
      }
    };

    const onMouseUp = () => {
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
      eventBus.emit('stateChanged');
    };

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  }

  _startTrimRight(e) {
    const startX = e.clientX;
    const startOutPoint = this.clip.outPoint;

    const onMouseMove = (e2) => {
      const dx = e2.clientX - startX;
      const dt = pxToTime(dx, this.timeline.zoom);
      const newOutPoint = Math.max(this.clip.inPoint + 0.1, startOutPoint + dt);
      this.clip.outPoint = newOutPoint;
      const { w } = this.timeline.getClipRect(this.clip);
      this._el.style.width = `${Math.max(w, 4)}px`;
    };

    const onMouseUp = () => {
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
      eventBus.emit('stateChanged');
    };

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  }
}

function await_import_clip_commands() {
  // 动态导入避免循环依赖
  return import('../commands/ClipCommands.js');
}
