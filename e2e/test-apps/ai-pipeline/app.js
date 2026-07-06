/**
 * app.js - 控制层：应用主逻辑
 * 负责状态管理、事件处理、UI 渲染
 */

// ===== 简单事件总线 =====
class EventBus {
  constructor() {
    this._listeners = {};
  }

  on(event, callback) {
    if (!this._listeners[event]) this._listeners[event] = [];
    this._listeners[event].push(callback);
    return () => this.off(event, callback);
  }

  off(event, callback) {
    if (!this._listeners[event]) return;
    this._listeners[event] = this._listeners[event].filter((cb) => cb !== callback);
  }

  emit(event, ...args) {
    (this._listeners[event] || []).forEach((cb) => cb(...args));
  }
}

const bus = new EventBus();

// ===== 应用状态 =====
const state = {
  currentSessionId: null,
  sessions: [],
  config: appConfig,
  isStreaming: false,
  abortController: null,
  statusMessage: '',
  statusType: 'info', // 'info' | 'error'
};

// ===== DOM 引用缓存 =====
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// ===== 初始化 =====
document.addEventListener('DOMContentLoaded', () => {
  initApp();
});

function initApp() {
  renderSessionList();
  // 如果有会话，自动选中第一个
  const sessions = appStorage.getSessionList();
  if (sessions.length > 0) {
    selectSession(sessions[0].id);
  } else {
    showEmptyState();
  }
  updateStatus('准备就绪', 'info');
  bindGlobalEvents();
}

// ===== 事件绑定 =====
function bindGlobalEvents() {
  // 新建对话
  $('.btn-new-chat')?.addEventListener('click', createNewSession);

  // 发送消息
  $('.btn-send')?.addEventListener('click', handleSend);
  $('.input-area textarea')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  });

  // 设置按钮
  $('.btn-settings')?.addEventListener('click', openSettings);

  // 监听设置保存事件
  bus.on('config:saved', () => {
    updateStatus('配置已保存', 'info');
  });

  // 监听错误
  bus.on('error', (msg) => {
    updateStatus(msg, 'error');
  });
}

// ===== 会话管理 =====
function createNewSession() {
  const session = createSession();
  appStorage.addSession(session);
  renderSessionList();
  selectSession(session.id);
  updateStatus('新对话已创建', 'info');
}

function selectSession(sessionId) {
  if (state.isStreaming) {
    // 如果正在流式输出，先取消
    cancelStreaming();
  }

  state.currentSessionId = sessionId;
  renderSessionList();
  renderMessages(sessionId);
  updateChatHeader(sessionId);
  enableInput(true);
}

function deleteSession(sessionId, event) {
  event?.stopPropagation();

  if (state.currentSessionId === sessionId && state.isStreaming) {
    cancelStreaming();
  }

  appStorage.deleteSession(sessionId);
  const sessions = appStorage.getSessionList();

  if (state.currentSessionId === sessionId) {
    if (sessions.length > 0) {
      selectSession(sessions[0].id);
    } else {
      state.currentSessionId = null;
      renderSessionList();
      showEmptyState();
      updateChatHeader(null);
    }
  } else {
    renderSessionList();
  }

  updateStatus('会话已删除', 'info');
}

// ===== 消息发送与流式接收 =====
function handleSend() {
  const textarea = $('.input-area textarea');
  const content = textarea.value.trim();
  if (!content || state.isStreaming) return;

  // 检查 API Key
  if (!appConfig.hasApiKey()) {
    openSettings();
    updateStatus('请先配置 API Key', 'error');
    return;
  }

  // 如果没有当前会话，自动创建
  if (!state.currentSessionId) {
    createNewSession();
  }

  const sessionId = state.currentSessionId;
  textarea.value = '';
  autoResizeTextarea(textarea);

  // 添加用户消息
  const userMsg = createMessage('user', content);
  appStorage.addMessage(sessionId, userMsg);
  renderMessages(sessionId);

  // 滚动到底部
  scrollToBottom();

  // 创建占位的助手消息
  const assistantMsg = createMessage('assistant', '', 'streaming');
  appStorage.addMessage(sessionId, assistantMsg);
  renderMessages(sessionId);
  scrollToBottom();

  // 禁用输入
  enableInput(false);
  state.isStreaming = true;
  updateStatus('AI 正在回复...', 'info');

  // 准备消息历史（取当前会话的所有消息，去掉状态标记）
  const session = appStorage.getSession(sessionId);
  const messagesForApi = session.messages
    .filter((m) => m.role !== 'system' || m.content)
    .map((m) => ({ role: m.role, content: m.content }));

  // 发送请求
  const config = {
    apiKey: appConfig.get('apiKey'),
    baseUrl: appConfig.get('baseUrl'),
    model: appConfig.get('model'),
    maxTokens: appConfig.get('maxTokens'),
    temperature: appConfig.get('temperature'),
  };

  let fullContent = '';

  state.abortController = apiService.sendChatStream(
    config,
    messagesForApi,
    // onChunk
    (chunk) => {
      fullContent += chunk;
      appStorage.updateLastMessage(sessionId, {
        content: fullContent,
        status: 'streaming',
      });
      // 局部更新最后一条消息（性能优化）
      updateLastMessageContent(sessionId);
      scrollToBottom();
    },
    // onDone
    () => {
      if (!fullContent) {
        fullContent = '（空回复）';
      }
      appStorage.updateLastMessage(sessionId, {
        content: fullContent,
        status: 'complete',
      });
      state.isStreaming = false;
      state.abortController = null;
      enableInput(true);
      renderMessages(sessionId);
      updateStatus('回复完成', 'info');
    },
    // onError
    (error) => {
      appStorage.updateLastMessage(sessionId, {
        content: error.message || '请求失败',
        status: 'error',
      });
      state.isStreaming = false;
      state.abortController = null;
      enableInput(true);
      renderMessages(sessionId);
      updateStatus(error.message || '请求失败', 'error');
    }
  );
}

