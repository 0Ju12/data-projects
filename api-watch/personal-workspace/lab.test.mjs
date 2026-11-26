import { test } from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';
import { labApi } from './worker/lab-api.js';
import {
  LabError,
  checkedRecord,
  freshRecord,
  weeklyDraft,
  answerDraft,
  markdownRecord,
  koreaDay,
  monday,
  plusDays,
} from './worker/lab-domain.js';
function database() {
  const store = new Map();
  let next = 0;
  return {
    store,
    BUCKET: {
      async get(key) {
        const v = store.get(key);
        return v ? { etag: v.etag, json: async () => JSON.parse(v.text) } : null;
      },
      async put(key, text, options) {
        const v = store.get(key);
        if (options.onlyIf?.etagDoesNotMatch === '*' && v) return null;
        if (options.onlyIf?.etagMatches && v?.etag !== options.onlyIf.etagMatches) return null;
        const etag = String(++next);
        store.set(key, { text, etag, metadata: options.customMetadata });
        return { etag };
      },
      async delete(key) {
        store.delete(key);
      },
      async list({ prefix, limit = 100, cursor }) {
        const all = [...store.entries()]
            .filter(([key]) => key.startsWith(prefix))
            .sort((a, b) => a[0].localeCompare(b[0])),
          start = Number(cursor || 0),
          rows = all.slice(start, start + limit),
          truncated = start + limit < all.length;
        return {
          objects: rows.map(([key, v]) => ({ key, customMetadata: v.metadata })),
          truncated,
          cursor: truncated ? String(start + limit) : undefined,
        };
      },
    },
  };
}
const request = (path, method = 'GET', data, owner = 'owner-A', origin = 'https://lab.test') =>
  new Request('https://lab.test' + path, {
    method,
    headers: {
      ...(owner ? { 'oai-authenticated-user-id': owner } : {}),
      ...(method !== 'GET' ? { origin: origin, 'content-type': 'application/json' } : {}),
    },
    ...(data !== undefined ? { body: JSON.stringify(data) } : {}),
  });
