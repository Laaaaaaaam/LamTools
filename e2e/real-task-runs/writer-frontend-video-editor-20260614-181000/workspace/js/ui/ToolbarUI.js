import { eventBus } from '../utils/EventBus.js';

/**
 * 工具栏UI - 导入/分割/转场/文字/导出等操作
 */
export class ToolbarUI {
  constructor(container) {
    this.container = container;
    this._el = null;

    this._build();
    this._bindEvents();
  }

  _build() {
    this._el = document.createElement('div');
    this._el.className = 'toolbar';
    this._el.innerHTML = `
      <div class="toolbar-group">
        <button class="toolbar-btn" data-action="import" title="Import Media">
          <span class="toolbar-icon">📁</span>
          <span class="toolbar-label">Import</span>
        </button>
        <input type="file" data-part="file-input" multiple accept="video/*,audio/*,image/*" style="display:none">
      </div>
      <div class="toolbar-separator"></div>
      <div class="toolbar-group">
        <button class="toolbar-btn" data-action="split" title="Split Clip (S)">
          <span class="toolbar-icon">✂️</span>
          <span class="toolbar-label">Split</span>
        </button>
        <button class="toolbar-btn" data-action="delete" title="Delete Clip (Del)">
          <span class="toolbar-icon">🗑️</span>
          <span class="toolbar-label">Delete</span>
        </button>
      </div>
      <div class="toolbar-separator"></div>
      <div class="toolbar-group">
        <button class="toolbar-btn" data-action="add-fade" title="Add Fade Transition">
          <span class="toolbar-icon">🌅</span>
          <span class="toolbar-label">Fade</span>
        </button>
        <button class="toolbar-btn" data-action="add-text" title="Add Text Overlay">
          <span class="toolbar-icon">📝</span>
          <span class="toolbar-label">Text</span>
        </button>
      </div>
      <div class="toolbar-separator"></div>
      <div class="toolbar-group">
        <button class="toolbar-btn" data-action="undo" title="Undo (Ctrl+Z)">
          <span class="toolbar-icon">↩️</span>
          <span class="toolbar-label">Undo</span>
        </button>
        <button class="toolbar-btn" data-action="redo" title="Redo (Ctrl+Y)">
          <span class="toolbar-icon">↪️</span>
          <span class="toolbar-label">Redo</span>
        </button>
      </div>
      <div class="toolbar-spacer"></div>
      <div class="toolbar-group">
        <button class="toolbar-btn toolbar-btn-export" data-action="export" title="Export Video">
          <span class="toolbar-icon">🎬</span>
          <span class="toolbar-label">Export</span>
        </button>
      </div>
    `;

    this._fileInput = this._el.querySelector('[data-part="file-input"]');
    this.container.appendChild(this._el);
  }

  _bindEvents() {
    // 导入
    this._el.querySelector('[data-action="import"]').addEventListener('click', () => {
      this._fileInput.click();
    });

    this._fileInput.addEventListener('change', (e) => {
      const files = Array.from(e.target.files);
      if (files.length > 0) {
        eventBus.emit('importFiles', files);
      }
      this._fileInput.value = '';
    });

    // 分割
    this._el.querySelector('[data-action="split"]').addEventListener('click', () => {
      eventBus.emit('splitRequest');
    });

    // 删除
    this._el.querySelector('[data-action="delete"]').addEventListener('click', () => {
      eventBus.emit('deleteClipRequest');
    });

    // 转场
    this._el.querySelector('[data-action="add-fade"]').addEventListener('click', () => {
      eventBus.emit('addFadeRequest');
    });

    // 文字
    this._el.querySelector('[data-action="add-text"]').addEventListener('click', () => {
      eventBus.emit('addTextRequest');
    });

    // 撤销/重做
    this._el.querySelector('[data-action="undo"]').addEventListener('click', () => {
      eventBus.emit('undoRequest');
    });

    this._el.querySelector('[data-action="redo"]').addEventListener('click', () => {
      eventBus.emit('redoRequest');
    });

    // 导出
    this._el.querySelector('[data-action="export"]').addEventListener('click', () => {
      eventBus.emit('exportRequest');
    });

    // 键盘快捷键
    document.addEventListener('keydown', (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

      if (e.key === 's' || e.key === 'S') {
        if (!e.ctrlKey && !e.metaKey) {
          eventBus.emit('splitRequest');
        }
      } else if (e.key === 'Delete' || e.key === 'Backspace') {
        eventBus.emit('deleteClipRequest');
      } else if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
        e.preventDefault();
        eventBus.emit('undoRequest');
      } else if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.shiftKey && e.key === 'z'))) {
        e.preventDefault();
        eventBus.emit('redoRequest');
      } else if (e.key === ' ') {
        e.preventDefault();
        eventBus.emit('togglePlayRequest');
      }
    });
  }

  destroy() {
    this._el.remove();
  }
}
