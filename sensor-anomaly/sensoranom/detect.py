"""부품별 이상 탐지 + 스트리밍 경보.

- 부품마다 '그 부품이 최적 상태인 사이클'만으로 정상 모델을 학습 (다른 부품 상태는 섞여 있음 → 모델이 그 변화는 무시하도록 배움)
- 점수: 표준화한 특징의 Ledoit-Wolf 공분산 마할라노비스 거리(제곱) (작은 표본에서도 공분산 역행렬이 안정적)
- 임계값: 학습에 쓰지 않은 정상 검증 사이클의 99번째 백분위 → 목표 오경보율 1%
- 경보: 점수가 임계값을 k 사이클 연속 넘을 때만 (한 번 튀는 값은 무시) — 지연과 오경보의 균형
- 분할: 사이클은 시간 순서대로 이웃끼리 거의 같으므로 무작위가 아니라 연속 구간(block) 단위로 나눔
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.covariance import LedoitWolf
from sklearn.preprocessing import StandardScaler


def block_split(n: int, n_blocks: int = 10, test_blocks=(7, 8, 9)) -> tuple[np.ndarray, np.ndarray]:
    """0..n-1 을 연속 구간 n_blocks 개로 나눠 test_blocks 를 시험용으로"""
    edges = np.linspace(0, n, n_blocks + 1).astype(int)
    test = np.concatenate([np.arange(edges[b], edges[b + 1]) for b in test_blocks])
    train = np.setdiff1d(np.arange(n), test)
    return train, test


@dataclass
class Detector:
    scaler: StandardScaler
    cov: LedoitWolf
    threshold: float

    def score(self, X: np.ndarray) -> np.ndarray:
        return self.cov.mahalanobis(self.scaler.transform(X))


def fit_detector(X_normal: np.ndarray, val_frac: float = 0.25, fa_rate: float = 0.01, seed: int = 0) -> Detector:
    """정상 사이클 X_normal 로 학습. 뒤쪽 val_frac 은 임계값 정하는 검증용으로 남김 (시간 순서 유지)"""
    n = len(X_normal)
    cut = int(n * (1 - val_frac))
    tr, va = X_normal[:cut], X_normal[cut:]
    sc = StandardScaler().fit(tr)
    cov = LedoitWolf().fit(sc.transform(tr))
    det = Detector(sc, cov, 0.0)
    det.threshold = float(np.quantile(det.score(va), 1 - fa_rate))
    return det


def debounce(flags: np.ndarray, k: int) -> np.ndarray:
    """k 번 연속 True 가 된 시점부터 True (연속이 끊기면 다시 False)"""
    out = np.zeros_like(flags, dtype=bool)
    run = 0
    for i, f in enumerate(flags):
        run = run + 1 if f else 0
        out[i] = run >= k
    return out


def alert_latency(is_fault: np.ndarray, alerts: np.ndarray) -> list[int]:
    """정상→고장으로 바뀐 각 구간에서 처음 경보까지 걸린 사이클 수 (그 고장 구간 안에서 경보가 없으면 -1)"""
    lat, i, n = [], 0, len(is_fault)
    while i < n:
        if is_fault[i] and (i == 0 or not is_fault[i - 1]):
            j = i
            while j < n and is_fault[j] and not alerts[j]:
                j += 1
            lat.append(j - i if j < n and is_fault[j] else -1)
            while i < n and is_fault[i]:
                i += 1
        else:
            i += 1
    return lat
