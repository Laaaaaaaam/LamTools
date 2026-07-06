/**
 * VideoForge - 导出模块
 */

class Export {
    constructor(app) {
        this.app = app;
        this.isExporting = false;

        this.initElements();
        this.bindEvents();
    }

    initElements() {
        this.modal = document.getElementById('export-modal');
        this.formatSelect = document.getElementById('export-format');
        this.resolutionSelect = document.getElementById('export-resolution');
        this.fpsSelect = document.getElementById('export-fps');
        this.qualitySlider = document.getElementById('export-quality');
        this.qualityValue = document.getElementById('quality-value');
        this.progressDiv = document.getElementById('export-progress');
        this.progressFill = document.getElementById('progress-fill');
        this.progressText = document.getElementById('progress-text');
        this.progressPercent = document.getElementById('progress-percent');
        this.startBtn = document.getElementById('btn-export-start');
        this.cancelBtn = document.getElementById('btn-export-cancel');
        this.closeBtn = document.getElementById('modal-close');
    }

    bindEvents() {
        // 打开导出模态框
        document.getElementById('btn-export').addEventListener('click', () => this.showModal());

        // 关闭
        this.closeBtn.addEventListener('click', () => this.hideModal());
        this.cancelBtn.addEventListener('click', () => {
            if (this.isExporting) this.cancelExport();
            else this.hideModal();
        });

        // 质量滑块
        this.qualitySlider.addEventListener('input', () => {
            this.qualityValue.textContent = this.qualitySlider.value + '%';
        });

        // 开始导出
        this.startBtn.addEventListener('click', () => this.startExport());

        // 点击模态框外部关闭
        this.modal.addEventListener('click', (e) => {
            if (e.target === this.modal) this.hideModal();
        });
    }

    /**
     * 显示导出模态框
     */
    showModal() {
        if (this.app.timeline.clips.length === 0) {
            Utils.showToast('时间线上没有内容可导出', 'warning');
            return;
        }
        this.modal.classList.add('show');
        this.progressDiv.style.display = 'none';
        this.startBtn.disabled = false;
    }

    /**
     * 隐藏模态框
     */
    hideModal() {
        this.modal.classList.remove('show');
    }

    /**
     * 开始导出
     */
    async startExport() {
        if (this.isExporting) return;

        this.isExporting = true;
        this.startBtn.disabled = true;
        this.progressDiv.style.display = 'block';
        this.progressText.textContent = '正在准备导出...';
        this.progressFill.style.width = '0%';
        this.progressPercent.textContent = '0%';

        try {
            const format = this.formatSelect.value;
            const [width, height] = this.resolutionSelect.value.split('x').map(Number);
            const fps = parseInt(this.fpsSelect.value);
            const quality = parseInt(this.qualitySlider.value) / 100;

            // 创建离屏 Canvas
            const offscreenCanvas = document.createElement('canvas');
            offscreenCanvas.width = width;
            offscreenCanvas.height = height;
            const ctx = offscreenCanvas.getContext('2d');

            // 确定 MIME 类型和编码
            let mimeType, fileExt;
            if (format === 'webm') {
                mimeType = 'video/webm;codecs=vp9';
                if (!MediaRecorder.isTypeSupported(mimeType)) {
                    mimeType = 'video/webm;codecs=vp8';
                }
                if (!MediaRecorder.isTypeSupported(mimeType)) {
                    mimeType = 'video/webm';
                }
                fileExt = 'webm';
            } else {
                mimeType = 'video/webm'; // 大多数浏览器不支持 mp4 录制
                fileExt = 'webm';
                Utils.showToast('当前浏览器仅支持 WebM 格式导出', 'info');
            }

            // 设置 MediaRecorder
            const stream = offscreenCanvas.captureStream(fps);
            const mediaRecorder = new MediaRecorder(stream, {
                mimeType: mimeType,
                videoBitsPerSecond: quality * 8000000 // 基于质量的比特率
            });

            const chunks = [];
            mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) chunks.push(e.data);
            };

            mediaRecorder.onstop = () => {
                const blob = new Blob(chunks, { type: mimeType });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `VideoForge_Export_${Date.now()}.${fileExt}`;
                a.click();
                URL.revokeObjectURL(url);

                this.isExporting = false;
                this.progressText.textContent = '导出完成！';
                this.progressFill.style.width = '100%';
                this.progressPercent.textContent = '100%';
                this.startBtn.disabled = false;

                Utils.showToast('视频导出成功！', 'success');

                setTimeout(() => this.hideModal(), 2000);
            };

            mediaRecorder.start(100); // 每100ms收集一次数据

