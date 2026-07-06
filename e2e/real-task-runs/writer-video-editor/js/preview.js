/**
 * VideoForge - 预览模块
 */

class Preview {
    constructor(app) {
        this.app = app;
        this.canvas = document.getElementById('preview-canvas');
        this.ctx = this.canvas.getContext('2d');
        this.isPlaying = false;
        this.animationFrame = null;
        this.volume = 1;
        this.currentMediaElements = new Map(); // clipId -> { video/audio element }

        this.initElements();
        this.bindEvents();
        this.resizeCanvas();
    }

    initElements() {
        this.playBtn = document.getElementById('btn-play');
        this.skipBackBtn = document.getElementById('btn-skip-back');
        this.skipForwardBtn = document.getElementById('btn-skip-forward');
        this.frameBackBtn = document.getElementById('btn-frame-back');
        this.frameForwardBtn = document.getElementById('btn-frame-forward');
        this.volumeBtn = document.getElementById('btn-volume');
        this.volumeSlider = document.getElementById('volume-slider');
        this.overlay = document.getElementById('preview-overlay');
        this.currentTimeEl = document.getElementById('current-time');
    }

    bindEvents() {
        // 播放/暂停
        this.playBtn.addEventListener('click', () => this.togglePlay());
        this.overlay.addEventListener('click', () => this.togglePlay());

        // 跳转
        this.skipBackBtn.addEventListener('click', () => {
            this.app.timeline.setCurrentTime(this.app.timeline.currentTime - 5);
        });

        this.skipForwardBtn.addEventListener('click', () => {
            this.app.timeline.setCurrentTime(this.app.timeline.currentTime + 5);
        });

        // 逐帧
        this.frameBackBtn.addEventListener('click', () => {
            this.app.timeline.setCurrentTime(this.app.timeline.currentTime - 1/30);
        });

        this.frameForwardBtn.addEventListener('click', () => {
            this.app.timeline.setCurrentTime(this.app.timeline.currentTime + 1/30);
        });

        // 音量
        this.volumeSlider.addEventListener('input', (e) => {
            this.volume = parseInt(e.target.value) / 100;
            this.updateVolumeIcon();
            this.updateMediaVolume();
        });

        this.volumeBtn.addEventListener('click', () => {
            if (this.volume > 0) {
                this._prevVolume = this.volume;
                this.volume = 0;
            } else {
                this.volume = this._prevVolume || 1;
            }
            this.volumeSlider.value = this.volume * 100;
            this.updateVolumeIcon();
            this.updateMediaVolume();
        });

        // 窗口缩放
        window.addEventListener('resize', () => this.resizeCanvas());

        // Canvas 点击暂停/播放
        this.canvas.addEventListener('click', () => this.togglePlay());
    }

    /**
     * 调整画布大小
     */
    resizeCanvas() {
        const wrapper = this.canvas.parentElement;
        const w = wrapper.clientWidth;
        const h = wrapper.clientHeight;
        this.canvas.width = w;
        this.canvas.height = h;
        this.renderFrame();
    }

    /**
     * 渲染欢迎画面
     */
    renderWelcomeScreen() {
        const ctx = this.ctx;
        const w = this.canvas.width;
        const h = this.canvas.height;

        ctx.fillStyle = '#0a0a1a';
        ctx.fillRect(0, 0, w, h);

        // 渐变背景
        const gradient = ctx.createRadialGradient(w/2, h/2, 0, w/2, h/2, Math.max(w, h) * 0.5);
        gradient.addColorStop(0, 'rgba(233, 69, 96, 0.15)');
        gradient.addColorStop(1, 'rgba(0, 0, 0, 0)');
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, w, h);

        // 绘制胶片图标（使用基本图形）
        const cx = w/2;
        const cy = h/2 - 30;
        const iconSize = 40;

        // 胶片框
        ctx.strokeStyle = 'rgba(233, 69, 96, 0.5)';
        ctx.lineWidth = 2;
        ctx.strokeRect(cx - iconSize, cy - iconSize * 0.7, iconSize * 2, iconSize * 1.4);

        // 胶片孔
        const holeSize = 6;
        for (let i = 0; i < 3; i++) {
            const hy = cy - iconSize * 0.5 + i * iconSize * 0.5;
            ctx.strokeRect(cx - iconSize + 4, hy, holeSize, holeSize);
            ctx.strokeRect(cx + iconSize - 4 - holeSize, hy, holeSize, holeSize);
        }

