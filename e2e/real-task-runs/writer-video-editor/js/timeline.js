/**
 * VideoForge - 时间线模块
 */

class Timeline {
    constructor(app) {
        this.app = app;
        this.clips = []; // 所有片段
        this.selectedClips = new Set();
        this.pixelsPerSecond = 30; // 缩放级别
        this.currentTime = 0; // 当前播放头位置(秒)
        this.duration = 0; // 总时长
        this.isDragging = false;
        this.isResizing = false;
        this.isSelecting = false;
        this.dragType = null; // 'move', 'trim-left', 'trim-right'
        this.dragClip = null;
        this.dragStartX = 0;
        this.dragStartTime = 0;
        this.dragClipStartTime = 0;
        this.dragClipStartOffset = 0;
        this.dragClipStartDuration = 0;
        this.magnetEnabled = true;
        this.activeTool = 'select'; // 'select', 'razor'
        this.copiedClips = [];

        this.initElements();
        this.bindEvents();
        this.updateRuler();
    }

    initElements() {
        this.scrollContainer = document.getElementById('timeline-scroll');
        this.ruler = document.getElementById('timeline-ruler');
        this.tracksContainer = document.getElementById('timeline-tracks');
        this.playhead = document.getElementById('playhead');
        this.zoomSlider = document.getElementById('timeline-zoom');

        // 轨道
        this.trackV1 = document.getElementById('track-V1');
        this.trackA1 = document.getElementById('track-A1');
        this.trackT1 = document.getElementById('track-T1');
    }

