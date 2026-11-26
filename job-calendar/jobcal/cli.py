"""python -m jobcal.cli collect   # 공고 수집 → data/postings.json 합치기 → docs/jobs.json"""

import argparse
import datetime as dt
import sys

from . import feed, sources


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["collect", "export"])
    ap.add_argument("--today", help="YYYY-MM-DD (테스트용)")
    a = ap.parse_args(argv)
    today = (
        dt.date.fromisoformat(a.today) if a.today else dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
    )  # 한국 날짜
    store = feed.load()
    log = []
    if a.cmd == "collect":
        rows, log = sources.collect()
        new, changed = feed.merge(store, rows, today)
        ok = {feed.feed_of(r["id"]) for r in rows}
        dropped = feed.prune(store, today, ok)
        feed.save(store)
        for x in log:
            print(f"{x['src']:<18} {'받음 ' + str(x['n']) if x['ok'] else '실패 ' + x['error']}")
        print(f"새 공고 {new} · 바뀜 {changed} · 정리 {dropped} · 전체 {len(store)}")
    data = feed.export(store, log, today)
    print("docs/jobs.json 공고", data["count"])
    return 1 if log and not any(x["ok"] for x in log) else 0


if __name__ == "__main__":
    sys.exit(main())
