/**
 * 导出Worker - 预留FFmpeg.wasm Worker脚本
 * 当前导出使用MediaRecorder，此Worker为未来FFmpeg增强预留
 */

// FFmpeg.wasm 加载（当可用时）
let ffmpeg = null;

async function loadFFmpeg() {
  try {
    const { createFFmpeg } = await import('https://unpkg.com/@ffmpeg/ffmpeg@0.11.6/dist/ffmpeg.min.js');
    ffmpeg = createFFmpeg({ log: true });
    await ffmpeg.load();
    return true;
  } catch (e) {
    console.warn('FFmpeg.wasm not available:', e);
    return false;
  }
}

self.onmessage = async function(e) {
  const { type, data } = e.data;

  switch (type) {
    case 'load':
      const loaded = await loadFFmpeg();
      self.postMessage({ type: 'loaded', success: loaded });
      break;

    case 'export':
      // 预留：接收帧数据进行FFmpeg编码
      self.postMessage({ type: 'progress', percent: 0 });
      break;

    case 'cancel':
      self.postMessage({ type: 'cancelled' });
      break;
  }
};
