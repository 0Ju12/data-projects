/* 오프라인용 서비스 워커: 앱 화면·조회 로직·격자는 미리 저장, 격자는 온라인이면 새 것으로 갱신. 지도 타일은 저장하지 않음 */
const VERSION = 'near-v1';
const SHELL = ['./', 'index.html', 'finder.js', 'grid.json', 'manifest.webmanifest', 'icons/icon.svg', 'icons/icon-192.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin) return;     // 지도·CDN 은 그대로 네트워크로
  const fresh = /\/(grid|beds)\.json$/.test(url.pathname);
  if (fresh) {                       // 자료: 네트워크 먼저, 안 되면 저장본
    e.respondWith(fetch(e.request).then(r => {
      if (r.ok) { const copy = r.clone(); caches.open(VERSION).then(c => c.put(e.request, copy)); }
      return r;
    }).catch(() => caches.match(e.request)));
    return;
  }
  e.respondWith(caches.match(e.request, { ignoreSearch: true }).then(hit => hit || fetch(e.request).then(r => {
    if (r.ok && url.pathname.startsWith(new URL('./', location).pathname)) { const copy = r.clone(); caches.open(VERSION).then(c => c.put(e.request, copy)); }
    return r;
  })));
});