        // 播放三角形
        ctx.fillStyle = 'rgba(233, 69, 96, 0.5)';
        ctx.beginPath();
        ctx.moveTo(cx - 12, cy - 15);
        ctx.lineTo(cx - 12, cy + 15);
        ctx.lineTo(cx + 15, cy);
        ctx.closePath();
        ctx.fill();

        // 文字
        ctx.font = '600 20px Inter, sans-serif';
        ctx.fillStyle = 'rgba(255, 255, 255, 0.5)';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('VideoForge', cx, cy + 55);

        ctx.font = '400 13px Inter, sans-serif';
        ctx.fillStyle = 'rgba(255, 255, 255, 0.25)';
        ctx.fillText('导入媒体文件开始创作', cx, cy + 80);

        // 底部装饰线
        ctx.strokeStyle = 'rgba(233, 69, 96, 0.2)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(cx - 80, cy + 100);
        ctx.lineTo(cx + 80, cy + 100);
        ctx.stroke();
    }

    /**
     * 播放/暂停切换
     */
    togglePlay() {
        if (this.isPlaying) {
            this.pause();
        } else {
            this.play();
        }
    }

    /**
     * 播放
     */
    play() {
        if (this.app.timeline.clips.length === 0) {
            Utils.showToast('请先添加媒体到时间线', 'warning');
            return;
        }

        this.isPlaying = true;
        this.playBtn.innerHTML = '<i class="fas fa-pause"></i>';
        this.overlay.style.display = 'none';

        this.lastFrameTime = performance.now();
        this.playbackLoop();
    }

    /**
     * 暂停
     */
    pause() {
        this.isPlaying = false;
        this.playBtn.innerHTML = '<i class="fas fa-play"></i>';

        if (this.animationFrame) {
            cancelAnimationFrame(this.animationFrame);
            this.animationFrame = null;
        }

        // 暂停所有媒体元素
        this.currentMediaElements.forEach(el => {
            if (el.video) el.video.pause();
            if (el.audio) el.audio.pause();
        });
    }

    /**
     * 播放循环
     */
    playbackLoop() {
        if (!this.isPlaying) return;

        const now = performance.now();
        const delta = (now - this.lastFrameTime) / 1000;
        this.lastFrameTime = now;

        const timeline = this.app.timeline;
        const newTime = timeline.currentTime + delta;

        // 检查是否到达末尾
        if (newTime >= timeline.duration) {
            this.pause();
            timeline.setCurrentTime(0);
            return;
        }

        timeline.setCurrentTime(newTime);
        this.renderFrame();
        this.syncMediaPlayback();

        this.animationFrame = requestAnimationFrame(() => this.playbackLoop());
    }

    /**
     * 渲染当前帧
     */
    renderFrame() {
        const ctx = this.ctx;
        const w = this.canvas.width;
        const h = this.canvas.height;
        const time = this.app.timeline.currentTime;

        // 清除画布
        ctx.fillStyle = '#000';
        ctx.fillRect(0, 0, w, h);

        // 获取当前时间的片段
        const clips = this.app.timeline.getClipsAtTime(time);

        // 如果没有片段，显示欢迎画面
        if (clips.length === 0) {
            this.renderWelcomeScreen();
            return;
        }

        // 按轨道顺序渲染
        const trackOrder = ['V1', 'A1', 'T1'];

        trackOrder.forEach(trackName => {
            const clip = clips.find(c => c.track === trackName);
            if (!clip) return;

            const mediaItem = this.app.media.getMedia(clip.mediaId);
            if (!mediaItem) return;

            if (clip.type === 'video' || clip.type === 'image') {
                this.renderVideoClip(ctx, clip, mediaItem, w, h, time);
            } else if (clip.type === 'text') {
                this.renderTextClip(ctx, clip, w, h);
            }
            // 音频不需要视觉渲染
        });
    }

    /**
     * 渲染视频片段
     */
    renderVideoClip(ctx, clip, mediaItem, canvasW, canvasH, time) {
        let source = null;

        if (clip.type === 'video') {
            // 获取或创建视频元素
            if (!this.currentMediaElements.has(clip.id)) {
                const video = document.createElement('video');
                video.src = mediaItem.url;
                video.muted = true; // 预览时静音视频，音频由单独轨道处理
                video.preload = 'auto';
                video.playsInline = true;
                this.currentMediaElements.set(clip.id, { video });
            }

            const el = this.currentMediaElements.get(clip.id);
            source = el.video;

            // 计算视频内的时间
            const clipTime = (time - clip.startTime) * clip.speed + clip.offset;
            if (Math.abs(source.currentTime - clipTime) > 0.1) {
                source.currentTime = clipTime;
            }
        } else if (clip.type === 'image') {
            // 静态图片
            if (!this.currentMediaElements.has(clip.id)) {
                const img = new Image();
                img.src = mediaItem.url;
                this.currentMediaElements.set(clip.id, { image: img });
            }
            const el = this.currentMediaElements.get(clip.id);
            source = el.image;
        }

        if (!source) return;

        // 应用变换
        ctx.save();

        const transform = clip.transform || {};
        const offsetX = (transform.x || 0) * canvasW / 100;
        const offsetY = (transform.y || 0) * canvasH / 100;
        const scale = (transform.scale || 100) / 100;
        const rotation = (transform.rotation || 0) * Math.PI / 180;

        // 应用滤镜
        const filters = clip.filters || {};
        const filterStr = this.buildFilterString(filters);
        if (filterStr) ctx.filter = filterStr;

        // 应用透明度
        ctx.globalAlpha = (filters.opacity || 100) / 100;

        // 计算绘制区域（适应画布）
        let drawW, drawH, drawX, drawY;
        const sourceW = source.videoWidth || source.naturalWidth || mediaItem.width || canvasW;
        const sourceH = source.videoHeight || source.naturalHeight || mediaItem.height || canvasH;
        const aspectRatio = sourceW / sourceH;
        const canvasAspect = canvasW / canvasH;

        if (aspectRatio > canvasAspect) {
            drawW = canvasW * scale;
            drawH = drawW / aspectRatio;
        } else {
            drawH = canvasH * scale;
            drawW = drawH * aspectRatio;
        }

        drawX = (canvasW - drawW) / 2 + offsetX;
        drawY = (canvasH - drawH) / 2 + offsetY;

        // 旋转
        ctx.translate(drawX + drawW / 2, drawY + drawH / 2);
        ctx.rotate(rotation);
        ctx.translate(-(drawX + drawW / 2), -(drawY + drawH / 2));

        try {
            ctx.drawImage(source, drawX, drawY, drawW, drawH);
        } catch(e) {
            // 视频可能还没加载完成
        }

        ctx.restore();
    }

    /**
     * 渲染文字片段
     */
    renderTextClip(ctx, clip, canvasW, canvasH) {
        if (!clip.text) return;

        ctx.save();

        const text = clip.text;
        const fontSize = text.fontSize || 32;
        const fontFamily = text.fontFamily || 'Inter';
        const fontWeight = text.fontWeight || 700;
        const color = text.color || '#ffffff';
        const strokeColor = text.strokeColor || '#000000';
        const strokeWidth = text.strokeWidth || 2;
        const bgColor = text.bgColor || '#000000';
        const bgOpacity = (text.bgOpacity || 0) / 100;

        // 位置
        const x = canvasW / 2 + (text.x || 0);
        const y = canvasH / 2 + (text.y || 0);

        ctx.font = `${fontWeight} ${fontSize}px "${fontFamily}"`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';

        // 背景
        if (bgOpacity > 0) {
            const metrics = ctx.measureText(text.content || '');
            const padding = fontSize * 0.3;
            ctx.fillStyle = bgColor;
            ctx.globalAlpha = bgOpacity;
            ctx.fillRect(
                x - metrics.width / 2 - padding,
                y - fontSize / 2 - padding,
                metrics.width + padding * 2,
                fontSize + padding * 2
            );
            ctx.globalAlpha = 1;
        }

        // 描边
        if (strokeWidth > 0) {
            ctx.strokeStyle = strokeColor;
            ctx.lineWidth = strokeWidth;
            ctx.lineJoin = 'round';
            ctx.strokeText(text.content || '', x, y);
        }

        // 填充
        ctx.fillStyle = color;
        ctx.fillText(text.content || '', x, y);

        ctx.restore();
    }

    /**
     * 构建滤镜字符串
     */
    buildFilterString(filters) {
        const parts = [];
        if (filters.brightness && filters.brightness !== 100) {
            parts.push(`brightness(${filters.brightness}%)`);
        }
        if (filters.contrast && filters.contrast !== 100) {
            parts.push(`contrast(${filters.contrast}%)`);
        }
        if (filters.saturation && filters.saturation !== 100) {
            parts.push(`saturate(${filters.saturation}%)`);
        }
        if (filters.blur && filters.blur > 0) {
            parts.push(`blur(${filters.blur}px)`);
        }
        if (filters.hue && filters.hue > 0) {
            parts.push(`hue-rotate(${filters.hue}deg)`);
        }
        return parts.join(' ');
    }

    /**
     * 同步媒体播放
     */
    syncMediaPlayback() {
        const time = this.app.timeline.currentTime;

        this.currentMediaElements.forEach((el, clipId) => {
            const clip = this.app.timeline.clips.find(c => c.id === clipId);
            if (!clip) return;

            const clipTime = time - clip.startTime;
            const inRange = clipTime >= 0 && clipTime < clip.duration;

            if (el.video) {
                if (this.isPlaying && inRange) {
                    if (el.video.paused) {
                        el.video.play().catch(() => {});
                    }
                    const targetTime = clipTime * clip.speed + clip.offset;
                    if (Math.abs(el.video.currentTime - targetTime) > 0.3) {
                        el.video.currentTime = targetTime;
                    }
                } else {
                    if (!el.video.paused) el.video.pause();
                }
            }

            if (el.audio) {
                if (this.isPlaying && inRange) {
                    if (el.audio.paused) {
                        el.audio.play().catch(() => {});
                    }
                    const targetTime = clipTime * clip.speed + clip.offset;
                    if (Math.abs(el.audio.currentTime - targetTime) > 0.3) {
                        el.audio.currentTime = targetTime;
                    }
                } else {
                    if (!el.audio.paused) el.audio.pause();
                }
            }
        });
    }

    /**
     * 更新时间（由时间线调用）
     */
    updateTime(time) {
        this.renderFrame();
    }

    /**
     * 加载媒体到预览
     */
    loadMedia(mediaItem) {
        if (!mediaItem) return;

        this.pause();
        const ctx = this.ctx;
        const w = this.canvas.width;
        const h = this.canvas.height;

        ctx.fillStyle = '#000';
        ctx.fillRect(0, 0, w, h);

        if (mediaItem.type === 'video') {
            const video = document.createElement('video');
            video.src = mediaItem.url;
            video.muted = true;
            video.onloadeddata = () => {
                const aspect = video.videoWidth / video.videoHeight;
                let dw, dh;
                if (aspect > w / h) {
                    dw = w;
                    dh = w / aspect;
                } else {
                    dh = h;
                    dw = h * aspect;
                }
                ctx.drawImage(video, (w - dw) / 2, (h - dh) / 2, dw, dh);
            };
        } else if (mediaItem.type === 'image') {
            const img = new Image();
            img.onload = () => {
                const aspect = img.width / img.height;
                let dw, dh;
                if (aspect > w / h) {
                    dw = w;
                    dh = w / aspect;
                } else {
                    dh = h;
                    dw = h * aspect;
                }
                ctx.drawImage(img, (w - dw) / 2, (h - dh) / 2, dw, dh);
            };
            img.src = mediaItem.url;
        }
    }

    /**
     * 更新音量图标
     */
    updateVolumeIcon() {
        const icon = this.volumeBtn.querySelector('i');
        if (this.volume === 0) {
            icon.className = 'fas fa-volume-mute';
        } else if (this.volume < 0.5) {
            icon.className = 'fas fa-volume-down';
        } else {
            icon.className = 'fas fa-volume-up';
        }
    }

    /**
     * 更新媒体音量
     */
    updateMediaVolume() {
        this.currentMediaElements.forEach(el => {
            if (el.audio) el.audio.volume = this.volume;
            if (el.video) el.video.volume = this.volume;
        });
    }

    /**
     * 清除缓存
     */
    clearCache() {
        this.currentMediaElements.forEach(el => {
            if (el.video) { el.video.pause(); el.video.src = ''; }
            if (el.audio) { el.audio.pause(); el.audio.src = ''; }
            if (el.image) el.image.src = '';
        });
        this.currentMediaElements.clear();
    }
}
