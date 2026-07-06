/**
 * VideoForge - 媒体管理模块
 */

class MediaManager {
    constructor(app) {
        this.app = app;
        this.mediaItems = new Map(); // id -> mediaItem
        this.selectedItem = null;

        this.initElements();
        this.bindEvents();
    }

    initElements() {
        this.importZone = document.getElementById('media-import-zone');
        this.mediaList = document.getElementById('media-list');
        this.fileInput = document.getElementById('file-input');
    }

    bindEvents() {
        // 导入区域点击
        this.importZone.addEventListener('click', () => this.fileInput.click());

        // 文件选择
        this.fileInput.addEventListener('change', (e) => {
            this.importFiles(e.target.files);
            e.target.value = '';
        });

        // 拖拽导入
        this.importZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            this.importZone.classList.add('drag-over');
        });

        this.importZone.addEventListener('dragleave', () => {
            this.importZone.classList.remove('drag-over');
        });

        this.importZone.addEventListener('drop', (e) => {
            e.preventDefault();
            this.importZone.classList.remove('drag-over');
            this.importFiles(e.dataTransfer.files);
        });

        // 全局拖拽支持
        document.addEventListener('dragover', (e) => e.preventDefault());
        document.addEventListener('drop', (e) => {
            e.preventDefault();
            if (e.dataTransfer.files.length > 0) {
                this.importFiles(e.dataTransfer.files);
            }
        });

        // 媒体项拖拽到时间线
        this.mediaList.addEventListener('dragstart', (e) => {
            const item = e.target.closest('.media-item');
            if (!item) return;
            e.dataTransfer.setData('mediaId', item.dataset.id);
            e.dataTransfer.effectAllowed = 'copy';
        });
    }

    /**
     * 导入文件
     */
    async importFiles(files) {
        for (const file of files) {
            await this.importFile(file);
        }
    }

    /**
     * 导入单个文件
     */
    async importFile(file) {
        const type = Utils.getFileType(file);
        if (type === 'unknown') {
            Utils.showToast(`不支持的文件格式: ${file.name}`, 'error');
            return;
        }

        const id = Utils.generateId();
        const mediaItem = {
            id,
            file,
            name: file.name,
            type,
            size: file.size,
            url: URL.createObjectURL(file),
            duration: 0,
            thumbnail: null,
            width: 0,
            height: 0,
            waveform: null
        };

        // 获取媒体信息
        try {
            if (type === 'video') {
                const info = await Utils.createVideoThumbnail(file);
                mediaItem.thumbnail = info.thumbnail;
                mediaItem.duration = info.duration;
                mediaItem.width = info.width;
                mediaItem.height = info.height;
            } else if (type === 'audio') {
                const info = await Utils.createAudioWaveform(file);
                mediaItem.waveform = info.waveform;
                mediaItem.duration = info.duration;
            } else if (type === 'image') {
                mediaItem.thumbnail = mediaItem.url;
                const dims = await this.getImageDimensions(file);
                mediaItem.width = dims.width;
                mediaItem.height = dims.height;
                mediaItem.duration = 5; // 默认5秒
            }
        } catch (e) {
            console.warn('获取媒体信息失败:', e);
        }

        this.mediaItems.set(id, mediaItem);
        this.renderMediaItem(mediaItem);
        Utils.showToast(`已导入: ${file.name}`, 'success');

        // 隐藏导入区域如果已有媒体
        if (this.mediaItems.size > 0) {
            this.importZone.style.padding = '15px 20px';
            this.importZone.querySelector('p').textContent = '继续导入更多文件';
        }
    }

    /**
     * 获取图片尺寸
     */
    getImageDimensions(file) {
        return new Promise((resolve) => {
            const img = new Image();
            img.onload = () => resolve({ width: img.width, height: img.height });
            img.onerror = () => resolve({ width: 0, height: 0 });
            img.src = URL.createObjectURL(file);
        });
    }

    /**
     * 渲染媒体项
     */
    renderMediaItem(item) {
        const el = document.createElement('div');
        el.className = 'media-item';
        el.dataset.id = item.id;
        el.draggable = true;

        let thumbContent = '';
        if (item.type === 'video') {
            thumbContent = item.thumbnail
                ? `<img src="${item.thumbnail}" alt="${item.name}">`
                : `<i class="fas fa-video"></i>`;
        } else if (item.type === 'audio') {
            thumbContent = `<i class="fas fa-music"></i>`;
        } else if (item.type === 'image') {
            thumbContent = `<img src="${item.thumbnail}" alt="${item.name}">`;
        }

        const durationStr = item.duration > 0 ? Utils.formatShortTime(item.duration) : '';

        el.innerHTML = `
            <div class="media-item-thumb">
                ${thumbContent}
                ${durationStr ? `<span class="duration">${durationStr}</span>` : ''}
            </div>
            <div class="media-item-info">
                <div class="media-item-name" title="${item.name}">${item.name}</div>
                <div class="media-item-meta">
                    <span class="badge badge-${item.type}">${item.type === 'video' ? '视频' : item.type === 'audio' ? '音频' : '图片'}</span>
                    ${Utils.formatFileSize(item.size)}
                </div>
            </div>
        `;

        // 双击添加到时间线
        el.addEventListener('dblclick', () => {
            this.addMediaToTimeline(item.id);
        });

        // 右键菜单
        el.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            this.selectedItem = item.id;
            Utils.showContextMenu(e.clientX, e.clientY, [
                {
                    label: '添加到时间线',
                    icon: 'fas fa-plus',
                    action: 'add',
                    callback: () => this.addMediaToTimeline(item.id)
                },
                { label: '预览', icon: 'fas fa-play', action: 'preview', callback: () => this.previewMedia(item.id) },
                'divider',
                { label: '删除', icon: 'fas fa-trash', action: 'delete', callback: () => this.removeMedia(item.id) }
            ]);
        });

        this.mediaList.appendChild(el);
    }

    /**
     * 添加媒体到时间线
     */
    addMediaToTimeline(mediaId) {
        const item = this.mediaItems.get(mediaId);
        if (!item) return;

        this.app.timeline.addClipFromMedia(item);
    }

    /**
     * 预览媒体
     */
    previewMedia(mediaId) {
        const item = this.mediaItems.get(mediaId);
        if (!item) return;
        this.app.preview.loadMedia(item);
    }

    /**
     * 删除媒体
     */
    removeMedia(mediaId) {
        const item = this.mediaItems.get(mediaId);
        if (!item) return;

        URL.revokeObjectURL(item.url);
        this.mediaItems.delete(mediaId);

        const el = this.mediaList.querySelector(`[data-id="${mediaId}"]`);
        if (el) el.remove();

        Utils.showToast(`已删除: ${item.name}`, 'info');
    }

    /**
     * 获取媒体项
     */
    getMedia(id) {
        return this.mediaItems.get(id);
    }
}
