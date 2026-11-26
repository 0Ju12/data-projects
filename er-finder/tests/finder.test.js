const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');
const fs = require('node:fs');
const Finder = require('../docs/finder.js');

const deg = 1 / 120;
// 칸 (4400,15400) 과 (4400,15402) 두 칸, 대상 2개 (권역, 아무 곳)
const grid = {
  deg,
  i0: 4400,
  j0: 15400,
  stride: 6,
  targets: [{ name: '권역' }, { name: '아무 곳' }],
  ers: [
    ['가병원', 36.7, 128.4, 'regional', '권역응급의료센터'],
    ['나의원', 36.68, 128.35, 'other', '응급실'],
  ],
  cells: [0, 0, 255, 0, 72, 1, 0, 2, -1, -1, 40, 1],
};
const F = Finder.load(grid);
const c = (i, j) => [(i + 0.5) * deg, (j + 0.5) * deg];

test('exact cell lookup returns minutes and nearest ER per target', () => {
  const [lat, lon] = c(4400, 15400);
  const r = Finder.find(F, lat, lon);
  assert.equal(r.inGrid, true);
  assert.equal(r.exact, true);
  assert.deepEqual(
    r.targets.map((t) => [t.minutes, t.er && t.er.name]),
    [
      [25.5, '가병원'],
      [7.2, '나의원'],
    ],
  );
  assert.ok(r.byDistance[0].straightKm <= r.byDistance[1].straightKm);
});

test('empty cell snaps to nearest computed cell within 3 rings, else out of grid', () => {
  const [lat, lon] = c(4400, 15401); // 비어 있는 가운데 칸 → 양옆 중 가까운 쪽
  const r = Finder.find(F, lat + deg * 0.3, lon + deg * 0.3);
  assert.equal(r.exact, false);
  assert.equal(r.targets[1].minutes, 4.0);
  assert.equal(r.targets[0].minutes, null); // 권역센터까지 계산 안 된 칸
  const far = Finder.find(F, 37.5, 127.0);
  assert.equal(far.inGrid, false);
  assert.equal(far.targets.length, 0);
  assert.equal(far.byDistance.length, 2);
});

test('links and minute formatting', () => {
  const e = { name: '가 병원', lat: 36.7, lon: 128.4 };
  const l = Finder.links(e, [36.6, 128.3]);
  assert.equal(l.kakao, 'https://map.kakao.com/link/to/%EA%B0%80%20%EB%B3%91%EC%9B%90,36.7,128.4');
  assert.ok(l.google.includes('origin=36.6,128.3'));
  assert.deepEqual([0.4, 12.4, 60, 135].map(Finder.fmtMin), ['1분 미만', '12분', '1시간', '2시간 15분']);
});

test('real grid: 안동병원 cell is close to an ER and in grid', () => {
  const p = path.join(__dirname, '..', 'docs', 'grid.json');
  if (!fs.existsSync(p)) return;
  const R = Finder.load(JSON.parse(fs.readFileSync(p, 'utf8')));
  const r = Finder.find(R, 36.5655, 128.729); // 안동 시내
  assert.equal(r.inGrid, true);
  const any = r.targets[r.targets.length - 1];
  assert.ok(any.minutes < 15, `안동 시내에서 ${any.minutes}분`);
});
