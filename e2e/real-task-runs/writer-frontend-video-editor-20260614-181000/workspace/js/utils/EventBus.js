/**
 * 轻量级事件总线 - 模块间解耦通信
 */
export class EventBus {
  constructor() {
    this._listeners = new Map();
  }

  on(event, callback, context = null) {
    if (!this._listeners.has(event)) {
      this._listeners.set(event, []);
    }
    this._listeners.get(event).push({ callback, context });
    return () => this.off(event, callback, context);
  }

  off(event, callback, context = null) {
    const list = this._listeners.get(event);
    if (!list) return;
    this._listeners.set(event, list.filter(
      l => l.callback !== callback || l.context !== context
    ));
  }

  emit(event, ...args) {
    const list = this._listeners.get(event);
    if (!list) return;
    for (const { callback, context } of list) {
      callback.apply(context, args);
    }
  }

  once(event, callback, context = null) {
    const unsub = this.on(event, (...args) => {
      unsub();
      callback.apply(context, args);
    }, context);
    return unsub;
  }
}

// 全局单例
export const eventBus = new EventBus();
