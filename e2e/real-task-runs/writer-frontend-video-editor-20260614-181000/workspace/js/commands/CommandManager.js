import { eventBus } from '../utils/EventBus.js';

/**
 * 命令管理器 - 实现撤销/重做
 * 所有状态变更必须通过此管理器执行
 */
export class CommandManager {
  constructor() {
    this._undoStack = [];
    this._redoStack = [];
    this._maxStackSize = 100;
  }

  /** 执行命令并压入撤销栈 */
  execute(command) {
    command.execute();
    this._undoStack.push(command);
    this._redoStack = []; // 新操作清空重做栈
    if (this._undoStack.length > this._maxStackSize) {
      this._undoStack.shift();
    }
    eventBus.emit('stateChanged');
    eventBus.emit('commandExecuted', command);
  }

  /** 撤销 */
  undo() {
    if (!this.canUndo) return;
    const command = this._undoStack.pop();
    command.undo();
    this._redoStack.push(command);
    eventBus.emit('stateChanged');
    eventBus.emit('commandUndone', command);
  }

  /** 重做 */
  redo() {
    if (!this.canRedo) return;
    const command = this._redoStack.pop();
    command.redo();
    this._undoStack.push(command);
    eventBus.emit('stateChanged');
    eventBus.emit('commandRedone', command);
  }

  get canUndo() {
    return this._undoStack.length > 0;
  }

  get canRedo() {
    return this._redoStack.length > 0;
  }

  get undoCount() {
    return this._undoStack.length;
  }

  get redoCount() {
    return this._redoStack.length;
  }

  clear() {
    this._undoStack = [];
    this._redoStack = [];
  }
}

/**
 * 命令基类
 */
export class Command {
  constructor(name) {
    this.name = name;
    this.timestamp = Date.now();
  }

  execute() {
    throw new Error('Command.execute() must be implemented');
  }

  undo() {
    throw new Error('Command.undo() must be implemented');
  }

  redo() {
    this.execute();
  }
}
