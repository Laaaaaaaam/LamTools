// ===== EventBus =====
class EventBus {
  constructor() {
    this._listeners = {};
  }
  on(event, fn) {
    (this._listeners[event] ||= []).push(fn);
    return () => this.off(event, fn);
  }
  off(event, fn) {
    const list = this._listeners[event];
    if (list) this._listeners[event] = list.filter(f => f !== fn);
  }
  emit(event, data) {
    (this._listeners[event] || []).forEach(fn => fn(data));
  }
}

// ===== Data Models =====
let _idCounter = 0;
function uid() { return 'id_' + (++_idCounter) + '_' + Date.now().toString(36); }

function createProject(name = '未命名项目') {
  return {
    id: uid(),
    name,
    settings: { width: 1920, height: 1080, fps: 30 },
    assets: [],
    tracks: [
      { id: uid(), type: 'video', name: '视频', clips: [] },
      { id: uid(), type: 'video', name: '视频 2', clips: [] },
      { id: uid(), type: 'audio', name: '音频', clips: [] },
      { id: uid(), type: 'audio', name: '音频 2', clips: [] },
      { id: uid(), type: 'text', name: '文字', clips: [] },
    ],
  };
}

function createAsset(file, url, type, duration, thumbnailUrl) {
  return {
    id: uid(),
    type, // 'video' | 'audio' | 'image'
    name: file.name,
    file,
    url,
    duration,
    thumbnailUrl,
  };
}

function createClip(assetId, assetType, name, startTime, duration, trimStart = 0) {
  return {
    id: uid(),
    assetId,
    type: assetType, // 'video' | 'audio' | 'image' | 'text'
    name,
    startTime,       // position on timeline (seconds)
    duration,         // visible duration on timeline (seconds)
    trimStart,        // trim from source start (seconds)
    volume: 1,
    transitionIn: 'none',  // 'none' | 'fade' | 'dissolve'
    transitionDuration: 0.5,
    // Text overlay properties
    text: {
      content: '',
      font: 'Arial',
      size: 48,
      color: '#ffffff',
      x: 50,  // percentage
      y: 50,
    },
  };
}

// ===== ProjectStore =====
class ProjectStore {
  constructor(bus) {
    this._bus = bus;
    this._project = createProject();
    this._selectedClipId = null;
    this._currentTime = 0;
    this._history = [];
    this._historyIndex = -1;
  }

  get project() { return this._project; }
  get selectedClipId() { return this._selectedClipId; }
  get currentTime() { return this._currentTime; }

  set currentTime(t) {
    this._currentTime = Math.max(0, t);
    this._bus.emit('time:changed', this._currentTime);
  }

  get duration() {
    let maxEnd = 0;
    for (const track of this._project.tracks) {
      for (const clip of track.clips) {
        const end = clip.startTime + clip.duration;
        if (end > maxEnd) maxEnd = end;
      }
    }
    return maxEnd;
  }

  selectClip(clipId) {
    this._selectedClipId = clipId;
    this._bus.emit('clip:selected', clipId);
  }

  getSelectedClip() {
    if (!this._selectedClipId) return null;
    for (const track of this._project.tracks) {
      const clip = track.clips.find(c => c.id === this._selectedClipId);
      if (clip) return clip;
    }
    return null;
  }

  getTrackForClip(clipId) {
    for (const track of this._project.tracks) {
      if (track.clips.find(c => c.id === clipId)) return track;
    }
    return null;
  }

  addAsset(asset) {
    this._project.assets.push(asset);
    this._bus.emit('asset:added', asset);
  }

  removeAsset(assetId) {
    const idx = this._project.assets.findIndex(a => a.id === assetId);
    if (idx >= 0) {
      const asset = this._project.assets[idx];
      URL.revokeObjectURL(asset.url);
      if (asset.thumbnailUrl) URL.revokeObjectURL(asset.thumbnailUrl);
      this._project.assets.splice(idx, 1);
      // Remove clips referencing this asset
      for (const track of this._project.tracks) {
        track.clips = track.clips.filter(c => c.assetId !== assetId);
      }
      this._bus.emit('asset:removed', assetId);
      this._bus.emit('project:changed');
    }
  }

  addClip(trackIndex, clip) {
    this._saveHistory();
    this._project.tracks[trackIndex].clips.push(clip);
    this._bus.emit('clip:added', { trackIndex, clip });
    this._bus.emit('project:changed');
  }

