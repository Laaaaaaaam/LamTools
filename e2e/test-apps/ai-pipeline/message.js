/**
 * message.js - 模型层：消息与会话数据模型
 * 定义 Message 和 Session 的数据结构、工厂函数及工具方法
 */

/**
 * 生成简单 UUID v4
 */
function generateId() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * 创建一条消息
 * @param {'user'|'assistant'|'system'} role
 * @param {string} content
 * @param {'sending'|'streaming'|'complete'|'error'} [status='complete']
 * @returns {Message}
 */
function createMessage(role, content, status = 'complete') {
  return {
    id: generateId(),
    role,
    content,
    timestamp: Date.now(),
    status,
  };
}

/**
 * 创建一个新的会话
 * @param {string} [title='新对话']
 * @returns {Session}
 */
function createSession(title = '新对话') {
  return {
    id: generateId(),
    title,
    messages: [],
    createdAt: Date.now(),
    lastUpdatedAt: Date.now(),
  };
}

/**
 * 从消息内容自动生成会话标题
 * @param {string} content
 * @returns {string}
 */
function generateTitle(content) {
  const cleaned = content.replace(/[\r\n]+/g, ' ').trim();
  if (cleaned.length <= 30) return cleaned;
  return cleaned.substring(0, 27) + '...';
}

/**
 * 格式化时间戳
 * @param {number} ts
 * @returns {string}
 */
function formatTime(ts) {
  const d = new Date(ts);
  const now = new Date();
  const pad = (n) => String(n).padStart(2, '0');

  // 今天只显示时间
  if (d.toDateString() === now.toDateString()) {
    return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
  // 昨天
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  if (d.toDateString() === yesterday.toDateString()) {
    return `昨天 ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
  // 今年显示月日
  if (d.getFullYear() === now.getFullYear()) {
    return `${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
  // 更早显示完整日期
  return `${d.getFullYear()}/${pad(d.getMonth() + 1)}/${pad(d.getDate())}`;
}
