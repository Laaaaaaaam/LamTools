// ===== Media Importer =====
const bus = window.__bus;
const store = window.__store;
const createAsset = window.__createAsset;
const createClip = window.__createClip;

const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const btnImport = document.getElementById('btn-import');
const assetList = document.getElementById('asset-list');
const hiddenMedia = document.getElementById('hidden-media');

// Import button
btnImport.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', (e) => {
  handleFiles(e.target.files);
  fileInput.value = '';
});

// Drag & drop on media pool
dropZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropZone.classList.add('drag-over');
});
dropZone.addEventListener('dragleave', () => {
  dropZone.classList.remove('drag-over');
});
dropZone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  handleFiles(e.dataTransfer.files);
});

// Also allow drop on the whole page
document.body.addEventListener('dragover', (e) => e.preventDefault());
document.body.addEventListener('drop', (e) => {
  e.preventDefault();
  if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
});

function getMediaType(file) {
  if (file.type.startsWith('video/')) return 'video';
  if (file.type.startsWith('audio/')) return 'audio';
  if (file.type.startsWith('image/')) return 'image';
  return null;
}

async function handleFiles(fileList) {
  for (const file of fileList) {
    const type = getMediaType(file);
    if (!type) continue;
    await importFile(file, type);
  }
}

function importFile(file, type) {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const asset = createAsset(file, url, type, 0, null);

    if (type === 'video') {
      const video = document.createElement('video');
      video.preload = 'metadata';
      video.src = url;
      video.addEventListener('loadedmetadata', () => {
        asset.duration = video.duration;
        // Generate thumbnail
        video.currentTime = Math.min(1, video.duration / 2);
        video.addEventListener('seeked', function onSeeked() {
          video.removeEventListener('seeked', onSeeked);
          const canvas = document.createElement('canvas');
          canvas.width = 80;
          canvas.height = 45;
          const ctx = canvas.getContext('2d');
          ctx.drawImage(video, 0, 0, 80, 45);
          asset.thumbnailUrl = canvas.toDataURL('image/jpeg', 0.7);
          store.addAsset(asset);
          resolve();
        });
      });
    } else if (type === 'audio') {
      const audio = document.createElement('audio');
      audio.preload = 'metadata';
      audio.src = url;
      audio.addEventListener('loadedmetadata', () => {
        asset.duration = audio.duration;
        store.addAsset(asset);
        resolve();
      });
    } else if (type === 'image') {
      const img = new Image();
      img.onload = () => {
        asset.duration = 5; // Default 5 seconds for images
        asset.thumbnailUrl = url;
        store.addAsset(asset);
        resolve();
      };
      img.src = url;
    }
  });
}

// Render asset list
bus.on('asset:added', (asset) => {
  renderAssetItem(asset);
});

bus.on('asset:removed', (assetId) => {
  const el = document.querySelector(`.asset-item[data-asset-id="${assetId}"]`);
  if (el) el.remove();
});

function renderAssetItem(asset) {
  const div = document.createElement('div');
  div.className = 'asset-item';
  div.dataset.assetId = asset.id;
  div.draggable = true;

  let iconHtml = '';
  if (asset.type === 'video') {
    if (asset.thumbnailUrl) {
      iconHtml = `<img class="asset-thumb" src="${asset.thumbnailUrl}" alt="">`;
    } else {
      iconHtml = `<div class="asset-icon video">🎬</div>`;
    }
  } else if (asset.type === 'audio') {
    iconHtml = `<div class="asset-icon audio">🎵</div>`;
  } else {
    if (asset.thumbnailUrl) {
      iconHtml = `<img class="asset-thumb" src="${asset.thumbnailUrl}" alt="">`;
    } else {
      iconHtml = `<div class="asset-icon image">🖼</div>`;
    }
  }

  const durStr = formatTime(asset.duration);
  div.innerHTML = `
    ${iconHtml}
    <div class="asset-info">
      <div class="asset-name" title="${asset.name}">${asset.name}</div>
      <div class="asset-duration">${durStr}</div>
    </div>
    <button class="asset-delete" title="删除">×</button>
  `;

  // Delete button
  div.querySelector('.asset-delete').addEventListener('click', (e) => {
    e.stopPropagation();
    store.removeAsset(asset.id);
  });

  // Drag to timeline
  div.addEventListener('dragstart', (e) => {
    e.dataTransfer.setData('text/plain', asset.id);
    e.dataTransfer.effectAllowed = 'copy';
  });

  // Double-click to add to first matching track
  div.addEventListener('dblclick', () => {
    addAssetToTimeline(asset);
  });

  assetList.appendChild(div);
}

function addAssetToTimeline(asset) {
  let trackIndex;
  if (asset.type === 'video' || asset.type === 'image') {
    // Find first video track with space at the end
    trackIndex = findTrackWithSpace(0, 1, asset.duration);
  } else if (asset.type === 'audio') {
    trackIndex = findTrackWithSpace(2, 3, asset.duration);
  }

  if (trackIndex === null) return;

  const startTime = getTrackEndTime(trackIndex);
  const clip = createClip(asset.id, asset.type, asset.name, startTime, asset.duration, 0);
  store.addClip(trackIndex, clip);
}

function findTrackWithSpace(fromIdx, toIdx, duration) {
  for (let i = fromIdx; i <= toIdx; i++) {
    return i; // Always use first available track for simplicity
  }
  return fromIdx;
}

function getTrackEndTime(trackIndex) {
  const track = store.project.tracks[trackIndex];
  let maxEnd = 0;
  for (const clip of track.clips) {
    const end = clip.startTime + clip.duration;
    if (end > maxEnd) maxEnd = end;
  }
  return maxEnd;
}

function formatTime(seconds) {
  if (!seconds || !isFinite(seconds)) return '00:00';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

// Expose for other modules
window.__mediaImporter = { addAssetToTimeline, formatTime };
