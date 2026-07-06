import { MediaDecoder } from './MediaDecoder.js';

/**
 * 合成器 - 将当前时间的所有轨道内容合成到Canvas
 * 无状态投影：Render(t, State) = Frame
 */
export class Compositor {
  constructor(project, canvas) {
    this.project = project;
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.decoder = new MediaDecoder();
    this._lastRenderTime = -1;
    this._seekPromises = [];
  }

  /** 注册新媒体资源 */
  registerAsset(asset) {
    this.decoder.registerAsset(asset);
  }

  /** 合成指定时间的帧 */
  async render(time) {
    const { width, height } = this.canvas;
    this.ctx.clearRect(0, 0, width, height);

    // 黑色背景
    this.ctx.fillStyle = '#000';
    this.ctx.fillRect(0, 0, width, height);

    // 收集所有活跃clip
    const activeClips = this.project.getClipsAtTime(time);

    // 先渲染视频轨道（从下到上）
    const videoClips = activeClips.filter(c => {
      const track = this.project.tracks.find(t => t.id === c.trackId);
      return track && track.type === 'video';
    });

    for (const clip of videoClips) {
      await this._renderVideoClip(clip, time);
    }

    // 渲染文字叠加
    for (const clip of videoClips) {
      this._renderTextOverlays(clip, time);
    }

    this._lastRenderTime = time;
  }

  /** 渲染单个视频clip */
  async _renderVideoClip(clip, time) {
    const asset = this.project.getMediaAsset(clip.mediaId);
    if (!asset) return;

    const mediaTime = clip.toMediaTime(time);

    if (asset.type === 'video') {
      const video = this.decoder.getVideoElement(asset.id);
      if (!video) return;

      // Seek到正确时间
      await this.decoder.seekVideo(asset.id, mediaTime);

      // 计算转场透明度
      let alpha = 1;
      for (const trans of clip.transitions) {
        alpha *= this._calcTransitionAlpha(trans, clip, time);
      }

      this.ctx.save();
      this.ctx.globalAlpha = alpha;
      this._drawMediaFit(video, asset);
      this.ctx.restore();

    } else if (asset.type === 'image') {
      const img = this.decoder.getImageElement(asset.id);
      if (!img || !img.complete) return;

      let alpha = 1;
      for (const trans of clip.transitions) {
        alpha *= this._calcTransitionAlpha(trans, clip, time);
      }

      this.ctx.save();
      this.ctx.globalAlpha = alpha;
      this._drawMediaFit(img, asset);
      this.ctx.restore();
    }
  }

  /** 将媒体元素适配绘制到Canvas */
  _drawMediaFit(element, asset) {
    const { width: cw, height: ch } = this.canvas;
    const mw = asset.videoWidth || element.videoWidth || element.naturalWidth || cw;
    const mh = asset.videoHeight || element.videoHeight || element.naturalHeight || ch;

    // 保持宽高比适配
    const scale = Math.min(cw / mw, ch / mh);
    const dw = mw * scale;
    const dh = mh * scale;
    const dx = (cw - dw) / 2;
    const dy = (ch - dh) / 2;

    this.ctx.drawImage(element, dx, dy, dw, dh);
  }

  /** 计算转场透明度 */
  _calcTransitionAlpha(transition, clip, time) {
    const clipLocalTime = time - clip.trackStart;
    const clipDuration = clip.duration;

    if (transition.type === 'fade') {
      // 淡入淡出
      const fadeDuration = transition.duration;
      if (clipLocalTime < fadeDuration) {
        // 淡入
        return clipLocalTime / fadeDuration;
      } else if (clipLocalTime > clipDuration - fadeDuration) {
        // 淡出
        return (clipDuration - clipLocalTime) / fadeDuration;
      }
    } else if (transition.type === 'dissolve') {
      // 交叉溶解 - 简化实现
      const fadeDuration = transition.duration;
      if (clipLocalTime < fadeDuration) {
        return clipLocalTime / fadeDuration;
      } else if (clipLocalTime > clipDuration - fadeDuration) {
        return (clipDuration - clipLocalTime) / fadeDuration;
      }
    }
    return 1;
  }

  /** 渲染文字叠加 */
  _renderTextOverlays(clip, time) {
    const clipLocalTime = time - clip.trackStart;

    for (const overlay of clip.textOverlays) {
      if (clipLocalTime < overlay.startTime || clipLocalTime > overlay.endTime) continue;

      const { width: cw, height: ch } = this.canvas;
      const x = overlay.x * cw;
      const y = overlay.y * ch;

      this.ctx.save();
      this.ctx.font = `bold ${overlay.fontSize}px ${overlay.fontFamily}`;
      this.ctx.fillStyle = overlay.color;
      this.ctx.textAlign = 'center';
      this.ctx.textBaseline = 'middle';

      // 文字阴影
      this.ctx.shadowColor = 'rgba(0,0,0,0.7)';
      this.ctx.shadowBlur = 4;
      this.ctx.shadowOffsetX = 2;
      this.ctx.shadowOffsetY = 2;

      this.ctx.fillText(overlay.text, x, y);
      this.ctx.restore();
    }
  }

  /** 获取当前帧的Blob（用于导出） */
  async getFrameBlob() {
    return new Promise(resolve => {
      this.canvas.toBlob(resolve, 'image/png');
    });
  }

  destroy() {
    this.decoder.destroy();
  }
}
