// ===== Preview Player =====
const bus = window.__bus;
const store = window.__store;
const createClip = window.__createClip;

const canvas = document.getElementById('preview-canvas');
const ctx = canvas.getContext('2d');
const btnPlay = document.getElementById('btn-play');
const btnSkipStart = document.getElementById('btn-skip-start');
const btnSkipEnd = document.getElementById('btn-skip-end');
const timeDisplay = document.getElementById('time-display');

let isPlaying = false;
let animFrameId = null;
let audioContext = null;
let activeAudioSources = {};
let lastPlayTime = 0;

// Hidden media elements cache
const mediaCache = new Map(); // assetId -> { element, type }

function getMediaElement(asset) {
  if (mediaCache.has(asset.id)) return mediaCache.get(asset.id);

  let element;
  if (asset.type === 'video') {
    element = document.createElement('video');
    element.src = asset.url;
    element.preload = 'auto';
    element.muted = true; // We handle audio separately
    element.playsInline = true;
  } else if (asset.type === 'audio') {
    element = document.createElement('audio');
    element.src = asset.url;
    element.preload = 'auto';
  } else if (asset.type === 'image') {
    element = new Image();
    element.src = asset.url;
  }

  document.getElementById('hidden-media').appendChild(element);
  mediaCache.set(asset.id, { element, type: asset.type });
  return { element, type: asset.type };
}

// ===== Playback Controls =====
btnPlay.addEventListener('click', () => bus.emit('playback:toggle'));
btnSkipStart.addEventListener('click', () => {
  stopPlayback();
  store.currentTime = 0;
});
btnSkipEnd.addEventListener('click', () => {
  stopPlayback();
  store.currentTime = store.duration;
});

bus.on('playback:toggle', () => {
  if (isPlaying) stopPlayback();
  else startPlayback();
});

bus.on('playback:stop', () => {
  if (isPlaying) stopPlayback();
});

function startPlayback() {
  if (store.duration <= 0) return;

  isPlaying = true;
  btnPlay.textContent = '⏸';
  lastPlayTime = performance.now();

  // Initialize audio context
  if (!audioContext) {
    audioContext = new (window.AudioContext || window.webkitAudioContext)();
  }
  if (audioContext.state === 'suspended') {
    audioContext.resume();
  }

  // Start audio for current clips
  startAudioAtTime(store.currentTime);

  // Start render loop
  renderLoop();
}

function stopPlayback() {
  isPlaying = false;
  btnPlay.textContent = '▶';

  if (animFrameId) {
    cancelAnimationFrame(animFrameId);
    animFrameId = null;
  }

  // Stop all audio
  stopAllAudio();

  // Pause all video elements
  mediaCache.forEach(({ element, type }) => {
    if (type === 'video') {
      element.pause();
    }
  });
}

function renderLoop() {
  if (!isPlaying) return;

  const now = performance.now();
  const delta = (now - lastPlayTime) / 1000;
  lastPlayTime = now;

  store.currentTime = store.currentTime + delta;

  // Check if we've reached the end
  if (store.currentTime >= store.duration) {
    store.currentTime = store.duration;
    stopPlayback();
    return;
  }

  renderFrame(store.currentTime);
  updateTimeDisplay();

  animFrameId = requestAnimationFrame(renderLoop);
}

