"""정적 대시보드(docs/index.html) 생성 — GitHub Pages 로 그대로 공개.

지도는 deck.gl + MapLibre GL 3D(진원을 실제 깊이만큼 지도 아래에 그림), 그래프는 서버에서 만든 인라인 SVG 입니다.
모두 무료 오픈소스이고 배경 지도는 키가 필요 없는 OpenFreeMap 타일입니다.
"""
from __future__ import annotations

import html
import json
import math


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def bar_svg(pairs, w=640, h=170, color="#2a78d6", every=None) -> str:
    if not pairs:
        return "<p>데이터 없음</p>"
    every = every or max(1, len(pairs) // 8)
    n, top = len(pairs), max(v for _, v in pairs) or 1
    bw = (w - 40) / n
    bars, labels = [], []
    for i, (k, v) in enumerate(pairs):
        bh = (h - 34) * v / top
        x = 32 + i * bw
        bars.append(f'<rect x="{x:.1f}" y="{h - 20 - bh:.1f}" width="{max(bw - 1, 1):.1f}" height="{bh:.1f}" fill="{color}"><title>{_esc(k)}: {v}</title></rect>')
        if i % every == 0:
            labels.append(f'<text x="{x:.1f}" y="{h - 6}" font-size="10" fill="currentColor" opacity=".6">{_esc(k)}</text>')
    axis = f'<text x="0" y="12" font-size="10" fill="currentColor" opacity=".6">{top}</text>'
    return f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="막대 그래프">{axis}{"".join(bars)}{"".join(labels)}</svg>'


def fmd_svg(fmd, gr, w=640, h=230) -> str:
    pts = [(m, n) for m, n in fmd if n > 0]
    if len(pts) < 2:
        return "<p>데이터 없음</p>"
    m0, m1 = pts[0][0], pts[-1][0]
    ymax = math.log10(max(n for _, n in pts))
    X = lambda m: 40 + (m - m0) / ((m1 - m0) or 1) * (w - 60)
    Y = lambda lg: h - 26 - lg / (ymax or 1) * (h - 46)
    dots = "".join(f'<circle cx="{X(m):.1f}" cy="{Y(math.log10(n)):.1f}" r="2.6" fill="#0f766e"><title>M≥{m}: {n}</title></circle>' for m, n in pts)
    line = ""
    if gr.get("b"):
        a, b, mc = gr["a"], gr["b"], gr["mc"]
        xs = [mc, m1]
        seg = [(X(x), Y(a - b * x)) for x in xs if a - b * x >= 0]
        if len(seg) == 2:
            line = f'<line x1="{seg[0][0]:.1f}" y1="{seg[0][1]:.1f}" x2="{seg[1][0]:.1f}" y2="{seg[1][1]:.1f}" stroke="#b45309" stroke-width="2" stroke-dasharray="5 4"/>'
        line += f'<line x1="{X(mc):.1f}" y1="14" x2="{X(mc):.1f}" y2="{h - 26}" stroke="currentColor" opacity=".25"/><text x="{X(mc) + 4:.1f}" y="24" font-size="10" fill="currentColor" opacity=".7">Mc {mc}</text>'
    ticks = "".join(f'<text x="{X(m):.1f}" y="{h - 8}" font-size="10" fill="currentColor" opacity=".6" text-anchor="middle">{m:.1f}</text>'
                    for m in [round(m0 + i * 0.5, 1) for i in range(int((m1 - m0) / 0.5) + 1)])
    yt = "".join(f'<text x="4" y="{Y(k) + 3:.1f}" font-size="10" fill="currentColor" opacity=".6">{10 ** k:g}</text>' for k in range(0, int(ymax) + 1))
    return f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="규모-누적빈도 그래프 (로그)">{yt}{ticks}{line}{dots}</svg>'


# 깊이 색: 파랑 한 색상 5단계 (라이트는 깊을수록 진하게, 다크는 깊을수록 밝게). 단계 대비는 검증 스크립트로 확인.
DEPTH_EDGES = [30, 70, 150, 300]
DEPTH_LABELS = ["0–30", "30–70", "70–150", "150–300", "300 km↓"]

PAGE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>동아시아 지진 3D</title>
<meta name="description" content="USGS 지진 목록을 매일 모아, 진원을 실제 깊이만큼 지도 아래에 그린 동아시아 3D 지진 지도와 분석">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css">
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<script src="https://unpkg.com/deck.gl@9.0.38/dist.min.js"></script>
<script src="sitebar.js" defer></script>
<style>
:root{color-scheme:light;--bg:#f4f3f0;--card:#fcfcfb;--glass:rgba(252,252,251,.86);--text:#0b0b0b;--muted:#52514e;--faint:#6e6d68;--line:#e2e0da;--soft:#ecebe6;
  --d1:#86b6ef;--d2:#3987e5;--d3:#256abf;--d4:#184f95;--d5:#0d366b;--accent:#256abf;--shadow:0 10px 30px rgba(20,18,12,.10)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--bg:#0d0d0c;--card:#171716;--glass:rgba(23,23,22,.82);--text:#f0efec;--muted:#c3c2b7;--faint:#9a998f;--line:#2c2c29;--soft:#22221f;
  --d1:#184f95;--d2:#2a78d6;--d3:#5598e7;--d4:#9ec5f4;--d5:#cde2fb;--accent:#9ec5f4;--shadow:0 10px 30px rgba(0,0,0,.45)}}
:root[data-theme="dark"]{color-scheme:dark;--bg:#0d0d0c;--card:#171716;--glass:rgba(23,23,22,.82);--text:#f0efec;--muted:#c3c2b7;--faint:#9a998f;--line:#2c2c29;--soft:#22221f;
  --d1:#184f95;--d2:#2a78d6;--d3:#5598e7;--d4:#9ec5f4;--d5:#cde2fb;--accent:#9ec5f4;--shadow:0 10px 30px rgba(0,0,0,.45)}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--text)}
body{font:15px/1.6 "Pretendard Variable",Pretendard,system-ui,-apple-system,"Noto Sans KR",sans-serif;word-break:keep-all;-webkit-font-smoothing:antialiased}
a{color:inherit}
.hero{position:relative;height:min(84vh,880px);min-height:580px;border-bottom:1px solid var(--line)}
#map{position:absolute;inset:0}
.panel{position:absolute;top:16px;left:16px;width:min(380px,calc(100% - 32px));background:var(--glass);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);border:1px solid var(--line);border-radius:18px;padding:18px 18px 14px;box-shadow:var(--shadow);z-index:2;max-height:calc(100% - 32px);overflow:auto}
.eyebrow{font-size:12px;letter-spacing:.08em;color:var(--accent);font-weight:700;margin:0 0 4px}
h1{font-size:clamp(24px,3.2vw,32px);letter-spacing:-.035em;line-height:1.15;margin:0 0 8px;font-weight:800}
.lede{color:var(--muted);font-size:14px;margin:0 0 10px}
.label{font-size:12px;color:var(--faint);margin:10px 0 6px;font-weight:600}
.seg{display:flex;gap:4px;background:var(--soft);border-radius:12px;padding:4px}
.seg button{flex:1;border:0;background:transparent;color:var(--muted);font:inherit;font-size:13px;font-weight:600;padding:7px 10px;border-radius:9px;cursor:pointer;white-space:nowrap}
.seg button[aria-pressed="true"]{background:var(--card);color:var(--text);box-shadow:0 1px 3px rgba(0,0,0,.12)}
.ramp{display:grid;grid-template-columns:repeat(5,1fr);gap:2px;margin:2px 0 4px}.ramp i{height:10px;border-radius:3px;display:block}
.ramp-l{display:grid;grid-template-columns:repeat(5,1fr);gap:2px;font-size:11px;color:var(--faint)}
.sizes{display:flex;align-items:flex-end;gap:14px;font-size:11px;color:var(--faint)}.sizes span{display:flex;flex-direction:column;align-items:center;gap:3px}
.sizes i{display:block;border-radius:50%;border:1.5px solid var(--muted)}
.hint{font-size:12px;color:var(--faint);margin:10px 0 0;line-height:1.5}
.stat{position:absolute;right:16px;bottom:28px;z-index:2;background:var(--glass);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);border:1px solid var(--line);border-radius:16px;padding:12px 16px;box-shadow:var(--shadow);min-width:200px}
.stat .k{font-size:12px;color:var(--faint);font-weight:600}.stat .v{font-size:34px;font-weight:800;letter-spacing:-.03em;line-height:1.1}.stat .d{font-size:12px;color:var(--muted)}
@media (max-width:760px){.hero{height:auto;min-height:0;display:flex;flex-direction:column}#map{position:relative;height:64vh;order:2}.panel{position:relative;inset:auto;width:auto;margin:12px 16px;max-height:none;order:1}.stat{position:relative;right:auto;bottom:auto;margin:0 16px 16px;order:3}}
main{max-width:1120px;margin:0 auto;padding:26px 16px 60px}
.sub{color:var(--muted);margin:0 0 6px;font-size:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:18px;margin:14px 0}h2{margin:0 0 10px;font-size:19px;letter-spacing:-.02em}h2 small{font-weight:500;color:var(--faint);font-size:13px}
h3{font-size:13px;color:var(--muted);margin:10px 0 4px}.g2{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:18px}
svg.chart{width:100%;height:auto;color:var(--text)}table{width:100%;border-collapse:collapse;font-size:13px}td{padding:5px 6px;border-top:1px solid var(--line)}
.note{font-size:12.5px;color:var(--faint)}
.deck-tooltip{font-family:"Pretendard Variable",Pretendard,system-ui,sans-serif !important}
</style></head><body>
<section class="hero">
  <div id="map" aria-label="동아시아 3D 지진 지도"></div>
  <div class="panel">
    <p class="eyebrow">USGS · 매일 자동 갱신</p>
    <h1>동아시아 지진, 땅속까지</h1>
    <p class="lede">점 하나가 지진 하나이고, <b>지도 아래로 실제 진원 깊이만큼</b> 내려가 있습니다. 일본 밑에서 서쪽으로 비스듬히 깊어지는 띠는 태평양판이 파고드는 섭입대입니다.</p>
    <div class="label">보기</div>
    <div class="seg" id="view"><button data-v="3d" aria-pressed="true">3D 깊이</button><button data-v="2d" aria-pressed="false">평면</button></div>
    <div class="label">깊이 배율</div>
    <div class="seg" id="exag"><button data-x="1" aria-pressed="true">실제 비율</button><button data-x="3" aria-pressed="false">3배 과장</button></div>
    <div class="label">색: 진원 깊이</div>
    <div class="ramp"><i style="background:var(--d1)"></i><i style="background:var(--d2)"></i><i style="background:var(--d3)"></i><i style="background:var(--d4)"></i><i style="background:var(--d5)"></i></div>
    <div class="ramp-l">__DEPTH_LABELS__</div>
    <div class="label">크기: 규모</div>
    <div class="sizes" id="sizes"></div>
    <p class="hint">회색 틀은 깊이 100·300·500 km 높이입니다. 끌어서 이동, 오른쪽 버튼(또는 두 손가락)으로 회전·기울이기, 점에 마우스를 올리면 정보가 나옵니다.</p>
  </div>
  <div class="stat" id="stat"></div>
</section>
<main>
<p class="sub">USGS FDSN Event API → 정제(중복·수정본·범위 검사) → CSV/SQLite → 분석 → 이 페이지. GitHub Actions 가 매일 갱신 · 마지막 갱신 __UPDATED__ UTC · 지도: __MAP_NOTE__</p>
__CARDS__
<section class="card"><h2>데이터 품질 <small>마지막 실행 기준</small></h2><table>__QROWS__</table>
<p class="note">격리한 이벤트는 저장하지 않고 개수만 남깁니다. 같은 id 의 이벤트가 다시 오면 updated 시각이 더 늦은 수정본으로 교체합니다.</p></section>
<p class="note">데이터: U.S. Geological Survey, Earthquake Hazards Program (FDSN Event Web Service). 규모·위치는 USGS 목록 기준이며 기상청 발표와 다를 수 있습니다.
지도: deck.gl · MapLibre GL JS · 배경 OpenFreeMap / OpenMapTiles, © OpenStreetMap contributors. 깊이는 '실제 비율' 에서 수평 거리와 같은 축척입니다.</p>
</main>
<script>
var EV=__EVENTS__;
(function(){
  var root=document.documentElement, css=function(n){return getComputedStyle(root).getPropertyValue(n).trim()};
  var dark=function(){return root.dataset.theme==='dark'||(root.dataset.theme!=='light'&&matchMedia('(prefers-color-scheme: dark)').matches)};
  var hex=function(h){var n=parseInt(h.slice(1),16);return[n>>16&255,n>>8&255,n&255]};
  var EDGES=__DEPTH_EDGES__;
  var band=function(d){for(var i=0;i<EDGES.length;i++)if(d<EDGES[i])return i;return 4};
  var px=function(m){return 2+Math.pow(Math.max(m-4,0),2)*1.7};     // 규모 → 점 반지름(px)
  document.getElementById('sizes').innerHTML=[4,5,6,7].map(function(m){var r=px(m);return '<span><i style="width:'+2*r+'px;height:'+2*r+'px"></i>M'+m+'</span>'}).join('');
  var big=EV.reduce(function(a,e){return e[4]>a[4]?e:a},EV[0]||[0,0,0,0,0,'']);
  document.getElementById('stat').innerHTML='<div class="k">최근 __MAP_DAYS__일 M__MIN_MAG__+</div><div class="v">'+EV.length.toLocaleString('ko-KR')+'건</div>'
    +'<div class="d">가장 큰 지진 M'+big[4]+' · '+big[0].slice(0,10)+'<br>'+big[5]+'</div>';
  var small=matchMedia('(max-width:760px)').matches;
  var HOME={center:[139.0,38.2],zoom:small?4.1:5.0,pitch:72,bearing:-40};
  var style=function(){return 'https://tiles.openfreemap.org/styles/'+(dark()?'dark':'positron')};
  var map=new maplibregl.Map({container:'map',style:style(),center:HOME.center,zoom:HOME.zoom,pitch:HOME.pitch,bearing:HOME.bearing,maxPitch:75,attributionControl:{compact:true}});
  map.addControl(new maplibregl.NavigationControl({visualizePitch:true}),'top-right');
  if(!small)map.setPadding({left:400,top:0,right:0,bottom:0});
  var flat=false, exag=1;
  var overlay=new deck.MapboxOverlay({interleaved:false,layers:[],getTooltip:tip});
  map.addControl(overlay);
  var B=__BBOX__;   // [남, 북, 서, 동]
  function frame(){var out=[];[100,300,500].forEach(function(d){var z=-d*1000*exag;out.push({d:d,path:[[B[2],B[0],z],[B[3],B[0],z],[B[3],B[1],z],[B[2],B[1],z],[B[2],B[0],z]]})});
    [[B[2],B[0]],[B[3],B[0]],[B[3],B[1]],[B[2],B[1]]].forEach(function(c){out.push({d:0,path:[[c[0],c[1],0],[c[0],c[1],-500000*exag]]})});return out}
  function layers(){
    var ramp=['--d1','--d2','--d3','--d4','--d5'].map(function(v){return hex(css(v))});
    var k=flat?0:exag, grid=dark()?[200,200,190,70]:[60,60,55,60];
    var L=[
      new deck.PathLayer({id:'frame',data:flat?[]:frame(),getPath:function(d){return d.path},getColor:grid,widthUnits:'pixels',getWidth:1,parameters:{depthTest:false}}),
      new deck.TextLayer({id:'frame-label',data:flat?[]:[100,300,500],getPosition:function(d){return[B[3],B[0],-d*1000*exag]},getText:function(d){return d+' km'},
        getSize:12,getColor:dark()?[200,200,190,200]:[60,60,55,200],getTextAnchor:'start',getPixelOffset:[6,0],fontFamily:'Pretendard Variable, system-ui, sans-serif',parameters:{depthTest:false}}),
      // 진앙(지표)에서 진원까지 수직선: 모두 옅게, 규모 6 이상은 진하게 — 땅속 구조를 읽는 기준선
      new deck.LineLayer({id:'drop',data:flat?[]:EV,getSourcePosition:function(e){return[e[2],e[1],0]},getTargetPosition:function(e){return[e[2],e[1],-e[3]*1000*k]},
        getColor:function(e){var a=e[4]>=6?150:28;return dark()?[240,239,236,a]:[11,11,11,a]},getWidth:function(e){return e[4]>=6?1.2:.7},widthUnits:'pixels',
        parameters:{depthTest:false},updateTriggers:{getTargetPosition:k,getColor:dark()},transitions:{getTargetPosition:700}}),
      new deck.ScatterplotLayer({id:'quakes',data:EV.slice().sort(function(a,b){return b[3]-a[3]}),   // 깊은 것부터 그려 얕은 것이 위에
        getPosition:function(e){return[e[2],e[1],-e[3]*1000*k]},getRadius:function(e){return px(e[4])},radiusUnits:'pixels',
        getFillColor:function(e){var c=ramp[band(e[3])];return[c[0],c[1],c[2],205]},stroked:true,getLineColor:dark()?[13,13,12,180]:[252,252,251,200],lineWidthUnits:'pixels',getLineWidth:.8,
        pickable:true,autoHighlight:true,highlightColor:dark()?[255,255,255,160]:[0,0,0,120],parameters:{depthTest:false},
        updateTriggers:{getPosition:k,getFillColor:dark()},transitions:{getPosition:700}})];
    return L}
  function tip(o){if(!o.object||o.layer.id!=='quakes')return null;var e=o.object;
    return{html:'<b>M'+e[4]+'</b> · 깊이 '+Math.round(e[3])+' km<br>'+e[0]+' KST<br><span style="color:'+css('--muted')+'">'+e[5]+'</span>',
      style:{backgroundColor:css('--card'),color:css('--text'),border:'1px solid '+css('--line'),borderRadius:'10px',padding:'8px 10px',fontSize:'13px',boxShadow:css('--shadow')}}}
  function refresh(){overlay.setProps({layers:layers()})}
  document.querySelectorAll('#view button').forEach(function(b){b.onclick=function(){flat=b.dataset.v==='2d';
    document.querySelectorAll('#view button').forEach(function(x){x.setAttribute('aria-pressed',x===b)});
    map.easeTo({pitch:flat?0:HOME.pitch,bearing:flat?0:HOME.bearing,duration:900});refresh()}});
  document.querySelectorAll('#exag button').forEach(function(b){b.onclick=function(){exag=+b.dataset.x;
    document.querySelectorAll('#exag button').forEach(function(x){x.setAttribute('aria-pressed',x===b)});refresh()}});
  refresh();
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change',function(){map.setStyle(style());refresh()});
})();
</script></body></html>"""


def render(summaries: list[dict], quality: dict, events_js: list[list], updated: str, cfg: dict) -> str:
    cards = []
    for s in summaries:
        gr = s["gr"]
        gr_txt = (f'b = {gr["b"]} ± {gr["sigma"]} (Mc {gr["mc"]}, n = {gr["n"]})' if gr["b"] else _esc(gr["note"]))
        top = "".join(f'<tr><td>{_esc(e["time_kst"])}</td><td><b>{e["mag"]}</b> {_esc(e["mag_type"])}</td><td>{e["depth_km"]:.0f} km</td><td>{_esc(e["place"])}</td></tr>' for e in s["largest"][:8])
        cards.append(f'''<section class="card">
<h2>{_esc(s["region"])} <small>{s["n"]:,}건 · {_esc((s["first"] or "")[:10])} ~ {_esc((s["last"] or "")[:10])}</small></h2>
<div class="g2"><div><h3>월별 발생 건수</h3>{bar_svg(s["monthly"])}</div>
<div><h3>규모-누적빈도 (구텐베르크-리히터)</h3>{fmd_svg(s["fmd"], gr)}<p class="note">{gr_txt}. 규모 종류: {_esc(", ".join(f"{k} {v}" for k, v in sorted(s["mag_types"].items(), key=lambda x: -x[1])))} — 종류가 섞여 있어 b값은 참고용.</p></div></div>
<div class="g2"><div><h3>깊이 분포</h3>{bar_svg(s["depth"], color="#7c3aed", every=1)}</div>
<div><h3>큰 지진 (KST)</h3><table>{top}</table></div></div></section>''')
    q = quality
    qrows = "".join(f"<tr><td>{_esc(k)}</td><td>{v:,}</td></tr>" for k, v in [
        ("이번 실행에서 받은 이벤트", q.get("received", 0)), ("같은 실행 안 중복", q.get("duplicates", 0)), ("수정본으로 갱신", q.get("revised", 0)),
        ("규모 없음(격리)", q.get("no_magnitude", 0)), ("좌표·깊이 범위 밖(격리)", q.get("out_of_range", 0)), ("지진이 아닌 이벤트(격리)", q.get("not_earthquake", 0)),
        ("누적 보관 이벤트", q.get("kept", 0))])
    r0 = cfg["regions"][0]
    # 지도 이벤트의 장소 이름에 '</script>' 같은 문자열이 들어와도 스크립트가 끊기지 않게
    ev = json.dumps(events_js, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    subs = {
        "__EVENTS__": ev,
        "__BBOX__": json.dumps(r0["bbox"]),
        "__DEPTH_EDGES__": json.dumps(DEPTH_EDGES),
        "__DEPTH_LABELS__": "".join(f"<span>{_esc(x)}</span>" for x in DEPTH_LABELS),
        "__MAP_DAYS__": str(cfg["map_days"]),
        "__MIN_MAG__": str(r0["min_mag"]),
        "__MAP_NOTE__": f'{_esc(r0["name"])} M{r0["min_mag"]}+ 최근 {cfg["map_days"]}일',
        "__UPDATED__": _esc(updated),
        "__CARDS__": "".join(cards),
        "__QROWS__": qrows,
    }
    out = PAGE
    for k, v in subs.items():
        out = out.replace(k, v)
    return out