    bindEvents() {
        // 缩放
        this.zoomSlider.addEventListener('input', (e) => {
            this.pixelsPerSecond = parseInt(e.target.value);
            this.updateRuler();
            this.renderClips();
        });

        document.getElementById('btn-zoom-in').addEventListener('click', () => {
            this.pixelsPerSecond = Math.min(100, this.pixelsPerSecond + 5);
            this.zoomSlider.value = this.pixelsPerSecond;
            this.updateRuler();
            this.renderClips();
        });

        document.getElementById('btn-zoom-out').addEventListener('click', () => {
            this.pixelsPerSecond = Math.max(5, this.pixelsPerSecond - 5);
            this.zoomSlider.value = this.pixelsPerSecond;
            this.updateRuler();
            this.renderClips();
        });

        // 点击刻度尺定位播放头
        this.ruler.addEventListener('mousedown', (e) => {
            this.onRulerClick(e);
        });

        // 点击轨道区域
        this.tracksContainer.addEventListener('mousedown', (e) => {
            const clip = e.target.closest('.clip');
            if (clip) {
                this.onClipMouseDown(e, clip);
            } else {
                this.onTrackClick(e);
            }
        });

        // 全局鼠标移动和释放
        document.addEventListener('mousemove', (e) => this.onMouseMove(e));
        document.addEventListener('mouseup', (e) => this.onMouseUp(e));

        // 时间线拖放（从媒体库）
        this.tracksContainer.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'copy';
        });

        this.tracksContainer.addEventListener('drop', (e) => {
            e.preventDefault();
            const mediaId = e.dataTransfer.getData('mediaId');
            if (mediaId) {
                const track = e.target.closest('.track');
                if (track) {
                    const rect = track.getBoundingClientRect();
                    const scrollLeft = this.scrollContainer.scrollLeft;
                    const x = e.clientX - rect.left + scrollLeft - 100; // 减去标签宽度
                    const time = Utils.pixelsToSeconds(Math.max(0, x), this.pixelsPerSecond);
                    this.addClipFromMedia(this.app.media.getMedia(mediaId), track.dataset.track, time);
                }
            }
        });

        // 工具按钮
        document.getElementById('btn-select').addEventListener('click', () => this.setTool('select'));
        document.getElementById('btn-razor').addEventListener('click', () => this.setTool('razor'));
        document.getElementById('btn-magnet').addEventListener('click', () => this.toggleMagnet());

        // 键盘快捷键
        document.addEventListener('keydown', (e) => this.onKeyDown(e));

        // 轨道控制按钮（静音/锁定）
        document.querySelectorAll('.track-ctrl-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const action = btn.dataset.action;
                btn.classList.toggle(action === 'mute' ? 'muted' : 'locked');
                const icon = btn.querySelector('i');
                if (action === 'mute') {
                    if (btn.classList.contains('muted')) {
                        icon.className = icon.className.replace('fa-eye', 'fa-eye-slash')
                            .replace('fa-volume-up', 'fa-volume-mute');
                    } else {
                        icon.className = icon.className.replace('fa-eye-slash', 'fa-eye')
                            .replace('fa-volume-mute', 'fa-volume-up');
                    }
                } else if (action === 'lock') {
                    if (btn.classList.contains('locked')) {
                        icon.className = 'fas fa-lock';
                    } else {
                        icon.className = 'fas fa-lock-open';
                    }
                }
            });
        });
    }

    /**
     * 设置活动工具
     */
    setTool(tool) {
        this.activeTool = tool;
        document.querySelectorAll('.tl-tool-btn').forEach(btn => btn.classList.remove('active'));
        const btnId = tool === 'select' ? 'btn-select' : tool === 'razor' ? 'btn-razor' : null;
        if (btnId) document.getElementById(btnId).classList.add('active');
    }

    /**
     * 切换磁吸
     */
    toggleMagnet() {
        this.magnetEnabled = !this.magnetEnabled;
        const btn = document.getElementById('btn-magnet');
        btn.classList.toggle('active', this.magnetEnabled);
        Utils.showToast(`磁吸${this.magnetEnabled ? '开启' : '关闭'}`, 'info');
    }

    /**
     * 更新时间刻度尺
     */
    updateRuler() {
        const totalWidth = Math.max(3000, this.duration * this.pixelsPerSecond + 500);
        this.ruler.style.width = totalWidth + 'px';

        // 清除旧标记
        this.ruler.querySelectorAll('.ruler-mark').forEach(el => el.remove());

        // 计算间隔
        let interval = 1;
        const minPixelInterval = 60;
        const intervals = [0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300];
        for (const i of intervals) {
            if (i * this.pixelsPerSecond >= minPixelInterval) {
                interval = i;
                break;
            }
        }

        const maxTime = totalWidth / this.pixelsPerSecond;
        for (let t = 0; t <= maxTime; t += interval) {
            const mark = document.createElement('div');
            const isMajor = t % (interval * 5) === 0 || interval >= 10;
            mark.className = `ruler-mark ${isMajor ? 'major' : ''}`;
            mark.style.left = (t * this.pixelsPerSecond) + 'px';

            if (isMajor || this.pixelsPerSecond >= 20) {
                const label = document.createElement('span');
                label.className = 'ruler-label';
                label.textContent = Utils.formatShortTime(t);
                mark.appendChild(label);
            }

            this.ruler.appendChild(mark);
        }

        // 更新轨道宽度
        document.querySelectorAll('.track').forEach(track => {
            track.style.width = totalWidth + 'px';
        });

        this.updatePlayheadPosition();
    }

    /**
     * 更新播放头位置
     */
    updatePlayheadPosition() {
        const x = this.currentTime * this.pixelsPerSecond;
        this.playhead.style.left = x + 'px';
    }

    /**
     * 设置当前时间
     */
    setCurrentTime(time) {
        this.currentTime = Math.max(0, time);
        this.updatePlayheadPosition();
        this.app.preview.updateTime(this.currentTime);
        document.getElementById('current-time').textContent = Utils.formatTime(this.currentTime);
    }

    /**
     * 刻度尺点击
     */
    onRulerClick(e) {
        const rect = this.ruler.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const time = Utils.pixelsToSeconds(x, this.pixelsPerSecond);
        this.setCurrentTime(time);

        // 支持拖拽播放头
        const onMove = (me) => {
            const nx = me.clientX - rect.left;
            this.setCurrentTime(Utils.pixelsToSeconds(Math.max(0, nx), this.pixelsPerSecond));
        };
        const onUp = () => {
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
        };
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
    }

    /**
     * 轨道空白处点击
     */
    onTrackClick(e) {
        if (this.activeTool === 'razor') return;

        // 取消选中
        this.selectedClips.clear();
        this.renderClipSelections();

        // 定位播放头
        const track = e.target.closest('.track');
        if (track) {
            const rect = track.getBoundingClientRect();
            const scrollLeft = this.scrollContainer.scrollLeft;
            const x = e.clientX - rect.left;
            const time = Utils.pixelsToSeconds(Math.max(0, x), this.pixelsPerSecond);
            this.setCurrentTime(time);
        }
    }

    /**
     * 片段鼠标按下
     */
    onClipMouseDown(e, clipEl) {
        e.stopPropagation();
        const clipId = clipEl.dataset.id;
        const clip = this.clips.find(c => c.id === clipId);
        if (!clip) return;

        // 剃刀工具 - 分割片段
        if (this.activeTool === 'razor') {
            const rect = clipEl.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const clickTime = Utils.pixelsToSeconds(x, this.pixelsPerSecond);
            this.splitClip(clipId, clip.startTime + clickTime);
            return;
        }

        // 选中片段
        if (!e.shiftKey) {
            this.selectedClips.clear();
        }
        this.selectedClips.add(clipId);
        this.renderClipSelections();

        // 更新属性面板
        this.app.properties.loadClipProperties(clip);

        // 判断拖拽类型
        const rect = clipEl.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const handleSize = 8;

        if (x <= handleSize) {
            this.dragType = 'trim-left';
        } else if (x >= rect.width - handleSize) {
            this.dragType = 'trim-right';
        } else {
            this.dragType = 'move';
        }

        this.isDragging = true;
        this.dragClip = clip;
        this.dragStartX = e.clientX;
        this.dragStartTime = this.currentTime;
        this.dragClipStartTime = clip.startTime;
        this.dragClipStartOffset = clip.offset || 0;
        this.dragClipStartDuration = clip.duration;
    }

    /**
     * 鼠标移动
     */
    onMouseMove(e) {
        if (!this.isDragging || !this.dragClip) return;

        const deltaX = e.clientX - this.dragStartX;
        const deltaTime = Utils.pixelsToSeconds(deltaX, this.pixelsPerSecond);
        const clip = this.dragClip;

        if (this.dragType === 'move') {
            clip.startTime = Math.max(0, this.dragClipStartTime + deltaTime);
            // 磁吸
            if (this.magnetEnabled) {
                clip.startTime = this.snapTime(clip.startTime);
            }
        } else if (this.dragType === 'trim-left') {
            const maxTrim = clip.duration - 0.1;
            const trimAmount = Math.min(maxTrim, Math.max(-this.dragClipStartOffset, deltaTime));
            clip.offset = Math.max(0, this.dragClipStartOffset + trimAmount);
            clip.startTime = this.dragClipStartTime + trimAmount;
            clip.duration = this.dragClipStartDuration - trimAmount;
        } else if (this.dragType === 'trim-right') {
            const minDuration = 0.1;
            clip.duration = Math.max(minDuration, this.dragClipStartDuration + deltaTime);
        }

        this.renderClips();
        this.updateDuration();
    }

    /**
     * 鼠标释放
     */
    onMouseUp(e) {
        if (this.isDragging) {
            this.isDragging = false;
            this.dragClip = null;
            this.app.history.saveState();
        }
    }

    /**
     * 磁吸对齐
     */
    snapTime(time, threshold = 0.3) {
        // 对齐到播放头
        if (Math.abs(time - this.currentTime) < threshold) {
            return this.currentTime;
        }

        // 对齐到其他片段的边界
        for (const clip of this.clips) {
            if (clip === this.dragClip) continue;
            if (Math.abs(time - clip.startTime) < threshold) return clip.startTime;
            if (Math.abs(time - (clip.startTime + clip.duration)) < threshold) {
                return clip.startTime + clip.duration;
            }
        }

        return time;
    }

    /**
     * 键盘事件
     */
    onKeyDown(e) {
        // Delete 删除选中片段
        if (e.key === 'Delete' || e.key === 'Backspace') {
            if (this.selectedClips.size > 0) {
                this.deleteSelectedClips();
                e.preventDefault();
            }
        }

        // S 分割
        if (e.key === 's' || e.key === 'S') {
            if (!e.ctrlKey && !e.metaKey) {
                if (this.selectedClips.size === 1) {
                    const clipId = [...this.selectedClips][0];
                    this.splitClip(clipId, this.currentTime);
                }
                e.preventDefault();
            }
        }

        // V 选择工具
        if (e.key === 'v' || e.key === 'V') {
            this.setTool('select');
        }

        // Space 播放/暂停
        if (e.key === ' ') {
            this.app.preview.togglePlay();
            e.preventDefault();
        }

        // 方向键微调
        if (e.key === 'ArrowLeft') {
            this.setCurrentTime(this.currentTime - (e.shiftKey ? 1 : 1/30));
            e.preventDefault();
        }
        if (e.key === 'ArrowRight') {
            this.setCurrentTime(this.currentTime + (e.shiftKey ? 1 : 1/30));
            e.preventDefault();
        }
    }

    /**
     * 从媒体项添加片段
     */
    addClipFromMedia(mediaItem, trackName = null, startTime = null) {
        if (!mediaItem) return;

        // 确定轨道
        if (!trackName) {
            if (mediaItem.type === 'video' || mediaItem.type === 'image') trackName = 'V1';
            else if (mediaItem.type === 'audio') trackName = 'A1';
        }

        // 确定起始时间
        if (startTime === null) {
            startTime = this.currentTime;
            // 如果当前时间已有片段，则追加到最后
            const trackClips = this.clips.filter(c => c.track === trackName);
            if (trackClips.length > 0) {
                const lastEnd = Math.max(...trackClips.map(c => c.startTime + c.duration));
                if (startTime < lastEnd) {
                    startTime = lastEnd;
                }
            }
        }

        const clip = {
            id: Utils.generateId(),
            mediaId: mediaItem.id,
            name: mediaItem.name,
            type: mediaItem.type,
            track: trackName,
            startTime: startTime,
            duration: mediaItem.duration || 5,
            offset: 0, // 源媒体内的偏移
            thumbnail: mediaItem.thumbnail,
            waveform: mediaItem.waveform,
            // 效果属性
            filters: {
                brightness: 100,
                contrast: 100,
                saturation: 100,
                blur: 0,
                hue: 0,
                opacity: 100
            },
            transform: {
                x: 0,
                y: 0,
                scale: 100,
                rotation: 0
            },
            speed: 1,
            volume: 100,
            text: null // 文字层配置
        };

        this.clips.push(clip);
        this.updateDuration();
        this.renderClips();
        this.app.history.saveState();
        this.app.updateOverlayVisibility();

        Utils.showToast(`已添加: ${mediaItem.name}`, 'success', 1500);
    }

    /**
     * 分割片段
     */
    splitClip(clipId, time) {
        const clip = this.clips.find(c => c.id === clipId);
        if (!clip) return;

        // 确保在片段范围内
        if (time <= clip.startTime || time >= clip.startTime + clip.duration) return;

        const splitPoint = time - clip.startTime;

        // 创建右半部分
        const newClip = Utils.deepClone(clip);
        newClip.id = Utils.generateId();
        newClip.startTime = time;
        newClip.duration = clip.duration - splitPoint;
        newClip.offset = clip.offset + splitPoint;

        // 修改左半部分
        clip.duration = splitPoint;

        this.clips.push(newClip);
        this.renderClips();
        this.app.history.saveState();

        Utils.showToast('片段已分割', 'info', 1500);
    }

    /**
     * 删除选中片段
     */
    deleteSelectedClips() {
        if (this.selectedClips.size === 0) return;

        this.clips = this.clips.filter(c => !this.selectedClips.has(c.id));
        this.selectedClips.clear();
        this.updateDuration();
        this.renderClips();
        this.app.history.saveState();
        this.app.updateOverlayVisibility();

        Utils.showToast('已删除片段', 'info', 1500);
    }

    /**
     * 复制选中片段
     */
    copySelectedClips() {
        this.copiedClips = this.clips
            .filter(c => this.selectedClips.has(c.id))
            .map(c => Utils.deepClone(c));
        Utils.showToast('已复制片段', 'info', 1500);
    }

    /**
     * 粘贴片段
     */
    pasteClips() {
        if (!this.copiedClips || this.copiedClips.length === 0) return;

        this.copiedClips.forEach(clip => {
            clip.id = Utils.generateId();
            clip.startTime = this.currentTime;
            this.clips.push(Utils.deepClone(clip));
        });

        this.updateDuration();
        this.renderClips();
        this.app.history.saveState();
        Utils.showToast('已粘贴片段', 'info', 1500);
    }

    /**
     * 更新总时长
     */
    updateDuration() {
        if (this.clips.length === 0) {
            this.duration = 0;
        } else {
            this.duration = Math.max(...this.clips.map(c => c.startTime + c.duration));
        }
        document.getElementById('total-time').textContent = Utils.formatTime(this.duration);
        this.updateRuler();
    }

    /**
     * 渲染所有片段
     */
    renderClips() {
        // 清除所有轨道中的片段
        this.trackV1.querySelectorAll('.clip').forEach(el => el.remove());
        this.trackA1.querySelectorAll('.clip').forEach(el => el.remove());
        this.trackT1.querySelectorAll('.clip').forEach(el => el.remove());

        this.clips.forEach(clip => {
            this.renderClip(clip);
        });
    }

    /**
     * 渲染单个片段
     */
    renderClip(clip) {
        const trackEl = this.getTrackElement(clip.track);
        if (!trackEl) return;

        const el = document.createElement('div');
        el.className = `clip clip-${clip.type === 'image' ? 'video' : clip.type}`;
        el.dataset.id = clip.id;

        const left = clip.startTime * this.pixelsPerSecond;
        const width = clip.duration * this.pixelsPerSecond;
        el.style.left = left + 'px';
        el.style.width = Math.max(4, width) + 'px';

        // 缩略图
        let thumbHtml = '';
        if (clip.thumbnail && (clip.type === 'video' || clip.type === 'image')) {
            thumbHtml = `<div class="clip-thumbnail"><img src="${clip.thumbnail}" alt=""></div>`;
        }

        // 音频波形
        let waveformHtml = '';
        if (clip.type === 'audio' && clip.waveform && clip.waveform.length > 0) {
            waveformHtml = `<canvas class="clip-waveform" data-clip-id="${clip.id}"></canvas>`;
        }

        el.innerHTML = `
            <div class="clip-handle clip-handle-left"></div>
            <div class="clip-handle clip-handle-right"></div>
            ${thumbHtml}
            <div class="clip-info">
                <div class="clip-name">${clip.name}</div>
                <div class="clip-duration">${Utils.formatShortTime(clip.duration)}</div>
            </div>
            ${waveformHtml}
        `;

        // 选中状态
        if (this.selectedClips.has(clip.id)) {
            el.classList.add('selected');
        }

        // 右键菜单
        el.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            e.stopPropagation();
            this.selectedClips.clear();
            this.selectedClips.add(clip.id);
            this.renderClipSelections();

            Utils.showContextMenu(e.clientX, e.clientY, [
                { label: '分割', icon: 'fas fa-cut', action: 'split', shortcut: 'S',
                  callback: () => this.splitClip(clip.id, this.currentTime) },
                'divider',
                { label: '复制', icon: 'fas fa-copy', action: 'copy', shortcut: 'Ctrl+C',
                  callback: () => this.copySelectedClips() },
                { label: '删除', icon: 'fas fa-trash', action: 'delete', shortcut: 'Del',
                  callback: () => this.deleteSelectedClips() },
                'divider',
                { label: '属性', icon: 'fas fa-sliders-h', action: 'props',
                  callback: () => this.app.properties.loadClipProperties(clip) }
            ]);
        });

        trackEl.appendChild(el);

        // 绘制音频波形
        if (clip.type === 'audio' && clip.waveform) {
            this.drawWaveform(el.querySelector('.clip-waveform'), clip.waveform);
        }
    }

    /**
     * 绘制音频波形
     */
    drawWaveform(canvas, waveform) {
        if (!canvas || !waveform || waveform.length === 0) return;

        requestAnimationFrame(() => {
            const rect = canvas.parentElement.getBoundingClientRect();
            canvas.width = rect.width;
            canvas.height = rect.height;

            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            const barWidth = canvas.width / waveform.length;
            const maxAmp = Math.max(...waveform);

            ctx.fillStyle = 'rgba(255,255,255,0.6)';
            for (let i = 0; i < waveform.length; i++) {
                const amp = waveform[i] / maxAmp;
                const barHeight = amp * canvas.height * 0.8;
                const y = (canvas.height - barHeight) / 2;
                ctx.fillRect(i * barWidth, y, Math.max(1, barWidth - 1), barHeight);
            }
        });
    }

    /**
     * 渲染片段选中状态
     */
    renderClipSelections() {
        document.querySelectorAll('.clip').forEach(el => {
            el.classList.toggle('selected', this.selectedClips.has(el.dataset.id));
        });
    }

    /**
     * 获取轨道元素
     */
    getTrackElement(trackName) {
        const map = { 'V1': this.trackV1, 'A1': this.trackA1, 'T1': this.trackT1 };
        return map[trackName];
    }

    /**
     * 获取当前时间处的片段
     */
    getClipsAtTime(time) {
        return this.clips.filter(c =>
            time >= c.startTime && time < c.startTime + c.duration
        );
    }

    /**
     * 获取指定轨道在指定时间的片段
     */
    getClipAtTime(track, time) {
        return this.clips.find(c =>
            c.track === track && time >= c.startTime && time < c.startTime + c.duration
        );
    }

    /**
     * 获取序列化的片段数据（用于历史记录）
     */
    getState() {
        return Utils.deepClone(this.clips);
    }

    /**
     * 恢复状态
     */
    restoreState(state) {
        this.clips = Utils.deepClone(state);
        this.selectedClips.clear();
        this.updateDuration();
        this.renderClips();
    }
}
