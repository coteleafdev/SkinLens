"""src/skin/core/scoring_utils.py

공통 점수 계산 유틸리티 함수.

이 모듈은 도메인별 분석기(pigmentation, redness, pore, wrinkle_texture, tone_elasticity)에서
공통으로 사용하는 헬퍼 함수들을 제공한다.
"""
from __future__ import annotations

import cv2
import logging
import numpy as np

log = logging.getLogger(__name__)


def clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """값을 지정된 범위로 클램프."""
    return float(np.clip(v, lo, hi))


def area_to_score(ratio: float, breakpoints: list) -> float:
    """면적 비율을 점수로 변환."""
    if ratio <= breakpoints[0][0]:
        return breakpoints[0][1]
    if ratio >= breakpoints[-1][0]:
        return breakpoints[-1][1]
    for i in range(len(breakpoints) - 1):
        r0, s0 = breakpoints[i]
        r1, s1 = breakpoints[i + 1]
        if r0 <= ratio <= r1:
            if r1 == r0:
                return s0
            return s0 + (ratio - r0) / (r1 - r0) * (s1 - s0)
    return 0.0


def count_to_score(count: int, breakpoints: list) -> float:
    """개수를 점수로 변환."""
    if count <= breakpoints[0][0]:
        return breakpoints[0][1]
    if count >= breakpoints[-1][0]:
        return breakpoints[-1][1]
    for i in range(len(breakpoints) - 1):
        n0, s0 = breakpoints[i]
        n1, s1 = breakpoints[i + 1]
        if n0 <= count <= n1:
            if n1 == n0:
                return s0
            return s0 + (count - n0) / (n1 - n0) * (s1 - s0)
    return 0.0


def safe_region(arr: np.ndarray) -> np.ndarray:
    """안전한 영역 반환 (너무 작으면 더미 배열 반환)."""
    if arr is None or arr.size == 0 or min(arr.shape[:2]) < 4:
        return np.zeros((10, 10, 3), dtype=np.uint8)
    return arr


def strip_normalize_L(
    L_ch: np.ndarray,
    mask_bool: np.ndarray,
    n_strips: int = 10,
) -> np.ndarray:
    """수평 스트립별 중앙값을 빼서 조명 그라디언트 제거."""
    if not mask_bool.any():
        return L_ch.copy()
    
    # 배열 크기 검증
    if L_ch.shape != mask_bool.shape:
        log.warning(f"strip_normalize_L: 크기 불일치 L_ch={L_ch.shape}, mask={mask_bool.shape}")
        # 마스크를 L_ch 크기에 맞게 리사이즈
        if mask_bool.ndim == 2 and L_ch.ndim == 2:
            mask_bool = cv2.resize(mask_bool.astype(np.uint8), (L_ch.shape[1], L_ch.shape[0]), 
                                   interpolation=cv2.INTER_NEAREST).astype(bool)
        else:
            return L_ch.copy()
    
    L_norm = L_ch.copy()
    ys, _ = np.where(mask_bool)
    y_min, y_max = int(ys.min()), int(ys.max())
    sh = max((y_max - y_min) // n_strips, 4)
    for y_s in range(y_min, y_max + 1, sh):
        y_e = min(y_s + sh, y_max + 1)
        strip_sk = mask_bool[y_s:y_e, :]
        if strip_sk.any():
            strip_L = L_ch[y_s:y_e, :]
            # 크기 검증
            if strip_L.shape != strip_sk.shape:
                continue
            # 안전한 인덱싱: np.where로 인덱스 추출 후 사용
            strip_indices = np.where(strip_sk)
            if len(strip_indices[0]) > 0:
                smed = float(np.median(strip_L[strip_indices]))
                L_norm[y_s:y_e, :] = L_ch[y_s:y_e, :] - smed
    return L_norm