function cancelStreaming() {
  if (state.abortController) {
    state.abortController.abort();
    state.abortController = null;
  }
  state.isStreaming = false;
  enableInput(true);
  // 如果最后一条消息是 streaming 状态，标记为 error
  if (state.currentSessionId) {
    const session = appStorage.getSession(state.currentSessionId);
    if (session && session.messages.length > 0) {
      const last = session.messages[session.messages.length - 1];
      if (last.status === 'streaming') {
        last.status = 'error';
        last.content = last.content || '已取消';
        appStorage.updateSession(state.currentSessionId, { messages: session.messages });
        renderMessages(state.currentSessionId);
      }
    }
  }
  updateStatus('已取消', 'info');
}

// ===== 渲染函数 =====

function renderSessionList() {
  const container = $('.session-list');
  if (!container) return;

  const sessions = appStorage.getSessionList();

  if (sessions.length === 0) {
    container.innerHTML = `
      <div style="padding: 24px 12px; text-align: center; color: var(--text-muted); font-size: 13px;">
        暂无对话记录
      </div>
    `;
    return;
  }

  container.innerHTML = sessions
    .map(
      (s) => `
      <div class="session-item ${s.id === state.currentSessionId ? 'active' : ''}" data-id="${s.id}">
        <span class="session-item-title">${escapeHtml(s.title)}</span>
        <span class="session-item-time">${formatTime(s.lastUpdatedAt)}</span>
        <button class="session-item-delete" data-action="delete" title="删除对话">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="3 6 5 6 21 6"></polyline>
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
          </svg>
        </button>
      </div>
    `
    )
    .join('');

  // 绑定事件
  container.querySelectorAll('.session-item').forEach((el) => {
    el.addEventListener('click', (e) => {
      const deleteBtn = e.target.closest('[data-action="delete"]');
      if (deleteBtn) {
        deleteSession(el.dataset.id, e);
        return;
      }
      selectSession(el.dataset.id);
    });
  });
}

