"""저장: 사람이 읽고 diff 할 수 있는 CSV(data/events.csv)가 원본, SQLite 는 분석·질의용으로 매번 다시 만듦."""
from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from .transform import Event

FIELDS = list(Event.__dataclass_fields__)


def load_csv(path: Path) -> dict[str, Event]:
    if not path.exists():
        return {}
    out = {}
    with path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            out[r["id"]] = Event(id=r["id"], time_utc=r["time_utc"], time_kst=r["time_kst"], updated=int(r["updated"]),
                                 lat=float(r["lat"]), lon=float(r["lon"]), depth_km=float(r["depth_km"]), mag=float(r["mag"]),
                                 mag_type=r["mag_type"], place=r["place"], status=r["status"], type=r["type"])
    return out


def save_csv(path: Path, events: dict[str, Event]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(events.values(), key=lambda e: (e.time_utc, e.id))
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for e in rows:
            w.writerow(e.row())


def to_sqlite(path: Path, events: dict[str, Event]) -> None:
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    con.execute(f"CREATE TABLE events ({', '.join(f + (' TEXT PRIMARY KEY' if f == 'id' else '') for f in FIELDS)})")
    con.executemany(f"INSERT INTO events VALUES ({', '.join('?' for _ in FIELDS)})", [tuple(e.row()[k] for k in FIELDS) for e in events.values()])
    con.execute("CREATE INDEX idx_time ON events(time_utc)")
    con.commit()
    con.close()


def load_state(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
