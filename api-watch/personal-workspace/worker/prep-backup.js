export function validatePreparationState(value) {
  if (
    !value ||
    typeof value !== 'object' ||
    Array.isArray(value) ||
    value.v !== 1 ||
    !value.q ||
    typeof value.q !== 'object' ||
    Array.isArray(value.q)
  )
    throw new Error('준비 공간의 백업 형식을 확인해 주세요.');
  let visited = 0;
  function walk(x, depth) {
    if (++visited > 150000 || depth > 30) throw new Error('백업의 구조가 너무 큽니다.');
    if (x && typeof x === 'object')
      for (const key of Object.keys(x)) {
        if (['__proto__', 'constructor', 'prototype'].includes(key))
          throw new Error('지원하지 않는 백업 키가 있습니다.');
        walk(x[key], depth + 1);
      }
  }
  walk(value, 0);
  if (
    value.study != null &&
    (value.study.v !== 1 || !value.study.q || typeof value.study.q !== 'object' || Array.isArray(value.study.q))
  )
    throw new Error('공부 기록의 백업 형식을 확인해 주세요.');
  return value;
}
export function preparationEncrypted(box) {
  return !!box && box.sync === 1 && typeof box.ct === 'string' && !box.plain;
}
export async function openPreparationBackup(box, password = '', cryptoAPI = globalThis.crypto) {
  if (!box || typeof box !== 'object' || Array.isArray(box)) throw new Error('JSON 백업을 선택해 주세요.');
  let state,
    app = box.app || '';
  if (box.sync === 1) {
    if (!['interview', 'study', 'prep'].includes(app))
      throw new Error('준비 공간·이전 공부·면접 앱의 백업을 선택해 주세요.');
    if (box.plain != null && box.ct != null)
      throw new Error('백업의 암호화 형식이 모호합니다. 원본에서 다시 내보내 주세요.');
    if (box.plain != null) state = box.plain;
    else {
      if (!password) throw new Error('암호를 입력해 주세요.');
      if (typeof password !== 'string' || password.length > 1024) throw new Error('암호 형식을 확인해 주세요.');
      function bytes(value, max) {
        if (
          typeof value !== 'string' ||
          value.length > max ||
          !/^[A-Za-z0-9+/]*={0,2}$/.test(value) ||
          value.length % 4
        )
          throw new Error('암호화된 백업의 형식을 확인해 주세요.');
        return Uint8Array.from(atob(value), (c) => c.charCodeAt(0));
      }
      const salt = bytes(box.salt, 32),
        iv = bytes(box.iv, 24),
        ct = bytes(box.ct, 14000000);
      if (salt.length !== 16 || iv.length !== 12 || ct.length < 16)
        throw new Error('암호화된 백업의 형식을 확인해 주세요.');
      try {
        const material = await cryptoAPI.subtle.importKey('raw', new TextEncoder().encode(password), 'PBKDF2', false, [
            'deriveKey',
          ]),
          key = await cryptoAPI.subtle.deriveKey(
            { name: 'PBKDF2', salt, iterations: 250000, hash: 'SHA-256' },
            material,
            { name: 'AES-GCM', length: 256 },
            false,
            ['decrypt'],
          ),
          raw = await cryptoAPI.subtle.decrypt({ name: 'AES-GCM', iv }, key, ct);
        state = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(raw));
      } catch {
        throw new Error('암호가 맞지 않거나 파일이 손상되었습니다. 원본 파일은 변경하지 않았습니다.');
      }
    }
  } else state = box;
  validatePreparationState(state);
  const studyOnly = app === 'study' || (!state.study && !state.answers && !state.essay && (state.read || state.exams));
  if (studyOnly) state = { v: 1, q: {}, study: state };
  return { state, app: studyOnly ? 'study' : app || 'interview' };
}

export async function preparationBackupId(raw) {
  const bytes = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(raw)));
  return (
    'prep-' +
    [...bytes]
      .slice(0, 16)
      .map((v) => v.toString(16).padStart(2, '0'))
      .join('')
  );
}
