import { genId } from '../utils/IdGenerator.js';

/**
 * 文字叠加
 */
export class TextOverlay {
  constructor({ id, text, x, y, fontSize, fontFamily, color, startTime, duration }) {
    this.id = id || genId('txt');
    this.text = text || 'Text';
    this.x = x ?? 0.5;           // 归一化 0-1
    this.y = y ?? 0.5;
    this.fontSize = fontSize || 48;
    this.fontFamily = fontFamily || 'Arial';
    this.color = color || '#ffffff';
    this.startTime = startTime || 0;  // 相对于clip的时间
    this.duration = duration || 2;
  }

  get endTime() {
    return this.startTime + this.duration;
  }

  clone() {
    return new TextOverlay({ ...this, id: genId('txt') });
  }

  toJSON() {
    return { ...this };
  }

  static fromJSON(data) {
    return new TextOverlay(data);
  }
}

/**
 * 转场效果
 */
export class Transition {
  constructor({ id, type, duration, clipId }) {
    this.id = id || genId('trans');
    this.type = type || 'fade';     // 'fade' | 'dissolve'
    this.duration = duration || 0.5;
    this.clipId = clipId || null;   // 所属clip
  }

  clone() {
    return new Transition({ ...this, id: genId('trans') });
  }

  toJSON() {
    return { ...this };
  }

  static fromJSON(data) {
    return new Transition(data);
  }
}

/**
 * 片段 - 时间线上的一个媒体实例
 * trackStart: 片段在轨道上的起始时间
 * inPoint: 媒体源内的入点
 * outPoint: 媒体源内的出点
 */
export class Clip {
  constructor({ id, mediaId, trackId, trackStart, inPoint, outPoint, transitions, textOverlays }) {
    this.id = id || genId('clip');
    this.mediaId = mediaId || null;
    this.trackId = trackId || null;
    this.trackStart = trackStart || 0;
    this.inPoint = inPoint || 0;
    this.outPoint = outPoint || 0;
    this.transitions = (transitions || []).map(t => t instanceof Transition ? t : new Transition(t));
    this.textOverlays = (textOverlays || []).map(t => t instanceof TextOverlay ? t : new TextOverlay(t));
  }

  /** 片段在时间线上的时长 */
  get duration() {
    return this.outPoint - this.inPoint;
  }

  /** 片段在时间线上的结束时间 */
  get trackEnd() {
    return this.trackStart + this.duration;
  }

  /** 给定时间线时间是否在此片段范围内 */
  containsTime(time) {
    return time >= this.trackStart && time < this.trackEnd;
  }

  /** 时间线时间 -> 媒体源时间 */
  toMediaTime(timelineTime) {
    return this.inPoint + (timelineTime - this.trackStart);
  }

  addTransition(transition) {
    this.transitions.push(transition instanceof Transition ? transition : new Transition(transition));
  }

  removeTransition(transitionId) {
    this.transitions = this.transitions.filter(t => t.id !== transitionId);
  }

  addTextOverlay(overlay) {
    this.textOverlays.push(overlay instanceof TextOverlay ? overlay : new TextOverlay(overlay));
  }

  removeTextOverlay(overlayId) {
    this.textOverlays = this.textOverlays.filter(t => t.id !== overlayId);
  }

  clone() {
    return new Clip({
      ...this,
      id: genId('clip'),
      transitions: this.transitions.map(t => t.clone()),
      textOverlays: this.textOverlays.map(t => t.clone()),
    });
  }

  toJSON() {
    return {
      id: this.id,
      mediaId: this.mediaId,
      trackId: this.trackId,
      trackStart: this.trackStart,
      inPoint: this.inPoint,
      outPoint: this.outPoint,
      transitions: this.transitions.map(t => t.toJSON()),
      textOverlays: this.textOverlays.map(t => t.toJSON()),
    };
  }

  static fromJSON(data) {
    return new Clip(data);
  }
}

/**
 * 轨道 - 包含多个片段
 */
export class Track {
  constructor({ id, type, name, muted, clips }) {
    this.id = id || genId('track');
    this.type = type || 'video';  // 'video' | 'audio'
    this.name = name || (this.type === 'video' ? 'Video' : 'Audio');
    this.muted = muted || false;
    this.clips = (clips || []).map(c => c instanceof Clip ? c : new Clip(c));
  }

  /** 轨道总时长 */
  get duration() {
    if (this.clips.length === 0) return 0;
    return Math.max(...this.clips.map(c => c.trackEnd));
  }

  addClip(clip) {
    clip.trackId = this.id;
    this.clips.push(clip instanceof Clip ? clip : new Clip(clip));
    this._sortClips();
  }

  removeClip(clipId) {
    this.clips = this.clips.filter(c => c.id !== clipId);
  }

  getClip(clipId) {
    return this.clips.find(c => c.id === clipId) || null;
  }

  /** 获取给定时间点所在的clip */
  getClipAtTime(time) {
    return this.clips.find(c => c.containsTime(time)) || null;
  }

  /** 检测与已有clip是否重叠 */
  hasOverlap(newClip, excludeId = null) {
    for (const c of this.clips) {
      if (c.id === excludeId) continue;
      if (newClip.trackStart < c.trackEnd && newClip.trackEnd > c.trackStart) {
        return true;
      }
    }
    return false;
  }

  _sortClips() {
    this.clips.sort((a, b) => a.trackStart - b.trackStart);
  }

  clone() {
    return new Track({
      ...this,
      id: genId('track'),
      clips: this.clips.map(c => c.clone()),
    });
  }

