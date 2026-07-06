// ===== Export Pipeline =====
const bus = window.__bus;
const store = window.__store;

const exportDialog = document.getElementById('export-dialog');
const btnExport = document.getElementById('btn-export');
const btnExportCancel = document.getElementById('btn-export-cancel');
const btnExportStart = document.getElementById('btn-export-start');
const exportFormat = document.getElementById('export-format');
const exportResolution = document.getElementById('export-resolution');
const exportFps = document.getElementById('export-fps');
const exportProgressContainer = document.getElementById('export-progress-container');
const exportProgress = document.getElementById('export-progress');
const exportProgressText = document.getElementById('export-progress-text');

let isExporting = false;
let ffmpegInstance = null;

// Export-specific media cache
const exportMediaCache = new Map();

function getExportMediaElement(asset) {
  if (exportMediaCache.has(asset.id)) return exportMediaCache.get(asset.id);

  let element;
  if (asset.type === 'video') {
    element = document.createElement('video');
    element.src = asset.url;
    element.preload = 'auto';
    element.muted = true;
    element.playsInline = true;
  } else if (asset.type === 'image') {
    element = new Image();
    element.src = asset.url;
  }

  const entry = { element, type: asset.type };
  exportMediaCache.set(asset.id, entry);
  return entry;
}

// Show export dialog
btnExport.addEventListener('click', () => {
  if (store.duration <= 0) {
    alert('时间线上没有内容，请先添加媒体片段。');
    return;
  }
  exportDialog.classList.remove('hidden');
  exportProgressContainer.classList.add('hidden');
});

btnExportCancel.addEventListener('click', () => {
  exportDialog.classList.add('hidden');
});

// Start export
btnExportStart.addEventListener('click', async () => {
  if (isExporting) return;

  isExporting = true;
  document.body.classList.add('exporting');
  exportProgressContainer.classList.remove('hidden');
  btnExportStart.disabled = true;
  btnExportStart.textContent = '导出中...';

  try {
    await performExport();
  } catch (err) {
    console.error('Export failed:', err);
    alert('导出失败: ' + err.message);
  } finally {
    isExporting = false;
    document.body.classList.remove('exporting');
    btnExportStart.disabled = false;
    btnExportStart.textContent = '开始导出';
  }
});

async function performExport() {
  const format = exportFormat.value;
  const [width, height] = exportResolution.value.split('x').map(Number);
  const fps = parseInt(exportFps.value);
  const duration = store.duration;

  if (duration <= 0) throw new Error('时间线为空');

  // Try FFmpeg.wasm first, fallback to MediaRecorder
  try {
    await exportWithFFmpeg(format, width, height, fps, duration);
    return;
  } catch (e) {
    console.warn('FFmpeg export failed, falling back to Canvas recording:', e);
  }

  await exportWithMediaRecorder(format, width, height, fps, duration);
}

// ===== FFmpeg.wasm Export =====
async function exportWithFFmpeg(format, width, height, fps, duration) {
  const loaded = await loadFFmpeg();
  if (!loaded) throw new Error('FFmpeg 加载失败');

  // For now, delegate to MediaRecorder which is more reliable in browser
  throw new Error('Use MediaRecorder fallback');
}

async function loadFFmpeg() {
  if (ffmpegInstance) return ffmpegInstance;

  try {
    const script = document.createElement('script');
    script.src = 'https://unpkg.com/@ffmpeg/ffmpeg@0.12.10/dist/umd/ffmpeg.js';
    document.head.appendChild(script);

    await new Promise((resolve, reject) => {
      script.onload = resolve;
      script.onerror = reject;
      setTimeout(() => reject(new Error('Timeout')), 15000);
    });

    if (window.FFmpeg) {
      const { FFmpeg: FFmpegClass } = window.FFmpeg;
      ffmpegInstance = new FFmpegClass();
      await ffmpegInstance.load({
        coreURL: 'https://unpkg.com/@ffmpeg/core@0.12.6/dist/umd/ffmpeg-core.js',
      });
      return ffmpegInstance;
    }
  } catch (e) {
    console.warn('FFmpeg.wasm load failed:', e);
  }

  return null;
}

