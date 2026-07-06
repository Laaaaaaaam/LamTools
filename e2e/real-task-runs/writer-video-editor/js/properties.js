/**
 * VideoForge - 属性面板模块
 */

class Properties {
    constructor(app) {
        this.app = app;
        this.currentClip = null;

        this.initElements();
        this.bindEvents();
    }

    initElements() {
        // 变换属性
        this.propX = document.getElementById('prop-x');
        this.propY = document.getElementById('prop-y');
        this.propWidth = document.getElementById('prop-width');
        this.propHeight = document.getElementById('prop-height');
        this.propRotation = document.getElementById('prop-rotation');
        this.propScale = document.getElementById('prop-scale');
        this.propOpacity = document.getElementById('prop-opacity');

        // 滤镜属性
        this.filterBrightness = document.getElementById('filter-brightness');
        this.filterContrast = document.getElementById('filter-contrast');
        this.filterSaturation = document.getElementById('filter-saturation');
        this.filterBlur = document.getElementById('filter-blur');
        this.filterHue = document.getElementById('filter-hue');

        // 文字属性
        this.textContent = document.getElementById('text-content');
        this.textSize = document.getElementById('text-size');
        this.textColor = document.getElementById('text-color');
        this.textFont = document.getElementById('text-font');
        this.textWeight = document.getElementById('text-weight');
        this.textStrokeColor = document.getElementById('text-stroke-color');
        this.textStrokeWidth = document.getElementById('text-stroke-width');
        this.textBgColor = document.getElementById('text-bg-color');
        this.textBgOpacity = document.getElementById('text-bg-opacity');

        // 速度
        this.propSpeed = document.getElementById('prop-speed');

        // 值显示
        this.rotationValue = document.getElementById('rotation-value');
        this.scaleValue = document.getElementById('scale-value');
        this.opacityValue = document.getElementById('opacity-value');
        this.brightnessValue = document.getElementById('brightness-value');
        this.contrastValue = document.getElementById('contrast-value');
        this.saturationValue = document.getElementById('saturation-value');
        this.blurValue = document.getElementById('blur-value');
        this.hueValue = document.getElementById('hue-value');
        this.speedValue = document.getElementById('speed-value');
    }

