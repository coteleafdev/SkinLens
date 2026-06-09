"""src/skin/analyzers/pore.py

모공 카테고리 분석 — _SkinAnalyzerV2._analyze_pores 분리.

분석 항목:
  pore_size_score    : 모공 크기 (LoG blob 중앙값 sigma)
  pore_count         : 모공 개수 (raw)
  pore_sagging_score : 모공 늘어짐 (Otsu 타원비 + Laplacian)
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

import cv2
import numpy as np

from src.skin.core.scoring_utils import (
    area_to_score,
    clamp,
    safe_region,
)

log = logging.getLogger(__name__)

try:
    from skimage.feature import blob_log
    _SKIMAGE_OK = True
except ImportError:
    blob_log = None
    _SKIMAGE_OK = False


# 헬퍼 함수는 scoring_utils에서 import
_clamp = clamp
_area_to_score = area_to_score
_safe_region = safe_region


def _merge_pore_blobs_nms(blobs: np.ndarray, dist_scale: float = 1.35) -> np.ndarray:
    """blob NMS (Non-Maximum Suppression) - cKDTree 최적화.

    [REFACTOR P2-23] O(n²) 이중 루프 → cKDTree O(n log n) 최적화.
    scikit-learn의 KDTree를 사용하여 거리 계산 최적화.

    Args:
        blobs: (N, 3) 배열 - [y, x, signal]
        dist_scale: 거리 스케일 팩터

    Returns:
        필터링된 (M, 3) 배열
    """
    if blobs is None or len(blobs) == 0:
        return np.empty((0, 3))
    rows = np.asarray(blobs, dtype=np.float64)
    if rows.ndim != 2 or rows.shape[1] < 3:
        return np.empty((0, 3))

    # 신호 강도로 정렬 (강한 신호 우선)
    rows = rows[np.argsort(rows[:, 2])]

    kept: List[np.ndarray] = []
    kept_coords: List[tuple[float, float]] = []

    # cKDTree lazy import (선택적 의존성)
    try:
        from scipy.spatial import cKDTree
        use_kdtree = True
    except ImportError:
        use_kdtree = False
        log.warning("scipy.spatial.cKDTree를 import하지 못했습니다. 폴백 O(n²) 알고리즘 사용.")

    for b in rows:
        y, x, sig = float(b[0]), float(b[1]), float(max(b[2], 0.12))
        dmin = dist_scale * max(2.8, sig * 2.3)
        ok = True

        if use_kdtree and len(kept_coords) > 0:
            # cKDTree를 사용한 O(n log n) 거리 계산
            tree = cKDTree(kept_coords)
            # 가장 가까운 1개 이웃 쿼리
            dist, _ = tree.query([(y, x)], k=1)
            if dist[0] < dmin:
                ok = False
        else:
            # 폴백 O(n²) 이중 루프
            for k in kept:
                dy = y - float(k[0])
                dx = x - float(k[1])
                if dy * dy + dx * dx < dmin * dmin:
                    ok = False
                    break

        if ok:
            kept.append(np.asarray(b, dtype=np.float64))
            kept_coords.append((y, x))

    return np.vstack(kept) if kept else np.empty((0, 3))


def _pore_texture_laplacian_mean(
    regions: Dict[str, np.ndarray],
    keys: tuple,
) -> Optional[float]:
    vals: List[float] = []
    for key in keys:
        reg = _safe_region(regions.get(key, np.zeros((10, 10, 3), np.uint8)))
        if min(reg.shape[:2]) < 10:
            continue
        gray = cv2.cvtColor(reg, cv2.COLOR_BGR2GRAY).astype(np.float32)
        lap  = cv2.Laplacian(gray, cv2.CV_32F, ksize=3)
        vals.append(float(np.mean(np.abs(lap))))
    return float(sum(vals) / len(vals)) if vals else None


def _collect_pore_blobs(
    pore_regions: List[np.ndarray],
    blob_params: Dict,
    clahe_clip: float = 2.2,
    clahe_tile: tuple = (8, 8),
) -> np.ndarray:
    parts: List[np.ndarray] = []
    for reg in pore_regions:
        reg = _safe_region(reg)
        if min(reg.shape[:2]) < 10 or not _SKIMAGE_OK or blob_log is None:
            continue
        gray_r  = cv2.cvtColor(reg, cv2.COLOR_BGR2GRAY)
        inv_plain = np.uint8(255) - gray_r
        for thr in blob_params.get("thresholds", [0.055, 0.042, 0.030, 0.022]):
            try:
                b = blob_log(inv_plain,
                             min_sigma=blob_params.get("min_sigma", 1.12),
                             max_sigma=blob_params.get("max_sigma", 6.5),
                             num_sigma=blob_params.get("num_sigma", 6),
                             threshold=thr,
                             overlap=blob_params.get("overlap", 0.35))
                if len(b) > 0:
                    parts.append(b)
            except Exception as e:
                log.debug("blob_log 1차 임계 루프 실패: %s", e)
                pass
        clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=clahe_tile)
        g2    = clahe.apply(gray_r)
        inv_ce = np.uint8(255) - g2
        for thr in blob_params.get("thresholds", [0.055, 0.042, 0.030, 0.022]):
            try:
                b = blob_log(inv_ce,
                             min_sigma=blob_params.get("min_sigma", 1.12),
                             max_sigma=blob_params.get("max_sigma", 6.5),
                             num_sigma=blob_params.get("num_sigma", 6),
                             threshold=thr,
                             overlap=blob_params.get("overlap", 0.35))
                if len(b) > 0:
                    parts.append(b)
            except Exception as e:
                log.debug("blob_log 2차 CLAHE 루프 실패: %s", e)
                pass
    if not parts:
        return np.empty((0, 3))
    return _merge_pore_blobs_nms(np.vstack(parts))


_BP_PORE_SIZE_DENSITY = [
    (0, 100), (10, 90), (20, 77), (35, 63),
    (55, 47), (80, 30), (120, 10), (200, 0),
]
_BP_SAGGING_LAP = [
    (0.0, 100), (3.0, 76), (5.5, 58), (8.0, 42),
    (12.0, 24), (18.0, 8), (25.0, 0),
]
_BP_LAPLACIAN_FALLBACK = [
    (0.0, 100), (0.8, 90), (1.8, 76), (3.0, 60),
    (4.8, 42),  (7.0, 24), (10.5, 8), (15.0, 0),
]


def analyze_pores(
    face: np.ndarray,
    regions: Dict[str, np.ndarray],
    *,
    blob_params: Optional[Dict] = None,
    clahe_clip: float = 2.2,
    clahe_tile: tuple = (8, 8),
    bp_pore_density: Optional[list] = None,
    bp_sagging_lap: Optional[list] = None,
) -> Dict[str, float]:
    """모공 3항목 분석.

    Returns:
        {"pore_size_score": float, "pore_count": int, "pore_sagging_score": float}
    """
    blob_params      = blob_params      or {}
    bp_pore_density  = bp_pore_density  or _BP_PORE_SIZE_DENSITY
    bp_sagging_lap   = bp_sagging_lap   or _BP_SAGGING_LAP

    pore_regions = [
        regions.get("forehead",    np.zeros((10, 10, 3), np.uint8)),
        regions.get("left_cheek",  np.zeros((10, 10, 3), np.uint8)),
        regions.get("right_cheek", np.zeros((10, 10, 3), np.uint8)),
        regions.get("nose",        np.zeros((10, 10, 3), np.uint8)),
    ]
    blobs_all = _collect_pore_blobs(pore_regions, blob_params, clahe_clip, clahe_tile)
    pore_total_count = len(blobs_all)
    _h_px, fw_px = face.shape[:2]
    face_area_px = max(int(_h_px * fw_px), 1)
    pore_density = float(pore_total_count) / max(face_area_px / 10000.0, 1e-6)

    # (1) 모공 크기
    if pore_total_count > 0:
        avg_sigma = float(np.median(blobs_all[:, 2]))
        rel = avg_sigma / max(fw_px, 1) * 100.0
        _SBP = [(0, 100), (0.25, 92), (0.55, 78), (0.90, 60),
                (1.40, 40), (2.20, 18), (3.00, 0)]
        pore_size_score = min(
            _area_to_score(rel, _SBP),
            _area_to_score(pore_density, bp_pore_density),
        )
    else:
        e = _pore_texture_laplacian_mean(regions, ("forehead", "left_cheek", "right_cheek", "nose"))
        pore_size_score = _area_to_score(e, _BP_LAPLACIAN_FALLBACK) if e is not None else 55.0

    # (2) 모공 늘어짐
    elongated_count = 0
    total_contours  = 0
    for reg_key in ("lower_cheek_l", "lower_cheek_r"):
        reg = _safe_region(regions.get(reg_key, np.zeros((10, 10, 3), np.uint8)))
        if min(reg.shape[:2]) < 8:
            continue
        gray_lc = cv2.cvtColor(reg, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray_lc, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        cnts, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            area = cv2.contourArea(c)
            if area < 15 or area > 400:
                continue
            total_contours += 1
            if len(c) >= 5:
                try:
                    _, (ma, mi), _ = cv2.fitEllipse(c)
                    if mi > 0 and ma / mi > 1.45:
                        elongated_count += 1
                except Exception as e:
                    log.debug("fitEllipse 실패: %s", e)
                    pass

    sagging_ratio = elongated_count / max(total_contours, 1)
    if total_contours < 3:
        e_lc = _pore_texture_laplacian_mean(regions, ("lower_cheek_l", "lower_cheek_r"))
        pore_sagging_score = _area_to_score(e_lc, bp_sagging_lap) if e_lc is not None else 62.0
    else:
        score_otsu = _clamp(100.0 - sagging_ratio * 220.0)
        if   total_contours >= 28 and elongated_count == 0: score_otsu = min(score_otsu, 52.0)
        elif total_contours >= 14 and elongated_count == 0: score_otsu = min(score_otsu, 64.0)
        elif total_contours >= 8  and sagging_ratio < 0.12: score_otsu = min(score_otsu, 76.0)
        elif elongated_count == 0 and 3 <= total_contours < 8: score_otsu = min(score_otsu, 82.0)
        e_lc2 = _pore_texture_laplacian_mean(regions, ("lower_cheek_l", "lower_cheek_r"))
        if e_lc2 is not None:
            score_lap = _area_to_score(e_lc2, bp_sagging_lap)
            pore_sagging_score = _clamp(score_otsu * 0.36 + score_lap * 0.64)
        else:
            pore_sagging_score = score_otsu

    return {
        "pore_size_score":    round(_clamp(pore_size_score), 1),
        "pore_count":         pore_total_count,
        "pore_sagging_score": round(_clamp(pore_sagging_score), 1),
    }
