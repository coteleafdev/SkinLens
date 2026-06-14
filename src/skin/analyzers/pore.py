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
from src.utils.config import load_config
from src.utils.cv_utils import blob_log_cv

log = logging.getLogger(__name__)


# 헬퍼 함수는 scoring_utils에서 import
_clamp = clamp
_area_to_score = area_to_score
_safe_region = safe_region


def _get_cv_analyzer_params(analyzer: str, metric: str) -> Dict:
    """config.json에서 CV 분석기 파라미터 로드.

    Args:
        analyzer: 분석기 이름 (예: 'pigmentation', 'pore', 'wrinkle')
        metric: 메트릭 이름 (예: 'melasma', 'freckle', 'blob_detection')

    Returns:
        파라미터 딕셔너리. config 누락 시 빈 딕셔너리 반환.
    """
    try:
        config = load_config()
        return config.get("cv_analyzers", {}).get(analyzer, {}).get(metric, {})
    except Exception as e:
        log.warning(f"CV analyzer params load failed for {analyzer}.{metric}: {e}")
        return {}


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


def _chroma_gate_blobs(
    reg_bgr: np.ndarray,
    blobs: np.ndarray,
    *,
    delta_L: float = 1.0,
    tau_C: float = 5.0,
) -> np.ndarray:
    """[§H Part 1] 크로마 인식 blob 게이트 (region 베이스라인 대비).

    모공 = 무채색 명도 함몰(피부 평균색과 같은 색, 단지 어두움).
    melasma = 유채색 갈색 패치(피부 평균보다 C* 높음). melasma 는 '큰 확산 패치'라
    blob 의 로컬 링까지 같은 색으로 덮여 *로컬* 크로마 초과가 0 → 로컬 비교로는 못 잡는다.
    따라서 **region 피부 베이스라인(중앙값) 대비 절대 크로마 초과**로 판정한다.

    keep(모공): 베이스라인보다 어둡고(intensity_dip) AND 베이스라인 대비 유채색 아님.
    reject(melasma/색소): 베이스라인 대비 C* 가 tau_C 이상 높음.

    Args:
        delta_L: 모공으로 인정할 최소 명도 함몰(피부 baseline L* 대비)
        tau_C:   melasma 로 판정할 크로마 초과(피부 baseline C* 대비)
    """
    if blobs is None or len(blobs) == 0:
        return np.empty((0, 3))
    lab = cv2.cvtColor(_safe_region(reg_bgr), cv2.COLOR_BGR2LAB).astype(np.float32)
    L = lab[:, :, 0]
    A = lab[:, :, 1] - 128.0
    B = lab[:, :, 2] - 128.0
    Cstar = np.sqrt(A * A + B * B)
    H, W = L.shape
    base_L = float(np.median(L))       # region 피부 명도 baseline
    base_C = float(np.median(Cstar))   # region 피부 크로마 baseline
    kept: List[np.ndarray] = []
    for b in blobs:
        y, x, sig = int(round(b[0])), int(round(b[1])), float(max(b[2], 1.0))
        r_in = max(1, int(round(1.5 * sig)))
        y0, y1 = max(0, y - r_in), min(H, y + r_in + 1)
        x0, x1 = max(0, x - r_in), min(W, x + r_in + 1)
        if y1 <= y0 or x1 <= x0:
            continue
        cL = float(np.mean(L[y0:y1, x0:x1]))
        cC = float(np.mean(Cstar[y0:y1, x0:x1]))
        intensity_dip = base_L - cL      # 모공/색소 모두 양수(어두움)
        chroma_excess = cC - base_C      # melasma 면 양수(피부보다 유채색)
        if chroma_excess >= tau_C:
            continue                     # 유채색 패치 위 → 색소(melasma) 제거
        if intensity_dip > delta_L:
            kept.append(b)               # 무채색 함몰 → 모공 유지
        # else: 함몰 미약 → 제거
    return np.vstack(kept) if kept else np.empty((0, 3))
    return np.vstack(kept) if kept else np.empty((0, 3))


