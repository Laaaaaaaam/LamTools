let _counter = 0;

/** 生成唯一ID */
export function genId(prefix = 'id') {
  _counter++;
  return `${prefix}_${Date.now().toString(36)}_${_counter.toString(36)}`;
}