            // 渲染每一帧
            const timeline = this.app.timeline;
            const totalDuration = timeline.duration;
            const totalFrames = Math.ceil(totalDuration * fps);
            const frameDuration = 1 / fps;

            // 预加载所有视频元素
            const videoElements = new Map();
            for (const clip of timeline.clips) {
                if (clip.type === 'video') {
                    const mediaItem = this.app.media.getMedia(clip.mediaId);
                    if (mediaItem) {
                        const video = document.createElement('video');
                        video.src = mediaItem.url;
                        video.muted = true;
                        video.preload = 'auto';
                        video.playsInline = true;
                        await new Promise(resolve => {
                            video.onloadeddata = resolve;
                            video.onerror = resolve;
                        });
                        videoElements.set(clip.id, video);
                    }
                }
            }

            this.progressText.textContent = '正在渲染帧...';

            let currentFrame = 0;

            const renderNextFrame = () => {
                if (!this.isExporting || currentFrame >= totalFrames) {
                    mediaRecorder.stop();
                    // 清理
                    videoElements.forEach(v => { v.pause(); v.src = ''; });
                    return;
                }

                const time = currentFrame * frameDuration;

                // 清除画布
                ctx.fillStyle = '#000';
                ctx.fillRect(0, 0, width, height);

                // 渲染当前时间的所有片段
                const clips = timeline.getClipsAtTime(time);
                const trackOrder = ['V1', 'T1'];

                trackOrder.forEach(trackName => {
                    const clip = clips.find(c => c.track === trackName);
                    if (!clip) return;

                    if (clip.type === 'video' || clip.type === 'image') {
                        const mediaItem = this.app.media.getMedia(clip.mediaId);
                        if (!mediaItem) return;

                        const source = clip.type === 'video'
                            ? videoElements.get(clip.id)
                            : (() => {
                                const img = new Image();
                                img.src = mediaItem.url;
                                return img;
                            })();

                        if (!source) return;

                        // 计算源时间
                        if (clip.type === 'video') {
                            const clipTime = (time - clip.startTime) * clip.speed + clip.offset;
                            source.currentTime = clipTime;
                        }

                        // 应用滤镜和变换
                        ctx.save();
                        const filters = clip.filters || {};
                        const filterStr = this.app.preview.buildFilterString(filters);
                        if (filterStr) ctx.filter = filterStr;
                        ctx.globalAlpha = (filters.opacity || 100) / 100;

                        // 适应画布
                        const sourceW = source.videoWidth || source.naturalWidth || width;
                        const sourceH = source.videoHeight || source.naturalHeight || height;
                        const aspect = sourceW / sourceH;
                        const canvasAspect = width / height;
                        let dw, dh;
                        if (aspect > canvasAspect) {
                            dw = width;
                            dh = width / aspect;
                        } else {
                            dh = height;
                            dw = height * aspect;
                        }

                        const transform = clip.transform || {};
                        const scale = (transform.scale || 100) / 100;
                        dw *= scale;
                        dh *= scale;
                        const dx = (width - dw) / 2 + (transform.x || 0) * width / 100;
                        const dy = (height - dh) / 2 + (transform.y || 0) * height / 100;

                        const rotation = (transform.rotation || 0) * Math.PI / 180;
                        if (rotation) {
                            ctx.translate(dx + dw / 2, dy + dh / 2);
                            ctx.rotate(rotation);
                            ctx.translate(-(dx + dw / 2), -(dy + dh / 2));
                        }

                        try {
                            ctx.drawImage(source, dx, dy, dw, dh);
                        } catch(e) {}

                        ctx.restore();
                    } else if (clip.type === 'text' && clip.text) {
                        this.app.preview.renderTextClip(ctx, clip, width, height);
                    }
                });

                // 更新进度
                currentFrame++;
                const progress = (currentFrame / totalFrames) * 100;
                this.progressFill.style.width = progress + '%';
                this.progressPercent.textContent = Math.floor(progress) + '%';
                this.progressText.textContent = `正在渲染帧 ${currentFrame}/${totalFrames}`;

                // 使用 setTimeout 让 UI 更新
                setTimeout(renderNextFrame, 0);
            };

            // 等待视频元素就绪
            await new Promise(resolve => setTimeout(resolve, 500));

            renderNextFrame();

        } catch (error) {
            console.error('导出失败:', error);
            this.isExporting = false;
            this.startBtn.disabled = false;
            this.progressText.textContent = '导出失败: ' + error.message;
            Utils.showToast('导出失败: ' + error.message, 'error');
        }
    }

    /**
     * 取消导出
     */
    cancelExport() {
        this.isExporting = false;
        this.progressText.textContent = '导出已取消';
        Utils.showToast('导出已取消', 'info');
        this.hideModal();
    }
}
