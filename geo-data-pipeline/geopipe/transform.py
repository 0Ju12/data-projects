"""GeoJSON feature → 정제된 레코드, 품질 검사.

정제 규칙
- id 기준 중복 제거: 같은 id 가 여러 번 오면 `updated` 가 가장 늦은 것(가장 최근 수정본)을 남김
- 범위 밖 값(위도·경도·깊이)과 규모가 없는 이벤트는 버리지 않고 '격리'해 품질 보고서에 개수를 남김
- 시간은 UTC 와 KST(UTC+9) 둘 다 저장
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


@dataclass
class Event:
    id: str
    time_utc: str
    time_kst: str
    updated: int
    lat: float
    lon: float
    depth_km: float
    mag: float
    mag_type: str
    place: str
    status: str
    type: str

    def row(self) -> dict:
        return asdict(self)


@dataclass
class Quality:
    received: int = 0
    duplicates: int = 0
    revised: int = 0
    no_magnitude: int = 0
    out_of_range: int = 0
    not_earthquake: int = 0
    kept: int = 0
    mag_types: dict = field(default_factory=dict)

    def merge(self, other: "Quality") -> "Quality":
        out = Quality()
        for k in ("received", "duplicates", "revised", "no_magnitude", "out_of_range", "not_earthquake", "kept"):
            setattr(out, k, getattr(self, k) + getattr(other, k))
        for d in (self.mag_types, other.mag_types):
            for k, v in d.items():
                out.mag_types[k] = out.mag_types.get(k, 0) + v
        return out


def to_event(f: dict) -> Event | None:
    p, g = f.get("properties") or {}, (f.get("geometry") or {}).get("coordinates") or [None, None, None]
    if p.get("time") is None:
        return None
    t = datetime.fromtimestamp(p["time"] / 1000, tz=timezone.utc)
    return Event(
        id=f.get("id") or p.get("ids", "").strip(","),
        time_utc=t.strftime("%Y-%m-%dT%H:%M:%SZ"),
        time_kst=t.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S"),
        updated=int(p.get("updated") or 0),
        lon=g[0], lat=g[1], depth_km=g[2] if len(g) > 2 else None,
        mag=p.get("mag"), mag_type=(p.get("magType") or "").lower(),
        place=p.get("place") or "", status=p.get("status") or "", type=p.get("type") or "",
    )


def valid(e: Event) -> str | None:
    """문제가 있으면 사유, 없으면 None"""
    if e.type and e.type != "earthquake":
        return "not_earthquake"
    if e.mag is None:
        return "no_magnitude"
    if e.lat is None or e.lon is None or not (-90 <= e.lat <= 90) or not (-180 <= e.lon <= 180):
        return "out_of_range"
    if e.depth_km is None or not (-10 <= e.depth_km <= 800):
        return "out_of_range"
    return None


def clean(features: list[dict], existing: dict[str, Event] | None = None) -> tuple[dict[str, Event], Quality]:
    """새로 받은 feature 들을 기존 레코드와 합쳐 정제. (id → Event, 품질 집계)"""
    out = dict(existing or {})
    q = Quality(received=len(features))
    seen = set()
    for f in features:
        e = to_event(f)
        if e is None:
            q.out_of_range += 1
            continue
        reason = valid(e)
        if reason:
            setattr(q, reason, getattr(q, reason) + 1)
            continue
        if e.id in seen:
            q.duplicates += 1
        seen.add(e.id)
        old = out.get(e.id)
        if old is None or e.updated > old.updated:
            if old is not None:
                q.revised += 1
            out[e.id] = e
    q.kept = len(out)
    for e in out.values():
        q.mag_types[e.mag_type] = q.mag_types.get(e.mag_type, 0) + 1
    return out, q