  removeClip(clipId) {
    this._saveHistory();
    for (const track of this._project.tracks) {
      const idx = track.clips.findIndex(c => c.id === clipId);
      if (idx >= 0) {
        track.clips.splice(idx, 1);
        if (this._selectedClipId === clipId) {
          this._selectedClipId = null;
          this._bus.emit('clip:selected', null);
        }
        this._bus.emit('clip:removed', clipId);
        this._bus.emit('project:changed');
        return;
      }
    }
  }

  updateClip(clipId, updates) {
    this._saveHistory();
    for (const track of this._project.tracks) {
      const clip = track.clips.find(c => c.id === clipId);
      if (clip) {
        Object.assign(clip, updates);
        this._bus.emit('clip:updated', clip);
        this._bus.emit('project:changed');
        return;
      }
    }
  }

  splitClip(clipId, splitTime) {
    this._saveHistory();
    for (const track of this._project.tracks) {
      const idx = track.clips.findIndex(c => c.id === clipId);
      if (idx >= 0) {
        const clip = track.clips[idx];
        const relativeTime = splitTime - clip.startTime;
        if (relativeTime <= 0 || relativeTime >= clip.duration) return;

        const leftDuration = relativeTime;
        const rightDuration = clip.duration - relativeTime;
        const rightTrimStart = clip.trimStart + relativeTime;

        // Update left clip
        clip.duration = leftDuration;

        // Create right clip
        const rightClip = createClip(
          clip.assetId, clip.type, clip.name,
          splitTime, rightDuration, rightTrimStart
        );
        rightClip.volume = clip.volume;
        rightClip.transitionIn = clip.transitionIn;
        rightClip.transitionDuration = clip.transitionDuration;
        rightClip.text = { ...clip.text };

        track.clips.splice(idx + 1, 0, rightClip);
        this._bus.emit('clip:split', { leftClip: clip, rightClip });
        this._bus.emit('project:changed');
        return;
      }
    }
  }

  _saveHistory() {
    const snapshot = JSON.parse(JSON.stringify(this._project));
    this._history = this._history.slice(0, this._historyIndex + 1);
    this._history.push(snapshot);
    this._historyIndex = this._history.length - 1;
    if (this._history.length > 50) {
      this._history.shift();
      this._historyIndex--;
    }
  }

  undo() {
    if (this._historyIndex > 0) {
      this._historyIndex--;
      this._project = JSON.parse(JSON.stringify(this._history[this._historyIndex]));
      this._bus.emit('project:changed');
    }
  }

  redo() {
    if (this._historyIndex < this._history.length - 1) {
      this._historyIndex++;
      this._project = JSON.parse(JSON.stringify(this._history[this._historyIndex]));
      this._bus.emit('project:changed');
    }
  }
}

// ===== App Init =====
const bus = new EventBus();
const store = new ProjectStore(bus);

// Expose globally for module access
window.__bus = bus;
window.__store = store;
window.__createClip = createClip;
window.__createAsset = createAsset;
window.__createProject = createProject;

// Import and init modules
import './media-importer.js';
import './timeline-engine.js';
import './preview-player.js';
import './export-pipeline.js';

// ===== Keyboard Shortcuts =====
document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;

  switch (e.code) {
    case 'Space':
      e.preventDefault();
      bus.emit('playback:toggle');
      break;
    case 'KeyS':
      if (!e.ctrlKey && !e.metaKey) {
        bus.emit('clip:split:request');
      }
      break;
    case 'Delete':
    case 'Backspace':
      if (store.selectedClipId) {
        store.removeClip(store.selectedClipId);
      }
      break;
    case 'KeyZ':
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        if (e.shiftKey) store.redo();
        else store.undo();
      }
      break;
    case 'Home':
      store.currentTime = 0;
      break;
    case 'End':
      store.currentTime = store.duration;
      break;
    case 'ArrowLeft':
      store.currentTime = Math.max(0, store.currentTime - (e.shiftKey ? 1 : 0.1));
      break;
    case 'ArrowRight':
      store.currentTime = Math.min(store.duration, store.currentTime + (e.shiftKey ? 1 : 0.1));
      break;
  }
});

// Toolbar buttons
document.getElementById('btn-undo').addEventListener('click', () => store.undo());
document.getElementById('btn-redo').addEventListener('click', () => store.redo());
document.getElementById('btn-split').addEventListener('click', () => bus.emit('clip:split:request'));
document.getElementById('btn-delete').addEventListener('click', () => {
  if (store.selectedClipId) store.removeClip(store.selectedClipId);
});

console.log('🎬 VideoForge initialized');
