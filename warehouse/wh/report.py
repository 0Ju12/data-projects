"""dbt 산출물(manifest.json · run_results.json)과 실행 기록으로 한 장짜리 보고서를 만듭니다.

- 계보: 어느 표가 어느 표에서 나왔는지 (왼쪽 원본 → 오른쪽 집계)
- 테스트 결과: 통과·경고·실패
- 실행 기록: 날짜별 성공 여부·소요 시간·행 수
"""
from __future__ import annotations

import csv
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import re

LAYER = {"staging": 0, "intermediate": 1, "marts": 2, "snapshot": 2}
COLOR = {"staging": "#5b6cff", "intermediate": "#16a34a", "marts": "#ea7a0c", "snapshot": "#c0338a", "source": "#6b7280", "seed": "#0e9aa7"}
VAR_CSV = re.compile(r'var\("(\w+_csv)"\)')


def lineage(manifest: dict) -> tuple[list[dict], list[tuple[str, str]]]:
    """모델·변경 이력 노드와 (부모, 자식) 간선. 원본 CSV 는 staging 모델의 var() 이름으로 붙입니다."""
    nodes, edges = {}, []
    for uid, n in manifest["nodes"].items():
        if n["resource_type"] not in ("model", "snapshot", "seed"):
            continue
        kind = n["resource_type"] if n["resource_type"] in ("snapshot", "seed") else (n.get("fqn") or ["", "marts"])[1]
        nodes[uid] = {"id": uid, "name": n["name"], "kind": kind, "layer": 0 if kind == "seed" else 1 + LAYER.get(kind, 2),
                      "materialized": n["config"].get("materialized", ""), "description": n.get("description", "")}
    for uid, n in manifest["nodes"].items():
        if uid not in nodes:
            continue
        for parent in n["depends_on"].get("nodes", []):
            if parent in nodes:
                edges.append((parent, uid))
        raw = n.get("raw_code", "")
        for var in VAR_CSV.findall(raw):
            if True:
                sid = "source." + var
                nodes.setdefault(sid, {"id": sid, "name": var.replace("_csv", ".csv"), "kind": "source", "layer": 0,
                                       "materialized": "file", "description": ""})
                edges.append((sid, uid))
    # 집계 표가 변경 이력보다 오른쪽에 오도록, 부모보다 항상 한 칸 이상 오른쪽으로
    changed = True
    while changed:
        changed = False
        for a, b in edges:
            if nodes[b]["layer"] <= nodes[a]["layer"]:
                nodes[b]["layer"] = nodes[a]["layer"] + 1
                changed = True
    return sorted(nodes.values(), key=lambda x: (x["layer"], x["name"])), edges


def _svg(nodes, edges) -> str:
    cols = {}
    for n in nodes:
        cols.setdefault(n["layer"], []).append(n)
    W, BW, BH, GY = 250, 190, 40, 18
    height = max(len(v) for v in cols.values()) * (BH + GY) + 20
    pos = {}
    for layer, items in cols.items():
        y0 = (height - len(items) * (BH + GY) + GY) / 2
        for i, n in enumerate(items):
            pos[n["id"]] = (20 + layer * W, y0 + i * (BH + GY))
    width = 20 + (max(cols) + 1) * W - (W - BW) + 20
    out = [f'<svg viewBox="0 0 {width} {height:.0f}" role="img" aria-label="데이터 계보" style="width:100%;height:auto;min-width:720px">']
    for a, b in edges:
        (x1, y1), (x2, y2) = pos[a], pos[b]
        x1 += BW
        y1 += BH / 2
        y2 += BH / 2
        mx = (x1 + x2) / 2
        out.append(f'<path d="M{x1},{y1:.1f} C{mx},{y1:.1f} {mx},{y2:.1f} {x2},{y2:.1f}" fill="none" stroke="var(--line2)" stroke-width="1.5"/>')
    for n in nodes:
        x, y = pos[n["id"]]
        c = COLOR.get(n["kind"], "#888")
        out.append(f'<g><title>{html.escape(n["description"] or n["name"])}</title>'
                   f'<rect x="{x}" y="{y:.1f}" width="{BW}" height="{BH}" rx="10" fill="var(--card)" stroke="{c}" stroke-width="1.6"/>'
                   f'<rect x="{x}" y="{y:.1f}" width="6" height="{BH}" rx="3" fill="{c}"/>'
                   f'<text x="{x + 16}" y="{y + 18:.1f}" font-size="13" font-weight="700" fill="var(--text)">{html.escape(n["name"])}</text>'
                   f'<text x="{x + 16}" y="{y + 32:.1f}" font-size="10.5" fill="var(--muted)">{n["kind"]} · {n["materialized"]}</text></g>')
    out.append("</svg>")
    return "".join(out)


