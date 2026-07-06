import { Command } from './CommandManager.js';
import { TextOverlay } from '../models/ProjectModel.js';

/**
 * 添加文字叠加命令
 */
export class AddTextOverlayCommand extends Command {
  constructor(project, trackId, clipId, overlayData) {
    super('AddTextOverlay');
    this.project = project;
    this.trackId = trackId;
    this.clipId = clipId;
    this.overlayData = overlayData;
    this._overlayId = null;
  }

  execute() {
    const track = this.project.getTrack(this.trackId);
    if (!track) return;
    const clip = track.getClip(this.clipId);
    if (!clip) return;
    const overlay = new TextOverlay(this.overlayData);
    this._overlayId = overlay.id;
    clip.addTextOverlay(overlay);
  }

  undo() {
    const track = this.project.getTrack(this.trackId);
    if (!track) return;
    const clip = track.getClip(this.clipId);
    if (clip && this._overlayId) {
      clip.removeTextOverlay(this._overlayId);
    }
  }
}

/**
 * 删除文字叠加命令
 */
export class RemoveTextOverlayCommand extends Command {
  constructor(project, trackId, clipId, overlayId) {
    super('RemoveTextOverlay');
    this.project = project;
    this.trackId = trackId;
    this.clipId = clipId;
    this.overlayId = overlayId;
    this._overlayData = null;
  }

  execute() {
    const track = this.project.getTrack(this.trackId);
    if (!track) return;
    const clip = track.getClip(this.clipId);
    if (!clip) return;
    const overlay = clip.textOverlays.find(t => t.id === this.overlayId);
    if (overlay) {
      this._overlayData = overlay.toJSON();
      clip.removeTextOverlay(this.overlayId);
    }
  }

  undo() {
    const track = this.project.getTrack(this.trackId);
    if (!track) return;
    const clip = track.getClip(this.clipId);
    if (clip && this._overlayData) {
      clip.addTextOverlay(TextOverlay.fromJSON(this._overlayData));
    }
  }
}

/**
 * 修改文字叠加命令
 */
export class UpdateTextOverlayCommand extends Command {
  constructor(project, trackId, clipId, overlayId, updates) {
    super('UpdateTextOverlay');
    this.project = project;
    this.trackId = trackId;
    this.clipId = clipId;
    this.overlayId = overlayId;
    this.updates = updates;
    this._oldValues = {};
  }

  execute() {
    const track = this.project.getTrack(this.trackId);
    if (!track) return;
    const clip = track.getClip(this.clipId);
    if (!clip) return;
    const overlay = clip.textOverlays.find(t => t.id === this.overlayId);
    if (!overlay) return;
    // 保存旧值
    for (const key of Object.keys(this.updates)) {
      this._oldValues[key] = overlay[key];
    }
    // 应用新值
    Object.assign(overlay, this.updates);
  }

  undo() {
    const track = this.project.getTrack(this.trackId);
    if (!track) return;
    const clip = track.getClip(this.clipId);
    if (!clip) return;
    const overlay = clip.textOverlays.find(t => t.id === this.overlayId);
    if (overlay) {
      Object.assign(overlay, this._oldValues);
    }
  }
}