def _collect_pore_blobs(
    pore_regions: List[np.ndarray],
    blob_params: Dict,
    clahe_clip: float = 2.2,
    clahe_tile: tuple = (8, 8),
) -> np.ndarray:
    # [§H Part 1] 크로마 게이트 (기본 ON). OFF 시 기존 전역 NMS 경로를 그대로 보존(legacy 롤백).
    chroma_gate = blob_params.get("chroma_gate", True)
    gate_dL = blob_params.get("gate_delta_L", 1.0)
    gate_tC = blob_params.get("gate_tau_C", 5.0)
    parts: List[np.ndarray] = []          # legacy 전역 경로
    gated_regions: List[np.ndarray] = []  # 게이트 경로 (region별)
    for reg in pore_regions:
        reg = _safe_region(reg)
        if min(reg.shape[:2]) < 10:
            continue
        reg_parts: List[np.ndarray] = []
        gray_r  = cv2.cvtColor(reg, cv2.COLOR_BGR2GRAY)
        inv_plain = np.uint8(255) - gray_r
        for thr in blob_params.get("thresholds", [0.055, 0.042, 0.030, 0.022]):
            try:
                b = blob_log_cv(inv_plain,
                             min_sigma=blob_params.get("min_sigma", 1.12),
                             max_sigma=blob_params.get("max_sigma", 6.5),
                             num_sigma=blob_params.get("num_sigma", 6),
                             threshold=thr,
                             overlap=blob_params.get("overlap", 0.35))
                if len(b) > 0:
                    reg_parts.append(b)
            except Exception as e:
                log.debug("blob_log_cv 1차 임계 루프 실패: %s", e)
                pass
        clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=clahe_tile)
        g2    = clahe.apply(gray_r)
        inv_ce = np.uint8(255) - g2
        for thr in blob_params.get("thresholds", [0.055, 0.042, 0.030, 0.022]):
            try:
                b = blob_log_cv(inv_ce,
                             min_sigma=blob_params.get("min_sigma", 1.12),
                             max_sigma=blob_params.get("max_sigma", 6.5),
                             num_sigma=blob_params.get("num_sigma", 6),
                             threshold=thr,
                             overlap=blob_params.get("overlap", 0.35))
                if len(b) > 0:
                    reg_parts.append(b)
            except Exception as e:
                log.debug("blob_log_cv 2차 CLAHE 루프 실패: %s", e)
                pass
        if not reg_parts:
            continue
        if chroma_gate:
            # region별 NMS → 그 region 이미지로 크로마 게이트 (좌표계 일치 보장)
            reg_blobs = _merge_pore_blobs_nms(np.vstack(reg_parts))
            reg_blobs = _chroma_gate_blobs(reg, reg_blobs, delta_L=gate_dL, tau_C=gate_tC)
            if len(reg_blobs) > 0:
                gated_regions.append(reg_blobs)
        else:
            parts.extend(reg_parts)
    if chroma_gate:
        return np.vstack(gated_regions) if gated_regions else np.empty((0, 3))
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

# [§H Part 3] 텍스처 폴백 재보정 — clean baseline L_clean≈4.04 (합성 측정) → 88 에 앵커.
#   기존 폴백은 clean(L≈4.04)을 49.6 으로 매핑해 blob 경로(91)와 불일치 → 절벽 원인.
#   v2 는 매끄러운 clean = 모공 적음 = 높은 점수가 되도록 재앵커. 거칠수록(모공 많을수록) 하강.
_L_CLEAN = 4.04
_BP_LAPLACIAN_FALLBACK_V2 = [
    (0.0, 96.0),            (_L_CLEAN,       91.0), (_L_CLEAN * 1.8, 78.0),
    (_L_CLEAN * 3.0, 60.0), (_L_CLEAN * 5.0, 42.0), (_L_CLEAN * 8.0, 20.0),
    (_L_CLEAN * 12.0, 0.0),
]
# [§H Part 2] blob↔텍스처 블렌드 신뢰도 기준 개수. gated_count>=N_REF → blob 경로 지배.
_PORE_BLEND_N_REF = 6.0


