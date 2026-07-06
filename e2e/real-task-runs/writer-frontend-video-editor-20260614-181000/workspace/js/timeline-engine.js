// ===== Timeline Engine =====
const bus = window.__bus;
const store = window.__store;
const createClip = window.__createClip;

const tracksContainer = document.getElementById('tracks-container');
const timeRuler = document.getElementById('time-ruler');
const timelineScroll = document.getElementById('timeline-scroll');
const playhead = document.getElementById('playhead');
const zoomSlider = document.getElementById('zoom-slider');

let pixelsPerSecond = 60; // zoom level
let isDraggingClip = false;
let isDraggingPlayhead = false;
let isTrimming = false;
let trimSide = null;
let dragData = null;

// ===== Zoom =====
zoomSlider.addEventListener('input', () => {
  pixelsPerSecond = parseInt(zoomSlider.value);
  renderTimeline();
});

// ===== Render Timeline =====
function renderTimeline() {
  renderRuler();
  renderClips();
  updatePlayheadPosition();
}

function renderRuler() {
  timeRuler.innerHTML = '';
  const totalDuration = Math.max(store.duration + 5, 10);
  const width = totalDuration * pixelsPerSecond;
  timeRuler.style.width = width + 'px';

  // Determine tick interval
  let tickInterval = 1;
  if (pixelsPerSecond < 20) tickInterval = 5;
  else if (pixelsPerSecond < 40) tickInterval = 2;
  else if (pixelsPerSecond > 150) tickInterval = 0.5;

  for (let t = 0; t <= totalDuration; t += tickInterval) {
    const x = t * pixelsPerSecond;
    const isMajor = t % (tickInterval * 5) === 0 || tickInterval >= 1;

    const tick = document.createElement('div');
    tick.className = 'ruler-tick' + (isMajor ? ' major' : '');
    tick.style.left = x + 'px';
    timeRuler.appendChild(tick);

    if (isMajor || tickInterval >= 1) {
      const label = document.createElement('span');
      label.className = 'ruler-label';
      label.style.left = x + 'px';
      label.textContent = formatTimeLabel(t);
      timeRuler.appendChild(label);
    }
  }
}

function formatTimeLabel(seconds) {
  const m = Math.floor(seconds / 60);
  const s = (seconds % 60).toFixed(tickIntervalHasDecimal() ? 1 : 0);
  return m > 0 ? `${m}:${s.padStart(2, '0')}` : `${s}s`;
}

function tickIntervalHasDecimal() {
  return pixelsPerSecond > 150;
}

function renderClips() {
  // Clear existing clips
  tracksContainer.querySelectorAll('.clip').forEach(el => el.remove());

  const totalDuration = Math.max(store.duration + 5, 10);
  tracksContainer.style.width = (totalDuration * pixelsPerSecond) + 'px';

  store.project.tracks.forEach((track, trackIndex) => {
    const trackEl = tracksContainer.querySelector(`.track[data-track-index="${trackIndex}"]`);
    if (!trackEl) return;

    track.clips.forEach(clip => {
      const el = createClipElement(clip, trackIndex);
      trackEl.appendChild(el);
    });
  });
}

function createClipElement(clip, trackIndex) {
  const el = document.createElement('div');
  el.className = `clip ${clip.type}`;
  el.dataset.clipId = clip.id;
  el.dataset.trackIndex = trackIndex;

  const left = clip.startTime * pixelsPerSecond;
  const width = clip.duration * pixelsPerSecond;
  el.style.left = left + 'px';
  el.style.width = Math.max(width, 20) + 'px';

  if (clip.id === store.selectedClipId) {
    el.classList.add('selected');
  }

  // Clip name
  const nameSpan = document.createElement('span');
  nameSpan.className = 'clip-name';
  nameSpan.textContent = clip.name;
  el.appendChild(nameSpan);

  // Trim handles
  const leftHandle = document.createElement('div');
  leftHandle.className = 'trim-handle left';
  el.appendChild(leftHandle);

  const rightHandle = document.createElement('div');
  rightHandle.className = 'trim-handle right';
  el.appendChild(rightHandle);

  // Transition indicator
  if (clip.transitionIn !== 'none') {
    const transEl = document.createElement('div');
    transEl.className = 'transition-indicator';
    transEl.style.left = '0';
    transEl.style.width = (clip.transitionDuration * pixelsPerSecond) + 'px';
    el.appendChild(transEl);
  }

  // Click to select
  el.addEventListener('mousedown', (e) => {
    if (e.target.classList.contains('trim-handle')) return;
    e.stopPropagation();
    store.selectClip(clip.id);

    // Start drag
    isDraggingClip = true;
    dragData = {
      clipId: clip.id,
      trackIndex,
      startX: e.clientX,
      originalStartTime: clip.startTime,
    };
  });

  // Trim handles
  leftHandle.addEventListener('mousedown', (e) => {
    e.stopPropagation();
    isTrimming = true;
    trimSide = 'left';
    dragData = {
      clipId: clip.id,
      trackIndex,
      startX: e.clientX,
      originalStartTime: clip.startTime,
      originalDuration: clip.duration,
      originalTrimStart: clip.trimStart,
    };
  });

  rightHandle.addEventListener('mousedown', (e) => {
    e.stopPropagation();
    isTrimming = true;
    trimSide = 'right';
    dragData = {
      clipId: clip.id,
      trackIndex,
      startX: e.clientX,
      originalStartTime: clip.startTime,
      originalDuration: clip.duration,
      originalTrimStart: clip.trimStart,
    };
  });

  return el;
}