async function call(env, path, method = 'GET', data, owner = 'owner-A') {
  const r = await labApi(request('/api/learning' + path, method, data, owner), env);
  return { status: r.status, data: await r.json() };
}
async function put(env, id, body, version = 0, owner = 'owner-A') {
  return call(env, '/records/' + id, 'PUT', { version, body }, owner);
}
function completed(title = '검색 비교') {
  return {
    ...freshRecord('experiment'),
    title,
    status: 'completed',
    question: '검색 결과 부족을 줄일 수 있을까?',
    variant: '입력을 고정하고 재검색 단계를 비교했습니다.',
    observations: '20개 입력에서 누락 사례를 직접 확인했습니다.',
    conclusion: '재검색 조건과 실패 경로를 함께 검토했습니다.',
  };
}
test('identity and mutation origin are enforced on every private endpoint', async () => {
  const env = database();
  for (const path of ['/records', '/feed', '/records/secret', '/records/secret/versions'])
    assert.equal((await call(env, path, 'GET', undefined, '')).status, 401);
  assert.equal(
    (
      await labApi(
        request(
          '/api/learning/records/x',
          'PUT',
          { version: 0, body: freshRecord('reading') },
          'owner-A',
          'https://evil.test',
        ),
        env,
      )
    ).status,
    403,
  );
  assert.equal(env.store.size, 0);
});
test('records and version histories isolate account owners', async () => {
  const env = database(),
    b = freshRecord('reading');
  assert.equal((await put(env, 'note', b)).status, 200);
  assert.equal((await call(env, '/records/note', 'GET', undefined, 'owner-B')).status, 404);
  assert.equal((await call(env, '/records/note/versions', 'GET', undefined, 'owner-B')).status, 404);
  assert.equal((await call(env, '/records', 'GET', undefined, 'owner-B')).data.items.length, 0);
});
test('stale and simultaneous saves never overwrite a newer record', async () => {
  const env = database(),
    b = freshRecord('reading');
  await put(env, 'x', b);
  const results = await Promise.all([
    put(env, 'x', { ...b, facts: 'one' }, 1),
    put(env, 'x', { ...b, facts: 'two' }, 1),
  ]);
  assert.deepEqual(results.map((r) => r.status).sort(), [200, 409]);
  assert.equal((await put(env, 'x', b, 0)).status, 409);
  assert.equal((await call(env, '/records/x')).data.version, 2);
});
test('history retains twenty snapshots and restoring appends a new version', async () => {
  const env = database(),
    b = freshRecord('reading');
  for (let i = 0; i < 23; i++) assert.equal((await put(env, 'history', { ...b, facts: String(i) }, i)).status, 200);
  const history = (await call(env, '/records/history/versions')).data.items;
  assert.equal(history.length, 20);
  assert.equal(history[0].version, 23);
  assert.equal(history.at(-1).version, 4);
  const restored = await put(env, 'history', history.at(-1).body, 23);
  assert.equal(restored.data.record.version, 24);
  assert.equal((await call(env, '/records/history/versions')).data.items[1].version, 23);
});
test('complete experiment and resolved incident require observed evidence', async () => {
  const env = database();
  assert.equal((await put(env, 'empty', { ...freshRecord('experiment'), status: 'completed' })).status, 400);
  assert.equal(
    (await put(env, 'issue', { ...freshRecord('incident'), status: 'resolved', action: '재시작' })).status,
    400,
  );
  assert.equal((await put(env, 'done', completed())).status, 200);
});
test('unsafe URL, invalid calendar dates, unknown kinds, booleans and nonfinite metrics are rejected', () => {
  for (const b of [
    { ...freshRecord('project'), repository: 'javascript:alert(1)' },
    { ...freshRecord('reading'), date: '2026-02-30' },
    { kind: '__proto__' },
    { ...freshRecord('experiment'), metrics: [{ name: 'latency', baseline: true, variant: 2 }] },
    { ...freshRecord('experiment'), metrics: [{ name: 'latency', baseline: 'NaN', variant: 2 }] },
  ])
    assert.throws(() => checkedRecord(b), LabError);
});
test('project association cannot reference another owner project or an arbitrary note', async () => {
  const env = database();
  await put(env, 'project', freshRecord('project'), 0, 'owner-B');
  assert.equal((await put(env, 'x', { ...freshRecord('reading'), projectId: 'project' })).status, 400);
  await put(env, 'note', freshRecord('reading'));
  assert.equal((await put(env, 'x', { ...freshRecord('reading'), projectId: 'note' })).status, 400);
  await put(env, 'own-project', freshRecord('project'));
  assert.equal((await put(env, 'x', { ...freshRecord('reading'), projectId: 'own-project' })).status, 200);
});
test('reference review increments once and schedules the next Korean date using CAS', async () => {
  const env = database();
  await put(env, 'note', freshRecord('reading'));
  let r = await call(env, '/records/note/review', 'POST', { version: 1 });
  assert.equal(r.status, 200);
  assert.equal(r.data.record.body.review_count, 1);
  assert.equal(r.data.record.body.review_on, plusDays(koreaDay(), 7));
  assert.equal((await call(env, '/records/note/review', 'POST', { version: 1 })).status, 409);
});
test('list pagination returns every record without exposing other namespaces', async () => {
  const env = database();
  for (let i = 0; i < 105; i++) await put(env, 'note-' + String(i).padStart(3, '0'), freshRecord('reading'));
  await env.BUCKET.put('career-documents/owner-A/a.json', '{}', { customMetadata: {} });
  const a = (await call(env, '/records')).data,
    b = (await call(env, '/records?cursor=' + a.cursor)).data;
  assert.equal(a.items.length, 100);
  assert.equal(b.items.length, 5);
  assert.equal(b.cursor, null);
  assert.equal(new Set([...a.items, ...b.items].map((r) => r.id)).size, 105);
});
test('weekly drafting filters by date, kind, archive state and project; repeated creation is idempotent', async () => {
  const env = database();
  await put(env, 'p', freshRecord('project'));
  const start = monday();
  await put(env, 'done', { ...completed('검증한 실험'), projectId: 'p', date: start });
  await put(env, 'old', { ...freshRecord('reading'), date: plusDays(start, -1), projectId: 'p' });
  await put(env, 'archive', { ...freshRecord('reading'), date: start, status: 'archived', projectId: 'p' });
  const a = await call(env, '/weekly', 'POST', { start, projectId: 'p' });
  assert.equal(a.status, 201);
  assert.match(a.data.record.body.evidence_summary, /학습·실험·해결 기록 1건/);
  assert.deepEqual(a.data.record.body.sourceIds, ['done']);
  assert.equal((await call(env, '/weekly', 'POST', { start, projectId: 'p' })).data.existing, true);
  assert.equal((await call(env, '/weekly', 'POST', { start: plusDays(start, 1) })).status, 400);
});
test('weekly empty state reports zero rather than inventing achievements', () => {
  const body = weeklyDraft([], monday());
  assert.match(body.evidence_summary, /0건/);
  assert.equal(body.learnings, '');
  assert.equal(body.next_steps, '');
});
test('interview drafts cite actual versions and cannot use unverified or foreign evidence', async () => {
  const env = database();
  await put(env, 'experiment', completed('직접 확인한 실험'));
  await put(env, 'incomplete', freshRecord('experiment'));
  const result = await call(env, '/draft-answer', 'POST', {
    id: 'answer',
    sourceIds: ['experiment'],
    question: '어려움을 해결한 경험은?',
  });
  assert.equal(result.status, 201);
  assert.match(result.data.record.body.script, /20개 입력/);
  assert.equal(result.data.record.body.provenance.sources[0].version, 1);
  assert.equal((await call(env, '/draft-answer', 'POST', { id: 'bad', sourceIds: ['incomplete'] })).status, 422);
  assert.equal(
    (await call(env, '/draft-answer', 'POST', { id: 'bad', sourceIds: ['experiment'] }, 'owner-B')).status,
    404,
  );
  assert.equal(
    (
      await call(env, '/draft-answer', 'POST', {
        id: 'answer',
        sourceIds: ['experiment'],
        question: '어려움을 해결한 경험은?',
      })
    ).data.existing,
    true,
  );
});
test('backup import remaps references, preserves data, isolates users and is safe to retry', async () => {
  const env = database(),
    p = freshRecord('project'),
    e = { ...completed('그대로 보존할 결과'), projectId: 'old-p' },
    a = { ...freshRecord('answer'), projectId: 'old-p', sourceIds: ['old-e'], script: '내가 수정한 문장' };
  const input = {
    importId: 'import-job',
    knownIds: ['old-p', 'old-e', 'old-a'],
    items: [
      { id: 'old-e', body: e },
      { id: 'old-p', body: p },
      { id: 'old-a', body: a },
    ],
  };
  let result = await call(env, '/import', 'POST', input);
  assert.equal(result.status, 200);
  assert.equal(result.data.completed.length, 3);
  const rows = (await call(env, '/records')).data.items;
  assert.equal(rows.length, 3);
  const importedProject = rows.find((r) => r.kind === 'project'),
    importedExperiment = rows.find((r) => r.kind === 'experiment'),
    importedAnswer = rows.find((r) => r.kind === 'answer');
  assert.equal(importedExperiment.projectId, importedProject.id);
  assert.deepEqual((await call(env, '/records/' + importedAnswer.id)).data.body.sourceIds, [importedExperiment.id]);
  result = await call(env, '/import', 'POST', input);
  assert.ok(result.data.completed.every((r) => r.skipped));
  assert.equal((await call(env, '/records')).data.items.length, 3);
  assert.equal((await call(env, '/records', 'GET', undefined, 'owner-B')).data.items.length, 0);
});
test('import validates all bodies before writing and removes references absent from a partial backup', async () => {
  const env = database();
  let input = {
    importId: 'job',
    knownIds: ['one', 'two'],
    items: [
      { id: 'one', body: freshRecord('reading') },
      { id: 'two', body: { kind: 'unknown' } },
    ],
  };
  assert.equal((await call(env, '/import', 'POST', input)).status, 400);
  assert.equal(env.store.size, 0);
  input = {
    importId: 'job',
    knownIds: ['one'],
    items: [
      { id: 'one', body: { ...freshRecord('reading'), projectId: 'missing-project', sourceIds: ['missing-source'] } },
    ],
  };
  const result = await call(env, '/import', 'POST', input),
    record = (await call(env, '/records/' + result.data.completed[0].id)).data;
  assert.equal(record.body.projectId, '');
  assert.deepEqual(record.body.sourceIds, []);
});
test('import retry never overwrites a record edited after import', async () => {
  const env = database(),
    input = { importId: 'job', knownIds: ['one'], items: [{ id: 'one', body: freshRecord('reading') }] };
  let result = await call(env, '/import', 'POST', input),
    id = result.data.completed[0].id;
  await put(env, id, { ...freshRecord('reading'), facts: '가져온 뒤 직접 수정' }, 1);
  await call(env, '/import', 'POST', input);
  assert.equal((await call(env, '/records/' + id)).data.body.facts, '가져온 뒤 직접 수정');
});
test('Markdown includes actual numeric values, evidence and title without remote publication', () => {
  const r = {
    id: 'x',
    version: 2,
    body: checkedRecord({
      ...completed('실험 백업'),
      metrics: [{ name: '지연', baseline: 100, variant: 80, unit: 'ms', direction: 'lower' }],
      links: ['https://example.com/proof'],
    }),
  };
  const md = markdownRecord(r);
  assert.match(md, /100 \| 80 \| ms/);
  assert.match(md, /https:\/\/example.com\/proof/);
  assert.match(md, /실험 백업/);
});
test('oversized streaming requests fail before any write', async () => {
  const env = database();
  const r = await call(env, '/records/large', 'PUT', {
    version: 0,
    body: { ...freshRecord('reading'), facts: 'a'.repeat(1300000) },
  });
  assert.equal(r.status, 413);
  assert.equal(env.store.size, 0);
});