def analyze_pores(
    face: np.ndarray,
    regions: Dict[str, np.ndarray],
    *,
    blob_params: Optional[Dict] = None,
    clahe_clip: float = 2.2,
    clahe_tile: tuple = (8, 8),
    bp_pore_density: Optional[list] = None,
    bp_sagging_lap: Optional[list] = None,
    size_mode: str = "gated_blend",
) -> Dict[str, float]:
    """모공 3항목 분석.

    Args:
        size_mode: "gated_blend"(기본, §H — 크로마 게이트 + 연속 블렌드) 또는
                   "legacy"(기존 전역 NMS + 이분 분기, 롤백용).
    Returns:
        {"pore_size_score": float, "pore_count": int, "pore_sagging_score": float}
    """
    # Config에서 파라미터 로드
    blob_config = _get_cv_analyzer_params("pore", "blob_detection")
    sagging_config = _get_cv_analyzer_params("pore", "sagging")

    # 기본값 설정 (config 누락 시)
    blob_thresholds = blob_config.get("thresholds", [0.055, 0.042, 0.030, 0.022])
    blob_min_sigma = blob_config.get("min_sigma", 1.12)
    blob_max_sigma = blob_config.get("max_sigma", 6.5)
    blob_num_sigma = blob_config.get("num_sigma", 6)
    blob_overlap = blob_config.get("overlap", 0.35)
    blob_chroma_gate = blob_config.get("chroma_gate", True)
    blob_gate_delta_L = blob_config.get("gate_delta_L", 1.0)
    blob_gate_tau_C = blob_config.get("gate_tau_C", 5.0)

    sagging_ellipse_ratio = sagging_config.get("ellipse_ratio_threshold", 1.45)

    # blob_params 기본값 설정
    blob_params = dict(blob_params or {})
    blob_params.setdefault("thresholds", blob_thresholds)
    blob_params.setdefault("min_sigma", blob_min_sigma)
    blob_params.setdefault("max_sigma", blob_max_sigma)
    blob_params.setdefault("num_sigma", blob_num_sigma)
    blob_params.setdefault("overlap", blob_overlap)
    blob_params.setdefault("chroma_gate", blob_chroma_gate)
    blob_params.setdefault("gate_delta_L", blob_gate_delta_L)
    blob_params.setdefault("gate_tau_C", blob_gate_tau_C)

    bp_pore_density  = bp_pore_density  or _BP_PORE_SIZE_DENSITY
    bp_sagging_lap   = bp_sagging_lap   or _BP_SAGGING_LAP
    legacy = (size_mode == "legacy")
    if legacy:
        blob_params["chroma_gate"] = False

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
    if legacy:
        # ── 기존 이분 분기 (롤백 경로) ──
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
    else:
        # ── §H Part 2+3: 신뢰도 가중 블렌드 (절벽 제거) ──
        _SBP = [(0, 100), (0.25, 92), (0.55, 78), (0.90, 60),
                (1.40, 40), (2.20, 18), (3.00, 0)]
        if pore_total_count > 0:
            avg_sigma = float(np.median(blobs_all[:, 2]))
            rel = avg_sigma / max(fw_px, 1) * 100.0
            score_blob = min(
                _area_to_score(rel, _SBP),
                _area_to_score(pore_density, bp_pore_density),
            )
        else:
            score_blob = 95.0  # 게이트 후 0개 = 가시 모공 없음 → 높은 점수(블렌드에서 w→0)
        e = _pore_texture_laplacian_mean(regions, ("forehead", "left_cheek", "right_cheek", "nose"))
        score_tex = _area_to_score(e, _BP_LAPLACIAN_FALLBACK_V2) if e is not None else 88.0
        w = _clamp(pore_total_count / _PORE_BLEND_N_REF, 0.0, 1.0)
        pore_size_score = w * score_blob + (1.0 - w) * score_tex

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
                    if mi > 0 and ma / mi > sagging_ellipse_ratio:
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
