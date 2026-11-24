/* data-projects 공통 상단 막대 — 6개 대시보드가 같은 이름·같은 메뉴·같은 색으로 이어지도록 (각 페이지는 ../sitebar.js 를 불러옴)
   자체 접두어(.dpb)와 자체 색 토큰만 써서 각 대시보드의 CSS와 충돌하지 않음. 밝은/어두운 모드는 시스템 설정을 따름. */
(function () {
  if (document.querySelector('.dpb')) return;
  var base = (function () {
    var s = document.currentScript && document.currentScript.src;
    return s ? s.replace(/sitebar\.js(\?.*)?$/, '') : './';
  })();
  var PAGES = [
    ['warehouse/', '분석 웨어하우스'],
    ['energy/', '전력 전환'],
    ['', '지진 파이프라인'],
    ['api-watch/', 'API Watch'],
    ['power/', '전력 수요 예측'],
    ['fire/', '산불 위험 지도'],
    ['jobs/', '신입 공고 달력'],
  ];
  var here = location.pathname.replace(/index\.html$/, '');
  var root = new URL(base, location.href).pathname;
  var cur = PAGES.reduce(function (best, p) {
    var path = root + p[0];
    return here.indexOf(path) === 0 && path.length > (best ? (root + best[0]).length : -1) ? p : best;
  }, null);
  var css = '.dpb{--dpb-bg:#f4f4f2;--dpb-ink:#0b0b0b;--dpb-ink2:#52514e;--dpb-line:#e4e2dc;--dpb-acc:#2a78d6;' +
    'position:relative;z-index:50;background:var(--dpb-bg);border-bottom:1px solid var(--dpb-line);font:600 13px/1.4 system-ui,-apple-system,"Segoe UI","Noto Sans KR",sans-serif;word-break:keep-all}' +
    '@media (prefers-color-scheme:dark){.dpb{--dpb-bg:#111110;--dpb-ink:#f0efec;--dpb-ink2:#c3c2b7;--dpb-line:#2e2e2b;--dpb-acc:#3987e5}}' +
    '.dpb-in{max-width:1180px;margin:0 auto;padding:0 16px;display:flex;align-items:center;gap:4px 16px;min-height:42px}' +
    '.dpb-home{color:var(--dpb-ink);text-decoration:none;white-space:nowrap;display:flex;align-items:center;gap:8px}' +
    '.dpb-home i{width:9px;height:9px;border-radius:2px;background:var(--dpb-acc);display:inline-block}' +
    '.dpb .dpb-nav{display:flex !important;flex-wrap:nowrap;margin:0;padding:0;background:none;border:0;gap:2px;overflow-x:auto;scrollbar-width:none;flex:1;min-width:0}.dpb-nav::-webkit-scrollbar{display:none}' +
    '.dpb .dpb-nav a{color:var(--dpb-ink2);background:none;text-decoration:none;padding:11px 8px;margin:0;font-size:13px;white-space:nowrap;border-bottom:2px solid transparent;font-weight:500}' +
    '.dpb .dpb-nav a:hover{color:var(--dpb-ink)}.dpb .dpb-nav a[aria-current="page"]{color:var(--dpb-ink);border-bottom-color:var(--dpb-acc);font-weight:700}' +
    '.dpb-nav a:focus-visible,.dpb-home:focus-visible,.dpb-pf:focus-visible{outline:2px solid var(--dpb-acc);outline-offset:-2px;border-radius:6px}' +
    '.dpb-pf{color:var(--dpb-ink2);text-decoration:none;white-space:nowrap;font-weight:500}.dpb-pf:hover{color:var(--dpb-ink)}' +
    '@media (max-width:640px){.dpb-home b{display:none}.dpb-pf{display:none}}' +
    '.dpb.dpb-l{--dpb-bg:#f4f4f2;--dpb-ink:#0b0b0b;--dpb-ink2:#52514e;--dpb-line:#e4e2dc;--dpb-acc:#2a78d6}' +
    '.dpb.dpb-d{--dpb-bg:#111110;--dpb-ink:#f0efec;--dpb-ink2:#c3c2b7;--dpb-line:#2e2e2b;--dpb-acc:#3987e5}' +
    '@media print{.dpb{display:none}}';
  var st = document.createElement('style');
  st.textContent = css;
  document.head.appendChild(st);
  var bar = document.createElement('div');
  bar.className = 'dpb';
  bar.innerHTML = '<div class="dpb-in"><a class="dpb-home" href="https://0ju12.github.io/"><i aria-hidden="true"></i><b>이영주 · 공개 데이터 분석</b></a>' +
    '<div class="dpb-nav" role="navigation" aria-label="공개 데이터 프로젝트">' + PAGES.map(function (p) {
      return '<a href="' + base + p[0] + '"' + (cur === p ? ' aria-current="page"' : '') + '>' + p[1] + '</a>';
    }).join('') + '</div><a class="dpb-pf" href="https://github.com/0Ju12/data-projects">코드 ↗</a></div>';
  document.body.insertBefore(bar, document.body.firstChild);
  // 어두운 모드가 없는 페이지에서는 막대도 밝게: 페이지 바탕의 밝기를 보고 맞춤
  try {
    var m = getComputedStyle(document.body).backgroundColor.match(/\d+(\.\d+)?/g);
    if (m && (m.length < 4 || +m[3] > 0)) {
      var lum = (0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]) / 255;
      bar.classList.add(lum > 0.5 ? 'dpb-l' : 'dpb-d');
    }
  } catch (_) {}
  // 휴대폰에서 메뉴가 옆으로 넘칠 때 지금 페이지 항목이 보이도록
  var nav = bar.querySelector('.dpb-nav'), on = bar.querySelector('[aria-current]');
  if (nav && on && nav.scrollWidth > nav.clientWidth) nav.scrollLeft = Math.max(0, on.offsetLeft - nav.offsetLeft - 24);
})();
