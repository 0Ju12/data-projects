"""정적 대시보드(docs/index.html) 생성 — GitHub Pages 로 그대로 공개.

지도는 Leaflet(cdnjs), 그래프는 서버에서 만든 인라인 SVG 라서 브라우저에서 계산하지 않습니다.
"""
from __future__ import annotations

import html
import json
import math


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def bar_svg(pairs, w=640, h=170, color="#2563eb", every=None) -> str:
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
    return f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>동아시아 지진 데이터 파이프라인</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<style>
:root{{--bg:#f6f5f2;--card:#fff;--text:#17191e;--muted:#5e6472;--line:#e5e2db}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0e1116;--card:#161a21;--text:#eceef2;--muted:#a1a8b4;--line:#28303a}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:15px/1.6 system-ui,-apple-system,"Apple SD Gothic Neo","Noto Sans KR",sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:28px 16px 60px}}h1{{margin:0 0 4px;letter-spacing:-.03em}}.sub{{color:var(--muted);margin:0 0 18px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px;margin:14px 0}}h2{{margin:0 0 10px;font-size:19px}}h2 small{{font-weight:500;color:var(--muted);font-size:13px}}
h3{{font-size:13px;color:var(--muted);margin:10px 0 4px}}.g2{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:18px}}
svg.chart{{width:100%;height:auto;color:var(--text)}}#map{{height:440px;border-radius:12px}}table{{width:100%;border-collapse:collapse;font-size:13px}}td{{padding:4px 6px;border-top:1px solid var(--line)}}
.note{{font-size:12.5px;color:var(--muted)}}a{{color:inherit}}
</style></head><body><main>
<h1>동아시아 지진 데이터 파이프라인</h1>
<p class="sub">USGS FDSN Event API → 정제(중복·수정본·범위 검사) → CSV/SQLite → 분석 → 이 페이지. GitHub Actions 가 매일 갱신 · 마지막 갱신 {_esc(updated)} UTC</p>
<section class="card"><h2>지도 <small>원 크기 = 규모, 색 = 깊이</small></h2><div id="map"></div><p class="note">표시: {_esc(cfg["regions"][0]["name"])} M{cfg["regions"][0]["min_mag"]}+ 최근 {cfg["map_days"]}일</p></section>
{"".join(cards)}
<section class="card"><h2>데이터 품질 <small>마지막 실행 기준</small></h2><table>{qrows}</table>
<p class="note">격리한 이벤트는 저장하지 않고 개수만 남깁니다. 같은 id 의 이벤트가 다시 오면 updated 시각이 더 늦은 수정본으로 교체합니다.</p></section>
<p class="note">데이터: U.S. Geological Survey, Earthquake Hazards Program (FDSN Event Web Service). 규모·위치는 USGS 목록 기준이며 기상청 발표와 다를 수 있습니다.</p>
</main>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script>
var EV={json.dumps(events_js, separators=(",", ":"))};
var map=L.map('map',{{scrollWheelZoom:false}}).setView([37,134],5);
L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',maxZoom:10}}).addTo(map);
function col(d){{return d<30?'#dc2626':d<70?'#f59e0b':d<300?'#2563eb':'#7c3aed'}}
EV.forEach(function(e){{L.circleMarker([e[1],e[2]],{{radius:Math.max(2,(e[4]-3)*3),color:col(e[3]),weight:1,fillOpacity:.45}}).bindTooltip(e[0]+' · M'+e[4]+' · '+Math.round(e[3])+'km<br>'+e[5]).addTo(map)}});
</script></body></html>'''
