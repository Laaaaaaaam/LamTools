/**
 * storage.js - 服务层：localStorage 持久化管理
 * 负责会话数据的 CRUD 操作与存储容量预警
 */

const STORAGE_KEY = 'ai_chat_sessions';
const MAX_STORAGE_SIZE = 4.5 * 1024 * 1024; // 4.5MB 预警阈值

class Storage {
  constructor() {
    this.sessions = [];
    this._load();
  }

  /**
   * 从 localStorage 加载所有会话
   */
  _load() {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        this.sessions = JSON.parse(saved);
        // 按最后更新时间降序排列
        this.sessions.sort((a, b) => b.lastUpdatedAt - a.lastUpdatedAt);
      } else {
        this.sessions = [];
      }
    } catch (e) {
      console.warn('Storage load failed:', e);
      this.sessions = [];
    }
  }

  /**
   * 将会话数据写回 localStorage
   */
  _persist() {
    try {
      const serialized = JSON.stringify(this.sessions);
      // 容量检查
      const size = new Blob([serialized]).size;
      if (size > MAX_STORAGE_SIZE) {
        console.warn(`Storage nearing limit: ${(size / 1024 / 1024).toFixed(2)}MB`);
      }
      localStorage.setItem(STORAGE_KEY, serialized);
      return true;
    } catch (e) {
      if (e.name === 'QuotaExceededError' || e.code === 22) {
        throw new Error('存储空间已满，请删除部分旧会话后重试');
      }
      console.error('Storage persist failed:', e);
      return false;
    }
  }

  /**
   * 获取所有会话列表（不含消息内容，用于侧栏展示）
   * @returns {Array<{id, title, createdAt, lastUpdatedAt, messageCount}>}
   */
  getSessionList() {
    return this.sessions.map((s) => ({
      id: s.id,
      title: s.title,
      createdAt: s.createdAt,
      lastUpdatedAt: s.lastUpdatedAt,
      messageCount: s.messages.length,
    }));
  }

  /**
   * 获取单个会话（含完整消息）
   * @param {string} id
   * @returns {Session|null}
   */
  getSession(id) {
    return this.sessions.find((s) => s.id === id) || null;
  }

  /**
   * 创建新会话
   * @param {Session} session
   */
  addSession(session) {
    this.sessions.unshift(session);
    this._persist();
  }

  /**
   * 更新会话（合并字段）
   * @param {string} id
   * @param {Object} updates
   */
  updateSession(id, updates) {
    const session = this.sessions.find((s) => s.id === id);
    if (!session) return false;
    Object.assign(session, updates, { lastUpdatedAt: Date.now() });
    // 保持排序
    this.sessions.sort((a, b) => b.lastUpdatedAt - a.lastUpdatedAt);
    this._persist();
    return true;
  }

  /**
   * 删除会话
   * @param {string} id
   */
  deleteSession(id) {
    const idx = this.sessions.findIndex((s) => s.id === id);
    if (idx === -1) return false;
    this.sessions.splice(idx, 1);
    this._persist();
    return true;
  }

  /**
   * 向会话添加消息
   * @param {string} sessionId
   * @param {Message} message
   */
  addMessage(sessionId, message) {
    const session = this.sessions.find((s) => s.id === sessionId);
    if (!session) return false;
    session.messages.push(message);
    session.lastUpdatedAt = Date.now();
    // 如果这是第一条用户消息，自动生成标题
    if (message.role === 'user' && session.messages.filter((m) => m.role === 'user').length === 1) {
      session.title = generateTitle(message.content);
    }
    this.sessions.sort((a, b) => b.lastUpdatedAt - a.lastUpdatedAt);
    this._persist();
    return true;
  }

  /**
   * 更新会话中的最后一条消息
   * @param {string} sessionId
   * @param {Object} updates
   */
  updateLastMessage(sessionId, updates) {
    const session = this.sessions.find((s) => s.id === sessionId);
    if (!session || session.messages.length === 0) return false;
    const lastMsg = session.messages[session.messages.length - 1];
    Object.assign(lastMsg, updates);
    session.lastUpdatedAt = Date.now();
    this._persist();
    return true;
  }

  /**
   * 清空所有会话
   */
  clearAll() {
    this.sessions = [];
    localStorage.removeItem(STORAGE_KEY);
  }

  /**
   * 获取当前存储使用量（字节）
   */
  getStorageSize() {
    try {
      const serialized = JSON.stringify(this.sessions);
      return new Blob([serialized]).size;
    } catch {
      return 0;
    }
  }
}

const appStorage = new Storage();
