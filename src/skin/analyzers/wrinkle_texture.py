"""src/skin/analyzers/wrinkle_texture.py

주름·텍스처·복원품질 분석 — _SkinAnalyzerV2 분리.

분석 항목 (주름):
  eye_wrinkle_score, glabella_wrinkle_score,
  nasolabial_wrinkle_score, fine_deep_wrinkle_score

분석 항목 (텍스처):
  roughness_score, dead_skin_score, smoothness_score

분석 항목 (복원품질):
  noise_score, detail_score, color_balance_score
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

import cv2
import numpy as np

from src.config.roi_manager import ROIManager
from src.skin.core.scoring_utils import (
    area_to_score,
    clamp,
    safe_region,
)

log = logging.getLogger(__name__)

try:
    from skimage.feature import graycomatrix, graycoprops, local_binary_pattern
    _SKIMAGE_OK = True
except ImportError:
    graycomatrix = graycoprops = local_binary_pattern = None
    _SKIMAGE_OK = False


# 헬퍼 함수는 scoring_utils에서 import
_clamp = clamp
_area_to_score = area_to_score
_safe_region = safe_region


def _sobel_components(gray_raw: np.ndarray):
    blurred = cv2.GaussianBlur(gray_raw, (3, 3), 0)
    sx = cv2.Sobel(blurred.astype(float), cv2.CV_64F, 1, 0, ksize=3)
    sy = cv2.Sobel(blurred.astype(float), cv2.CV_64F, 0, 1, ksize=3)
    mag  = float(np.mean(np.sqrt(sx ** 2 + sy ** 2)))
    sx_m = float(np.mean(np.abs(sx)))
    sy_m = float(np.mean(np.abs(sy)))
    return mag, sx_m, sy_m


# ─────────────────────────────────────────────────────────────────
# 주름 분석
# ─────────────────────────────────────────────────────────────────

def analyze_wrinkles(
    face: np.ndarray,
    regions: Dict[str, np.ndarray],
    *,
    clahe_preprocessed: bool = False,
    skin_mask: Optional[np.ndarray] = None,
    bp_eye: Optional[list] = None,
    bp_nasolabial: Optional[list] = None,
) -> Dict[str, float]:
    """주름 4항목 분석.

    Returns:
        {eye_wrinkle_score, glabella_wrinkle_score,
         nasolabial_wrinkle_score, fine_deep_wrinkle_score}
    """
    _BP = (
        [(0, 100), (28, 90), (55, 75), (95, 55), (145, 30), (210, 0)]
        if clahe_preprocessed
        else [(0, 100), (14, 90), (28, 75), (50, 55), (78, 30), (115, 0)]
    )
    bp_eye       = bp_eye       or _BP
    bp_nasolabial = bp_nasolabial or _BP

    # (1) 눈가 주름
    eye_scores: List[float] = []
    for key in ("left_canthus", "right_canthus"):
        reg = _safe_region(regions.get(key, np.zeros((10, 10, 3), np.uint8)))
        if min(reg.shape[:2]) < 8:
            continue
        rw = reg.shape[1]
        inner = reg[:, int(rw * 0.20): int(rw * 0.80)]
        if inner.shape[1] < 4:
            inner = reg
        gray_e = cv2.cvtColor(inner, cv2.COLOR_BGR2GRAY)
        mag, _, sy_m = _sobel_components(gray_e)
        eye_scores.append(_area_to_score(sy_m * 0.65 + mag * 0.35, bp_eye))
    eye_wrinkle_score = float(np.mean(eye_scores)) if eye_scores else 65.0

    # (2) 미간 주름
    glabella = _safe_region(regions.get("glabella", np.zeros((10, 10, 3), np.uint8)))
    if min(glabella.shape[:2]) >= 8:
        gray_gl = cv2.cvtColor(glabella, cv2.COLOR_BGR2GRAY)
        mag, sx_m, _ = _sobel_components(gray_gl)
        glabella_wrinkle_score = _area_to_score(sx_m * 0.65 + mag * 0.35, _BP)
    else:
        glabella_wrinkle_score = 65.0

    # (3) 팔자 주름 (skin_mask 적용)
    nl_scores: List[float] = []
    fh_w, fw_w = face.shape[:2]
    for key in ("nasolabial_l", "nasolabial_r"):
        reg = _safe_region(regions.get(key, np.zeros((10, 10, 3), np.uint8)))
        if min(reg.shape[:2]) < 8:
            continue
        gray_nl = cv2.cvtColor(reg, cv2.COLOR_BGR2GRAY)
        if skin_mask is not None:
            y0_nl = int(fh_w * 0.48); y1_nl = int(fh_w * 0.80)
            if key == "nasolabial_l":
                x0_nl, x1_nl = 0, int(fw_w * 0.38)
            else:
                x0_nl, x1_nl = int(fw_w * 0.62), fw_w
            sm_nl = skin_mask[y0_nl:y1_nl, x0_nl:x1_nl]
            sm_nl_rs = cv2.resize(sm_nl, (reg.shape[1], reg.shape[0]), interpolation=cv2.INTER_NEAREST)
            if float(np.mean(sm_nl_rs > 0)) >= 0.30:
                blurred_nl = cv2.GaussianBlur(gray_nl, (3, 3), 0)
                sx_nl = cv2.Sobel(blurred_nl.astype(float), cv2.CV_64F, 1, 0, ksize=3)
                sy_nl = cv2.Sobel(blurred_nl.astype(float), cv2.CV_64F, 0, 1, ksize=3)
                mag_arr = np.sqrt(sx_nl ** 2 + sy_nl ** 2)
                skin_px_nl = sm_nl_rs > 0
                mag_val = float(np.mean(mag_arr[skin_px_nl])) if skin_px_nl.any() else float(np.mean(mag_arr))
                nl_scores.append(_area_to_score(mag_val, bp_nasolabial))
                continue
        mag, _, _ = _sobel_components(gray_nl)
        nl_scores.append(_area_to_score(mag, bp_nasolabial))
    nasolabial_wrinkle_score = float(np.mean(nl_scores)) if nl_scores else 65.0

    # (4) 잔주름·깊은 주름
    # [FIX P1-10] 직교 위반 수정: 전체 얼굴 → 이마 ROI로 제한
    # fine_deep_wrinkle_score는 이마의 깊은 주름을 측정하도록 변경
    # roughness_score(전체 얼굴 LBP)와 직교성 확보
    # [REFACTOR P1] ROIManager 사용: 중앙화된 ROI 관리자 사용
    roi_manager = ROIManager.get_instance()
    forehead = roi_manager.get_forehead_roi(face)
    gray_forehead = cv2.cvtColor(forehead, cv2.COLOR_BGR2GRAY).astype(float)
    
    win = 9
    mean_sq   = cv2.boxFilter(gray_forehead ** 2, -1, (win, win))
    mean_v    = cv2.boxFilter(gray_forehead,       -1, (win, win))
    local_std = np.sqrt(np.maximum(mean_sq - mean_v ** 2, 0.0))
    if clahe_preprocessed:
        _thr_fine_lo, _thr_fine_hi, _thr_deep = 32, 80, 80
    else:
        _thr_fine_lo, _thr_fine_hi, _thr_deep = 8, 20, 20
    deep_ratio = float(np.mean(local_std > _thr_deep))
    fine_ratio = float(np.mean((local_std > _thr_fine_lo) & (local_std <= _thr_fine_hi)))
    deep_score = _area_to_score(deep_ratio, bp_eye)
    fine_score = _area_to_score(fine_ratio, bp_nasolabial)
    fine_deep_score = 0.60 * deep_score + 0.40 * fine_score

    return {
        "eye_wrinkle_score":        round(_clamp(eye_wrinkle_score), 1),
        "glabella_wrinkle_score":   round(_clamp(glabella_wrinkle_score), 1),
        "nasolabial_wrinkle_score": round(_clamp(nasolabial_wrinkle_score), 1),
        "fine_deep_wrinkle_score":  round(_clamp(fine_deep_score), 1),
    }


# ─────────────────────────────────────────────────────────────────
# 텍스처 분석
# ─────────────────────────────────────────────────────────────────

_BP_ROUGHNESS = [
    (0, 100), (10, 90), (35, 75), (80, 55), (180, 30), (400, 0),
]


def analyze_texture(
    face: np.ndarray,
    regions: Dict[str, np.ndarray],
    skin_mask: np.ndarray,
    *,
    clahe_clip: float = 2.0,
    clahe_tile: tuple = (8, 8),
    bp_roughness: Optional[list] = None,
) -> Dict[str, float]:
    """텍스처 3항목 분석.

    Returns:
        {roughness_score, dead_skin_score, smoothness_score}
    """
    bp_roughness = bp_roughness or _BP_ROUGHNESS

    clahe      = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=clahe_tile)
    gray_face  = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
    gray_enh   = clahe.apply(gray_face)
    hsv        = cv2.cvtColor(face, cv2.COLOR_BGR2HSV)
    V_ch       = hsv[:, :, 2]
    S_ch       = hsv[:, :, 1]

    # (1) 거칠기 (LBP 분산)
    roughness_score = 65.0
    if _SKIMAGE_OK and local_binary_pattern is not None:
        lbp_vars: List[float] = []
        for radius in [1, 2, 3]:
            lbp = local_binary_pattern(gray_enh, P=8 * radius, R=radius, method="uniform")
            lbp_vars.append(float(np.var(lbp)))
        coarseness = float(np.mean(lbp_vars))
        roughness_score = _area_to_score(coarseness, bp_roughness)

    # (2) 각질 (dead skin) 계산
    # HSV 채널 분석: 낮은 채도(S) + 높은 명도(V) = 각질 가능성
    # 텍스처 불규칙성: 엣지 강도 분석
    sobel_x = cv2.Sobel(gray_enh, cv2.CV_64F, 1, 0, ksize=3)
    sobel_y = cv2.Sobel(gray_enh, cv2.CV_64F, 0, 1, ksize=3)
    edge_magnitude = np.sqrt(sobel_x**2 + sobel_y**2)
    
    # 각질 영역 마스크 (낮은 채도 + 높은 명도 + 높은 엣지)
    saturation_threshold = 40  # 낮은 채도
    value_threshold = 180     # 높은 명도
    edge_threshold = 30       # 높은 엣지
    
    dead_skin_mask = (S_ch < saturation_threshold) & (V_ch > value_threshold) & (edge_magnitude > edge_threshold)
    
    # 각질 영역 비율
    total_skin_pixels = skin_mask.sum() if skin_mask is not None else (gray_enh.shape[0] * gray_enh.shape[1])
    dead_skin_area = dead_skin_mask.sum()
    
    if total_skin_pixels > 0:
        dead_skin_ratio = dead_skin_area / total_skin_pixels
    else:
        dead_skin_ratio = 0.0
    
    # 각질 점수 (비율이 높을수록 점수 낮음)
    # 브레이크포인트: 0%→100, 5%→70, 10%→40, 20%→0
    bp_dead_skin = [(0.0, 100), (0.05, 70), (0.10, 40), (0.20, 0)]
    dead_skin_score = _area_to_score(dead_skin_ratio, bp_dead_skin)

    # (3) 매끄러움 (smoothness) 계산
    # 거칠기의 역수 + 그라디언트 매그니튜드 분석
    # 낮은 그라디언트 = 매끄러운 피부
    gradient_mean = float(np.mean(edge_magnitude))
    
    # 그라디언트 평균 기반 매끄러움 점수
    # 낮은 그라디언트 = 높은 점수
    # 브레이크포인트: 0→100, 20→90, 50→70, 100→40, 200→0
    bp_smoothness = [(0.0, 100), (20.0, 90), (50.0, 70), (100.0, 40), (200.0, 0)]
    smoothness_score = _area_to_score(gradient_mean, bp_smoothness)

    return {
        "roughness_score": round(_clamp(roughness_score), 1),
        "dead_skin_score": round(_clamp(dead_skin_score), 1),
        "smoothness_score": round(_clamp(smoothness_score), 1),
    }


# ─────────────────────────────────────────────────────────────────
# 복원 품질 분석
# ─────────────────────────────────────────────────────────────────

def analyze_restoration_quality(
    face: np.ndarray,
    regions: Dict[str, np.ndarray],
    skin_mask: np.ndarray,
) -> Dict[str, float]:
    """복원 효과 3항목 분석 (noise, detail, color_balance).

    Returns:
        {noise_score, detail_score, color_balance_score}
    """
    gray = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
    lab  = cv2.cvtColor(face, cv2.COLOR_BGR2LAB)
    sk   = skin_mask > 0

    # (1) 노이즈 (Gaussian 5×5 잔차)
    blur5 = cv2.GaussianBlur(gray, (5, 5), 0)
    noise_level = float(cv2.absdiff(gray, blur5)[sk].mean()) if sk.any() else 0.0
    noise_score = _area_to_score(noise_level,
        [(0.0, 100), (0.3, 92), (0.7, 78), (1.0, 68),
         (1.5, 55),  (2.0, 42), (2.8, 28), (4.0, 12), (6.0, 0)])

    # (2) 디테일 매끄러움 (Gaussian 3×3 잔차)
    blur3 = cv2.GaussianBlur(gray, (3, 3), 0)
    detail_level = float(cv2.absdiff(gray, blur3)[sk].mean()) if sk.any() else 0.0
    detail_score = _area_to_score(detail_level,
        [(0.0, 100), (0.2, 92), (0.4, 80), (0.7, 65),
         (1.0, 50),  (1.5, 32), (2.5, 12), (4.0, 0)])

    # (3) 색상 균형 (LAB 채널 std 평균)
    l_std = float(lab[:, :, 0][sk].std()) if sk.any() else 0.0
    a_std = float(lab[:, :, 1][sk].std()) if sk.any() else 0.0
    b_std = float(lab[:, :, 2][sk].std()) if sk.any() else 0.0
    color_variance = (l_std + a_std + b_std) / 3.0
    color_balance_score = _area_to_score(color_variance,
        [(0.0, 100), (10.0, 88), (13.0, 78), (15.0, 70),
         (17.0, 60), (19.0, 48), (22.0, 35), (28.0, 18), (40.0, 0)])

    return {
        "noise_score":         round(_clamp(noise_score), 1),
        "detail_score":        round(_clamp(detail_score), 1),
        "color_balance_score": round(_clamp(color_balance_score), 1),
    }
