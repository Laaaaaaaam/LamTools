/**
 * VideoForge - 工具函数模块
 */

const Utils = {
    /**
     * 格式化时间 (秒 -> HH:MM:SS.mm)
     */
    formatTime(seconds) {
        if (isNaN(seconds) || seconds < 0) seconds = 0;
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = Math.floor(seconds % 60);
        const ms = Math.floor((seconds % 1) * 100);
        return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}.${String(ms).padStart(2,'0')}`;
    },

    /**
     * 格式化短时间 (秒 -> MM:SS)
     */
    formatShortTime(seconds) {
        if (isNaN(seconds) || seconds < 0) seconds = 0;
        const m = Math.floor(seconds / 60);
        const s = Math.floor(seconds % 60);
        return `${m}:${String(s).padStart(2,'0')}`;
    },

    /**
     * 生成唯一ID
     */
    generateId() {
        return Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
    },

    /**
     * 限制数值范围
     */
    clamp(value, min, max) {
        return Math.min(Math.max(value, min), max);
    },

    /**
     * 线性插值
     */
    lerp(a, b, t) {
        return a + (b - a) * t;
    },

    /**
     * 将秒转换为像素位置
     */
    secondsToPixels(seconds, pixelsPerSecond) {
        return seconds * pixelsPerSecond;
    },

    /**
     * 将像素位置转换为秒
     */
    pixelsToSeconds(pixels, pixelsPerSecond) {
        return pixels / pixelsPerSecond;
    },

    /**
     * 格式化文件大小
     */
    formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },

    /**
     * 获取文件类型
     */
    getFileType(file) {
        const type = file.type || '';
        if (type.startsWith('video/')) return 'video';
        if (type.startsWith('audio/')) return 'audio';
        if (type.startsWith('image/')) return 'image';
        const ext = file.name.split('.').pop().toLowerCase();
        const videoExts = ['mp4', 'webm', 'mov', 'avi', 'mkv', 'flv', 'wmv'];
        const audioExts = ['mp3', 'wav', 'ogg', 'aac', 'flac', 'm4a'];
        const imageExts = ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg'];
        if (videoExts.includes(ext)) return 'video';
        if (audioExts.includes(ext)) return 'audio';
        if (imageExts.includes(ext)) return 'image';
        return 'unknown';
    },

    /**
     * 创建视频缩略图
     */
    createVideoThumbnail(file) {
        return new Promise((resolve) => {
            const video = document.createElement('video');
            video.preload = 'metadata';
            video.muted = true;
            const url = URL.createObjectURL(file);
            video.src = url;

            video.onloadeddata = () => {
                video.currentTime = Math.min(1, video.duration / 4);
            };

            video.onseeked = () => {
                const canvas = document.createElement('canvas');
                canvas.width = 160;
                canvas.height = 90;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                const thumbnailUrl = canvas.toDataURL('image/jpeg', 0.7);
                URL.revokeObjectURL(url);
                resolve({
                    thumbnail: thumbnailUrl,
                    duration: video.duration,
                    width: video.videoWidth,
                    height: video.videoHeight
                });
            };

            video.onerror = () => {
                URL.revokeObjectURL(url);
                resolve({ thumbnail: null, duration: 0, width: 0, height: 0 });
            };
        });
    },

    /**
     * 创建音频波形数据
     */
    async createAudioWaveform(file) {
        try {
            const arrayBuffer = await file.arrayBuffer();
            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
            const channelData = audioBuffer.getChannelData(0);
            const samples = 200;
            const blockSize = Math.floor(channelData.length / samples);
            const waveform = [];
            for (let i = 0; i < samples; i++) {
                let sum = 0;
                for (let j = 0; j < blockSize; j++) {
                    sum += Math.abs(channelData[i * blockSize + j]);
                }
                waveform.push(sum / blockSize);
            }
            audioContext.close();
            return { waveform, duration: audioBuffer.duration };
        } catch (e) {
            console.warn('无法生成音频波形:', e);
            return { waveform: [], duration: 0 };
        }
    },

    /**
     * 显示 Toast 通知
     */
    showToast(message, type = 'info', duration = 3000) {
        let container = document.querySelector('.toast-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'toast-container';
            document.body.appendChild(container);
        }

        const icons = {
            success: 'fas fa-check-circle',
            error: 'fas fa-exclamation-circle',
            info: 'fas fa-info-circle',
            warning: 'fas fa-exclamation-triangle'
        };

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `<i class="${icons[type] || icons.info}"></i><span>${message}</span>`;
        container.appendChild(toast);

        setTimeout(() => {
            toast.style.animation = 'toastOut 0.3s ease forwards';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    },

    /**
     * 防抖
     */
    debounce(fn, delay = 300) {
        let timer;
        return (...args) => {
            clearTimeout(timer);
            timer = setTimeout(() => fn.apply(this, args), delay);
        };
    },

    /**
     * 节流
     */
    throttle(fn, limit = 100) {
        let inThrottle;
        return (...args) => {
            if (!inThrottle) {
                fn.apply(this, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    },

    /**
     * 深拷贝
     */
    deepClone(obj) {
        return JSON.parse(JSON.stringify(obj));
    },

    /**
     * 显示上下文菜单
     */
    showContextMenu(x, y, items) {
        let menu = document.querySelector('.context-menu');
        if (!menu) {
            menu = document.createElement('div');
            menu.className = 'context-menu';
            document.body.appendChild(menu);
        }

        let html = '';
        items.forEach(item => {
            if (item === 'divider') {
                html += '<div class="context-menu-divider"></div>';
            } else {
                html += `<div class="context-menu-item" data-action="${item.action}">
                    <i class="${item.icon || ''}"></i>
                    ${item.label}
                    ${item.shortcut ? `<span class="shortcut">${item.shortcut}</span>` : ''}
                </div>`;
            }
        });

        menu.innerHTML = html;

        // 定位
        const maxX = window.innerWidth - 200;
        const maxY = window.innerHeight - menu.offsetHeight - 10;
        menu.style.left = Math.min(x, maxX) + 'px';
        menu.style.top = Math.min(y, maxY) + 'px';
        menu.classList.add('show');

        // 事件绑定
        menu.querySelectorAll('.context-menu-item').forEach(el => {
            el.onclick = () => {
                const action = el.dataset.action;
                const item = items.find(i => i && i.action === action);
                if (item && item.callback) item.callback();
                menu.classList.remove('show');
            };
        });

        // 点击其他地方关闭
        const closeMenu = (e) => {
            if (!menu.contains(e.target)) {
                menu.classList.remove('show');
                document.removeEventListener('click', closeMenu);
            }
        };
        setTimeout(() => document.addEventListener('click', closeMenu), 0);
    }
};
