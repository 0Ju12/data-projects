import {
  LabError,
  KINDS,
  checkedRecord,
  koreaDay,
  plusDays,
  monday,
  answerDraft,
  weeklyDraft,
  isoDay,
  cleanText,
  safeURL,
  isComputedReview,
} from './lab-domain.js';
const reply = (value, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'private, no-store',
      'x-content-type-options': 'nosniff',
    },
  });
const validId = (s) => typeof s === 'string' && /^[a-zA-Z0-9_-]{1,100}$/.test(s);
async function readJSON(request, limit = 1200000) {
  const reader = request.body?.getReader();
  if (!reader) throw new LabError('입력 내용이 없습니다.');
  let length = 0,
    chunks = [];
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    length += value.byteLength;
    if (length > limit) {
      try {
        await reader.cancel();
      } catch {}
      throw new LabError('요청이 너무 큽니다. 백업은 나누어 가져와 주세요.', 413);
    }
    chunks.push(value);
  }
  const bytes = new Uint8Array(length);
  let pos = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, pos);
    pos += chunk.length;
  }
  try {
    const parsed = JSON.parse(new TextDecoder().decode(bytes));
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw Error();
    return parsed;
  } catch {
    throw new LabError('JSON 형식을 확인해 주세요.');
  }
}
function recordKey(owner, id) {
  return 'learning-documents/' + encodeURIComponent(owner) + '/' + id + '.json';
}
async function getStored(env, owner, id) {
  if (!validId(id)) throw new LabError('기록 주소가 올바르지 않습니다.');
  const object = await env.BUCKET.get(recordKey(owner, id));
  return object ? { object, value: await object.json() } : null;
}
function metaRecord(object, owner) {
  const m = object.customMetadata || {};
  return {
    id: object.key.slice(('learning-documents/' + encodeURIComponent(owner) + '/').length, -5),
    kind: m.kind,
    title: m.title,
    status: m.status,
    projectId: m.projectId || '',
    date: m.date,
    review_on: m.review_on || '',
    version: Number(m.version),
    created_at: m.created_at,
    updated_at: m.updated_at,
  };
}
async function listing(env, owner, cursor) {
  const page = await env.BUCKET.list({
    prefix: 'learning-documents/' + encodeURIComponent(owner) + '/',
    limit: 100,
    include: ['customMetadata'],
    ...(cursor ? { cursor } : {}),
  });
  return {
    items: page.objects.map((o) => metaRecord(o, owner)),
    cursor: page.truncated ? page.cursor : null,
    truncated: page.truncated,
  };
}
async function matchingMeta(env, owner, predicate) {
  let rows = [],
    cursor;
  const seen = new Set();
  do {
    const page = await listing(env, owner, cursor);
    rows.push(...page.items.filter(predicate));
    if (rows.length > 100)
      throw new LabError('이번 주 기록이 100개를 넘었습니다. 프로젝트별 회고를 작성해 주세요.', 413);
    cursor = page.cursor;
    if (cursor && seen.has(cursor)) throw new LabError('목록 페이지를 갱신하지 못했습니다. 다시 시도해 주세요.', 503);
    if (cursor) seen.add(cursor);
  } while (cursor);
  return rows;
}
async function saveRecord(env, owner, id, input, { importTag = null } = {}) {
  if (
    !input ||
    typeof input !== 'object' ||
    Array.isArray(input) ||
    !validId(id) ||
    !Number.isSafeInteger(input.version) ||
    input.version < 0
  )
    throw new LabError('기록 ID와 저장 버전을 확인해 주세요.');
  const body = checkedRecord(input.body),
    stored = await getStored(env, owner, id),
    old = stored?.value;
  if (importTag && old?.importTag === importTag) return { record: old.record, skipped: true };
  if ((old?.record.version || 0) !== input.version)
    throw new LabError('다른 기기에서 먼저 저장했습니다. 입력을 백업하고 최신 버전을 불러와 주세요.', 409);
  if (old && old.record.body.kind !== body.kind) throw new LabError('기록 종류는 변경할 수 없습니다.');
  if (
    old &&
    isComputedReview(old.record.body, id) &&
    ['projectId', 'period_start', 'period_end'].some((key) => body[key] !== old.record.body[key])
  )
    throw new LabError('자동 집계 회고의 프로젝트와 기간은 바꿀 수 없습니다. 다른 기간은 새 회고로 만들어 주세요.');
  if (old && body.status === 'archived' && old.record.body.status !== 'archived')
    body.archived_from = old.record.body.status;
  if (body.projectId) {
    const project = await getStored(env, owner, body.projectId);
    if (!project || project.value.record.body.kind !== 'project')
      throw new LabError('연결할 프로젝트가 없습니다. 프로젝트를 먼저 저장해 주세요.');
  }
  const now = new Date().toISOString(),
    record = { id, body, version: input.version + 1, created_at: old?.record.created_at || now, updated_at: now },
    history = [...(old?.history || []), { version: record.version, body: record.body, created_at: now }].slice(-20);
  const written = await env.BUCKET.put(
    recordKey(owner, id),
    JSON.stringify({
      record,
      history,
      ...(importTag ? { importTag } : old?.importTag ? { importTag: old.importTag } : {}),
    }),
    {
      onlyIf: stored ? { etagMatches: stored.object.etag } : { etagDoesNotMatch: '*' },
      httpMetadata: { contentType: 'application/json' },
      customMetadata: {
        kind: body.kind,
        title: body.title,
        status: body.status,
        projectId: body.projectId,
        date: body.date,
        review_on: body.review_on,
        version: String(record.version),
        created_at: record.created_at,
        updated_at: now,
      },
    },
  );
  if (!written)
    throw new LabError('동시에 다른 저장이 완료되었습니다. 현재 입력을 백업한 뒤 최신 버전을 불러와 주세요.', 409);
  return { record };
}
function portfolioMetadata(p) {
  try {
    if (
      !p ||
      p.schema_version !== 1 ||
      p.source_repository !== '0Ju12/0Ju12.github.io' ||
      !Array.isArray(p.projects) ||
      !Array.isArray(p.learning_notes) ||
      !/^[0-9a-f]{40}$/.test(p.source_sha || '')
    )
      return null;
    const projects = p.projects
      .slice(0, 100)
      .filter((x) => x && validId(x.id))
      .map((x) => ({
        id: x.id,
        title: cleanText(x.title, '프로젝트 제목', 180),
        summary: cleanText(x.summary, '프로젝트 설명', 2000),
        url: safeURL(x.url),
        repository: safeURL(x.repository),
        stack: Array.isArray(x.stack) ? x.stack.slice(0, 20).map((v) => cleanText(v, '기술', 100)) : [],
        links: Array.isArray(x.links) ? x.links.slice(0, 20).map(safeURL) : [],
        activity_id: validId(x.activity_id) ? x.activity_id : x.id,
      }));
    const learning_notes = p.learning_notes
      .slice(0, 100)
      .filter((x) => x && validId(x.id) && isoDay(x.date) && Number.isInteger(x.episode))
      .map((x) => ({
        id: x.id,
        title: cleanText(x.title, 'AI 글 제목', 300),
        summary: cleanText(x.summary, 'AI 글 설명', 2000),
        url: safeURL(x.url),
        date: x.date,
        episode: x.episode,
        label: '내 포트폴리오의 AI 기술 정리 · 공식 신규 발표와 구분',
      }));
    const links = {};
    for (const key of ['preparation', 'study', 'interview', 'practice_log', 'ai_notes', 'monitor'])
      links[key] = safeURL(p.links?.[key]);
    const study = {
      note_count: Number.isInteger(p.study?.note_count) && p.study.note_count >= 0 ? p.study.note_count : 0,
      url: safeURL(p.study?.url),
      highlights: Array.isArray(p.study?.highlights)
        ? p.study.highlights
            .slice(0, 10)
            .map((n) => ({ title: cleanText(n.title, '강의 제목', 100), url: safeURL(n.url) }))
        : [],
    };
    return {
      study,
      source_sha: p.source_sha,
      source_updated_at: p.source_updated_at,
      synced_at: p.synced_at,
      links,
      projects,
      learning_notes,
    };
  } catch {
    return null;
  }
}
let feedCache = null;
async function publicFeed(fetcher = fetch) {
  if (feedCache && feedCache.fetcher === fetcher && Date.now() - feedCache.time < 60000) return feedCache.value;
  const controller = new AbortController(),
    timer = setTimeout(() => controller.abort(), 10000);
  try {
    const r = await fetcher(
      'https://raw.githubusercontent.com/0Ju12/data-projects/main/api-watch/public/workspace.json',
      { headers: { Accept: 'application/json' }, signal: controller.signal },
    );
    if (!r.ok) throw Error('http');
    const data = await readJSON(r, 2500000);
    if (!Array.isArray(data.targets) || data.targets.length > 100 || !Array.isArray(data.ai_archive))
      throw Error('shape');
    const targets = data.targets.map((t) => {
      if (!t || !validId(t.slug) || typeof t.name !== 'string' || !t.spec || typeof t.spec !== 'object')
        throw Error('target');
      const source = t.last_run;
      return {
        slug: t.slug,
        name: t.name.slice(0, 200),
        spec: {
          category: String(t.spec.category || '기타').slice(0, 100),
          description: String(t.spec.description || '').slice(0, 2000),
          docs: safeURL(t.spec.docs),
        },
        last_run: source
          ? {
              status: ['healthy', 'warning', 'critical', 'unknown'].includes(source.status) ? source.status : 'unknown',
              checked_at:
                typeof source.checked_at === 'string' && Number.isFinite(Date.parse(source.checked_at))
                  ? source.checked_at
                  : null,
              duration_ms: Number.isFinite(source.duration_ms) && source.duration_ms >= 0 ? source.duration_ms : null,
            }
          : null,
      };
    });
    function brief(b) {
      if (
        !b ||
        typeof b.title !== 'string' ||
        typeof b.what !== 'string' ||
        !isoDay(b.date) ||
        !Array.isArray(b.sources)
      )
        return null;
      return {
        item_id: cleanText(b.item_id, '자료 ID', 250),
        title: cleanText(b.title, '자료 제목', 300),
        date: b.date,
        what: cleanText(b.what, '자료 설명', 2000),
        technology: cleanText(b.technology, '기술 이름', 200),
        label: cleanText(b.label, '자료 종류', 200),
        question: cleanText(b.question, '자료 질문', 2000),
        why_for_you: cleanText(b.why_for_you, '적용점', 3000),
        sources: b.sources
          .slice(0, 10)
          .map((v) => ({ title: cleanText(v?.title, '출처 이름', 200), url: safeURL(v?.url) }))
          .filter((v) => v.url),
        exercise: {
          steps: Array.isArray(b.exercise?.steps)
            ? b.exercise.steps.slice(0, 20).map((v) => cleanText(v, '실습', 2000))
            : [],
        },
      };
    }
    const archive = data.ai_archive.slice(0, 100).map(brief).filter(Boolean),
      known = new Set(targets.map((t) => t.slug));
    const incidents = (Array.isArray(data.incidents) ? data.incidents : [])
      .filter((i) => i && known.has(i.target) && !i.resolved_at)
      .slice(0, 200)
      .map((i) => ({
        id: String(i.id).slice(0, 80),
        target: i.target,
        message: cleanText(i.message, '관제 근거', 1000),
        opened_at: typeof i.opened_at === 'string' && Number.isFinite(Date.parse(i.opened_at)) ? i.opened_at : null,
      }));
    const value = {
      last_check_at:
        typeof data.last_check_at === 'string' && Number.isFinite(Date.parse(data.last_check_at))
          ? data.last_check_at
          : null,
      targets,
      incidents,
      ai_latest: brief(data.ai_latest) || archive[0] || null,
      ai_archive: archive,
      portfolio: portfolioMetadata(data.portfolio),
    };
    feedCache = { time: Date.now(), value, fetcher };
    return value;
  } catch (_) {
    throw new LabError('공개 관제 자료를 확인하지 못했습니다. 개인 기록은 계속 작성할 수 있습니다.', 502);
  } finally {
    clearTimeout(timer);
  }
}
async function remapId(importId, old) {
  const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(importId + ':' + old));
  return (
    'imp-' +
    Array.from(new Uint8Array(bytes))
      .slice(0, 16)
      .map((n) => n.toString(16).padStart(2, '0'))
      .join('')
  );
}
export async function labApi(request, env) {
  try {
    const owner = request.headers.get('oai-authenticated-user-id');
    if (!owner) return reply({ error: 'ChatGPT 계정으로 로그인해 주세요.' }, 401);
    if (!env.BUCKET) return reply({ error: '서버 저장소에 연결할 수 없습니다. 입력을 백업해 주세요.' }, 503);
    const path = new URL(request.url).pathname.replace(/\/$/, '');
    if (request.method !== 'GET') {
      if (
        request.headers.get('origin') !== new URL(request.url).origin ||
        !request.headers.get('content-type')?.startsWith('application/json')
      )
        return reply({ error: '요청 출처를 확인해 주세요.' }, 403);
    }
    if (path === '/api/learning/feed' && request.method === 'GET')
      return reply(await publicFeed(env.PUBLIC_FETCH || fetch));
    if (path === '/api/learning/records' && request.method === 'GET') {
      const cursor = new URL(request.url).searchParams.get('cursor');
      if (cursor && cursor.length > 3000) throw new LabError('페이지 주소 오류');
      return reply(await listing(env, owner, cursor));
    }
    if (path === '/api/learning/weekly' && request.method === 'POST') {
      const input = await readJSON(request),
        start = input.start || monday(),
        projectId = input.projectId || '';
      if (!isoDay(start) || monday(start) !== start) throw new LabError('회고 시작일은 월요일로 선택해 주세요.');
      if (projectId && !validId(projectId)) throw new LabError('프로젝트 선택 오류');
      const id = 'week-' + start.replaceAll('-', '') + '-' + (await remapId('weekly', projectId || 'all')).slice(4, 24),
        existing = await getStored(env, owner, id);
      if (existing) return reply({ record: existing.value.record, existing: true });
      const end = plusDays(start, 6),
        selected = await matchingMeta(
          env,
          owner,
          (r) =>
            ['experiment', 'incident', 'reading'].includes(r.kind) &&
            r.status !== 'archived' &&
            r.date >= start &&
            r.date <= end &&
            (!projectId || r.projectId === projectId),
        );
      if (selected.length > 100)
        throw new LabError('이번 주 기록이 100개를 넘었습니다. 프로젝트별 회고를 작성해 주세요.', 413);
      const records = [];
      for (const row of selected) {
        const stored = await getStored(env, owner, row.id);
        if (stored) records.push(stored.value.record);
      }
      const body = weeklyDraft(records, start, projectId);
      try {
        return reply(await saveRecord(env, owner, id, { version: 0, body }), 201);
      } catch (e) {
        if (e.status === 409) {
          const saved = await getStored(env, owner, id);
          if (saved) return reply({ record: saved.value.record, existing: true });
        }
        throw e;
      }
    }
    if (path === '/api/learning/draft-answer' && request.method === 'POST') {
      const input = await readJSON(request);
      if (
        !validId(input.id) ||
        !Array.isArray(input.sourceIds) ||
        input.sourceIds.length < 1 ||
        input.sourceIds.length > 3 ||
        new Set(input.sourceIds).size !== input.sourceIds.length
      )
        throw new LabError('기록 1~3개를 선택해 주세요.');
      const existing = await getStored(env, owner, input.id);
      if (existing) {
        const saved = existing.value.record;
        if (
          saved.body.kind !== 'answer' ||
          JSON.stringify(saved.body.sourceIds) !== JSON.stringify(input.sourceIds) ||
          saved.body.question !== (input.question || '문제를 해결하거나 개선한 경험을 설명해 주세요.')
        )
          throw new LabError(
            '이 요청으로 이미 만든 답변이 있습니다. 기존 답변에서 수정하거나 새 답변을 시작해 주세요.',
            409,
          );
        return reply({ record: saved, existing: true });
      }
      const records = [];
      for (const id of input.sourceIds) {
        const stored = await getStored(env, owner, id);
        if (!stored) throw new LabError('선택한 근거 기록을 찾을 수 없습니다.', 404);
        records.push(stored.value.record);
      }
      const body = answerDraft(records, input.question);
      return reply(await saveRecord(env, owner, input.id, { version: 0, body }), 201);
    }
    if (path === '/api/learning/import' && request.method === 'POST') {
      const input = await readJSON(request);
      if (
        !validId(input.importId) ||
        !Array.isArray(input.items) ||
        input.items.length > 100 ||
        input.items.some((i) => !i || typeof i !== 'object' || Array.isArray(i)) ||
        new Set(input.items.map((i) => i.id)).size !== input.items.length ||
        !Array.isArray(input.knownIds) ||
        input.knownIds.length > 10000 ||
        input.knownIds.some((id) => !validId(id))
      )
        throw new LabError('백업은 요청당 최대 100개 기록으로 가져옵니다.');
      const ids = new Set(input.knownIds),
        rows = [];
      for (const item of input.items) {
        if (!validId(item.id) || !ids.has(item.id)) throw new LabError('백업 기록 ID 오류');
        const body = checkedRecord(item.body);
        body.projectId = body.projectId && ids.has(body.projectId) ? await remapId(input.importId, body.projectId) : '';
        body.sourceIds = await Promise.all(
          body.sourceIds.filter((id) => ids.has(id)).map((id) => remapId(input.importId, id)),
        );
        if (body.provenance)
          body.provenance.sources = await Promise.all(
            body.provenance.sources
              .filter((s) => ids.has(s.id))
              .map(async (s) => ({
                ...s,
                id: await remapId(input.importId, s.id),
                version: input.knownVersions?.[s.id] === s.version ? 1 : 0,
              })),
          );
        rows.push({ id: await remapId(input.importId, item.id), body });
      }
      rows.sort((a, b) => (a.body.kind === 'project' ? 0 : 1) - (b.body.kind === 'project' ? 0 : 1));
      const completed = [],
        failed = [];
      for (const row of rows) {
        try {
          const r = await saveRecord(env, owner, row.id, { version: 0, body: row.body }, { importTag: input.importId });
          completed.push({ id: row.id, skipped: !!r.skipped });
        } catch (e) {
          failed.push({
            id: row.id,
            error:
              e.status === 409
                ? '다른 저장이 먼저 완료되어 덮어쓰지 않았습니다.'
                : e instanceof LabError
                  ? e.message
                  : '일시적인 저장 오류입니다. 같은 파일로 다시 시도해 주세요.',
          });
        }
      }
      return reply({ completed, failed }, failed.length ? 207 : 200);
    }
    const match = path.match(/^\/api\/learning\/records\/([a-zA-Z0-9_-]{1,100})(?:\/(versions|review))?$/);
    if (!match) return reply({ error: '요청 경로를 찾을 수 없습니다.' }, 404);
    const id = match[1],
      action = match[2];
    if (request.method === 'GET') {
      if (action === 'review') return reply({ error: '복습 완료는 POST 요청으로 기록합니다.' }, 405);
      const stored = await getStored(env, owner, id);
      if (!stored) return reply({ error: '기록을 찾을 수 없습니다.' }, 404);
      return reply(action === 'versions' ? { items: stored.value.history.slice().reverse() } : stored.value.record);
    }
    if (request.method === 'PUT' && !action) return reply(await saveRecord(env, owner, id, await readJSON(request)));
    if (request.method === 'POST' && action === 'review') {
      const input = await readJSON(request),
        stored = await getStored(env, owner, id);
      if (!stored) return reply({ error: '기록을 찾을 수 없습니다.' }, 404);
      const b = {
        ...stored.value.record.body,
        review_on: plusDays(koreaDay(), 7),
        review_count: (stored.value.record.body.review_count || 0) + 1,
      };
      return reply(await saveRecord(env, owner, id, { version: input.version, body: b }));
    }
    return reply({ error: '지원하지 않는 요청입니다.' }, 405);
  } catch (e) {
    return reply(
      {
        error:
          e instanceof LabError ? e.message : '서버 요청을 완료하지 못했습니다. 입력을 백업한 뒤 다시 시도해 주세요.',
      },
      e instanceof LabError ? e.status : 500,
    );
  }
}