    bindEvents() {
        // 变换属性变更
        const transformInputs = [this.propX, this.propY, this.propWidth, this.propHeight];
        transformInputs.forEach(input => {
            input.addEventListener('change', () => this.updateTransform());
        });

        this.propRotation.addEventListener('input', () => {
            this.rotationValue.textContent = this.propRotation.value + '°';
            this.updateTransform();
        });

        this.propScale.addEventListener('input', () => {
            this.scaleValue.textContent = this.propScale.value + '%';
            this.updateTransform();
        });

        this.propOpacity.addEventListener('input', () => {
            this.opacityValue.textContent = this.propOpacity.value + '%';
            this.updateFilters();
        });

        // 滤镜属性变更
        this.filterBrightness.addEventListener('input', () => {
            this.brightnessValue.textContent = this.filterBrightness.value + '%';
            this.updateFilters();
        });

        this.filterContrast.addEventListener('input', () => {
            this.contrastValue.textContent = this.filterContrast.value + '%';
            this.updateFilters();
        });

        this.filterSaturation.addEventListener('input', () => {
            this.saturationValue.textContent = this.filterSaturation.value + '%';
            this.updateFilters();
        });

        this.filterBlur.addEventListener('input', () => {
            this.blurValue.textContent = this.filterBlur.value + 'px';
            this.updateFilters();
        });

        this.filterHue.addEventListener('input', () => {
            this.hueValue.textContent = this.filterHue.value + '°';
            this.updateFilters();
        });

        // 速度
        this.propSpeed.addEventListener('input', () => {
            const speed = this.propSpeed.value / 100;
            this.speedValue.textContent = speed.toFixed(2) + 'x';
            if (this.currentClip) {
                this.currentClip.speed = speed;
                this.app.preview.renderFrame();
            }
        });

        // 速度预设
        document.querySelectorAll('.speed-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const speed = parseFloat(btn.dataset.speed);
                this.propSpeed.value = speed * 100;
                this.speedValue.textContent = speed.toFixed(2) + 'x';
                document.querySelectorAll('.speed-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                if (this.currentClip) {
                    this.currentClip.speed = speed;
                    this.app.preview.renderFrame();
                }
            });
        });

        // 文字属性
        const textInputs = [this.textContent, this.textSize, this.textColor, this.textFont,
            this.textWeight, this.textStrokeColor, this.textStrokeWidth, this.textBgColor, this.textBgOpacity];
        textInputs.forEach(input => {
            input.addEventListener('input', () => this.updateTextProperties());
        });

        // 添加文字层
        document.getElementById('btn-add-text').addEventListener('click', () => this.addTextClip());

        // 属性面板折叠
        document.querySelectorAll('.property-title').forEach(title => {
            title.addEventListener('click', () => {
                title.parentElement.classList.toggle('collapsed');
            });
        });

        // 特效拖拽到片段
        document.querySelectorAll('.effect-item').forEach(item => {
            item.addEventListener('click', () => {
                this.applyEffect(item.dataset.effect);
            });
        });
    }

    /**
     * 加载片段属性
     */
    loadClipProperties(clip) {
        this.currentClip = clip;

        if (!clip) {
            this.resetProperties();
            return;
        }

        // 变换
        const transform = clip.transform || {};
        this.propX.value = transform.x || 0;
        this.propY.value = transform.y || 0;
        this.propScale.value = transform.scale || 100;
        this.scaleValue.textContent = (transform.scale || 100) + '%';
        this.propRotation.value = transform.rotation || 0;
        this.rotationValue.textContent = (transform.rotation || 0) + '°';

        // 滤镜
        const filters = clip.filters || {};
        this.filterBrightness.value = filters.brightness || 100;
        this.brightnessValue.textContent = (filters.brightness || 100) + '%';
        this.filterContrast.value = filters.contrast || 100;
        this.contrastValue.textContent = (filters.contrast || 100) + '%';
        this.filterSaturation.value = filters.saturation || 100;
        this.saturationValue.textContent = (filters.saturation || 100) + '%';
        this.filterBlur.value = filters.blur || 0;
        this.blurValue.textContent = (filters.blur || 0) + 'px';
        this.filterHue.value = filters.hue || 0;
        this.hueValue.textContent = (filters.hue || 0) + '°';
        this.propOpacity.value = filters.opacity || 100;
        this.opacityValue.textContent = (filters.opacity || 100) + '%';

        // 速度
        this.propSpeed.value = (clip.speed || 1) * 100;
        this.speedValue.textContent = (clip.speed || 1).toFixed(2) + 'x';

        // 文字
        if (clip.text) {
            this.textContent.value = clip.text.content || '';
            this.textSize.value = clip.text.fontSize || 32;
            this.textColor.value = clip.text.color || '#ffffff';
            this.textFont.value = clip.text.fontFamily || 'Inter';
            this.textWeight.value = clip.text.fontWeight || 700;
            this.textStrokeColor.value = clip.text.strokeColor || '#000000';
            this.textStrokeWidth.value = clip.text.strokeWidth || 2;
            this.textBgColor.value = clip.text.bgColor || '#000000';
            this.textBgOpacity.value = clip.text.bgOpacity || 0;
        } else {
            this.textContent.value = '';
        }

        // 更新速度预设按钮
        document.querySelectorAll('.speed-btn').forEach(btn => {
            btn.classList.toggle('active', parseFloat(btn.dataset.speed) === (clip.speed || 1));
        });
    }

    /**
     * 更新变换属性
     */
    updateTransform() {
        if (!this.currentClip) return;

        this.currentClip.transform = {
            x: parseInt(this.propX.value) || 0,
            y: parseInt(this.propY.value) || 0,
            scale: parseInt(this.propScale.value) || 100,
            rotation: parseInt(this.propRotation.value) || 0
        };

        this.app.preview.renderFrame();
    }

    /**
     * 更新滤镜属性
     */
    updateFilters() {
        if (!this.currentClip) return;

        this.currentClip.filters = {
            brightness: parseInt(this.filterBrightness.value) || 100,
            contrast: parseInt(this.filterContrast.value) || 100,
            saturation: parseInt(this.filterSaturation.value) || 100,
            blur: parseInt(this.filterBlur.value) || 0,
            hue: parseInt(this.filterHue.value) || 0,
            opacity: parseInt(this.propOpacity.value) || 100
        };

        this.app.preview.renderFrame();
    }

    /**
     * 更新文字属性
     */
    updateTextProperties() {
        if (!this.currentClip) return;

        this.currentClip.text = {
            content: this.textContent.value,
            fontSize: parseInt(this.textSize.value) || 32,
            color: this.textColor.value,
            fontFamily: this.textFont.value,
            fontWeight: this.textWeight.value,
            strokeColor: this.textStrokeColor.value,
            strokeWidth: parseInt(this.textStrokeWidth.value) || 0,
            bgColor: this.textBgColor.value,
            bgOpacity: parseInt(this.textBgOpacity.value) || 0,
            x: 0,
            y: 0
        };

        this.app.preview.renderFrame();
    }

    /**
     * 添加文字片段
     */
    addTextClip() {
        const content = this.textContent.value.trim();
        if (!content) {
            Utils.showToast('请输入文字内容', 'warning');
            return;
        }

        const clip = {
            id: Utils.generateId(),
            mediaId: null,
            name: content.substring(0, 20),
            type: 'text',
            track: 'T1',
            startTime: this.app.timeline.currentTime,
            duration: 5,
            offset: 0,
            thumbnail: null,
            waveform: null,
            filters: { brightness: 100, contrast: 100, saturation: 100, blur: 0, hue: 0, opacity: 100 },
            transform: { x: 0, y: 0, scale: 100, rotation: 0 },
            speed: 1,
            volume: 100,
            text: {
                content: content,
                fontSize: parseInt(this.textSize.value) || 32,
                color: this.textColor.value,
                fontFamily: this.textFont.value,
                fontWeight: this.textWeight.value,
                strokeColor: this.textStrokeColor.value,
                strokeWidth: parseInt(this.textStrokeWidth.value) || 2,
                bgColor: this.textBgColor.value,
                bgOpacity: parseInt(this.textBgOpacity.value) || 0,
                x: 0,
                y: 0
            }
        };

        this.app.timeline.clips.push(clip);
        this.app.timeline.updateDuration();
        this.app.timeline.renderClips();
        this.app.history.saveState();
        this.app.updateOverlayVisibility();

        Utils.showToast('已添加文字层', 'success', 1500);
    }

    /**
     * 应用特效
     */
    applyEffect(effectName) {
        if (!this.currentClip) {
            Utils.showToast('请先选中一个片段', 'warning');
            return;
        }

        const presets = {
            brightness: { brightness: 130 },
            contrast: { contrast: 140 },
            saturation: { saturation: 150 },
            blur: { blur: 3 },
            grayscale: { saturation: 0 },
            sepia: { saturation: 50, hue: 30 },
            invert: { brightness: 0, contrast: 200 },
            'hue-rotate': { hue: 90 }
        };

        const preset = presets[effectName];
        if (preset) {
            Object.assign(this.currentClip.filters, preset);
            this.loadClipProperties(this.currentClip);
            this.app.preview.renderFrame();
            Utils.showToast(`已应用特效: ${effectName}`, 'success', 1500);
        }
    }

    /**
     * 重置属性
     */
    resetProperties() {
        this.propX.value = 0;
        this.propY.value = 0;
        this.propScale.value = 100;
        this.scaleValue.textContent = '100%';
        this.propRotation.value = 0;
        this.rotationValue.textContent = '0°';
        this.propOpacity.value = 100;
        this.opacityValue.textContent = '100%';
        this.filterBrightness.value = 100;
        this.brightnessValue.textContent = '100%';
        this.filterContrast.value = 100;
        this.contrastValue.textContent = '100%';
        this.filterSaturation.value = 100;
        this.saturationValue.textContent = '100%';
        this.filterBlur.value = 0;
        this.blurValue.textContent = '0px';
        this.filterHue.value = 0;
        this.hueValue.textContent = '0°';
        this.propSpeed.value = 100;
        this.speedValue.textContent = '1.00x';
        this.textContent.value = '';
    }
}
