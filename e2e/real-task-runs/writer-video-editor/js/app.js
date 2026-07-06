/**
 * VideoForge - 主应用模块
 */

class App {
    constructor() {
        this.media = null;
        this.timeline = null;
        this.preview = null;
        this.properties = null;
        this.effects = null;
        this.export = null;
        this.history = null;

        this.init();
    }

    init() {
        // 初始化各模块
        this.media = new MediaManager(this);
        this.timeline = new Timeline(this);
        this.preview = new Preview(this);
        this.properties = new Properties(this);
        this.effects = new Effects(this);
        this.exportModule = new Export(this);
        this.history = new History(this);

        // 绑定全局事件
        this.bindGlobalEvents();

        // 初始化历史记录
        this.history.init();

        // 初始渲染
        this.preview.renderFrame();

        // 显示欢迎覆盖层
        this.updateOverlayVisibility();

        // 欢迎提示
        setTimeout(() => {
            Utils.showToast('欢迎使用 VideoForge！导入媒体文件开始编辑', 'info', 4000);
        }, 500);
    }

    bindGlobalEvents() {
        // 导入按钮
        document.getElementById('btn-import').addEventListener('click', () => {
            document.getElementById('file-input').click();
        });

        // 分割按钮
        document.getElementById('btn-split').addEventListener('click', () => {
            if (this.timeline.selectedClips.size === 1) {
                const clipId = [...this.timeline.selectedClips][0];
                this.timeline.splitClip(clipId, this.timeline.currentTime);
            } else {
                Utils.showToast('请先选中一个片段', 'warning');
            }
        });

        // 删除按钮
        document.getElementById('btn-delete').addEventListener('click', () => {
            this.timeline.deleteSelectedClips();
        });

        // 复制按钮
        document.getElementById('btn-copy').addEventListener('click', () => {
            this.timeline.copySelectedClips();
        });

        // 粘贴按钮
        document.getElementById('btn-paste').addEventListener('click', () => {
            this.timeline.pasteClips();
        });

        // 面板标签切换
        document.querySelectorAll('.panel-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                const tabName = tab.dataset.tab;
                document.querySelectorAll('.panel-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                document.getElementById(`tab-${tabName}`).classList.add('active');
            });
        });

        // 键盘快捷键
        document.addEventListener('keydown', (e) => {
            // Ctrl+C 复制
            if ((e.ctrlKey || e.metaKey) && e.key === 'c') {
                this.timeline.copySelectedClips();
                e.preventDefault();
            }
            // Ctrl+V 粘贴
            if ((e.ctrlKey || e.metaKey) && e.key === 'v') {
                this.timeline.pasteClips();
                e.preventDefault();
            }
            // Ctrl+A 全选
            if ((e.ctrlKey || e.metaKey) && e.key === 'a') {
                this.timeline.clips.forEach(c => this.timeline.selectedClips.add(c.id));
                this.timeline.renderClipSelections();
                e.preventDefault();
            }
            // Escape 取消选中
            if (e.key === 'Escape') {
                this.timeline.selectedClips.clear();
                this.timeline.renderClipSelections();
                this.properties.currentClip = null;
            }
        });

        // 防止默认右键菜单
        document.addEventListener('contextmenu', (e) => {
            if (e.target.closest('.clip') || e.target.closest('.media-item')) {
                e.preventDefault();
            }
        });

        // 窗口关闭前提醒
        window.addEventListener('beforeunload', (e) => {
            if (this.timeline.clips.length > 0) {
                e.preventDefault();
                e.returnValue = '';
            }
        });

        // 适应窗口按钮
        document.getElementById('btn-zoom-fit').addEventListener('click', () => {
            this.preview.resizeCanvas();
        });
    }

    /**
     * 更新预览覆盖层可见性
     */
    updateOverlayVisibility() {
        const overlay = document.getElementById('preview-overlay');
        if (this.timeline.clips.length === 0) {
            overlay.style.display = 'flex';
        } else {
            overlay.style.display = 'none';
        }
    }
}

// 启动应用
document.addEventListener('DOMContentLoaded', () => {
    window.app = new App();
});
