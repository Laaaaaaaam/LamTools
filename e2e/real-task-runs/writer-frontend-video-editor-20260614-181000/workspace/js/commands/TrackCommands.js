import { Command } from './CommandManager.js';
import { Track } from '../models/ProjectModel.js';

/**
 * 添加轨道命令
 */
export class AddTrackCommand extends Command {
  constructor(project, type, name) {
    super('AddTrack');
    this.project = project;
    this.type = type;
    this.name = name;
    this._trackId = null;
  }

  execute() {
    const track = new Track({ type: this.type, name: this.name });
    this._trackId = track.id;
    this.project.addTrack(track);
  }

  undo() {
    if (this._trackId) {
      this.project.removeTrack(this._trackId);
    }
  }
}

/**
 * 删除轨道命令
 */
export class RemoveTrackCommand extends Command {
  constructor(project, trackId) {
    super('RemoveTrack');
    this.project = project;
    this.trackId = trackId;
    this._trackData = null;
  }

  execute() {
    const track = this.project.getTrack(this.trackId);
    if (track) {
      this._trackData = track.toJSON();
      this.project.removeTrack(this.trackId);
    }
  }

  undo() {
    if (this._trackData) {
      const track = Track.fromJSON(this._trackData);
      this.project.tracks.push(track);
    }
  }
}

/**
 * 静音/取消静音轨道命令
 */
export class ToggleMuteTrackCommand extends Command {
  constructor(project, trackId) {
    super('ToggleMuteTrack');
    this.project = project;
    this.trackId = trackId;
    this._oldMuted = null;
  }

  execute() {
    const track = this.project.getTrack(this.trackId);
    if (track) {
      this._oldMuted = track.muted;
      track.muted = !track.muted;
    }
  }

  undo() {
    const track = this.project.getTrack(this.trackId);
    if (track) {
      track.muted = this._oldMuted;
    }
  }
}
