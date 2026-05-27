"""src/skin/analyzers/tone_elasticity.py

톤·탄력·피부타입·트러블 분석 — _SkinAnalyzerV2 분리.

분석 항목:
  [톤]      skin_tone_score, dullness_score, uneven_tone_score
  [탄력]    cheek_sagging_score, jawline_blur_score, eye_elasticity_score
  [피부타입] oily_score, dry_score, sebum_score, skin_type_label, skin_type_score
  [트러블]  acne_score, post_acne_pigment_score
  [보조]    dark_circle_score (float), perceived_age (float)
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
    strip_normalize_L,
)

log = logging.getLogger(__name__)

try:
    from skimage.feature import local_binary_pattern
    _SKIMAGE_OK = True
except ImportError:
    local_binary_pattern = None
    _SKIMAGE_OK = False


# 헬퍼 함수는 scoring_utils에서 import
_clamp = clamp
_area_to_score = area_to_score
_safe_region = safe_region
_strip_normalize_L = strip_normalize_L


# ─────────────────────────────────────────────────────────────────
# 톤·밝기 분석
# ─────────────────────────────────────────────────────────────────

def analyze_tone(
    face: np.ndarray,
    regions: Dict[str, np.ndarray],
    skin_mask: np.ndarray,
) -> Dict[str, float]:
    """피부톤·칙칙함·얼룩톤 3항목 분석."""
    lab  = cv2.cvtColor(face, cv2.COLOR_BGR2LAB)
    L_ch = lab[:, :, 0].astype(float)
    b_ch = lab[:, :, 2].astype(float)
    hsv  = cv2.cvtColor(face, cv2.COLOR_BGR2HSV)
    S_ch = hsv[:, :, 1].astype(float)
    V_ch = hsv[:, :, 2].astype(float)
    sk   = skin_mask > 0

    # (1) ITA 기반 skin_tone
    L_mean = float(np.mean(L_ch[sk])) if sk.any() else float(np.mean(L_ch))
    b_mean = float(np.mean(b_ch[sk])) if sk.any() else float(np.mean(b_ch))
    L_star = L_mean / 255.0 * 100.0
    b_star = float(b_mean - 128.0)
    b_floor = 2.8
    b_denom = float(np.copysign(b_floor, 1.0 if b_star >= 0.0 else -1.0)) if abs(b_star) < b_floor else b_star
    ITA = float(np.degrees(np.arctan2(L_star - 50.0, b_denom)))
    skin_tone_score = _clamp((ITA + 55.0) / 125.0 * 100.0)

    # (2) 칙칙함
    # 개선 (2026-05-22): ITA(L_mean)와의 신호 중복 감소
    #   - 이전: L_norm 0.50, S_norm 0.40, radiance 0.10 (L_mean 의존도 높음)
    #   - 개선: L_norm 0.20, S_norm 0.50, radiance 0.30 (채도/하이라이트 강화)
    L_norm = _clamp(L_mean / 155.0 * 100.0)
    S_mean = float(np.mean(S_ch[sk])) if sk.any() else float(np.mean(S_ch))
    S_norm = _clamp(S_mean / 90.0 * 100.0)
    highlight_mask  = ((V_ch > 228) & (S_ch < 38) & sk)
    highlight_ratio = float(np.count_nonzero(highlight_mask)) / max(np.count_nonzero(sk), 1)
    radiance     = _clamp(highlight_ratio * 1000.0)
    dullness_score = _clamp(L_norm * 0.20 + S_norm * 0.50 + radiance * 0.30)

    # (3) 얼룩톤 (strip-norm L_std + block_std + 비대칭)
    if sk.any():
        L_normalized = _strip_normalize_L(L_ch, sk)
        L_std = float(np.std(L_normalized[sk]))
        ys, xs = np.where(sk)
        y_min, y_max = int(ys.min()), int(ys.max())
        x_min, x_max = int(xs.min()), int(xs.max())
        L_roi  = L_ch[y_min:y_max + 1, x_min:x_max + 1]
        sk_roi = skin_mask[y_min:y_max + 1, x_min:x_max + 1].astype(float)
        bsz = 10
        h_b, w_b = L_roi.shape
        h_blocks  = h_b // bsz; w_blocks = w_b // bsz
        if h_blocks > 0 and w_blocks > 0:
            L_trunc   = L_roi[:h_blocks * bsz, :w_blocks * bsz]
            sk_trunc  = sk_roi[:h_blocks * bsz, :w_blocks * bsz]
            L_blk     = L_trunc.reshape(h_blocks, bsz, w_blocks, bsz)
            sk_blk    = sk_trunc.reshape(h_blocks, bsz, w_blocks, bsz)
            skin_ratio = sk_blk.mean(axis=(1, 3))
            L_masked   = np.where(skin_ratio[:, None, :, None] >= 0.5, L_blk, np.nan)
            valid_cnt  = np.sum(~np.isnan(L_masked), axis=(1, 3))
            valid_sum  = np.nansum(L_masked, axis=(1, 3))
            with np.errstate(invalid="ignore", divide="ignore"):
                b_means = np.where(valid_cnt > 0, valid_sum / valid_cnt, np.nan).ravel()
            b_means  = b_means[~np.isnan(b_means)]
            block_std = float(np.std(b_means)) if len(b_means) >= 4 else L_std
        else:
            block_std = L_std
    else:
        L_std = float(np.std(L_ch)); block_std = L_std

    lc = _safe_region(regions.get("left_cheek",  np.zeros((10, 10, 3), np.uint8)))
    rc = _safe_region(regions.get("right_cheek", np.zeros((10, 10, 3), np.uint8)))
    lc_L = float(np.mean(cv2.cvtColor(lc, cv2.COLOR_BGR2LAB)[:, :, 0]))
    rc_L = float(np.mean(cv2.cvtColor(rc, cv2.COLOR_BGR2LAB)[:, :, 0]))
    asymmetry = abs(lc_L - rc_L)
    uneven_tone_score = _clamp(
        0.45 * _clamp(100.0 - L_std * 0.9) +
        0.35 * _clamp(100.0 - block_std * 1.0) +
        0.20 * _clamp(100.0 - asymmetry * 0.5))

    return {
        "skin_tone_score":   round(_clamp(skin_tone_score), 1),
        "dullness_score":    round(_clamp(dullness_score), 1),
        "uneven_tone_score": round(_clamp(uneven_tone_score), 1),
    }


# ─────────────────────────────────────────────────────────────────
# 탄력·처짐 분석
# ─────────────────────────────────────────────────────────────────

def analyze_dark_circle(regions: Dict[str, np.ndarray]) -> float:
    """다크서클 점수 (0~100, 높을수록 양호)."""
    scores: List[float] = []
    for key in ("left_eye", "right_eye"):
        reg = _safe_region(regions.get(key, np.zeros((10, 10, 3), np.uint8)))
        if min(reg.shape[:2]) < 4:
            continue
        lab_e = cv2.cvtColor(reg, cv2.COLOR_BGR2LAB)
        L_e   = lab_e[:, :, 0].astype(float)
        mean_L = float(np.mean(L_e))
        dark_ratio = float(np.sum(L_e < mean_L - 14)) / max(L_e.size, 1)
        scores.append(_clamp(100.0 - dark_ratio * 300.0))
    return float(np.mean(scores)) if scores else 70.0


def analyze_elasticity(
    face: np.ndarray,
    regions: Dict[str, np.ndarray],
    *,
    bp_jawline: Optional[list] = None,
) -> Dict[str, float]:
    """볼 처짐·턱선 흐림·눈가 탄력 3항목 분석."""
    _BP_JAWLINE = bp_jawline or [
        (0.0, 0), (5.0, 20), (12.0, 40), (20.0, 60),
        (30.0, 80), (40.0, 90), (55.0, 100),
    ]

    fh, fw = face.shape[:2]
    gray_face = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)

    # (1) 볼 처짐
    upper_row = gray_face[int(fh * 0.38), :]
    lower_row = gray_face[int(fh * 0.68), :]

    def _effective_width(row: np.ndarray) -> int:
        row_mean = float(np.mean(row)); row_std = float(np.std(row))
        threshold = max(10, int(row_mean - 1.5 * row_std))
        nonzero = np.where(row > threshold)[0]
        # 개선 (2026-05-22): 특수 케이스 처리
        #   - len(nonzero) == 0: 임계값 초과 픽셀 없음 → 0 반환
        #   - len(nonzero) == 1: 단일 픽셀만 초과 → 0 반환 (과대 추정 방지)
        if len(nonzero) < 2:
            return 0
        return int(nonzero[-1] - nonzero[0])

    upper_w = _effective_width(upper_row)
    lower_w = _effective_width(lower_row)
    width_ratio  = lower_w / max(upper_w, 1)
    sagging_idx  = max(0.0, (width_ratio - 1.0) * 100.0)
    upper_bright = float(np.mean(gray_face[int(fh * 0.30):int(fh * 0.50), :]))
    lower_bright = float(np.mean(gray_face[int(fh * 0.60):int(fh * 0.80), :]))
    bright_diff  = max(0.0, upper_bright - lower_bright)
    cheek_sagging_score = _clamp(100.0 - sagging_idx * 1.5 - bright_diff * 0.4)

    # (2) 턱선 흐림
    chin = _safe_region(regions.get("chin", np.zeros((10, 10, 3), np.uint8)))
    if min(chin.shape[:2]) >= 8:
        gray_chin = cv2.cvtColor(chin, cv2.COLOR_BGR2GRAY)
        blurred_chin = cv2.GaussianBlur(gray_chin, (3, 3), 0)
        sobelY = cv2.Sobel(blurred_chin.astype(float), cv2.CV_64F, 0, 1, ksize=5)
        edge_strength = float(np.mean(np.abs(sobelY)))
        jawline_blur_score = _area_to_score(edge_strength, _BP_JAWLINE)
    else:
        jawline_blur_score = 60.0

    # (3) 눈가 탄력
    return {
        "cheek_sagging_score": round(_clamp(cheek_sagging_score), 1),
        "jawline_blur_score":  round(_clamp(jawline_blur_score), 1),
    }


# ─────────────────────────────────────────────────────────────────
# 피부타입 분석
# ─────────────────────────────────────────────────────────────────

def analyze_sebum(
    face: np.ndarray,
    regions: Dict[str, np.ndarray],
    skin_mask: np.ndarray,
) -> Dict[str, float]:
    """피부타입 분석 (skin_type 분류 포함).

    반환 키:
      oily_score       T-zone 광택 기반 지성 점수 (높을수록 양호 = 피지 적음)
      dry_score        U-zone 건조·각질 기반 건성 점수 (높을수록 양호 = 건조 적음)
      sebum_score      T+U 복합 피지 점수
      skin_type_label  피부 타입 한국어 라벨 (지성/건성/복합성/중성)
      skin_type_score  피부 타입 균형 점수 (높을수록 균형 = 중성에 가까움)
    """
    def _shine_ratio(region: np.ndarray) -> float:
        if min(region.shape[:2]) < 4:
            return 0.0
        hsv_r = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
        V = hsv_r[:, :, 2]; S = hsv_r[:, :, 1]
        return np.sum((V > 210) & (S < 40)) / max(region.shape[0] * region.shape[1], 1)

    t_zone = _safe_region(regions.get("t_zone", np.zeros((10, 10, 3), np.uint8)))
    t_shine = _shine_ratio(t_zone)
    oily_score = _area_to_score(t_shine,
        [(0.0, 100), (0.005, 90), (0.015, 75), (0.030, 55),
         (0.050, 35), (0.080, 10), (0.100, 0)])

    u_zone = _safe_region(regions.get("u_zone", np.zeros((10, 10, 3), np.uint8)))
    if min(u_zone.shape[:2]) >= 4:
        hsv_u = cv2.cvtColor(u_zone, cv2.COLOR_BGR2HSV)
        S_u = hsv_u[:, :, 1]; V_u = hsv_u[:, :, 2]
        _total_u_px = max(u_zone.shape[0] * u_zone.shape[1], 1)
        dry_pixel_ratio = float(np.sum(S_u < 28)) / _total_u_px
        _flake_bin_u = ((V_u > 215) & (S_u < 35)).astype(np.uint8)
        try:
            import skimage.measure as _skm
            _labeled_u = _skm.label(_flake_bin_u)
            for region in _skm.regionprops(_labeled_u):
                if region.area >= 400:
                    _flake_bin_u[_labeled_u == region.label] = 0
        except Exception as e:
            log.debug("skimage.measure.label 실패: %s", e)
            pass
        flake_ratio_u = float(np.count_nonzero(_flake_bin_u)) / _total_u_px
        combined_dry  = dry_pixel_ratio * 0.60 + flake_ratio_u * 0.40
        dry_score = _clamp(100.0 - combined_dry * 550.0)
    else:
        dry_score = 70.0

    u_shine = _shine_ratio(u_zone)
    sebum_ratio = t_shine * 0.60 + u_shine * 0.40
    sebum_score = _area_to_score(sebum_ratio,
        [(0.0, 100), (0.004, 90), (0.012, 75), (0.025, 55),
         (0.045, 35), (0.070, 10), (0.090, 0)])

    # ── 피부 타입 분류 ──────────────────────────────────────────────
    # oily_score / dry_score 모두 "높을수록 양호(피지·건조 적음)" 방향.
    # 임계값 55: 10~90 스케일 기준 중간(50) 보다 약간 위 → 실측 분포 기반.
    _oily_raw = _clamp(oily_score)
    _dry_raw  = _clamp(dry_score)
    _THRESH   = 55.0

    _is_oily = _oily_raw < _THRESH   # T-zone 피지 과다
    _is_dry  = _dry_raw  < _THRESH   # U-zone 건조 과다

    if _is_oily and _is_dry:
        skin_type_label = "복합성"
    elif _is_oily:
        skin_type_label = "지성"
    elif _is_dry:
        skin_type_label = "건성"
    else:
        skin_type_label = "중성"

    # balance_score: 두 점수 차이가 클수록 낮아짐 (복합성이 불균형 최대)
    # 개선 (2026-05-22): 평균값도 반영하여 절대적 건강도 구분
    #   - oily=100, dry=100 → 100점 (양호)
    #   - oily=0, dry=0 → 40점 (불량, 차이는 없으나 절대 건강도 낮음)
    #   - 이전 공식: 100 - diff*0.5 만으로는 두 케이스 구분 불가
    _mean = (_oily_raw + _dry_raw) / 2.0
    _diff = abs(_oily_raw - _dry_raw)
    skin_type_score = _clamp(_mean * 0.6 + (100.0 - _diff * 0.5) * 0.4)

    return {
        "oily_score":       round(_oily_raw, 1),
        "dry_score":        round(_dry_raw, 1),
        "sebum_score":      round(_clamp(sebum_score), 1),
        "skin_type_label":  skin_type_label,
        "skin_type_score":  round(skin_type_score, 1),
    }


# ─────────────────────────────────────────────────────────────────
# 트러블·흔적 분석
# ─────────────────────────────────────────────────────────────────

# 브레이크포인트 이원화 P0 버그 수정: 하드코딩 제거, config 단일화
# _BP_ACNE, _BP_PAP 제거 - _get_metric_bp()로 config.json에서 로드


def analyze_acne_marks(
    face: np.ndarray,
    skin_mask: np.ndarray,
    stat: Dict[str, float],
    *,
    bp_acne: Optional[list] = None,
    bp_pap: Optional[list] = None,
) -> Dict[str, float]:
    """트러블·흔적 2항목 분석.

    Returns:
        {"acne_score": float, "post_acne_pigment_score": float}
    """
    # P0 수정: 브레이크포인트 단일화 - config.json에서만 로드
    from src.scoring._breakpoints import _get_metric_bp
    bp_acne = bp_acne or _get_metric_bp("acne_score")
    bp_pap  = bp_pap  or _get_metric_bp("post_acne_pigment_score")

    hsv  = cv2.cvtColor(face, cv2.COLOR_BGR2HSV)
    lab  = cv2.cvtColor(face, cv2.COLOR_BGR2LAB)
    a_ch = lab[:, :, 1].astype(float)
    L_ch = lab[:, :, 0].astype(float)
    b_ch = lab[:, :, 2].astype(float)
    sk   = skin_mask > 0
    total_px = face.shape[0] * face.shape[1]

    base_a = stat["base_a"]; std_a = stat["std_a"]
    base_L = stat["base_L"]; std_L  = stat["std_L"]
    base_b = stat["base_b"]

    # 눈/입술/코 ROI 제외
    _fh, _fw = face.shape[:2]
    _acne_roi = np.ones(face.shape[:2], np.uint8) * 255
    _acne_roi[int(_fh * 0.18):int(_fh * 0.50), :] = 0          # 눈
    _acne_roi[int(_fh * 0.62):int(_fh * 0.88), int(_fw * 0.25):int(_fw * 0.75)] = 0  # 입
    _acne_roi[int(_fh * 0.35):int(_fh * 0.60), int(_fw * 0.30):int(_fw * 0.70)] = 0  # 코 (T-zone 오탐 방지)
    _acne_skin_mask = cv2.bitwise_and((sk.astype(np.uint8) * 255), _acne_roi)

    lower_r1 = np.array([0,   40, 40], dtype=np.uint8)
    upper_r1 = np.array([10, 255, 255], dtype=np.uint8)
    lower_r2 = np.array([165, 40, 40], dtype=np.uint8)
    upper_r2 = np.array([180, 255, 255], dtype=np.uint8)
    acne_mask = cv2.bitwise_or(cv2.inRange(hsv, lower_r1, upper_r1),
                               cv2.inRange(hsv, lower_r2, upper_r2))
    # P1 수정: 팽창 커널 해상도 비례 - 이미지 크기에 따라 동적 조정
    _dil_k = max(5, int(_fh * 0.012))
    if _dil_k % 2 == 0:
        _dil_k += 1  # 홀수 보장
    a_acne     = (a_ch > base_a + 1.5 * std_a).astype(np.uint8) * 255
    a_acne_dil = cv2.dilate(a_acne, np.ones((_dil_k, _dil_k), np.uint8))
    acne_mask  = cv2.bitwise_and(acne_mask, a_acne_dil)
    acne_mask  = cv2.bitwise_and(acne_mask, acne_mask, mask=_acne_skin_mask)
    kernel3    = np.ones((3, 3), np.uint8)
    acne_mask  = cv2.morphologyEx(acne_mask, cv2.MORPH_OPEN,  kernel3)
    acne_mask  = cv2.morphologyEx(acne_mask, cv2.MORPH_CLOSE, kernel3)
    cnts_a, _ = cv2.findContours(acne_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # P1 수정: contour 면적 상하한 상대화 - 해상도 의존성 제거
    _min_area = max(18, int(acne_skin_px * 0.00004))
    _max_area = int(acne_skin_px * 0.05)
    acne_spots = [c for c in cnts_a if _min_area < cv2.contourArea(c) < _max_area]
    acne_count = len(acne_spots)
    acne_area  = sum(cv2.contourArea(c) for c in acne_spots)
    # 실제 탐지 ROI 픽셀 사용 (버그 수정: 전체 face 픽셀이 아닌 _acne_skin_mask 픽셀)
    acne_skin_px = max(int(np.count_nonzero(_acne_skin_mask)), 1)
    density_ratio = acne_area / acne_skin_px
    density_score = _area_to_score(density_ratio, bp_acne)
    if acne_spots:
        # a* 채널 기반 intensity (더 정확한 홍반 강도 측정)
        a_vals = a_ch[acne_mask > 0]
        avg_a = float(np.mean(a_vals))
        intensity_score = _clamp(100.0 - max(0.0, avg_a - base_a - 5.0) * 3.0)
    else:
        intensity_score = 100.0
    # P1 수정: 개수 패널티 상한 추가 - 대량 병변 판별력 상실 방지
    count_penalty = min(20.0, max(0.0, (acne_count - 15) * 0.3))
    acne_score = _clamp(0.70 * density_score + 0.30 * intensity_score - count_penalty)

    # post_acne_pigment_score
    # P0 수정: 분모 통일 - acne_skin_px 사용 (sk 전체 피부 대신 ROI 제한 분모)
    # P2 수정: _PAP_A_FLOOR 동적 설정 - 황색계 피부 위양성 방지
    _PAP_A_FLOOR_BASE: float = 142.0
    pap_thresh = max(base_a + 1.8 * float(std_a), max(_PAP_A_FLOOR_BASE, base_a + 5.0))
    intense_mask = ((a_ch > pap_thresh) & sk).astype(np.uint8) * 255
    intense_mask[acne_mask > 0] = 0
    intense_mask = cv2.morphologyEx(intense_mask, cv2.MORPH_OPEN, kernel3)
    cnts_r, _   = cv2.findContours(intense_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # P1 수정: contour 면적 상하한 상대화 - 해상도 의존성 제거
    _min_pap = max(15, int(acne_skin_px * 0.00003))
    _max_pap = int(acne_skin_px * 0.03)
    red_spots   = [c for c in cnts_r if _min_pap < cv2.contourArea(c) < _max_pap]
    pap_area    = sum(cv2.contourArea(c) for c in red_spots)
    # P0 수정: 분모 통일 - acne_skin_px 사용
    post_acne_pigment_score = _area_to_score(pap_area / acne_skin_px, bp_pap)

    return {
        "acne_score":             round(_clamp(acne_score), 1),
        "post_acne_pigment_score": round(_clamp(post_acne_pigment_score), 1),
    }


# ─────────────────────────────────────────────────────────────────
# 인지 나이 추정
# ─────────────────────────────────────────────────────────────────

def analyze_perceived_age(
    face: np.ndarray,
    eye_wrinkle_score: float,
    lines_score: float,
) -> float:
    """인지 나이 추정 (18~72세).

    가중치 재조정 (2026-05-22):
    - 베이스 나이: 20 → 30세로 상향
    - 가중치 조정: eye_wrinkle 0.25→0.45, lines 0.20→0.35, texture 0.12→0.15, pigment 0.08→0.05
    - 최대 가중합: 6.375 → 42로 상향 (상한 72세 도달 가능)
    """
    gray = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
    age  = 30.0  # 베이스 나이 상향 (20 → 30)
    if _SKIMAGE_OK and local_binary_pattern is not None:
        lbp = local_binary_pattern(gray, 8, 1, method="uniform")
        texture_roughness = float(np.var(lbp))
    else:
        texture_roughness = 0.0
    lab = cv2.cvtColor(face, cv2.COLOR_BGR2LAB)
    pigment_variance = float(np.std(lab[:, :, 0].astype(float)))
    age += max(0.0, (100.0 - eye_wrinkle_score) / 100.0 * 30.0) * 0.45  # 0.25 → 0.45
    age += max(0.0, (100.0 - lines_score)        / 100.0 * 30.0) * 0.35  # 0.20 → 0.35
    age += min(texture_roughness / 12.0, 18.0) * 0.15  # 0.12 → 0.15
    age += min(pigment_variance  / 6.0,  14.0) * 0.05  # 0.08 → 0.05
    return round(float(np.clip(age, 18.0, 72.0)), 1)
