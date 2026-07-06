import { eventBus } from '../utils/EventBus.js';

/**
 * 媒体解码器 - 管理视频帧提取与缓存
 */
export class MediaDecoder {
  constructor() {
    this._videoElements = new Map();  // mediaId -> HTMLVideoElement
    this._audioElements = new Map();  // mediaId -> HTMLAudioElement
    this._imageElements = new Map();  // mediaId -> HTMLImageElement
  }

  /** 注册媒体资源，创建解码元素 */
  registerAsset(asset) {
    if (this._videoElements.has(asset.id)) return;

    if (asset.type === 'video') {
      const video = document.createElement('video');
      video.src = asset.objectURL;
      video.preload = 'auto';
      video.muted = true;
      video.playsInline = true;
      this._videoElements.set(asset.id, video);
    } else if (asset.type === 'audio') {
      const audio = document.createElement('audio');
      audio.src = asset.objectURL;
      audio.preload = 'auto';
      this._audioElements.set(asset.id, audio);
    } else if (asset.type === 'image') {
      const img = document.createElement('img');
      img.src = asset.objectURL;
      this._imageElements.set(asset.id, img);
    }
  }

  /** 获取视频元素 */
  getVideoElement(mediaId) {
    return this._videoElements.get(mediaId) || null;
  }

  /** 获取音频元素 */
  getAudioElement(mediaId) {
    return this._audioElements.get(mediaId) || null;
  }

  /** 获取图片元素 */
  getImageElement(mediaId) {
    return this._imageElements.get(mediaId) || null;
  }

  /** seek视频到指定时间并返回Promise */
  async seekVideo(mediaId, time) {
    const video = this._videoElements.get(mediaId);
    if (!video) return;
    if (Math.abs(video.currentTime - time) < 0.02) return; // 已在目标位置
    video.currentTime = time;
    return new Promise((resolve) => {
      const onSeeked = () => {
        video.removeEventListener('seeked', onSeeked);
        resolve();
      };
      video.addEventListener('seeked', onSeeked);
      // 超时保护
      setTimeout(resolve, 200);
    });
  }

  /** 注销媒体资源 */
  unregisterAsset(mediaId) {
    this._videoElements.delete(mediaId);
    this._audioElements.delete(mediaId);
    this._imageElements.delete(mediaId);
  }

  destroy() {
    for (const video of this._videoElements.values()) {
      video.src = '';
      video.load();
    }
    for (const audio of this._audioElements.values()) {
      audio.src = '';
      audio.load();
    }
    this._videoElements.clear();
    this._audioElements.clear();
    this._imageElements.clear();
  }
}