  toJSON() {
    return {
      id: this.id,
      type: this.type,
      name: this.name,
      muted: this.muted,
      clips: this.clips.map(c => c.toJSON()),
    };
  }

  static fromJSON(data) {
    return new Track(data);
  }
}

/**
 * 媒体资源
 */
export class MediaAsset {
  constructor({ id, name, type, duration, file, videoWidth, videoHeight }) {
    this.id = id || genId('media');
    this.name = name || 'Untitled';
    this.type = type || 'video';  // 'video' | 'audio' | 'image'
    this.duration = duration || 0;
    this.file = file || null;     // File object
    this.videoWidth = videoWidth || 1920;
    this.videoHeight = videoHeight || 1080;
    this._objectURL = null;
    this._element = null;         // HTMLVideoElement / HTMLAudioElement / HTMLImageElement
  }

  get objectURL() {
    if (!this._objectURL && this.file) {
      this._objectURL = URL.createObjectURL(this.file);
    }
    return this._objectURL;
  }

  /** 获取/创建媒体元素 */
  getElement() {
    if (this._element) return this._element;
    if (this.type === 'video') {
      const el = document.createElement('video');
      el.src = this.objectURL;
      el.preload = 'auto';
      el.muted = true;
      this._element = el;
    } else if (this.type === 'audio') {
      const el = document.createElement('audio');
      el.src = this.objectURL;
      el.preload = 'auto';
      this._element = el;
    } else if (this.type === 'image') {
      const el = document.createElement('img');
      el.src = this.objectURL;
      this._element = el;
    }
    return this._element;
  }

  revoke() {
    if (this._objectURL) {
      URL.revokeObjectURL(this._objectURL);
      this._objectURL = null;
    }
  }

  toJSON() {
    return {
      id: this.id,
      name: this.name,
      type: this.type,
      duration: this.duration,
      videoWidth: this.videoWidth,
      videoHeight: this.videoHeight,
    };
  }
}

/**
 * 导出设置
 */
export class ExportSettings {
  constructor({ format, width, height, fps, videoBitrate, audioBitrate }) {
    this.format = format || 'mp4';
    this.width = width || 1920;
    this.height = height || 1080;
    this.fps = fps || 30;
    this.videoBitrate = videoBitrate || '5M';
    this.audioBitrate = audioBitrate || '128k';
  }

  toJSON() {
    return { ...this };
  }
}

/**
 * 项目 - 顶层根节点
 */
export class Project {
  constructor({ id, name, tracks, mediaAssets, settings }) {
    this.id = id || genId('proj');
    this.name = name || 'Untitled Project';
    this.tracks = (tracks || []).map(t => t instanceof Track ? t : new Track(t));
    this.mediaAssets = new Map();
    this.settings = settings instanceof ExportSettings ? settings : new ExportSettings(settings || {});

    if (mediaAssets) {
      for (const m of mediaAssets) {
        const asset = m instanceof MediaAsset ? m : new MediaAsset(m);
        this.mediaAssets.set(asset.id, asset);
      }
    }

    // 确保至少有一条视频轨和一条音频轨
    if (!this.tracks.find(t => t.type === 'video')) {
      this.tracks.unshift(new Track({ type: 'video', name: 'Video 1' }));
    }
    if (!this.tracks.find(t => t.type === 'audio')) {
      this.tracks.push(new Track({ type: 'audio', name: 'Audio 1' }));
    }
  }

  /** 项目总时长 */
  get duration() {
    if (this.tracks.length === 0) return 0;
    return Math.max(...this.tracks.map(t => t.duration), 0);
  }

  addTrack(track) {
    this.tracks.push(track instanceof Track ? track : new Track(track));
  }

  removeTrack(trackId) {
    this.tracks = this.tracks.filter(t => t.id !== trackId);
  }

  getTrack(trackId) {
    return this.tracks.find(t => t.id === trackId) || null;
  }

  get videoTracks() {
    return this.tracks.filter(t => t.type === 'video');
  }

  get audioTracks() {
    return this.tracks.filter(t => t.type === 'audio');
  }

  addMediaAsset(asset) {
    const a = asset instanceof MediaAsset ? asset : new MediaAsset(asset);
    this.mediaAssets.set(a.id, a);
    return a;
  }

  getMediaAsset(mediaId) {
    return this.mediaAssets.get(mediaId) || null;
  }

  removeMediaAsset(mediaId) {
    const asset = this.mediaAssets.get(mediaId);
    if (asset) {
      asset.revoke();
      this.mediaAssets.delete(mediaId);
    }
  }

  /** 获取给定时间点所有活跃的clip */
  getClipsAtTime(time) {
    const clips = [];
    for (const track of this.tracks) {
      if (track.muted) continue;
      const clip = track.getClipAtTime(time);
      if (clip) clips.push(clip);
    }
    return clips;
  }

  /** 获取所有clip的扁平列表 */
  getAllClips() {
    const clips = [];
    for (const track of this.tracks) {
      clips.push(...track.clips);
    }
    return clips;
  }

  toJSON() {
    return {
      id: this.id,
      name: this.name,
      tracks: this.tracks.map(t => t.toJSON()),
      mediaAssets: Array.from(this.mediaAssets.values()).map(m => m.toJSON()),
      settings: this.settings.toJSON(),
    };
  }

  static fromJSON(data) {
    return new Project({
      ...data,
      tracks: data.tracks.map(t => Track.fromJSON(t)),
      mediaAssets: data.mediaAssets.map(m => MediaAsset.fromJSON ? MediaAsset.fromJSON(m) : new MediaAsset(m)),
      settings: new ExportSettings(data.settings),
    });
  }
}