test('answer drafting never invents an action when a completed note has none', () => {
  assert.throws(
    () => answerDraft([{ id: 'x', version: 1, body: { ...completed('조건 미작성'), variant: '', plan: '' } }]),
    /실제로 시도한 방법/,
  );
});

test('primitive JSON and malformed nested structures return validation errors without writes', async () => {
  const env = database();
  for (const value of [null, [], true, 42, 'bad'])
    for (const [path, method] of [
      ['/records/bad', 'PUT'],
      ['/weekly', 'POST'],
      ['/draft-answer', 'POST'],
      ['/import', 'POST'],
    ])
      assert.equal((await call(env, path, method, value)).status, 400);
  for (const patch of [
    { metrics: [null] },
    { metrics: [[]] },
    { provenance: { sources: [null] } },
    { provenance: [] },
    { source: false },
    { links: {} },
    { sourceIds: 'bad' },
    { review_count: false },
  ])
    assert.equal((await put(env, 'bad', { ...freshRecord('experiment'), ...patch })).status, 400);
  assert.equal(env.store.size, 0);
});
test('numeric metric validation distinguishes blanks, arrays, booleans and finite decimals', () => {
  const spec = freshRecord('experiment');
  const body = checkedRecord({ ...spec, metrics: [{ name: 'one', baseline: '   ', variant: '-1.25e2' }] });
  assert.equal(body.metrics[0].baseline, '');
  assert.equal(body.metrics[0].variant, -125);
  for (const v of [[], {}, false, '0x10', '1,000', 'Infinity'])
    assert.throws(() => checkedRecord({ ...spec, metrics: [{ baseline: v, variant: 0 }] }), LabError);
  assert.throws(() => checkedRecord({ ...freshRecord('reading'), date: '' }), LabError);
});
test('archive saves preserve the exact status to restore rather than resetting progress', async () => {
  const env = database(),
    b = completed('완료된 실험');
  await put(env, 'archive-test', b);
  let r = await put(env, 'archive-test', { ...b, status: 'archived' }, 1);
  assert.equal(r.data.record.body.archived_from, 'completed');
  r = await put(env, 'archive-test', { ...r.data.record.body, status: r.data.record.body.archived_from }, 2);
  assert.equal(r.data.record.body.status, 'completed');
  assert.equal(r.data.record.body.observations, b.observations);
});
test('automatic weekly summaries cannot be moved to a different period or project', async () => {
  const env = database(),
    r = await call(env, '/weekly', 'POST', { start: monday() });
  const record = r.data.record;
  assert.equal(
    (await put(env, record.id, { ...record.body, period_end: plusDays(record.body.period_end, 7) }, record.version))
      .status,
    400,
  );
  const ok = await put(env, record.id, { ...record.body, highlights: '실제로 배운 내용을 추가' }, record.version);
  assert.equal(ok.status, 200);
});
test('weekly summaries retain all 100 source references even with long titles', () => {
  const start = monday(),
    rows = Array.from({ length: 100 }, (_, i) => ({
      id: 'source-' + i,
      version: 1,
      body: { ...freshRecord('reading'), title: '긴 제목'.repeat(40), date: start },
    }));
  const b = weeklyDraft(rows, start);
  assert.equal(b.sourceIds.length, 100);
  assert.equal(b.provenance.sources.length, 100);
  assert.ok(b.evidence_summary.length < 16000);
});
test('a draft answer idempotency id cannot silently return an unrelated record or changed question', async () => {
  const env = database();
  await put(env, 'e', completed());
  await put(env, 'project-id', freshRecord('project'));
  assert.equal((await call(env, '/draft-answer', 'POST', { id: 'project-id', sourceIds: ['e'] })).status, 409);
  await call(env, '/draft-answer', 'POST', { id: 'a', sourceIds: ['e'], question: '첫 질문' });
  assert.equal(
    (await call(env, '/draft-answer', 'POST', { id: 'a', sourceIds: ['e'], question: '바뀐 질문' })).status,
    409,
  );
});
test('GET on the review mutation route does not masquerade as a record read', async () => {
  const env = database();
  await put(env, 'note', freshRecord('reading'));
  assert.equal((await call(env, '/records/note/review')).status, 405);
  assert.equal((await call(env, '/records/note')).data.version, 1);
});
test('malformed public feeds cannot break access to private records', async () => {
  for (const data of [
    { targets: [null], ai_archive: [] },
    { targets: [], ai_archive: null },
    { targets: [{ slug: 'bad', name: 'bad', spec: { docs: 'javascript:alert(1)' } }], ai_archive: [] },
  ]) {
    const env = database();
    env.PUBLIC_FETCH = async () => new Response(JSON.stringify(data), { status: 200 });
    await put(env, 'private', freshRecord('reading'));
    assert.equal((await call(env, '/feed')).status, 502);
    assert.equal((await call(env, '/records/private')).status, 200);
  }
});
test('public feed proxy uses its fixed source and sanitizes unrecognized status and times', async () => {
  const env = database();
  let source;
  env.PUBLIC_FETCH = async (url) => {
    source = url;
    return new Response(
      JSON.stringify({
        targets: [
          {
            slug: 'test',
            name: 'Test',
            spec: { docs: 'https://example.com' },
            last_run: { status: 'invented', checked_at: 'bad', duration_ms: -2 },
          },
        ],
        ai_archive: [],
        last_check_at: 'bad',
      }),
    );
  };
  const r = await call(env, '/feed?url=https://untrusted.example');
  assert.equal(r.status, 200);
  assert.equal(source, 'https://raw.githubusercontent.com/0Ju12/data-projects/main/api-watch/public/workspace.json');
  assert.equal(r.data.targets[0].last_run.status, 'unknown');
  assert.equal(r.data.targets[0].last_run.checked_at, null);
  assert.equal(r.data.targets[0].last_run.duration_ms, null);
  assert.equal(r.data.last_check_at, null);
});
test('large streamed public responses fail with a recoverable source error', async () => {
  const env = database();
  env.PUBLIC_FETCH = async () => new Response('x'.repeat(2500001));
  assert.equal((await call(env, '/feed')).status, 502);
});
test('malformed import elements are rejected atomically before the first write', async () => {
  const env = database();
  for (const items of [[null], [{ id: 'a', body: freshRecord('reading') }, null]])
    assert.equal((await call(env, '/import', 'POST', { importId: 'i', knownIds: ['a'], items })).status, 400);
  assert.equal(env.store.size, 0);
});