// ===== Mouse Move / Up for drag & trim =====
document.addEventListener('mousemove', (e) => {
  if (isDraggingClip && dragData) {
    const dx = e.clientX - dragData.startX;
    const dt = dx / pixelsPerSecond;
    const newStart = Math.max(0, dragData.originalStartTime + dt);
    store.updateClip(dragData.clipId, { startTime: newStart });
  }

  if (isTrimming && dragData) {
    const dx = e.clientX - dragData.startX;
    const dt = dx / pixelsPerSecond;

    if (trimSide === 'left') {
      const newTrimStart = Math.max(0, dragData.originalTrimStart + dt);
      const newDuration = dragData.originalDuration - (newTrimStart - dragData.originalTrimStart);
      const newStartTime = dragData.originalStartTime + (newTrimStart - dragData.originalTrimStart);
      if (newDuration > 0.1) {
        store.updateClip(dragData.clipId, {
          trimStart: newTrimStart,
          duration: newDuration,
          startTime: newStartTime,
        });
      }
    } else {
      const newDuration = Math.max(0.1, dragData.originalDuration + dt);
      store.updateClip(dragData.clipId, { duration: newDuration });
    }
  }

  if (isDraggingPlayhead) {
    const rect = tracksContainer.getBoundingClientRect();
    const x = e.clientX - rect.left + timelineScroll.scrollLeft;
    const time = Math.max(0, x / pixelsPerSecond);
    store.currentTime = time;
  }
});

document.addEventListener('mouseup', () => {
  isDraggingClip = false;
  isTrimming = false;
  trimSide = null;
  isDraggingPlayhead = false;
  dragData = null;
});

// ===== Playhead drag =====
timeRuler.addEventListener('mousedown', (e) => {
  isDraggingPlayhead = true;
  const rect = tracksContainer.getBoundingClientRect();
  const x = e.clientX - rect.left + timelineScroll.scrollLeft;
  store.currentTime = Math.max(0, x / pixelsPerSecond);
});

tracksContainer.addEventListener('mousedown', (e) => {
  if (e.target === tracksContainer || e.target.classList.contains('track')) {
    const rect = tracksContainer.getBoundingClientRect();
    const x = e.clientX - rect.left + timelineScroll.scrollLeft;
    store.currentTime = Math.max(0, x / pixelsPerSecond);
    store.selectClip(null);
  }
});

// ===== Drop from media pool =====
tracksContainer.querySelectorAll('.track').forEach(trackEl => {
  trackEl.addEventListener('dragover', (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
    trackEl.classList.add('drag-over');
  });

  trackEl.addEventListener('dragleave', () => {
    trackEl.classList.remove('drag-over');
  });

  trackEl.addEventListener('drop', (e) => {
    e.preventDefault();
    trackEl.classList.remove('drag-over');

    const assetId = e.dataTransfer.getData('text/plain');
    const asset = store.project.assets.find(a => a.id === assetId);
    if (!asset) return;

    const trackIndex = parseInt(trackEl.dataset.trackIndex);
    const track = store.project.tracks[trackIndex];

    // Check type compatibility
    if (track.type === 'video' && asset.type === 'audio') return;
    if (track.type === 'audio' && (asset.type === 'video' || asset.type === 'image')) return;

    // Calculate start time from drop position
    const rect = tracksContainer.getBoundingClientRect();
    const x = e.clientX - rect.left + timelineScroll.scrollLeft;
    const startTime = Math.max(0, x / pixelsPerSecond);

    const clip = createClip(asset.id, asset.type, asset.name, startTime, asset.duration, 0);
    store.addClip(trackIndex, clip);
  });
});

// ===== Update playhead position =====
function updatePlayheadPosition() {
  const x = store.currentTime * pixelsPerSecond;
  playhead.style.left = x + 'px';
}

bus.on('time:changed', () => {
  updatePlayheadPosition();
  // Auto-scroll to keep playhead visible
  const x = store.currentTime * pixelsPerSecond;
  const scrollLeft = timelineScroll.scrollLeft;
  const viewWidth = timelineScroll.clientWidth;
  if (x < scrollLeft || x > scrollLeft + viewWidth - 20) {
    timelineScroll.scrollLeft = x - 100;
  }
});

// ===== Re-render on project changes =====
bus.on('project:changed', () => renderTimeline());
bus.on('clip:selected', () => {
  // Update selection visual
  tracksContainer.querySelectorAll('.clip').forEach(el => {
    el.classList.toggle('selected', el.dataset.clipId === store.selectedClipId);
  });
  updatePropertyPanel();
});

