import { eventBus } from '../utils/EventBus.js';

/**
 * 导出管线 - 使用Canvas逐帧录制 + MediaRecorder导出
 * FFmpeg.wasm作为可选增强
 */
export class ExportPipeline {
  constructor(project, compositor) {
    this.project = project;
    this.compositor = compositor;
    this._isExporting = false;
    this._cancelled = false;
  }

  get isExporting() { return this._isExporting; }

  /**
   * 导出视频
   * @param {Object} options - { width, height, fps, format, videoBitrate }
   */
  async export(options = {}) {
    const {
      width = 1920,
      height = 1080,
      fps = 30,
      format = 'webm',
      videoBitrate = 5000000,
    } = options;

    this._isExporting = true;
    this._cancelled = false;

    const duration = this.project.duration;
    if (duration <= 0) {
      eventBus.emit('exportError', { message: 'Project is empty' });
      this._isExporting = false;
      return;
    }

    eventBus.emit('exportProgress', { percent: 0, message: 'Preparing export...' });

    // 创建离屏Canvas
    const offscreen = document.createElement('canvas');
    offscreen.width = width;
    offscreen.height = height;
    const offCtx = offscreen.getContext('2d');

    // 使用Canvas流 + MediaRecorder
    const stream = offscreen.captureStream(fps);
    const mimeType = format === 'webm' ? 'video/webm;codecs=vp9' : 'video/webm;codecs=vp8';

    let recorder;
    try {
      recorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported(mimeType) ? mimeType : 'video/webm',
        videoBitsPerSecond: videoBitrate,
      });
    } catch (e) {
      recorder = new MediaRecorder(stream);
    }

    const chunks = [];
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.push(e.data);
    };

    return new Promise((resolve) => {
      recorder.onstop = () => {
        const blob = new Blob(chunks, { type: 'video/webm' });
        const url = URL.createObjectURL(blob);
        const filename = `${this.project.name || 'output'}.webm`;

        eventBus.emit('exportComplete', { url, filename, blob });
        this._isExporting = false;
        resolve({ url, filename, blob });
      };

      recorder.start(100); // 每100ms收集一次数据

      // 逐帧渲染
      const frameInterval = 1 / fps;
      let currentTime = 0;
      let frameCount = 0;
      const totalFrames = Math.ceil(duration * fps);

      const renderFrame = async () => {
        if (this._cancelled) {
          recorder.stop();
          this._isExporting = false;
          resolve(null);
          return;
        }

        if (currentTime >= duration) {
          recorder.stop();
          return;
        }

        // 渲染帧到离屏Canvas
        // 先清空
        offCtx.fillStyle = '#000';
        offCtx.fillRect(0, 0, width, height);

        // 获取活跃clips
        const activeClips = this.project.getClipsAtTime(currentTime);
        const videoClips = activeClips.filter(c => {
          const track = this.project.tracks.find(t => t.id === c.trackId);
          return track && track.type === 'video';
        });

        for (const clip of videoClips) {
          const asset = this.project.getMediaAsset(clip.mediaId);
          if (!asset) continue;

          const mediaTime = clip.toMediaTime(currentTime);

          if (asset.type === 'video') {
            const video = this.compositor.decoder.getVideoElement(asset.id);
            if (video) {
              video.currentTime = mediaTime;
              await new Promise(r => {
                const onSeeked = () => { video.removeEventListener('seeked', onSeeked); r(); };
                video.addEventListener('seeked', onSeeked);
                setTimeout(r, 100);
              });

              // 计算转场alpha
              let alpha = 1;
              for (const trans of clip.transitions) {
                const clipLocalTime = currentTime - clip.trackStart;
                const clipDuration = clip.duration;
                if (trans.type === 'fade' || trans.type === 'dissolve') {
                  if (clipLocalTime < trans.duration) {
                    alpha *= clipLocalTime / trans.duration;
                  } else if (clipLocalTime > clipDuration - trans.duration) {
                    alpha *= (clipDuration - clipLocalTime) / trans.duration;
                  }
                }
              }

              offCtx.save();
              offCtx.globalAlpha = alpha;
              // 适配绘制
              const mw = asset.videoWidth || video.videoWidth || width;
              const mh = asset.videoHeight || video.videoHeight || height;
              const scale = Math.min(width / mw, height / mh);
              const dw = mw * scale;
              const dh = mh * scale;
              const dx = (width - dw) / 2;
              const dy = (height - dh) / 2;
              offCtx.drawImage(video, dx, dy, dw, dh);
              offCtx.restore();
            }
          } else if (asset.type === 'image') {
            const img = this.compositor.decoder.getImageElement(asset.id);
            if (img && img.complete) {
              offCtx.save();
              const mw = asset.videoWidth || img.naturalWidth || width;
              const mh = asset.videoHeight || img.naturalHeight || height;
              const scale = Math.min(width / mw, height / mh);
              const dw = mw * scale;
              const dh = mh * scale;
              const dx = (width - dw) / 2;
              const dy = (height - dh) / 2;
              offCtx.drawImage(img, dx, dy, dw, dh);
              offCtx.restore();
            }
          }

          // 渲染文字叠加
          const clipLocalTime = currentTime - clip.trackStart;
          for (const overlay of clip.textOverlays) {
            if (clipLocalTime < overlay.startTime || clipLocalTime > overlay.endTime) continue;
            offCtx.save();
            offCtx.font = `bold ${overlay.fontSize}px ${overlay.fontFamily}`;
            offCtx.fillStyle = overlay.color;
            offCtx.textAlign = 'center';
            offCtx.textBaseline = 'middle';
            offCtx.shadowColor = 'rgba(0,0,0,0.7)';
            offCtx.shadowBlur = 4;
            offCtx.shadowOffsetX = 2;
            offCtx.shadowOffsetY = 2;
            offCtx.fillText(overlay.text, overlay.x * width, overlay.y * height);
            offCtx.restore();
          }
        }

        frameCount++;
        currentTime += frameInterval;

        // 更新进度
        const percent = frameCount / totalFrames;
        eventBus.emit('exportProgress', {
          percent,
          message: `Exporting frame ${frameCount}/${totalFrames}...`,
        });

        // 下一帧
        requestAnimationFrame(renderFrame);
      };

      renderFrame();
    });
  }

  cancel() {
    this._cancelled = true;
  }

  destroy() {
    this.cancel();
  }
}