test('partial imports can resume without duplicating successful rows or exposing storage details', async () => {
  const env = database(),
    original = env.BUCKET.put;
  let fail = true;
  env.BUCKET.put = async (...args) => {
    if (fail && env.store.size === 1) {
      fail = false;
      throw Error('internal-storage-details');
    }
    return original(...args);
  };
  const input = {
    importId: 'same-file',
    knownIds: ['a', 'b'],
    items: [
      { id: 'a', body: freshRecord('reading') },
      { id: 'b', body: freshRecord('reading') },
    ],
  };
  let result = await call(env, '/import', 'POST', input);
  assert.equal(result.status, 207);
  assert.equal(result.data.completed.length, 1);
  assert.equal(result.data.failed.length, 1);
  assert.ok(!JSON.stringify(result.data).includes('internal-storage-details'));
  result = await call(env, '/import', 'POST', input);
  assert.equal(result.status, 200);
  assert.equal(env.store.size, 2);
  assert.equal(result.data.completed.filter((i) => i.skipped).length, 1);
});
test('imported automatic reviews keep their original aggregation period fixed', async () => {
  const env = database(),
    review = weeklyDraft([], monday());
  await put(env, 'imported-review', review);
  assert.equal(
    (await put(env, 'imported-review', { ...review, period_end: plusDays(review.period_end, 7) }, 1)).status,
    400,
  );
});

