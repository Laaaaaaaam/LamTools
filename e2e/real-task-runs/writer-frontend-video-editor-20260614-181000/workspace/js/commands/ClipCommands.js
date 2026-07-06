import { Command } from './CommandManager.js';
import { Clip, Transition, TextOverlay } from '../models/ProjectModel.js';
import { genId } from '../utils/IdGenerator.js';

/**
 * 添加片段命令
 */
export class AddClipCommand extends Command {
  constructor(project, trackId, clipData) {
    super('AddClip');
    this.project = project;
    this.trackId = trackId;
    this.clipData = clipData;
  }

  execute() {
    const track = this.project.getTrack(this.trackId);
    if (!track) return;
    const clip = this.clipData instanceof Clip ? this.clipData : new Clip(this.clipData);
    clip.trackId = this.trackId;
    track.addClip(clip);
    this._clipId = clip.id;
  }

  undo() {
    const track = this.project.getTrack(this.trackId);
    if (!track) return;
    track.removeClip(this._clipId);
  }
}

/**
 * 删除片段命令
 */
export class RemoveClipCommand extends Command {
  constructor(project, trackId, clipId) {
    super('RemoveClip');
    this.project = project;
    this.trackId = trackId;
    this.clipId = clipId;
    this._clipData = null;
  }

  execute() {
    const track = this.project.getTrack(this.trackId);
    if (!track) return;
    const clip = track.getClip(this.clipId);
    if (clip) {
      this._clipData = clip.toJSON();
      track.removeClip(this.clipId);
    }
  }

  undo() {
    const track = this.project.getTrack(this.trackId);
    if (!track || !this._clipData) return;
    const clip = Clip.fromJSON(this._clipData);
    track.addClip(clip);
  }
}

/**
 * 裁剪片段命令（调整入出点）
 */
export class TrimClipCommand extends Command {
  constructor(project, trackId, clipId, newInPoint, newOutPoint) {
    super('TrimClip');
    this.project = project;
    this.trackId = trackId;
    this.clipId = clipId;
    this.newInPoint = newInPoint;
    this.newOutPoint = newOutPoint;
    this._oldInPoint = null;
    this._oldOutPoint = null;
    this._oldTrackStart = null;
  }

  execute() {
    const track = this.project.getTrack(this.trackId);
    if (!track) return;
    const clip = track.getClip(this.clipId);
    if (!clip) return;
    this._oldInPoint = clip.inPoint;
    this._oldOutPoint = clip.outPoint;
    this._oldTrackStart = clip.trackStart;
    // 调整入点时同步移动trackStart
    const inDelta = this.newInPoint - clip.inPoint;
    clip.inPoint = this.newInPoint;
    clip.outPoint = this.newOutPoint;
    clip.trackStart += inDelta;
  }

  undo() {
    const track = this.project.getTrack(this.trackId);
    if (!track) return;
    const clip = track.getClip(this.clipId);
    if (!clip) return;
    clip.inPoint = this._oldInPoint;
    clip.outPoint = this._oldOutPoint;
    clip.trackStart = this._oldTrackStart;
  }
}

/**
 * 分割片段命令
 */
export class SplitClipCommand extends Command {
  constructor(project, trackId, clipId, splitTime) {
    super('SplitClip');
    this.project = project;
    this.trackId = trackId;
    this.clipId = clipId;
    this.splitTime = splitTime; // 时间线上的分割时间点
    this._secondClipId = null;
  }

  execute() {
    const track = this.project.getTrack(this.trackId);
    if (!track) return;
    const clip = track.getClip(this.clipId);
    if (!clip) return;
    if (this.splitTime <= clip.trackStart || this.splitTime >= clip.trackEnd) return;

    // 计算分割点
    const mediaSplitTime = clip.toMediaTime(this.splitTime);
    const originalOutPoint = clip.outPoint;
    const originalTrackStart = clip.trackStart;

    // 修改原clip为左半部分
    clip.outPoint = mediaSplitTime;

    // 创建右半部分clip
    const rightClip = new Clip({
      mediaId: clip.mediaId,
      trackId: this.trackId,
      trackStart: this.splitTime,
      inPoint: mediaSplitTime,
      outPoint: originalOutPoint,
    });
    this._secondClipId = rightClip.id;
    track.addClip(rightClip);
  }

  undo() {
    const track = this.project.getTrack(this.trackId);
    if (!track) return;
    const leftClip = track.getClip(this.clipId);
    const rightClip = track.getClip(this._secondClipId);
    if (!leftClip || !rightClip) return;

    // 恢复原clip的outPoint
    leftClip.outPoint = rightClip.outPoint;
    // 移除右半部分
    track.removeClip(this._secondClipId);
  }
}

/**
 * 移动片段命令
 */
export class MoveClipCommand extends Command {
  constructor(project, clipId, newTrackId, newTrackStart) {
    super('MoveClip');
    this.project = project;
    this.clipId = clipId;
    this.newTrackId = newTrackId;
    this.newTrackStart = newTrackStart;
    this._oldTrackId = null;
    this._oldTrackStart = null;
    this._clipData = null;
  }

  execute() {
    // 查找clip所在轨道
    let sourceTrack = null;
    for (const track of this.project.tracks) {
      if (track.getClip(this.clipId)) {
        sourceTrack = track;
        break;
      }
    }
    if (!sourceTrack) return;

    const clip = sourceTrack.getClip(this.clipId);
    this._oldTrackId = sourceTrack.id;
    this._oldTrackStart = clip.trackStart;
    this._clipData = clip.toJSON();

    // 如果只是同轨道移动
    if (sourceTrack.id === this.newTrackId) {
      clip.trackStart = this.newTrackStart;
      sourceTrack._sortClips();
    } else {
      // 跨轨道移动
      sourceTrack.removeClip(this.clipId);
      const targetTrack = this.project.getTrack(this.newTrackId);
      if (targetTrack) {
        clip.trackId = this.newTrackId;
        clip.trackStart = this.newTrackStart;
        targetTrack.addClip(clip);
      }
    }
  }

  undo() {
    // 查找clip当前所在轨道
    let currentTrack = null;
    for (const track of this.project.tracks) {
      if (track.getClip(this.clipId)) {
        currentTrack = track;
        break;
      }
    }
    if (!currentTrack) return;

    const clip = currentTrack.getClip(this.clipId);
    if (currentTrack.id !== this._oldTrackId) {
      currentTrack.removeClip(this.clipId);
      const oldTrack = this.project.getTrack(this._oldTrackId);
      if (oldTrack) {
        clip.trackId = this._oldTrackId;
        clip.trackStart = this._oldTrackStart;
        oldTrack.addClip(clip);
      }
    } else {
      clip.trackStart = this._oldTrackStart;
      currentTrack._sortClips();
    }
  }
}