// ===== Split clip =====
bus.on('clip:split:request', () => {
  if (store.selectedClipId) {
    store.splitClip(store.selectedClipId, store.currentTime);
  }
});

// ===== Property Panel =====
const propClipName = document.getElementById('prop-clip-name');
const propStart = document.getElementById('prop-start');
const propDuration = document.getElementById('prop-duration');
const propTrimStart = document.getElementById('prop-trim-start');
const propVolume = document.getElementById('prop-volume');
const volumeValue = document.getElementById('volume-value');
const propTransitionIn = document.getElementById('prop-transition-in');
const propTransitionDuration = document.getElementById('prop-transition-duration');
const textProps = document.getElementById('text-props');
const propTextContent = document.getElementById('prop-text-content');
const propTextFont = document.getElementById('prop-text-font');
const propTextSize = document.getElementById('prop-text-size');
const propTextColor = document.getElementById('prop-text-color');
const propTextX = document.getElementById('prop-text-x');
const propTextY = document.getElementById('prop-text-y');
const noSelection = document.getElementById('no-selection');
const clipProperties = document.getElementById('clip-properties');

function updatePropertyPanel() {
  const clip = store.getSelectedClip();
  if (!clip) {
    noSelection.classList.remove('hidden');
    clipProperties.classList.add('hidden');
    return;
  }

  noSelection.classList.add('hidden');
  clipProperties.classList.remove('hidden');

  propClipName.value = clip.name;
  propStart.value = clip.startTime.toFixed(2);
  propDuration.value = clip.duration.toFixed(2);
  propTrimStart.value = clip.trimStart.toFixed(2);
  propVolume.value = clip.volume;
  volumeValue.textContent = Math.round(clip.volume * 100) + '%';
  propTransitionIn.value = clip.transitionIn;
  propTransitionDuration.value = clip.transitionDuration;

  // Text properties
  if (clip.type === 'text' || clip.type === 'video' || clip.type === 'image') {
    textProps.classList.remove('hidden');
    propTextContent.value = clip.text.content;
    propTextFont.value = clip.text.font;
    propTextSize.value = clip.text.size;
    propTextColor.value = clip.text.color;
    propTextX.value = clip.text.x;
    propTextY.value = clip.text.y;
  } else {
    textProps.classList.add('hidden');
  }
}

// Property change handlers
propStart.addEventListener('change', () => {
  const clip = store.getSelectedClip();
  if (clip) store.updateClip(clip.id, { startTime: parseFloat(propStart.value) || 0 });
});

propDuration.addEventListener('change', () => {
  const clip = store.getSelectedClip();
  if (clip) store.updateClip(clip.id, { duration: Math.max(0.1, parseFloat(propDuration.value) || 0.1) });
});

propTrimStart.addEventListener('change', () => {
  const clip = store.getSelectedClip();
  if (clip) store.updateClip(clip.id, { trimStart: Math.max(0, parseFloat(propTrimStart.value) || 0) });
});

propVolume.addEventListener('input', () => {
  const clip = store.getSelectedClip();
  if (clip) {
    store.updateClip(clip.id, { volume: parseFloat(propVolume.value) });
    volumeValue.textContent = Math.round(propVolume.value * 100) + '%';
  }
});

propTransitionIn.addEventListener('change', () => {
  const clip = store.getSelectedClip();
  if (clip) store.updateClip(clip.id, { transitionIn: propTransitionIn.value });
});

propTransitionDuration.addEventListener('change', () => {
  const clip = store.getSelectedClip();
  if (clip) store.updateClip(clip.id, { transitionDuration: parseFloat(propTransitionDuration.value) || 0.5 });
});

// Text property handlers
propTextContent.addEventListener('input', () => {
  const clip = store.getSelectedClip();
  if (clip) store.updateClip(clip.id, { text: { ...clip.text, content: propTextContent.value } });
});

propTextFont.addEventListener('change', () => {
  const clip = store.getSelectedClip();
  if (clip) store.updateClip(clip.id, { text: { ...clip.text, font: propTextFont.value } });
});

propTextSize.addEventListener('change', () => {
  const clip = store.getSelectedClip();
  if (clip) store.updateClip(clip.id, { text: { ...clip.text, size: parseInt(propTextSize.value) || 48 } });
});

propTextColor.addEventListener('input', () => {
  const clip = store.getSelectedClip();
  if (clip) store.updateClip(clip.id, { text: { ...clip.text, color: propTextColor.value } });
});

propTextX.addEventListener('change', () => {
  const clip = store.getSelectedClip();
  if (clip) store.updateClip(clip.id, { text: { ...clip.text, x: parseInt(propTextX.value) || 50 } });
});

propTextY.addEventListener('change', () => {
  const clip = store.getSelectedClip();
  if (clip) store.updateClip(clip.id, { text: { ...clip.text, y: parseInt(propTextY.value) || 50 } });
});

bus.on('clip:updated', () => updatePropertyPanel());

// Initial render
renderTimeline();