function renderFrame(time) {
  const project = store.project;
  const w = canvas.width;
  const h = canvas.height;

  // Clear canvas
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, w, h);

  // Render tracks from bottom to top (later tracks overlay earlier ones)
  // Video tracks first, then text
  const videoTracks = project.tracks.filter(t => t.type === 'video');
  const textTrack = project.tracks.find(t => t.type === 'text');

  // Render video/image clips
  for (const track of videoTracks) {
    for (const clip of track.clips) {
      if (time < clip.startTime || time >= clip.startTime + clip.duration) continue;

      const asset = project.assets.find(a => a.id === clip.assetId);
      if (!asset) continue;

      const media = getMediaElement(asset);
      const { element } = media;

      // Calculate opacity for transitions
      let opacity = 1;
      const clipTime = time - clip.startTime;
      if (clip.transitionIn === 'fade') {
        opacity = Math.min(1, clipTime / clip.transitionDuration);
      } else if (clip.transitionIn === 'dissolve') {
        opacity = Math.min(1, clipTime / clip.transitionDuration);
      }

      ctx.globalAlpha = opacity;

      if (asset.type === 'video') {
        // Seek video to correct time
        const targetTime = clip.trimStart + clipTime;
        if (Math.abs(element.currentTime - targetTime) > 0.1) {
          element.currentTime = targetTime;
        }
        if (element.paused && isPlaying) {
          element.play().catch(() => {});
        }

        try {
          ctx.drawImage(element, 0, 0, w, h);
        } catch (e) {
          // Video not ready yet
        }
      } else if (asset.type === 'image') {
        try {
          ctx.drawImage(element, 0, 0, w, h);
        } catch (e) {}
      }

      ctx.globalAlpha = 1;
    }
  }

  // Render text overlays
  if (textTrack) {
    for (const clip of textTrack.clips) {
      if (time < clip.startTime || time >= clip.startTime + clip.duration) continue;
      if (!clip.text.content) continue;

      const clipTime = time - clip.startTime;
      let opacity = 1;
      if (clip.transitionIn === 'fade') {
        opacity = Math.min(1, clipTime / clip.transitionDuration);
      }

      ctx.globalAlpha = opacity;
      ctx.font = `bold ${clip.text.size}px ${clip.text.font}`;
      ctx.fillStyle = clip.text.color;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';

      // Add text shadow for readability
      ctx.shadowColor = 'rgba(0,0,0,0.7)';
      ctx.shadowBlur = 4;
      ctx.shadowOffsetX = 2;
      ctx.shadowOffsetY = 2;

      const x = (clip.text.x / 100) * w;
      const y = (clip.text.y / 100) * h;

      // Handle multi-line text
      const lines = clip.text.content.split('\n');
      const lineHeight = clip.text.size * 1.2;
      const totalHeight = lines.length * lineHeight;
      const startY = y - totalHeight / 2 + lineHeight / 2;

      lines.forEach((line, i) => {
        ctx.fillText(line, x, startY + i * lineHeight);
      });

      ctx.shadowColor = 'transparent';
      ctx.shadowBlur = 0;
      ctx.globalAlpha = 1;
    }
  }
}

// ===== Audio Playback =====
function startAudioAtTime(time) {
  stopAllAudio();

  const audioTracks = store.project.tracks.filter(t => t.type === 'audio');

  for (const track of audioTracks) {
    for (const clip of track.clips) {
      if (time < clip.startTime || time >= clip.startTime + clip.duration) continue;

      const asset = store.project.assets.find(a => a.id === clip.assetId);
      if (!asset) continue;

      const media = getMediaElement(asset);
      const { element } = media;

      const clipTime = time - clip.startTime;
      const offset = clip.trimStart + clipTime;
      const remaining = clip.duration - clipTime;

      element.currentTime = offset;
      element.volume = clip.volume;

      // Fade in
      if (clip.transitionIn === 'fade' && clipTime < clip.transitionDuration) {
        element.volume = clip.volume * (clipTime / clip.transitionDuration);
      }

      element.play().catch(() => {});
      activeAudioSources[clip.id] = element;
    }
  }
}

function stopAllAudio() {
  for (const [clipId, element] of Object.entries(activeAudioSources)) {
    try {
      element.pause();
    } catch (e) {}
  }
  activeAudioSources = {};
}

// ===== Time Display =====
function updateTimeDisplay() {
  const current = formatDisplayTime(store.currentTime);
  const total = formatDisplayTime(store.duration);
  timeDisplay.textContent = `${current} / ${total}`;
}

function formatDisplayTime(seconds) {
  if (!seconds || !isFinite(seconds)) return '00:00.00';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  const ms = Math.floor((seconds % 1) * 100);
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${String(ms).padStart(2, '0')}`;
}

bus.on('time:changed', () => {
  updateTimeDisplay();
  if (!isPlaying) {
    renderFrame(store.currentTime);
  }
});

bus.on('project:changed', () => {
  if (!isPlaying) {
    renderFrame(store.currentTime);
    updateTimeDisplay();
  }
});

// ===== Add text clip to text track =====
// Double-click on text track to add text
const textTrackEl = document.querySelector('.track[data-track-index="4"]');
if (textTrackEl) {
  textTrackEl.addEventListener('dblclick', (e) => {
    const rect = document.getElementById('tracks-container').getBoundingClientRect();
    const scrollEl = document.getElementById('timeline-scroll');
    const x = e.clientX - rect.left + scrollEl.scrollLeft;
    const pps = parseInt(document.getElementById('zoom-slider').value) || 60;
    const startTime = Math.max(0, x / pps);

    const clip = createClip(null, 'text', '文字', startTime, 3, 0);
    clip.text.content = '双击编辑文字';
    store.addClip(4, clip);
    store.selectClip(clip.id);
  });
}

// Initial render
updateTimeDisplay();
renderFrame(0);
