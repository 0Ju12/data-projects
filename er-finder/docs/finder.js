/* 가까운 응급실 찾기 — 격자 조회 로직 (브라우저·node 테스트 공용) */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.Finder = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  var R = 6371008.8;
  function haversine(lat1, lon1, lat2, lon2) {
    var p = Math.PI / 180, a = Math.sin((lat2 - lat1) * p / 2), b = Math.sin((lon2 - lon1) * p / 2);
    return 2 * R * Math.asin(Math.sqrt(a * a + Math.cos(lat1 * p) * Math.cos(lat2 * p) * b * b));
  }

  /** grid.json → 조회용 색인 (칸 번호 → 배열 위치) */
  function load(grid) {
    var idx = new Map(), s = grid.stride, c = grid.cells;
    for (var k = 0; k < c.length; k += s) idx.set((grid.i0 + c[k]) * 1e6 + (grid.j0 + c[k + 1]), k);
    return { grid: grid, idx: idx };
  }

  function center(g, i, j) { return [(i + 0.5) * g.deg, (j + 0.5) * g.deg]; }

  /** 이 위치의 칸. 사람이 사는 칸만 계산돼 있어 빈 칸이면 maxRing 칸 안 가장 가까운 칸으로 (산·논 한가운데 등) */
  function locate(F, lat, lon, maxRing) {
    var g = F.grid, i = Math.floor(lat / g.deg), j = Math.floor(lon / g.deg), best = null;
    maxRing = maxRing == null ? 3 : maxRing;
    for (var r = 0; r <= maxRing && !best; r++) {
      for (var di = -r; di <= r; di++) for (var dj = -r; dj <= r; dj++) {
        if (Math.max(Math.abs(di), Math.abs(dj)) !== r) continue;
        var k = F.idx.get((i + di) * 1e6 + (j + dj));
        if (k == null) continue;
        var cc = center(g, i + di, j + dj), d = haversine(lat, lon, cc[0], cc[1]);
        if (!best || d < best.dist) best = { k: k, i: i + di, j: j + dj, dist: d, exact: r === 0 };
      }
    }
    return best;
  }

  function er(F, n, lat, lon) {
    var e = F.grid.ers[n];
    return { index: n, name: e[0], lat: e[1], lon: e[2], tier: e[3], tierName: e[4], straightKm: haversine(lat, lon, e[1], e[2]) / 1000 };
  }

  /** 위치 → 대상(권역센터, 아무 응급실…)마다 가장 가까운 응급실과 이동 분. 계산 범위 밖이면 inGrid=false 와 직선 거리 순 목록만 */
  function find(F, lat, lon) {
    var g = F.grid, hit = locate(F, lat, lon), out = { inGrid: !!hit, snappedM: hit ? Math.round(hit.dist) : null, exact: hit ? hit.exact : false, targets: [] };
    if (hit) {
      for (var t = 0; t < g.targets.length; t++) {
        var m = g.cells[hit.k + 2 + 2 * t], n = g.cells[hit.k + 3 + 2 * t];
        out.targets.push({ name: g.targets[t].name, tiers: g.targets[t].tiers, minutes: m < 0 ? null : m / 10, er: n < 0 ? null : er(F, n, lat, lon) });
      }
    }
    out.byDistance = g.ers.map(function (_, n) { return er(F, n, lat, lon); }).sort(function (a, b) { return a.straightKm - b.straightKm; });
    return out;
  }

  /** 길찾기 링크 (앱이 깔려 있으면 앱으로 열림) */
  function links(e, from) {
    var name = encodeURIComponent(e.name);
    return {
      kakao: 'https://map.kakao.com/link/to/' + name + ',' + e.lat + ',' + e.lon,
      naver: 'https://map.naver.com/p/search/' + name,
      google: 'https://www.google.com/maps/dir/?api=1&destination=' + e.lat + ',' + e.lon + (from ? '&origin=' + from[0] + ',' + from[1] : '') + '&travelmode=driving'
    };
  }

  function fmtMin(m) {
    if (m == null) return null;
    if (m < 1) return '1분 미만';
    if (m < 60) return Math.round(m) + '분';
    var h = Math.floor(m / 60), r = Math.round(m % 60);
    return h + '시간' + (r ? ' ' + r + '분' : '');
  }

  return { haversine: haversine, load: load, locate: locate, find: find, links: links, fmtMin: fmtMin };
});
