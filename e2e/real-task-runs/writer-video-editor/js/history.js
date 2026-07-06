/**
 * VideoForge - 历史记录（撤销/重做）模块
 */

class History {
    constructor(app) {
        this.app = app;
        this.undoStack = [];
        this.redoStack = [];
        this.maxHistory = 50;
        this.isRestoring = false;

        this.bindEvents();
    }

    bindEvents() {
        // 撤销
        document.getElementById('btn-undo').addEventListener('click', () => this.undo());

        // 重做
        document.getElementById('btn-redo').addEventListener('click', () => this.redo());

        // 键盘快捷键
        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
                if (e.shiftKey) {
                    this.redo();
                } else {
                    this.undo();
                }
                e.preventDefault();
            }
            if ((e.ctrlKey || e.metaKey) && e.key === 'y') {
                this.redo();
                e.preventDefault();
            }
        });
    }

    /**
     * 保存当前状态
     */
    saveState() {
        if (this.isRestoring) return;

        const state = {
            clips: this.app.timeline.getState(),
            timestamp: Date.now()
        };

        this.undoStack.push(state);
        this.redoStack = []; // 清除重做栈

        // 限制历史长度
        if (this.undoStack.length > this.maxHistory) {
            this.undoStack.shift();
        }

        this.updateButtons();
    }

    /**
     * 撤销
     */
    undo() {
        if (this.undoStack.length <= 1) {
            Utils.showToast('没有可撤销的操作', 'info', 1500);
            return;
        }

        const currentState = this.undoStack.pop();
        this.redoStack.push(currentState);

        const previousState = this.undoStack[this.undoStack.length - 1];
        this.restoreState(previousState);

        this.updateButtons();
    }

    /**
     * 重做
     */
    redo() {
        if (this.redoStack.length === 0) {
            Utils.showToast('没有可重做的操作', 'info', 1500);
            return;
        }

        const state = this.redoStack.pop();
        this.undoStack.push(state);

        this.restoreState(state);

        this.updateButtons();
    }

    /**
     * 恢复状态
     */
    restoreState(state) {
        this.isRestoring = true;

        this.app.timeline.restoreState(state.clips);
        this.app.preview.clearCache();
        this.app.preview.renderFrame();

        this.isRestoring = false;
    }

    /**
     * 更新按钮状态
     */
    updateButtons() {
        const undoBtn = document.getElementById('btn-undo');
        const redoBtn = document.getElementById('btn-redo');

        undoBtn.style.opacity = this.undoStack.length > 1 ? '1' : '0.4';
        redoBtn.style.opacity = this.redoStack.length > 0 ? '1' : '0.4';
    }

    /**
     * 清除所有历史
     */
    clear() {
        this.undoStack = [];
        this.redoStack = [];
        this.updateButtons();
    }

    /**
     * 初始化（保存初始状态）
     */
    init() {
        this.saveState();
    }
}