def jobs_section(db: Path) -> str:
    """채용 공고 요약: 최근 4주 기술별 언급 비중 상위와 수집 현황. DB 가 없으면 빈 문자열"""
    if not db.exists():
        return ""
    import duckdb
    con = duckdb.connect(str(db), read_only=True)
    try:
        tot = con.execute("select count(*), count(*) filter (where is_tech), min(posted_date), max(posted_date) from fct_job_postings").fetchall()[0]
        top = con.execute("""
            with recent as (select * from int_job_skills where posted_date >= (select max(posted_date) from int_job_skills) - 27),
                 base as (select count(distinct job_key) n from recent)
            select r.skill, d.category, count(distinct r.job_key) c, round(100.0 * count(distinct r.job_key) / (select n from base), 1) pct
            from recent r join dim_skill d using (skill) where d.category <> 'role' group by 1, 2 order by c desc, 1 limit 15""").fetchall()
        feed = con.execute("select source, max(run_date), sum(new_jobs), sum((overlap = 'no' or overlap like 'error%')::int) from stg_jobs_fetch_log group by 1 order by 1").fetchall()
    except Exception:
        return ""
    finally:
        con.close()
    if not tot[0]:
        return ""
    mx = max([t[2] for t in top] or [1])
    rows = "".join(f"<tr><td>{html.escape(s)}</td><td class='m'>{c0}</td><td><i class='bar' style='width:{c / mx * 100:.0f}%'></i></td><td class='n'>{c}</td><td class='n'>{p}%</td></tr>" for s, c0, c, p in top)
    feeds = " · ".join(f"{s}: 마지막 수집 {d}, 누적 새 공고 {n}건, 빈틈·실패 {g}일" for s, d, n, g in feed)
    return f"""<div class="card"><h2>채용 공고 — 최근 4주, 기술 공고에서 많이 언급된 기술</h2>
<p class="note" style="margin:0 0 10px">모은 공고 {tot[0]}건(게시일 {tot[2]} ~ {tot[3]}) 가운데 기술 이름이 하나라도 나온 {tot[1]}건 기준. 해외 원격·유럽 공고이고, 제목과 본문에서 사전에 있는 이름을 찾은 것이라 실제 요구 수준과는 다를 수 있습니다.</p>
<div class="sc"><table><tr><th>기술</th><th>분류</th><th style="width:40%"></th><th class="n">공고</th><th class="n">비중</th></tr>{rows}</table></div>
<p class="note" style="margin:10px 0 0">{html.escape(feeds)}<br>출처: <a href="https://remoteok.com">Remote OK</a> · <a href="https://www.arbeitnow.com">Arbeitnow</a> 공개 피드. 공고 본문은 저장하지 않습니다.</p></div>"""


def build_report(root: Path = ROOT, out: Path | None = None, db: Path | None = None) -> Path:
    target = root / "target"
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    rr = json.loads((target / "run_results.json").read_text(encoding="utf-8"))
    nodes, edges = lineage(manifest)
    tests = []
    for r in rr["results"]:
        if r["unique_id"].startswith("test."):
            node = manifest["nodes"].get(r["unique_id"], {})
            tests.append((node.get("name", r["unique_id"]), r["status"], r.get("failures") or 0, round(r.get("execution_time", 0), 3)))
    tests.sort(key=lambda t: ({"fail": 0, "error": 0, "warn": 1}.get(t[1], 2), t[0]))
    npass = sum(t[1] == "pass" for t in tests)
    nwarn = sum(t[1] == "warn" for t in tests)
    nfail = len(tests) - npass - nwarn
    hist = []
    hp = root / "runs" / "history.csv"
    if hp.exists():
        with hp.open(encoding="utf-8", newline="") as f:
            hist = list(csv.DictReader(f))
    ok = sum(h["status"] == "success" for h in hist)
    last = hist[-1] if hist else {}
    badge = lambda s: f'<b class="b {"ok" if s in ("pass", "success") else "wn" if s == "warn" else "ng"}">{ {"pass": "통과", "success": "성공", "warn": "경고", "fail": "실패", "error": "오류", "failed": "실패"}.get(s, s) }</b>'
    trs = "".join(f"<tr><td>{html.escape(n)}</td><td>{badge(s)}</td><td class='n'>{f}</td><td class='n'>{t}</td></tr>" for n, s, f, t in tests)
    hrs = "".join(
        f"<tr><td>{h['logical_date']}</td><td>{badge(h['status'])}</td><td class='n'>{h['models']}</td><td class='n'>{h['tests_pass']}</td>"
        f"<td class='n'>{h['tests_warn']}</td><td class='n'>{h['tests_fail']}</td><td class='n'>{h['seconds']}</td>"
        f"<td class='n'>{h['rows_quakes']}</td><td class='n'>{h['snapshot_versions']}</td><td class='n'>{h['exported_rows']}</td></tr>"
        for h in reversed(hist[-30:]))
    legend = "".join(f'<span><i style="background:{c}"></i>{k}</span>' for k, c in COLOR.items())
    doc = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>웨어하우스 상태</title><style>