function renderMessages(sessionId) {
  const container = $('.messages-container');
  if (!container) return;

  if (!sessionId) {
    showEmptyState();
    return;
  }

  const session = appStorage.getSession(sessionId);
  if (!session || session.messages.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
        </svg>
        <h2>开始对话</h2>
        <p>在下方输入消息，开始与 AI 对话</p>
      </div>
    `;
    return;
  }

  container.innerHTML = session.messages
    .map((msg) => {
      const roleClass = msg.role === 'user' ? 'user' : msg.role === 'assistant' ? 'assistant' : 'system';
      const isError = msg.status === 'error';
      const isStreaming = msg.status === 'streaming';
      const displayContent = isStreaming && !msg.content ? '...' : msg.content;

      return `
        <div class="message ${roleClass} ${isError ? 'error' : ''}" data-id="${msg.id}">
          <div class="message-avatar">${msg.role === 'user' ? 'U' : msg.role === 'assistant' ? 'AI' : 'S'}</div>
          <div class="message-body">
            <div class="message-content">${escapeHtml(displayContent)}${isStreaming ? '<span class="streaming-cursor"></span>' : ''}</div>
            <div class="message-time">${formatTime(msg.timestamp)}${isError ? ' · 发送失败' : ''}</div>
          </div>
        </div>
      `;
    })
    .join('');

  scrollToBottom();
}

/**
 * 仅更新最后一条消息的内容（流式优化）
 */
function updateLastMessageContent(sessionId) {
  const container = $('.messages-container');
  if (!container) return;

  const session = appStorage.getSession(sessionId);
  if (!session || session.messages.length === 0) return;

  const lastMsg = session.messages[session.messages.length - 1];
  const lastMsgEl = container.querySelector(`.message:last-child .message-content`);
  if (lastMsgEl) {
    const cursor = lastMsgEl.querySelector('.streaming-cursor');
    lastMsgEl.textContent = lastMsg.content;
    if (lastMsg.status === 'streaming') {
      // 重新追加光标
      const newCursor = document.createElement('span');
      newCursor.className = 'streaming-cursor';
      lastMsgEl.appendChild(newCursor);
    }
  }
}

function showEmptyState() {
  const container = $('.messages-container');
  if (!container) return;
  container.innerHTML = `
    <div class="empty-state">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M12 2a10 10 0 0 1 10 10c0 2.5-1 4.8-2.6 6.4L12 22l-7.4-3.6A10 10 0 0 1 2 12 10 10 0 0 1 12 2z"></path>
        <path d="M8 12h8"></path>
        <path d="M12 8v8"></path>
      </svg>
      <h2>AI 对话助手</h2>
      <p>点击「新建对话」开始，或在设置中配置 API</p>
    </div>
  `;
}

function updateChatHeader(sessionId) {
  const titleEl = $('.chat-header-title');
  if (!titleEl) return;

  if (!sessionId) {
    titleEl.textContent = 'AI 对话助手';
    return;
  }

  const session = appStorage.getSession(sessionId);
  titleEl.textContent = session ? session.title : 'AI 对话助手';
}

function enableInput(enabled) {
  const textarea = $('.input-area textarea');
  const sendBtn = $('.btn-send');
  if (textarea) textarea.disabled = !enabled;
  if (sendBtn) sendBtn.disabled = !enabled;
}

function updateStatus(msg, type = 'info') {
  const bar = $('.status-bar');
  if (!bar) return;
  bar.textContent = msg;
  bar.className = 'status-bar ' + (type === 'error' ? 'error' : '');
}

function scrollToBottom() {
  const container = $('.messages-container');
  if (container) {
    requestAnimationFrame(() => {
      container.scrollTop = container.scrollHeight;
    });
  }
}

function autoResizeTextarea(textarea) {
  textarea.style.height = 'auto';
  textarea.style.height = Math.min(textarea.scrollHeight, 150) + 'px';
}

// ===== 设置面板 =====
function openSettings() {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal">
      <div class="modal-header">
        <h2>设置</h2>
        <button class="modal-close" data-action="close-settings">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      </div>
      <div class="modal-body">
        <div class="form-group">
          <label for="setting-api-key">API Key</label>
          <input type="password" id="setting-api-key" value="${escapeHtml(appConfig.get('apiKey'))}" placeholder="sk-..." />
          <div class="form-hint">你的 API Key 仅存储在本地浏览器中</div>
        </div>
        <div class="form-group">
          <label for="setting-base-url">API Base URL</label>
          <input type="url" id="setting-base-url" value="${escapeHtml(appConfig.get('baseUrl'))}" placeholder="https://api.openai.com/v1" />
          <div class="form-hint">支持 OpenAI 兼容的任意 API 端点</div>
        </div>
        <div class="form-group">
          <label for="setting-model">模型</label>
          <input type="text" id="setting-model" list="model-suggestions" value="${escapeHtml(appConfig.get('model'))}" autocomplete="off" />
          <datalist id="model-suggestions">
            ${MODEL_LIST.map((m) => `<option value="${m.id}">${m.name}</option>`).join('')}
          </datalist>
          <div class="form-hint">输入任意模型 ID（如 deepseek-chat、gpt-4o），下拉仅为建议</div>
        </div>
        <div class="form-group">
          <label for="setting-max-tokens">最大 Token 数</label>
          <input type="number" id="setting-max-tokens" value="${appConfig.get('maxTokens')}" min="1" max="16384" />
        </div>
        <div class="form-group">
          <label for="setting-temperature">温度 (Temperature)</label>
          <input type="range" id="setting-temperature" min="0" max="2" step="0.1" value="${appConfig.get('temperature')}" />
          <div class="form-hint">当前值: <span id="temperature-value">${appConfig.get('temperature')}</span></div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" data-action="close-settings">取消</button>
        <button class="btn btn-primary" data-action="save-settings">保存</button>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);

  // 温度滑块联动
  const tempSlider = overlay.querySelector('#setting-temperature');
  const tempValue = overlay.querySelector('#temperature-value');
  tempSlider.addEventListener('input', () => {
    tempValue.textContent = tempSlider.value;
  });

  // 关闭
  const close = () => {
    overlay.remove();
  };

  overlay.querySelectorAll('[data-action="close-settings"]').forEach((el) => {
    el.addEventListener('click', close);
  });

  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) close();
  });

  // 保存
  overlay.querySelector('[data-action="save-settings"]').addEventListener('click', () => {
    const apiKey = overlay.querySelector('#setting-api-key').value.trim();
    const baseUrl = overlay.querySelector('#setting-base-url').value.trim();
    const model = overlay.querySelector('#setting-model').value;
    const maxTokens = parseInt(overlay.querySelector('#setting-max-tokens').value, 10) || 2048;
    const temperature = parseFloat(overlay.querySelector('#setting-temperature').value);

    appConfig.update({ apiKey, baseUrl, model, maxTokens, temperature });
    const saved = appConfig.save();
    if (saved) {
      bus.emit('config:saved');
    } else {
      bus.emit('error', '配置保存失败');
    }
    close();
  });

  // ESC 关闭
  const escHandler = (e) => {
    if (e.key === 'Escape') {
      close();
      document.removeEventListener('keydown', escHandler);
    }
  };
  document.addEventListener('keydown', escHandler);
}

// ===== 工具函数 =====
function escapeHtml(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}