// ===== MediaRecorder Export =====
async function exportWithMediaRecorder(format, width, height, fps, duration) {
  // Stop any current playback via event
  bus.emit('playback:stop');

  // Create offscreen canvas
  const offCanvas = document.createElement('canvas');
  offCanvas.width = width;
  offCanvas.height = height;
  const offCtx = offCanvas.getContext('2d');

  // Set up MediaRecorder
  const stream = offCanvas.captureStream(fps);

  // Add audio track if there are audio clips
  const audioTracks = store.project.tracks.filter(t => t.type === 'audio');
  let audioCtx, audioDest;

  if (audioTracks.some(t => t.clips.length > 0)) {
    audioCtx = new AudioContext({ sampleRate: 44100 });
    audioDest = audioCtx.createMediaStreamDestination();

    for (const track of audioTracks) {
      for (const clip of track.clips) {
        const asset = store.project.assets.find(a => a.id === clip.assetId);
        if (!asset) continue;

        try {
          const response = await fetch(asset.url);
          const arrayBuffer = await response.arrayBuffer();
          const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer);

          const source = audioCtx.createBufferSource();
          source.buffer = audioBuffer;

          const gainNode = audioCtx.createGain();
          gainNode.gain.value = clip.volume;
          source.connect(gainNode);
          gainNode.connect(audioDest);

          source.start(clip.startTime, clip.trimStart, clip.duration);
        } catch (e) {
          console.warn('Failed to decode audio for export:', e);
        }
      }
    }

    audioDest.stream.getAudioTracks().forEach(track => {
      stream.addTrack(track);
    });
  }

  // Determine MIME type
  let mimeType = 'video/webm;codecs=vp9,opus';
  if (!MediaRecorder.isTypeSupported(mimeType)) {
    mimeType = 'video/webm;codecs=vp8,opus';
  }
  if (!MediaRecorder.isTypeSupported(mimeType)) {
    mimeType = 'video/webm';
  }

  const recorder = new MediaRecorder(stream, {
    mimeType,
    videoBitsPerSecond: 5000000,
  });

  const chunks = [];
  recorder.ondataavailable = (e) => {
    if (e.data.size > 0) chunks.push(e.data);
  };

  recorder.onstop = () => {
    const blob = new Blob(chunks, { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${store.project.name}.${format === 'mp4' ? 'webm' : format}`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);

    exportProgress.value = 100;
    exportProgressText.textContent = '100% - 导出完成!';

    setTimeout(() => {
      exportDialog.classList.add('hidden');
    }, 1500);
  };

  recorder.start(100);

  const totalFrames = Math.ceil(duration * fps);
  let currentFrame = 0;

  await new Promise((resolve) => {
    function renderExportFrame() {
      if (currentFrame >= totalFrames) {
        recorder.stop();
        if (audioCtx) audioCtx.close();
        resolve();
        return;
      }

      const time = currentFrame / fps;
      renderExportFrameAtTime(offCtx, time, width, height);

      currentFrame++;
      const progress = Math.round((currentFrame / totalFrames) * 100);
      exportProgress.value = progress;
      exportProgressText.textContent = `${progress}%`;

      setTimeout(renderExportFrame, 0);
    }

    renderExportFrame();
  });
}

function renderExportFrameAtTime(ctx, time, width, height) {
  const project = store.project;

  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, width, height);

  const videoTracks = project.tracks.filter(t => t.type === 'video');
  const textTrack = project.tracks.find(t => t.type === 'text');

  for (const track of videoTracks) {
    for (const clip of track.clips) {
      if (time < clip.startTime || time >= clip.startTime + clip.duration) continue;

      const asset = project.assets.find(a => a.id === clip.assetId);
      if (!asset) continue;

      const clipTime = time - clip.startTime;
      let opacity = 1;
      if (clip.transitionIn === 'fade' || clip.transitionIn === 'dissolve') {
        opacity = Math.min(1, clipTime / clip.transitionDuration);
      }

      ctx.globalAlpha = opacity;

      if (asset.type === 'video') {
        const media = getExportMediaElement(asset);
        const { element } = media;
        const targetTime = clip.trimStart + clipTime;
        if (Math.abs(element.currentTime - targetTime) > 0.05) {
          element.currentTime = targetTime;
        }
        try {
          ctx.drawImage(element, 0, 0, width, height);
        } catch (e) {}
      } else if (asset.type === 'image') {
        const media = getExportMediaElement(asset);
        try {
          ctx.drawImage(media.element, 0, 0, width, height);
        } catch (e) {}
      }

      ctx.globalAlpha = 1;
    }
  }

  // Render text
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
      ctx.shadowColor = 'rgba(0,0,0,0.7)';
      ctx.shadowBlur = 4;
      ctx.shadowOffsetX = 2;
      ctx.shadowOffsetY = 2;

      const x = (clip.text.x / 100) * width;
      const y = (clip.text.y / 100) * height;
      const lines = clip.text.content.split('\n');
      const lineHeight = clip.text.size * 1.2;
      const totalHeight = lines.length * lineHeight;
      const startY = y - totalHeight / 2 + lineHeight / 2;

      lines.forEach((line, i) => {
        ctx.fillText(line, x, startY + i * lineHeight);
      });

      ctx.shadowColor = 'transparent';
      ctx.globalAlpha = 1;
    }
  }
}

console.log('Export pipeline ready');
