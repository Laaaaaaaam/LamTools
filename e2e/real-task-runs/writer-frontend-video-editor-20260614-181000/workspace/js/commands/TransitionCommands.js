import { Command } from './CommandManager.js';
import { Transition } from '../models/ProjectModel.js';

/**
 * 添加转场命令
 */
export class AddTransitionCommand extends Command {
  constructor(project, trackId, clipId, type, duration) {
    super('AddTransition');
    this.project = project;
    this.trackId = trackId;
    this.clipId = clipId;
    this.type = type;
    this.duration = duration;
    this._transitionId = null;
  }

  execute() {
    const track = this.project.getTrack(this.trackId);
    if (!track) return;
    const clip = track.getClip(this.clipId);
    if (!clip) return;
    const trans = new Transition({ type: this.type, duration: this.duration, clipId: this.clipId });
    this._transitionId = trans.id;
    clip.addTransition(trans);
  }

  undo() {
    const track = this.project.getTrack(this.trackId);
    if (!track) return;
    const clip = track.getClip(this.clipId);
    if (clip && this._transitionId) {
      clip.removeTransition(this._transitionId);
    }
  }
}

/**
 * 删除转场命令
 */
export class RemoveTransitionCommand extends Command {
  constructor(project, trackId, clipId, transitionId) {
    super('RemoveTransition');
    this.project = project;
    this.trackId = trackId;
    this.clipId = clipId;
    this.transitionId = transitionId;
    this._transData = null;
  }

  execute() {
    const track = this.project.getTrack(this.trackId);
    if (!track) return;
    const clip = track.getClip(this.clipId);
    if (!clip) return;
    const trans = clip.transitions.find(t => t.id === this.transitionId);
    if (trans) {
      this._transData = trans.toJSON();
      clip.removeTransition(this.transitionId);
    }
  }

  undo() {
    const track = this.project.getTrack(this.trackId);
    if (!track) return;
    const clip = track.getClip(this.clipId);
    if (clip && this._transData) {
      clip.addTransition(Transition.fromJSON(this._transData));
    }
  }
}