:root{{--bg:#f7f7f6;--card:#fff;--text:#1b1b1b;--muted:#6b6b6b;--line:#e6e4df;--line2:#b9b6ae}}
@media (prefers-color-scheme:dark){{:root{{--bg:#131313;--card:#1d1d1d;--text:#f0efec;--muted:#a3a19b;--line:#2e2e2c;--line2:#5a5852}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:15px/1.6 system-ui,-apple-system,"Noto Sans KR",sans-serif;padding:28px 16px 60px}}
main{{max-width:1040px;margin:0 auto}}h1{{font-size:26px;margin:0 0 4px}}h2{{font-size:16px;margin:0 0 12px}}.sub{{color:var(--muted);font-size:13.5px;margin:0 0 20px}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}}.kpi,.card{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px}}
.kpi b{{display:block;font-size:24px;line-height:1.2}}.kpi span{{font-size:12.5px;color:var(--muted)}}.card{{margin-bottom:14px}}.sc{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-size:13.5px}}th{{text-align:left;font-size:12px;color:var(--muted);font-weight:600;padding:6px 6px}}td{{padding:6px;border-top:1px solid var(--line)}}
td.n,th.n{{text-align:right;font-variant-numeric:tabular-nums}}td.m{{color:var(--muted);font-size:12.5px}}.bar{{display:block;height:8px;border-radius:4px;background:#0e9aa7}}.b{{font-size:12px;padding:2px 9px;border-radius:999px;font-weight:700}}
.ok{{background:rgba(22,163,74,.14);color:#15803d}}.wn{{background:rgba(234,122,12,.16);color:#b45309}}.ng{{background:rgba(220,38,38,.14);color:#b91c1c}}
.lg{{display:flex;flex-wrap:wrap;gap:14px;font-size:12px;color:var(--muted);margin-top:10px}}.lg i{{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px}}
.note{{font-size:12.5px;color:var(--muted)}}a{{color:inherit}}@media (max-width:640px){{.grid{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><main>
<h1>웨어하우스 상태</h1>
<p class="sub">지진 목록·전력 수요·기온·채용 공고 원본을 dbt 로 정리한 결과입니다. 생성 {rr['metadata']['generated_at'][:19].replace('T', ' ')} UTC · <a href="https://github.com/0Ju12/data-projects/tree/main/warehouse">코드</a></p>
<div class="grid">
<div class="kpi"><b>{sum(n['kind'] != 'source' for n in nodes)}</b><span>모델·변경 이력</span></div>
<div class="kpi"><b>{npass} / {len(tests)}</b><span>테스트 통과{f" · 경고 {nwarn}" if nwarn else ""}{f" · 실패 {nfail}" if nfail else ""}</span></div>
<div class="kpi"><b>{ok} / {len(hist)}</b><span>기록된 실행 중 성공</span></div>
<div class="kpi"><b>{last.get('seconds', '–')}초</b><span>마지막 실행 소요</span></div></div>
<div class="card"><h2>계보 — 어느 표가 어느 표에서 나왔나</h2><div class="sc">{_svg(nodes, edges)}</div><div class="lg">{legend}</div></div>
{jobs_section(db or root / "target" / "warehouse.duckdb")}
<div class="card"><h2>실행 기록 (최근 30회)</h2><div class="sc"><table><tr><th>날짜</th><th>결과</th><th class="n">모델</th><th class="n">통과</th><th class="n">경고</th><th class="n">실패</th><th class="n">초</th><th class="n">지진 행</th><th class="n">이력 판</th><th class="n">내보낸 행</th></tr>{hrs or '<tr><td colspan="10">아직 기록 없음</td></tr>'}</table></div></div>
<div class="card"><h2>테스트 결과</h2><div class="sc"><table><tr><th>테스트</th><th>결과</th><th class="n">걸린 행</th><th class="n">초</th></tr>{trs}</table></div></div>
<p class="note">· "이력 판"은 지진 변경 이력 표의 행 수입니다. USGS 가 규모·위치를 고치면 이전 판을 닫고 새 판을 추가하므로, 지진 행 수보다 많아질 수 있습니다.<br>· 전력 수요 자료는 2025년 한 해뿐이라, 매일 실행에서는 작년 같은 날짜의 파티션을 다시 내보내 재실행 안전성만 확인합니다.</p>
</main></body></html>"""
    out = out or root / "docs" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    return out
