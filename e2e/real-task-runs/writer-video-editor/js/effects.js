/**
 * VideoForge - 特效与转场模块
 */

class Effects {
    constructor(app) {
        this.app = app;
        this.transitions = new Map(); // 存储转场配置

        this.bindEvents();
    }

    bindEvents() {
        // 转场项点击
        document.querySelectorAll('.transition-item').forEach(item => {
            item.addEventListener('click', () => {
                this.applyTransition(item.dataset.transition);
            });
        });
    }

    /**
     * 应用转场
     */
    applyTransition(type) {
        if (!this.app.timeline.currentClip) {
            Utils.showToast('请先选中一个片段', 'warning');
            return;
        }

        const clip = this.app.timeline.currentClip;
        const transitionDuration = 0.5; // 转场时长

        this.transitions.set(clip.id, {
            type: type,
            duration: transitionDuration
        });

        Utils.showToast(`已添加转场: ${type}`, 'success', 1500);
    }

    /**
     * 渲染转场效果
     */
    renderTransition(ctx, fromClip, toClip, progress, canvasW, canvasH, time) {
        const transition = this.transitions.get(toClip?.id);
        if (!transition) return;

        const type = transition.type;

        switch (type) {
            case 'fade':
                this.renderFadeTransition(ctx, fromClip, toClip, progress, canvasW, canvasH, time);
                break;
            case 'dissolve':
                this.renderDissolveTransition(ctx, fromClip, toClip, progress, canvasW, canvasH, time);
                break;
            case 'wipe-left':
                this.renderWipeTransition(ctx, fromClip, toClip, progress, canvasW, canvasH, time, 'left');
                break;
            case 'wipe-right':
                this.renderWipeTransition(ctx, fromClip, toClip, progress, canvasW, canvasH, time, 'right');
                break;
            case 'wipe-up':
                this.renderWipeTransition(ctx, fromClip, toClip, progress, canvasW, canvasH, time, 'up');
                break;
            case 'wipe-down':
                this.renderWipeTransition(ctx, fromClip, toClip, progress, canvasW, canvasH, time, 'down');
                break;
        }
    }

    /**
     * 淡入淡出转场
     */
    renderFadeTransition(ctx, fromClip, toClip, progress, canvasW, canvasH, time) {
        // 先渲染前一帧
        if (fromClip) {
            ctx.globalAlpha = 1 - progress;
            this.app.preview.renderVideoClip(ctx, fromClip, this.app.media.getMedia(fromClip.mediaId), canvasW, canvasH, time);
        }
        // 再渲染后一帧
        if (toClip) {
            ctx.globalAlpha = progress;
            this.app.preview.renderVideoClip(ctx, toClip, this.app.media.getMedia(toClip.mediaId), canvasW, canvasH, time);
        }
        ctx.globalAlpha = 1;
    }

    /**
     * 溶解转场
     */
    renderDissolveTransition(ctx, fromClip, toClip, progress, canvasW, canvasH, time) {
        // 简化版：类似淡入淡出但带有噪点效果
        this.renderFadeTransition(ctx, fromClip, toClip, progress, canvasW, canvasH, time);

        // 添加噪点
        const imageData = ctx.getImageData(0, 0, canvasW, canvasH);
        const data = imageData.data;
        const intensity = Math.sin(progress * Math.PI) * 30; // 中间最强
        for (let i = 0; i < data.length; i += 4) {
            const noise = (Math.random() - 0.5) * intensity;
            data[i] += noise;
            data[i+1] += noise;
            data[i+2] += noise;
        }
        ctx.putImageData(imageData, 0, 0);
    }

    /**
     * 擦除转场
     */
    renderWipeTransition(ctx, fromClip, toClip, progress, canvasW, canvasH, time, direction) {
        // 渲染前一帧
        if (fromClip) {
            ctx.save();
            ctx.globalAlpha = 1;
            this.app.preview.renderVideoClip(ctx, fromClip, this.app.media.getMedia(fromClip.mediaId), canvasW, canvasH, time);
            ctx.restore();
        }

        // 渲染后一帧（带裁剪）
        if (toClip) {
            ctx.save();
            ctx.beginPath();

            switch (direction) {
                case 'left':
                    ctx.rect(0, 0, canvasW * progress, canvasH);
                    break;
                case 'right':
                    ctx.rect(canvasW * (1 - progress), 0, canvasW * progress, canvasH);
                    break;
                case 'up':
                    ctx.rect(0, 0, canvasW, canvasH * progress);
                    break;
                case 'down':
                    ctx.rect(0, canvasH * (1 - progress), canvasW, canvasH * progress);
                    break;
            }

            ctx.clip();
            this.app.preview.renderVideoClip(ctx, toClip, this.app.media.getMedia(toClip.mediaId), canvasW, canvasH, time);
            ctx.restore();
        }
    }

    /**
     * 获取预设滤镜配置
     */
    static getFilterPresets() {
        return {
            none: { brightness: 100, contrast: 100, saturation: 100, blur: 0, hue: 0 },
            vintage: { brightness: 110, contrast: 90, saturation: 70, hue: 20 },
            warm: { brightness: 105, contrast: 105, saturation: 120, hue: 350 },
            cool: { brightness: 100, contrast: 110, saturation: 90, hue: 190 },
            dramatic: { brightness: 90, contrast: 150, saturation: 80 },
            pop: { brightness: 110, contrast: 130, saturation: 160 },
            bw: { brightness: 100, contrast: 120, saturation: 0 },
            noir: { brightness: 80, contrast: 140, saturation: 0 },
            dreamy: { brightness: 115, contrast: 85, saturation: 110, blur: 1 },
            retro: { brightness: 105, contrast: 95, saturation: 60, hue: 30 },
            matrix: { brightness: 90, contrast: 130, saturation: 50, hue: 100 },
            sunset: { brightness: 110, contrast: 110, saturation: 140, hue: 340 }
        };
    }

    /**
     * 获取转场类型列表
     */
    static getTransitionTypes() {
        return [
            { id: 'fade', name: '淡入淡出', icon: 'fa-adjust' },
            { id: 'dissolve', name: '溶解', icon: 'fa-water' },
            { id: 'wipe-left', name: '左擦除', icon: 'fa-arrow-left' },
            { id: 'wipe-right', name: '右擦除', icon: 'fa-arrow-right' },
            { id: 'wipe-up', name: '上擦除', icon: 'fa-arrow-up' },
            { id: 'wipe-down', name: '下擦除', icon: 'fa-arrow-down' }
        ];
    }
}
