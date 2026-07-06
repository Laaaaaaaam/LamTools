import { eventBus } from '../utils/EventBus.js';
import { formatTimecode } from '../utils/TimeUtils.js';

/**
 * 预览窗口UI - Canvas预览 + 播放控制
 */
export class PreviewUI {
  constructor(container) {
    this.container = container;
    this._el = null;
    this._canvas = null;
    this._timeDisplay = null;
    this._isPlaying = false;

    this._build();
    this._bindEvents();
  }

  get canvas() { return this._canvas; }

  _build() {
    this._el = document.createElement('div');
    this._el.className = 'preview-panel';
    this._el.innerHTML = `
      <div class="preview-header">
        <span class="preview-title">Preview</span>
        <span class="preview-time" data-part="time">00:00:00.000</span>
      </div>
      <div class="preview-canvas-wrapper">
        <canvas class="preview-canvas" data-part="canvas" width="640" height="360"></canvas>
      </div>
      <div class="preview-controls">
        <button class="ctrl-btn" data-action="skip-back" title="Skip Back">⏮</button>
        <button class="ctrl-btn ctrl-btn-play" data-action="play" title="Play/Pause">▶</button>
        <button class="ctrl-btn" data-action="skip-forward" title="Skip Forward">⏭</button>
        <div class="preview-progress-bar" data-part="progress">
          <div class="preview-progress-fill" data-part="progress-fill"></div>
        </div>
      </div>
    `;

    this._canvas = this._el.querySelector('[data-part="canvas"]');
    this._timeDisplay = this._el.querySelector('[data-part="time"]');
    this._progressBar = this._el.querySelector('[data-part="progress"]');
    this._progressFill = this._el.querySelector('[data-part="progress-fill"]');
    this._playBtn = this._el.querySelector('[data-action="play"]');

    this.container.appendChild(this._el);
  }

  _bindEvents() {
    // 播放/暂停
    this._playBtn.addEventListener('click', () => {
      eventBus.emit(this._isPlaying ? 'pauseRequest' : 'playRequest');
    });

    // 跳转
    this._el.querySelector('[data-action="skip-back"]').addEventListener('click', () => {
      eventBus.emit('seekRequest', 0);
    });

    this._el.querySelector('[data-action="skip-forward"]').addEventListener('click', () => {
      eventBus.emit('skipForwardRequest');
    });

    // 进度条点击
    this._progressBar.addEventListener('click', (e) => {
      const rect = this._progressBar.getBoundingClientRect();
      const ratio = (e.clientX - rect.left) / rect.width;
      eventBus.emit('progressClick', ratio);
    });

    // 事件监听
    eventBus.on('playbackStarted', () => {
      this._isPlaying = true;
      this._playBtn.textContent = '⏸';
      this._playBtn.title = 'Pause';
    });

    eventBus.on('playbackPaused', () => {
      this._isPlaying = false;
      this._playBtn.textContent = '▶';
      this._playBtn.title = 'Play';
    });

    eventBus.on('playbackTick', (time) => this._updateTime(time));
    eventBus.on('playbackSeeked', (time) => this._updateTime(time));
  }

  _updateTime(time) {
    this._timeDisplay.textContent = formatTimecode(time);
  }

  /** 更新进度条 */
  updateProgress(currentTime, duration) {
    if (duration <= 0) return;
    const ratio = currentTime / duration;
    this._progressFill.style.width = `${ratio * 100}%`;
  }

  destroy() {
    this._el.remove();
  }
}
