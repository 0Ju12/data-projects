"""UTM-K (EPSG:5179) ↔ WGS84 위경도.

GRS80 타원체 횡메르카토르. 원점 38°N 127.5°E, 축척 0.9996, 가산 (1,000,000 E, 2,000,000 N).
GRS80 과 WGS84 차이는 한국 범위에서 수 mm 라 무시한다. 공식은 Snyder (1987) 'Map Projections — A Working Manual' 8장.
격자 분석도 이 좌표(미터)로 해서, 위경도 칸처럼 위도에 따라 칸 넓이가 달라지지 않게 한다.
"""
from __future__ import annotations

import math

A = 6_378_137.0
F = 1 / 298.257222101
E2 = F * (2 - F)
EP2 = E2 / (1 - E2)
K0, LAT0, LON0, FE, FN = 0.9996, math.radians(38.0), math.radians(127.5), 1_000_000.0, 2_000_000.0


def _meridian(phi: float) -> float:
    e4, e6 = E2 * E2, E2 * E2 * E2
    return A * ((1 - E2 / 4 - 3 * e4 / 64 - 5 * e6 / 256) * phi
                - (3 * E2 / 8 + 3 * e4 / 32 + 45 * e6 / 1024) * math.sin(2 * phi)
                + (15 * e4 / 256 + 45 * e6 / 1024) * math.sin(4 * phi)
                - (35 * e6 / 3072) * math.sin(6 * phi))


M0 = _meridian(LAT0)


def to_utmk(lat: float, lon: float) -> tuple[float, float]:
    phi, lam = math.radians(lat), math.radians(lon)
    n = A / math.sqrt(1 - E2 * math.sin(phi) ** 2)
    t, c = math.tan(phi) ** 2, EP2 * math.cos(phi) ** 2
    a = (lam - LON0) * math.cos(phi)
    m = _meridian(phi)
    x = K0 * n * (a + (1 - t + c) * a ** 3 / 6 + (5 - 18 * t + t * t + 72 * c - 58 * EP2) * a ** 5 / 120)
    y = K0 * (m - M0 + n * math.tan(phi) * (a * a / 2 + (5 - t + 9 * c + 4 * c * c) * a ** 4 / 24
                                             + (61 - 58 * t + t * t + 600 * c - 330 * EP2) * a ** 6 / 720))
    return FE + x, FN + y


def to_wgs84(x: float, y: float) -> tuple[float, float]:
    m = M0 + (y - FN) / K0
    mu = m / (A * (1 - E2 / 4 - 3 * E2 ** 2 / 64 - 5 * E2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - E2)) / (1 + math.sqrt(1 - E2))
    phi1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu)
            + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
            + (151 * e1 ** 3 / 96) * math.sin(6 * mu) + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
    s, c_ = math.sin(phi1), math.cos(phi1)
    n1 = A / math.sqrt(1 - E2 * s * s)
    r1 = A * (1 - E2) / (1 - E2 * s * s) ** 1.5
    t1, c1 = math.tan(phi1) ** 2, EP2 * c_ * c_
    d = (x - FE) / (n1 * K0)
    lat = phi1 - (n1 * math.tan(phi1) / r1) * (d * d / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 * c1 - 9 * EP2) * d ** 4 / 24
                                               + (61 + 90 * t1 + 298 * c1 + 45 * t1 * t1 - 252 * EP2 - 3 * c1 * c1) * d ** 6 / 720)
    lon = LON0 + (d - (1 + 2 * t1 + c1) * d ** 3 / 6
                  + (5 - 2 * c1 + 28 * t1 - 3 * c1 * c1 + 8 * EP2 + 24 * t1 * t1) * d ** 5 / 120) / c_
    return math.degrees(lat), math.degrees(lon)
