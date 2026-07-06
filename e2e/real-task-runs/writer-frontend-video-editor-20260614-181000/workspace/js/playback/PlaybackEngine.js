import { eventBus } from '../utils/EventBus.js';

/**
 * 播放引擎 - 以 AudioContext 为主时钟驱动 rAF 合成
 */
export class PlaybackEngine {
  constructor(project) {
    this.project = project;
    this._audioContext = null;
    this._isPlaying = false;
    this._currentTime = 0;       // 当前播放头位置（秒）
    this._playStartContextTime = 0; // AudioContext时间戳
    this._playStartProjectTime = 0; // 播放开始时的项目时间
    this._activeSources = [];     // 活跃的音频源
    this._rafId = null;
    this._onTick = null;          // 外部tick回调
    this._looping = false;
  }

  get isPlaying() { return this._isPlaying; }
  get currentTime() { return this._currentTime; }
  get duration() { return this.project.duration; }

  set onTick(fn) { this._onTick = fn; }
  set looping(v) { this._looping = v; }

  /** 获取AudioContext（懒创建） */
  get audioContext() {
    if (!this._audioContext) {
      this._audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }
    return this._audioContext;
  }

  /** 播放 */
  play() {
    if (this._isPlaying) return;
    this._isPlaying = true;
    this._playStartContextTime = this.audioContext.currentTime;
    this._playStartProjectTime = this._currentTime;

    // 启动所有音频
    this._startAudioSources();

    // 启动渲染循环
    this._scheduleFrame();
    eventBus.emit('playbackStarted');
  }

  /** 暂停 */
  pause() {
    if (!this._isPlaying) return;
    this._isPlaying = false;
    this._stopAudioSources();
    if (this._rafId) {
      cancelAnimationFrame(this._rafId);
      this._rafId = null;
    }
    eventBus.emit('playbackPaused', this._currentTime);
  }

  /** 跳转到指定时间 */
  seek(time) {
    const wasPlaying = this._isPlaying;
    if (wasPlaying) this.pause();
    this._currentTime = Math.max(0, Math.min(time, this.duration));
    eventBus.emit('playbackSeeked', this._currentTime);
    if (wasPlaying) this.play();
  }

  /** 停止并回到起点 */
  stop() {
    this.pause();
    this._currentTime = 0;
    eventBus.emit('playbackStopped');
  }

  /** rAF 驱动 */
  _scheduleFrame() {
    this._rafId = requestAnimationFrame(() => {
      if (!this._isPlaying) return;

      // 以AudioContext为主时钟
      const elapsed = this.audioContext.currentTime - this._playStartContextTime;
      this._currentTime = this._playStartProjectTime + elapsed;

      // 检查是否到达末尾
      if (this._currentTime >= this.duration) {
        if (this._looping) {
          this._currentTime = 0;
          this._playStartContextTime = this.audioContext.currentTime;
          this._playStartProjectTime = 0;
          this._stopAudioSources();
          this._startAudioSources();
        } else {
          this._currentTime = this.duration;
          this.pause();
          return;
        }
      }

      // 通知外部
      if (this._onTick) {
        this._onTick(this._currentTime);
      }
      eventBus.emit('playbackTick', this._currentTime);

      this._scheduleFrame();
    });
  }

  /** 启动当前时间点的音频源 */
  _startAudioSources() {
    this._stopAudioSources();

    for (const track of this.project.audioTracks) {
      if (track.muted) continue;
      for (const clip of track.clips) {
        if (this._currentTime >= clip.trackStart && this._currentTime < clip.trackEnd) {
          this._playAudioClip(clip);
        }
      }
    }
  }

  /** 播放单个音频clip */
  _playAudioClip(clip) {
    const asset = this.project.getMediaAsset(clip.mediaId);
    if (!asset) return;

    const element = asset.getElement();
    if (!element) return;

    try {
      const source = this.audioContext.createMediaElementSource(element);
      source.connect(this.audioContext.destination);

      const mediaTime = clip.toMediaTime(this._currentTime);
      element.currentTime = mediaTime;
      element.play().catch(() => {});

      this._activeSources.push({ source, element, clip });
    } catch (e) {
      // 可能已经连接过，直接播放
      try {
        const mediaTime = clip.toMediaTime(this._currentTime);
        element.currentTime = mediaTime;
        element.play().catch(() => {});
      } catch (e2) { /* ignore */ }
    }
  }

  /** 停止所有音频源 */
  _stopAudioSources() {
    for (const { source, element, clip } of this._activeSources) {
      try {
        element.pause();
        element.currentTime = clip.inPoint;
      } catch (e) { /* ignore */ }
    }
    this._activeSources = [];
  }

  /** 更新音频源（当时间线变更时调用） */
  refreshAudio() {
    if (this._isPlaying) {
      this._stopAudioSources();
      this._startAudioSources();
    }
  }

  destroy() {
    this.pause();
    if (this._audioContext) {
      this._audioContext.close();
      this._audioContext = null;
    }
  }
}
