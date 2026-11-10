"""UCI 'Condition monitoring of hydraulic systems' (ZeMA, CC BY 4.0) 내려받기·적재·특징 추출.

원자료: 2,205 사이클 × 17개 센서 (1·10·100 Hz), 사이클 하나 = 60초 일정 부하.
특징: 센서마다 사이클 단위 통계 8개 → 136개 (평균·표준편차·최소·최대·5/95 백분위·기울기·RMS 변화량).
처음 한 번 계산한 특징은 cache/features.npz 에 저장해 다시 쓰고, 원본 ZIP 은 SHA-256 으로 확인합니다.
"""
from __future__ import annotations

import hashlib
import urllib.request
import zipfile
from pathlib import Path

import numpy as np

URL = "https://archive.ics.uci.edu/static/public/447/condition+monitoring+of+hydraulic+systems.zip"
SHA256 = "24128aad2ee45eea7e6b63ebbd9992cdf25d0483a2cebefbfc13bc69079af1f2"
SENSORS = ["PS1", "PS2", "PS3", "PS4", "PS5", "PS6", "EPS1", "FS1", "FS2", "TS1", "TS2", "TS3", "TS4", "VS1", "CE", "CP", "SE"]
STATS = ["mean", "std", "min", "max", "p05", "p95", "slope", "diff_rms"]
TARGETS = ["cooler", "valve", "pump", "accumulator", "stable"]
NORMAL = {"cooler": 100, "valve": 100, "pump": 0, "accumulator": 130}   # 각 부품의 '최적 상태' 값 (documentation.txt)


def download(raw: Path) -> Path:
    raw.mkdir(parents=True, exist_ok=True)
    z = raw / "hydraulic.zip"
    if not z.exists():
        urllib.request.urlretrieve(URL, z)
    h = hashlib.sha256(z.read_bytes()).hexdigest()
    if h != SHA256:
        raise ValueError(f"checksum mismatch: {h}")
    if not (raw / "profile.txt").exists():
        zipfile.ZipFile(z).extractall(raw)
    return raw


def cycle_features(x: np.ndarray) -> np.ndarray:
    """x: (사이클, 샘플) → (사이클, len(STATS))"""
    t = np.linspace(0, 1, x.shape[1])
    tc = t - t.mean()
    slope = (x - x.mean(axis=1, keepdims=True)) @ tc / (tc @ tc)
    d = np.diff(x, axis=1)
    return np.column_stack([x.mean(1), x.std(1), x.min(1), x.max(1), np.percentile(x, 5, axis=1), np.percentile(x, 95, axis=1),
                            slope, np.sqrt((d ** 2).mean(1))])


def feature_names() -> list[str]:
    return [f"{s}_{k}" for s in SENSORS for k in STATS]


def load(raw: Path, cache: Path) -> tuple[np.ndarray, np.ndarray]:
    """(특징 X: 2205×136, 상태 Y: 2205×5)"""
    f = cache / "features.npz"
    if f.exists():
        d = np.load(f)
        return d["X"], d["Y"]
    download(raw)
    X = np.hstack([cycle_features(np.loadtxt(raw / f"{s}.txt")) for s in SENSORS])
    Y = np.loadtxt(raw / "profile.txt")
    cache.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(f, X=X, Y=Y)
    return X, Y
