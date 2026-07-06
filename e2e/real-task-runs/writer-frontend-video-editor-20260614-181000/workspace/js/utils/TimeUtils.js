/**
 * 时间工具函数
 */

/** 秒数 -> 时间码字符串 HH:MM:SS.mmm */
export function formatTimecode(seconds) {
  if (seconds == null || isNaN(seconds)) return '00:00:00.000';
  const s = Math.max(0, seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  const ms = Math.round((s % 1) * 1000);
  return `${pad(h)}:${pad(m)}:${pad(sec)}.${pad3(ms)}`;
}

/** 秒数 -> 简短显示 MM:SS */
export function formatTimeShort(seconds) {
  if (seconds == null || isNaN(seconds)) return '00:00';
  const s = Math.max(0, seconds);
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${pad(m)}:${pad(sec)}`;
}

/** 像素位置 -> 时间（基于缩放） */
export function pxToTime(px, zoom) {
  return px / zoom;
}

/** 时间 -> 像素位置（基于缩放） */
export function timeToPx(time, zoom) {
  return time * zoom;
}

/** 限制值在范围内 */
export function clamp(val, min, max) {
  return Math.max(min, Math.min(max, val));
}

function pad(n) {
  return String(n).padStart(2, '0');
}

function pad3(n) {
  return String(n).padStart(3, '0');
}
