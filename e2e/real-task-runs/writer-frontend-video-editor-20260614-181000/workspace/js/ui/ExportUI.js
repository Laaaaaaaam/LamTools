import { eventBus } from '../utils/EventBus.js';

/**
 * 导出UI - 导出对话框与进度显示
 */
export class ExportUI {
  constructor(container) {
    this.container = container;
    this._el = null;
    this._progressBar = null;
    this._statusText = null;
    this._isShowing = false;

    this._build();
    this._bindEvents();
  }

  _build() {
    this._el = document.createElement('div');
    this._el.className = 'export-dialog';
    this._el.style.display = 'none';
    this._el.innerHTML = `
      <div class="export-dialog-content">
        <h3 class="export-title">Export Video</h3>
        <div class="export-settings">
          <div class="export-field">
            <label>Resolution</label>
            <select data-part="resolution">
              <option value="1920x1080" selected>1920×1080 (1080p)</option>
              <option value="1280x720">1280×720 (720p)</option>
              <option value="854x480">854×480 (480p)</option>
            </select>
          </div>
          <div class="export-field">
            <label>FPS</label>
            <select data-part="fps">
              <option value="24">24</option>
              <option value="30" selected>30</option>
              <option value="60">60</option>
            </select>
          </div>
          <div class="export-field">
            <label>Format</label>
            <select data-part="format">
              <option value="mp4" selected>MP4</option>
              <option value="webm">WebM</option>
            </select>
          </div>
        </div>
        <div class="export-progress" data-part="progress-section" style="display:none">
          <div class="export-progress-bar">
            <div class="export-progress-fill" data-part="progress-fill"></div>
          </div>
          <div class="export-status" data-part="status">Preparing...</div>
        </div>
        <div class="export-actions">
          <button class="export-btn export-btn-cancel" data-action="cancel">Cancel</button>
          <button class="export-btn export-btn-start" data-action="start">Start Export</button>
        </div>
      </div>
    `;

    this._progressBar = this._el.querySelector('[data-part="progress-fill"]');
    this._statusText = this._el.querySelector('[data-part="status"]');
    this._progressSection = this._el.querySelector('[data-part="progress-section"]');
    this._startBtn = this._el.querySelector('[data-action="start"]');

    this.container.appendChild(this._el);
  }

  _bindEvents() {
    this._el.querySelector('[data-action="cancel"]').addEventListener('click', () => {
      this.hide();
      eventBus.emit('exportCancel');
    });

    this._startBtn.addEventListener('click', () => {
      const resolution = this._el.querySelector('[data-part="resolution"]').value.split('x');
      const fps = parseInt(this._el.querySelector('[data-part="fps"]').value);
      const format = this._el.querySelector('[data-part="format"]').value;

      eventBus.emit('exportStart', {
        width: parseInt(resolution[0]),
        height: parseInt(resolution[1]),
        fps,
        format,
      });
    });

    eventBus.on('exportProgress', (progress) => {
      this._progressBar.style.width = `${progress.percent * 100}%`;
      this._statusText.textContent = progress.message || `Exporting... ${Math.round(progress.percent * 100)}%`;
    });

    eventBus.on('exportComplete', (result) => {
      this._statusText.textContent = 'Export complete!';
      this._progressBar.style.width = '100%';
      this._startBtn.textContent = 'Close';
      this._startBtn.onclick = () => this.hide();

      // 自动下载
      if (result.url) {
        const a = document.createElement('a');
        a.href = result.url;
        a.download = result.filename || 'output.mp4';
        a.click();
      }
    });

    eventBus.on('exportError', (error) => {
      this._statusText.textContent = `Error: ${error.message || 'Export failed'}`;
      this._statusText.style.color = '#ff4444';
    });
  }

  show() {
    this._el.style.display = 'flex';
    this._progressSection.style.display = 'none';
    this._progressBar.style.width = '0%';
    this._statusText.textContent = 'Preparing...';
    this._statusText.style.color = '';
    this._startBtn.textContent = 'Start Export';
    this._startBtn.onclick = null;
    this._isShowing = true;
  }

  showProgress() {
    this._progressSection.style.display = 'block';
    this._startBtn.disabled = true;
  }

  hide() {
    this._el.style.display = 'none';
    this._startBtn.disabled = false;
    this._isShowing = false;
  }

  get isShowing() { return this._isShowing; }

  destroy() {
    this._el.remove();
  }
}
