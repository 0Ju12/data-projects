const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright'),
  http = require('node:http'),
  fs = require('node:fs'),
  path = require('node:path'),
  assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../public');
const server = http.createServer((req, res) => {
  const n = new URL(req.url, 'http://localhost').pathname;
  const f = path.join(root, n === '/' ? 'index.html' : n);
  if (!f.startsWith(root) || !fs.existsSync(f)) {
    res.statusCode = 404;
    return res.end();
  }
  res.setHeader('Content-Type', f.endsWith('.json') ? 'application/json' : 'text/html');
  res.end(fs.readFileSync(f));
});
(async () => {
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROMIUM_PATH || undefined,
    args: ['--no-sandbox'],
  });
  let count = 0;
  try {
    for (const width of [320, 390, 768, 1440]) {
      const ctx = await browser.newContext({ viewport: { width, height: 900 } }),
        p = await ctx.newPage(),
        errors = [];
      p.on('pageerror', (e) => errors.push(e.message));
      await p.route('https://raw.githubusercontent.com/**', (r) => {
        const name = r.request().url().split('/').pop();
        return r.fulfill({ path: path.join(root, name), contentType: 'application/json' });
      });
      await p.goto('http://127.0.0.1:' + server.address().port);
      await p.locator('[data-detail]').first().waitFor();
      assert.equal(await p.locator('[data-detail]').count(), 8);
      assert.equal(
        await p.locator('.latency-bar').count(),
        JSON.parse(fs.readFileSync(path.join(root, 'report.json')))
          .targets.filter(
            (t) =>
              t.last_run.http_status >= 200 && t.last_run.http_status < 300 && Number.isFinite(t.last_run.duration_ms),
          )
          .slice(0, 7).length,
      );
      assert.equal(await p.locator('.chart-card').count(), 3);
      await p.locator('#show-more').click();
      assert.equal(await p.locator('[data-detail]').count(), 22);
      count++;
      await p.locator('[data-detail]').first().click();
      await p.locator('#back').waitFor();
      assert((await p.locator('.checks tbody tr').count()) > 3);
      await p.locator('#back').click();
      count++;
      await p.locator('#search').fill('USGS');
      assert.equal(await p.locator('[data-detail]').count(), 1);
      await p.locator('#search').fill('');
      await p.locator('#filter').selectOption('critical');
      assert.equal(
        await p.locator('[data-detail]').count(),
        JSON.parse(fs.readFileSync(path.join(root, 'report.json'))).targets.filter(
          (t) => t.last_run.status === 'critical',
        ).length,
      );
      count += 2;
      for (const tab of ['incidents', 'lab', 'ai', 'catalog', 'about']) {
        await p.locator('[data-tab="' + tab + '"]').click();
        await p.waitForTimeout(80);
        assert(
          (await p.evaluate(() => document.documentElement.scrollWidth)) <= width + 2,
          'overflow ' + tab + ' ' + width,
        );
        count++;
      }
      await p.locator('[data-tab="catalog"]').click();
      assert.equal(await p.locator('.catalog-card').count(), 24);
      await p.locator('#catalog-search').fill('기상청');
      assert((await p.locator('.catalog-card').count()) > 0);
      await p.locator('#catalog-auth').selectOption('none');
      assert((await p.locator('.catalog-card').count()) === 0);
      await p.locator('#catalog-search').fill('');
      assert.equal(await p.locator('.catalog-card').count(), 24);
      await p.locator('#catalog-next').click();
      assert((await p.locator('.pagination').innerText()).includes('2 /'));
      count += 5;
      await p.locator('[data-tab="overview"]').click();
      await p.locator('#chart-target').selectOption('hacker-news');
      assert.equal(
        await p.locator('.trend-svg circle').count(),
        JSON.parse(fs.readFileSync(path.join(root, 'report.json')))
          .history.filter((r) => r.target === 'hacker-news')
          .slice(0, 24).length,
      );
      count++;
      await p.locator('[data-tab="lab"]').click();
      assert.equal(await p.locator('[data-case]').count(), 10);
      await p.locator('[data-case="4"]').click();
      assert((await p.locator('#lab-case').innerText()).includes('최신성'));
      count += 2;
      await p.locator('[data-tab="ai"]').click();
      await p.locator('#ai-note').fill('직접 확인한 학습 메모');
      await p.locator('#save-note').click();
      await p.reload();
      await p.locator('[data-tab="ai"]').click();
      assert.equal(await p.locator('#ai-note').inputValue(), '직접 확인한 학습 메모');
      assert((await p.locator('.tech a').count()) >= 2);
      count += 2;
      await p.screenshot({ path: path.join(root, '../.qa/ai-' + width + '.png'), fullPage: true });
      await p.locator('[data-tab="overview"]').click();
      await p.screenshot({ path: path.join(root, '../.qa/dashboard-' + width + '.png'), fullPage: true });
      assert.deepEqual(errors, []);
      await ctx.close();
    }
    const p = await browser.newPage();
    await p.route('https://raw.githubusercontent.com/**', (r) => r.abort());
    await p.goto('http://127.0.0.1:' + server.address().port);
    await p.locator('[data-detail]').first().waitFor();
    assert((await p.locator('#error').innerText()).includes('저장본'));
    count++;
    await p.close();
    const focused = await browser.newPage({ acceptDownloads: true });
    await focused.route('https://raw.githubusercontent.com/**', (r) =>
      r.fulfill({ path: path.join(root, r.request().url().split('/').pop()), contentType: 'application/json' }),
    );
    await focused.goto('http://127.0.0.1:' + server.address().port + '/?targets=weather,own-pipeline');
    await focused.locator('.donut').waitFor();
    assert.equal(await focused.locator('[data-detail]').count(), 2);
    assert.equal(
      await focused.locator('.latency-bar').count(),
      JSON.parse(fs.readFileSync(path.join(root, 'report.json'))).targets.filter(
        (t) =>
          ['weather', 'own-pipeline'].includes(t.slug) &&
          t.last_run.http_status >= 200 &&
          t.last_run.http_status < 300 &&
          Number.isFinite(t.last_run.duration_ms),
      ).length,
    );
    assert((await focused.locator('#focus-banner').innerText()).includes('2개'));
    assert((await focused.locator('.personal-link').getAttribute('href')).endsWith('/lab'));
    assert.equal(await focused.locator('.authored-grid article').count(), 3);
    assert(
      (await focused.locator('.authored-notes').innerText()).includes(
        'AI 글 ' + JSON.parse(fs.readFileSync(path.join(root, 'portfolio.json'))).learning_notes.length + '편',
      ),
    );
    assert(
      (await focused.locator('.authored-notes').innerText()).includes(
        JSON.parse(fs.readFileSync(path.join(root, 'portfolio.json'))).learning_notes[0].title,
      ),
    );
    count += 7;
    await focused.locator('[data-tab="ai"]').click();
    await focused.locator('#ai-note').fill('옮길 내 메모');
    await focused.locator('#save-note').click();
    await focused.evaluate(() => localStorage.setItem('unrelated-secret', 'must-not-export'));
    const downloadPromise = focused.waitForEvent('download');
    await focused.locator('#export-ai-notes').click();
    const file = await (await downloadPromise).path(),
      payload = JSON.parse(fs.readFileSync(file, 'utf8'));
    assert.equal(payload.schema, 'api-watch-notes/v1');
    assert(payload.items.some((n) => n.text === '옮길 내 메모'));
    assert(!JSON.stringify(payload).includes('must-not-export'));
    assert.equal(await focused.locator('a[href*="/lab?source="]').count(), 1);
    count += 4;
    let releaseLab, startedLab;
    const held = new Promise((resolve) => (releaseLab = resolve)),
      started = new Promise((resolve) => (startedLab = resolve));
    await focused.route('**/lab.json', async (r) => {
      startedLab();
      await held;
      await r.fulfill({ path: path.join(root, 'lab.json'), contentType: 'application/json' });
    });
    await focused.locator('[data-tab="lab"]').click();
    await started;
    await focused.locator('[data-tab="ai"]').click();
    releaseLab();
    await focused.waitForTimeout(150);
    assert(await focused.locator('#ai-note').isVisible());
    assert.equal(await focused.locator('[data-case]').count(), 0);
    count++;
    await focused.locator('[data-tab="lab"]').click();
    assert.equal(await focused.locator('[data-case]').count(), 10);
    count++;
    await focused.close();
    console.log(
      'PASS: ' +
        count +
        ' dashboard checks at mobile/desktop widths; detail, filters, synthetic lab, daily AI, note persistence and honest fallback.',
    );
  } finally {
    await browser.close();
    server.close();
  }
})().catch((e) => {
  console.error(e);
  server.close();
  process.exitCode = 1;
});