test('long evidence is never cut into a misleading factual claim', () => {
  const source = completed('길게 기록한 검증');
  source.observations = '처음에는 개선처럼 보였지만 '.repeat(15) + '재검증에서는 개선을 확인하지 못했습니다.';
  const draft = answerDraft([{ id: 'x', version: 1, body: source }]);
  assert.match(draft.script, /\[직접 요약:/);
  assert.ok(!draft.script.includes('처음에는 개선처럼'));
  assert.equal(draft.status, 'draft');
});
test('an answer with unresolved generated placeholders cannot be marked reviewed', () => {
  const b = { ...freshRecord('answer'), status: 'ready', script: '[직접 요약: 결과를 확인해 주세요.]' };
  assert.throws(() => checkedRecord(b), /실제 경험으로/);
});

test('portfolio metadata exposes new learning links without adding private record data', async () => {
  const env = database();
  env.PUBLIC_FETCH = async () =>
    new Response(
      JSON.stringify({
        targets: [],
        ai_archive: [],
        portfolio: {
          schema_version: 1,
          source_repository: '0Ju12/0Ju12.github.io',
          source_sha: 'a'.repeat(40),
          projects: [
            {
              id: 'vqa',
              title: 'VQA',
              summary: 'public',
              url: 'https://example.com/vqa',
              repository: 'https://github.com/0Ju12/example',
              stack: ['PyTorch'],
            },
          ],
          learning_notes: [
            {
              id: 'small-model',
              episode: 14,
              date: '2026-11-16',
              title: '소형 모델',
              summary: 'public',
              url: 'https://example.com/slm',
            },
          ],
          links: { preparation: 'https://0ju12.github.io/study/index.html' },
          study: {
            note_count: 54,
            url: 'https://0ju12.github.io/study/index.html#/notes',
            highlights: [
              { title: 'Basic Syntax 02', url: 'https://0ju12.github.io/study/notes/js_basic_syntax_2.html' },
            ],
          },
          profile: { email: 'DO_NOT_COPY' },
        },
      }),
    );
  const r = await call(env, '/feed');
  assert.equal(r.status, 200);
  assert.equal(r.data.portfolio.projects[0].id, 'vqa');
  assert.equal(r.data.portfolio.study.note_count, 54);
  assert.equal(r.data.portfolio.learning_notes[0].episode, 14);
  assert.ok(!JSON.stringify(r.data).includes('DO_NOT_COPY'));
  assert.equal(env.store.size, 0);
});
