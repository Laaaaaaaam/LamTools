/* ============================================================
   待办事项应用 — 事件驱动型 MVC + 观察者模式
   架构: EventBus → Model → View → Controller
   数据流: Controller → Model → EventBus.emit → View.render
   ============================================================ */
;(function () {
  'use strict';

  // ===================== 常量 =====================
  const STORAGE_KEY = 'todo_app_data';
  const FILTER_ALL = 'all';
  const FILTER_ACTIVE = 'active';
  const FILTER_COMPLETED = 'completed';

  // ===================== EventBus =====================
  // 应用内解耦通信中枢，管理自定义事件的注册、触发与移除
  const EventBus = {
    _listeners: {},

    on(event, callback) {
      if (!this._listeners[event]) this._listeners[event] = [];
      this._listeners[event].push(callback);
    },

    emit(event, data) {
      const list = this._listeners[event];
      if (!list) return;
      list.forEach(cb => cb(data));
    },

    off(event, callback) {
      const list = this._listeners[event];
      if (!list) return;
      this._listeners[event] = list.filter(cb => cb !== callback);
    }
  };

  // ===================== Model =====================
  // 待办数据核心管理，CRUD操作，状态流转，localStorage读写同步
  const TodoModel = {
    _todos: [],
    _filter: FILTER_ALL,

    // 初始化：从 localStorage 恢复数据
    init() {
      try {
        const raw = localStorage.getItem(STORAGE_KEY);
        this._todos = raw ? JSON.parse(raw) : [];
      } catch (e) {
        this._todos = [];
      }
      this._notify();
    },

    // 持久化到 localStorage
    _save() {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(this._todos));
      } catch (e) {
        console.warn('localStorage 写入失败', e);
      }
    },

    // 通知 View 重新渲染
    _notify() {
      EventBus.emit('todos:changed', {
        todos: this.getFiltered(),
        stats: this.getStats()
      });
    },

    // 生成唯一 ID
    _generateId() {
      return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
    },

    // 添加待办
    add(title) {
      const trimmed = title.trim();
      if (!trimmed) return null;
      const todo = {
        id: this._generateId(),
        title: trimmed,
        completed: false,
        createdAt: Date.now()
      };
      this._todos.unshift(todo);
      this._save();
      this._notify();
      return todo;
    },

    // 切换完成状态
    toggle(id) {
      const todo = this._todos.find(t => t.id === id);
      if (!todo) return;
      todo.completed = !todo.completed;
      this._save();
      this._notify();
    },

    // 更新标题
    update(id, title) {
      const trimmed = title.trim();
      if (!trimmed) return false;
      const todo = this._todos.find(t => t.id === id);
      if (!todo) return false;
      todo.title = trimmed;
      this._save();
      this._notify();
      return true;
    },

    // 删除待办
    destroy(id) {
      this._todos = this._todos.filter(t => t.id !== id);
      this._save();
      this._notify();
    },

    // 清空已完成
    clearCompleted() {
      this._todos = this._todos.filter(t => !t.completed);
      this._save();
      this._notify();
    },

    // 设置筛选
    setFilter(filter) {
      this._filter = filter;
      this._notify();
    },

    // 获取筛选后的列表
    getFiltered() {
      switch (this._filter) {
        case FILTER_ACTIVE:
          return this._todos.filter(t => !t.completed);
        case FILTER_COMPLETED:
          return this._todos.filter(t => t.completed);
        default:
          return [...this._todos];
      }
    },

    // 获取统计信息
    getStats() {
      const total = this._todos.length;
      const completed = this._todos.filter(t => t.completed).length;
      const active = total - completed;
      return { total, completed, active, filter: this._filter };
    }
  };

  // ===================== View =====================
  // UI渲染与DOM管理，监听Model变更并更新界面
  const TodoView = {
    // DOM 引用缓存
    _els: {},
    _editingId: null,

    // 初始化：缓存 DOM 引用，绑定事件
    init() {
      this._els = {
        form: document.getElementById('todoForm'),
        input: document.getElementById('todoInput'),
        addBtn: document.getElementById('addBtn'),
        errorMsg: document.getElementById('errorMsg'),
        filterBar: document.getElementById('filterBar'),
        todoList: document.getElementById('todoList'),
        emptyState: document.getElementById('emptyState'),
        emptyText: document.getElementById('emptyText'),
        footer: document.getElementById('footer'),
        itemCount: document.getElementById('itemCount'),
        clearBtn: document.getElementById('clearCompletedBtn'),
        dateDisplay: document.getElementById('dateDisplay')
      };

      this._renderDate();
      this._bindEvents();
    },

    // 渲染日期
    _renderDate() {
      const now = new Date();
      const options = { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' };
      this._els.dateDisplay.textContent = now.toLocaleDateString('zh-CN', options);
    },

    // 绑定 DOM 事件 → 转发到 Controller
    _bindEvents() {
      // 提交表单
      this._els.form.addEventListener('submit', (e) => {
        e.preventDefault();
        const title = this._els.input.value;
        EventBus.emit('view:add', title);
      });

      // 筛选按钮
      this._els.filterBar.addEventListener('click', (e) => {
        const btn = e.target.closest('.filter-btn');
        if (!btn) return;
        const filter = btn.dataset.filter;
        EventBus.emit('view:filter', filter);
      });

      // 清除已完成
      this._els.clearBtn.addEventListener('click', () => {
        EventBus.emit('view:clearCompleted');
      });

      // 列表事件委托（checkbox / 编辑 / 删除）
      this._els.todoList.addEventListener('click', (e) => {
        const item = e.target.closest('.todo-item');
        if (!item) return;
        const id = item.dataset.id;

        // Checkbox
        if (e.target.closest('.todo-item__checkbox')) {
          EventBus.emit('view:toggle', id);
          return;
        }

        // 编辑按钮
        if (e.target.closest('.todo-item__action-btn--edit')) {
          this._startEditing(id, item);
          return;
        }

        // 删除按钮
        if (e.target.closest('.todo-item__action-btn--delete')) {
          EventBus.emit('view:destroy', id);
          return;
        }

        // 保存按钮
        if (e.target.closest('.todo-item__action-btn--save')) {
          this._saveEditing(id, item);
          return;
        }

        // 取消按钮
        if (e.target.closest('.todo-item__action-btn--cancel')) {
          this._cancelEditing();
          return;
        }
      });

      // 编辑输入框的键盘事件
      this._els.todoList.addEventListener('keydown', (e) => {
        if (e.target.classList.contains('todo-item__edit-input')) {
          const item = e.target.closest('.todo-item');
          const id = item.dataset.id;
          if (e.key === 'Enter') {
            e.preventDefault();
            this._saveEditing(id, item);
          } else if (e.key === 'Escape') {
            this._cancelEditing();
          }
        }
      });

      // 双击标题进入编辑
      this._els.todoList.addEventListener('dblclick', (e) => {
        if (e.target.classList.contains('todo-item__title')) {
          const item = e.target.closest('.todo-item');
          const id = item.dataset.id;
          this._startEditing(id, item);
        }
      });
    },

    // 进入编辑模式
    _startEditing(id, itemEl) {
      // 先取消之前的编辑
      if (this._editingId && this._editingId !== id) {
        this._cancelEditing();
      }
      this._editingId = id;
      const titleEl = itemEl.querySelector('.todo-item__title');
      const currentTitle = titleEl.textContent;
      const actionsEl = itemEl.querySelector('.todo-item__actions');

      // 替换标题为输入框
      const input = document.createElement('input');
      input.type = 'text';
      input.className = 'todo-item__edit-input';
      input.value = currentTitle;
      input.maxLength = 200;
      titleEl.style.display = 'none';
      titleEl.parentNode.insertBefore(input, titleEl.nextSibling);
      input.focus();
      input.select();

      // 替换操作按钮
      actionsEl.innerHTML = `
        <button class="todo-item__action-btn todo-item__action-btn--save" title="保存">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M3 8.5l3.5 3.5L13 5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
        <button class="todo-item__action-btn todo-item__action-btn--cancel" title="取消">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
        </button>
      `;

      itemEl.classList.add('editing');
    },

    // 保存编辑
    _saveEditing(id, itemEl) {
      const input = itemEl.querySelector('.todo-item__edit-input');
      if (!input) return;
      const newTitle = input.value.trim();
      if (!newTitle) {
        this.showError('待办内容不能为空');
        input.focus();
        return;
      }
      this._editingId = null;
      EventBus.emit('view:update', { id, title: newTitle });
    },

    // 取消编辑
    _cancelEditing() {
      this._editingId = null;
      // 重新渲染列表以恢复原始状态
      TodoModel._notify();
    },

    // 渲染列表（由 Model 变更触发）
    renderList(data) {
      const { todos, stats } = data;

      // 如果正在编辑，先记录编辑状态
      const wasEditing = this._editingId;

      // 渲染列表项
      if (todos.length === 0) {
        this._els.todoList.innerHTML = '';
        this._els.emptyState.style.display = 'block';
        const filterTexts = {
          [FILTER_ALL]: '暂无待办事项，添加一个吧 ✨',
          [FILTER_ACTIVE]: '所有待办都已完成 🎉',
          [FILTER_COMPLETED]: '还没有已完成的待办'
        };
        this._els.emptyText.textContent = filterTexts[stats.filter] || '暂无待办事项';
      } else {
        this._els.emptyState.style.display = 'none';
        this._els.todoList.innerHTML = todos.map(todo => this._renderItem(todo)).join('');
      }

      // 更新筛选按钮
      this._els.filterBar.querySelectorAll('.filter-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.filter === stats.filter);
      });

      // 更新底部统计
      if (stats.total > 0) {
        this._els.footer.style.display = 'flex';
        const activeText = stats.active === 1 ? '1 项待办' : `${stats.active} 项待办`;
        this._els.itemCount.innerHTML = `<strong>${activeText}</strong>剩余`;
        this._els.clearBtn.disabled = stats.completed === 0;
      } else {
        this._els.footer.style.display = 'none';
      }

      // 恢复编辑状态
      if (wasEditing) {
        const editItem = this._els.todoList.querySelector(`[data-id="${wasEditing}"]`);
        if (editItem) {
          this._startEditing(wasEditing, editItem);
        } else {
          this._editingId = null;
        }
      }
    },

    // 渲染单个待办项 HTML
    _renderItem(todo) {
      const escapedTitle = this._escapeHtml(todo.title);
      return `
        <div class="todo-item ${todo.completed ? 'completed' : ''}" data-id="${todo.id}">
          <label class="todo-item__checkbox">
            <input type="checkbox" ${todo.completed ? 'checked' : ''}>
            <span class="todo-item__checkmark"></span>
          </label>
          <span class="todo-item__title">${escapedTitle}</span>
          <div class="todo-item__actions">
            <button class="todo-item__action-btn todo-item__action-btn--edit" title="编辑">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M8.5 2.5l3 3M1.5 9.5l-.5 3 3-.5L12 4l-3-3L1.5 9.5z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </button>
            <button class="todo-item__action-btn todo-item__action-btn--delete" title="删除">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M2 3.5h10M5.5 3.5V2a1 1 0 011-1h1a1 1 0 011 1v1.5M3.5 3.5l.5 8.5a1 1 0 001 1h4a1 1 0 001-1l.5-8.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </button>
          </div>
        </div>
      `;
    },

    // 清空输入框
    clearInput() {
      this._els.input.value = '';
      this._els.input.focus();
    },

    // 显示错误信息
    showError(msg) {
      this._els.errorMsg.textContent = msg;
      clearTimeout(this._errorTimer);
      this._errorTimer = setTimeout(() => {
        this._els.errorMsg.textContent = '';
      }, 2500);
    },

    // HTML 转义
    _escapeHtml(str) {
      const div = document.createElement('div');
      div.textContent = str;
      return div.innerHTML;
    }
  };

  // ===================== Controller =====================
  // 业务逻辑调度，监听View的DOM事件，校验输入，调用Model方法
  const TodoController = {
    init() {
      // 监听 View 事件
      EventBus.on('view:add', (title) => this.handleAdd(title));
      EventBus.on('view:toggle', (id) => this.handleToggle(id));
      EventBus.on('view:update', (data) => this.handleUpdate(data.id, data.title));
      EventBus.on('view:destroy', (id) => this.handleDestroy(id));
      EventBus.on('view:filter', (filter) => this.handleFilter(filter));
      EventBus.on('view:clearCompleted', () => this.handleClearCompleted());

      // 监听 Model 变更 → 通知 View 渲染
      EventBus.on('todos:changed', (data) => TodoView.renderList(data));
    },

    handleAdd(title) {
      const trimmed = title.trim();
      if (!trimmed) {
        TodoView.showError('请输入待办内容');
        return;
      }
      if (trimmed.length > 200) {
        TodoView.showError('待办内容不能超过200个字符');
        return;
      }
      const result = TodoModel.add(trimmed);
      if (result) {
        TodoView.clearInput();
        TodoView.showError('');
      } else {
        TodoView.showError('添加失败，请重试');
      }
    },

    handleToggle(id) {
      TodoModel.toggle(id);
    },

    handleUpdate(id, title) {
      const trimmed = title.trim();
      if (!trimmed) {
        TodoView.showError('待办内容不能为空');
        return;
      }
      const success = TodoModel.update(id, trimmed);
      if (!success) {
        TodoView.showError('更新失败，请重试');
      }
    },

    handleDestroy(id) {
      TodoModel.destroy(id);
    },

    handleFilter(filter) {
      if ([FILTER_ALL, FILTER_ACTIVE, FILTER_COMPLETED].includes(filter)) {
        TodoModel.setFilter(filter);
      }
    },

    handleClearCompleted() {
      TodoModel.clearCompleted();
    }
  };

  // ===================== 启动应用 =====================
  function bootstrap() {
    TodoView.init();
    TodoController.init();
    TodoModel.init();
  }

  // DOM 就绪后启动
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootstrap);
  } else {
    bootstrap();
  }

})();
