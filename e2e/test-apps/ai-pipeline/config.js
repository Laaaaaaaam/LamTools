/**
 * config.js - 模型层：应用配置管理
 * 负责配置的默认值定义、读写与校验
 */

const DEFAULT_CONFIG = {
  apiKey: '',
  baseUrl: 'https://api.openai.com/v1',
  model: 'gpt-3.5-turbo',
  maxTokens: 2048,
  temperature: 0.7,
};

const MODEL_LIST = [
  { id: 'gpt-3.5-turbo', name: 'GPT-3.5 Turbo' },
  { id: 'gpt-4', name: 'GPT-4' },
  { id: 'gpt-4-turbo', name: 'GPT-4 Turbo' },
  { id: 'gpt-4o', name: 'GPT-4o' },
  { id: 'gpt-4o-mini', name: 'GPT-4o Mini' },
];

const CONFIG_KEY = 'ai_chat_config';

class Config {
  constructor() {
    this.data = { ...DEFAULT_CONFIG };
    this._load();
  }

  /**
   * 从 localStorage 加载配置
   */
  _load() {
    try {
      const saved = localStorage.getItem(CONFIG_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        // 只合并合法字段，防止污染
        Object.keys(DEFAULT_CONFIG).forEach((key) => {
          if (parsed[key] !== undefined) {
            this.data[key] = parsed[key];
          }
        });
      }
    } catch (e) {
      console.warn('Config load failed, using defaults:', e);
    }
  }

  /**
   * 保存配置到 localStorage
   */
  save() {
    try {
      localStorage.setItem(CONFIG_KEY, JSON.stringify(this.data));
      return true;
    } catch (e) {
      console.error('Config save failed:', e);
      return false;
    }
  }

  /**
   * 获取配置项
   * @param {string} key
   */
  get(key) {
    return this.data[key];
  }

  /**
   * 设置配置项
   * @param {string} key
   * @param {*} value
   */
  set(key, value) {
    this.data[key] = value;
  }

  /**
   * 批量更新配置
   * @param {Object} updates
   */
  update(updates) {
    Object.keys(updates).forEach((key) => {
      if (key in DEFAULT_CONFIG) {
        this.data[key] = updates[key];
      }
    });
  }

  /**
   * 检查 API Key 是否已配置
   */
  hasApiKey() {
    return !!this.data.apiKey;
  }

  /**
   * 获取完整的 API URL
   */
  getApiUrl() {
    const base = this.data.baseUrl.replace(/\/+$/, '');
    return `${base}/chat/completions`;
  }
}

// 导出单例
const appConfig = new Config();
