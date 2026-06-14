"""src/skin/analyzers/pigmentation.py

색소 카테고리 분석 — _SkinAnalyzerV2._analyze_pigmentation 분리.
외부에서 직접 호출하지 말고 반드시 _SkinAnalyzerV2 경유 사용.

분석 항목:
  melasma_score         : 기미·잡티 (LAB strip-norm + b 상대 임계)
  freckle_score         : 주근깨 (소형 LoG blob)
  pih_score             : 여드름 후 색소침착 (strip-norm + a 강한 픽셀)
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

import cv2
import numpy as np

from src.skin.core.face_roi import FaceROI
from src.skin.core.scoring_utils import (
    clamp,
    area_to_score,
    count_to_score,
    strip_normalize_L,
)
from src.utils.config import load_config
from src.utils.cv_utils import blob_log_cv

log = logging.getLogger(__name__)


# 헬퍼 함수는 scoring_utils에서 import
_clamp = clamp
_strip_normalize_L = strip_normalize_L
_area_to_score = area_to_score
_count_to_score = count_to_score


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


def make_pigment_mask(smask: np.ndarray, fh: int, fw: int) -> np.ndarray:
    """색소 전용 피부 마스크 — 눈·코·입·헤어라인·목 제외.

    _SkinAnalyzerV2._make_pigment_mask 와 동일 로직, 독립 함수로 추출.
    """
    m = smask.copy()
    m[int(fh * FaceROI.PIGMENT_EXCLUDE_EYE_TOP)   : int(fh * FaceROI.PIGMENT_EXCLUDE_EYE_BOTTOM),   :] = 0
    m[int(fh * FaceROI.PIGMENT_EXCLUDE_MOUTH_TOP)  : int(fh * FaceROI.PIGMENT_EXCLUDE_MOUTH_BOTTOM),
      int(fw * FaceROI.PIGMENT_EXCLUDE_MOUTH_LEFT) : int(fw * FaceROI.PIGMENT_EXCLUDE_MOUTH_RIGHT)]  = 0
    m[int(fh * FaceROI.PIGMENT_EXCLUDE_NOSE_TOP)   : int(fh * FaceROI.PIGMENT_EXCLUDE_NOSE_BOTTOM),
      int(fw * FaceROI.PIGMENT_EXCLUDE_NOSE_LEFT)  : int(fw * FaceROI.PIGMENT_EXCLUDE_NOSE_RIGHT)]   = 0
    m[0 : int(fh * FaceROI.PIGMENT_EXCLUDE_HAIR_BOTTOM), :] = 0
    m[int(fh * FaceROI.PIGMENT_EXCLUDE_NECK_BOTTOM):, :]   = 0
    return m


# ── breakpoints (config 미사용 폴백용 기본값) ───────────────────
_BP_MELASMA = [
    (0.000, 100), (0.001, 90), (0.003, 80), (0.007, 70),
    (0.015, 60),  (0.030, 45), (0.050, 30), (0.080, 15), (0.120, 0),
]
_BP_FRECKLE_COUNT = [
    (0, 100), (3, 90), (8, 78), (18, 60),
    (35, 40), (60, 20), (100, 0),
]
_BP_PIH = []  # config.json에서 로드


def analyze_pigmentation(
    face: np.ndarray,
    skin_mask: np.ndarray,
    stat: Dict[str, float],
    *,
    bp_melasma: Optional[list] = None,
    bp_freckle_count: Optional[list] = None,
    bp_pih: Optional[list] = None,
    freckle_params: Optional[Dict] = None,
) -> Dict[str, float]:
    """색소 3항목 분석.

    Args:
        face:       얼굴 BGR 이미지
        skin_mask:  피부 마스크 (uint8)
        stat:       _skin_stat() + pig_*/red_* 병합 결과
        bp_*:       항목별 브레이크포인트 (None이면 모듈 기본값 사용)
        freckle_params: {threshold, min_sigma, max_sigma, overlap}

    Returns:
        {"melasma_score": float, "freckle_score": float, "pih_score": float}
    """
    # Config에서 파라미터 로드
    melasma_params = _get_cv_analyzer_params("pigmentation", "melasma")
    freckle_config = _get_cv_analyzer_params("pigmentation", "freckle")
    lentigo_config = _get_cv_analyzer_params("pigmentation", "lentigo")
    pih_config = _get_cv_analyzer_params("pigmentation", "pih")

    # 기본값 설정 (config 누락 시)
    melasma_l_threshold_std = melasma_params.get("l_threshold_std", -2.2)
    melasma_l_threshold_cap = melasma_params.get("l_threshold_cap", [4.0, 15.0])
    melasma_b_threshold_std = melasma_params.get("b_threshold_std", 0.3)
    melasma_morph_close = melasma_params.get("morph_close", 7)
    melasma_morph_open = melasma_params.get("morph_open", 5)

    freckle_threshold = freckle_config.get("threshold", 0.08)
    freckle_min_sigma = freckle_config.get("min_sigma", 1.0)
    freckle_max_sigma = freckle_config.get("max_sigma", 5.0)
    freckle_overlap = freckle_config.get("overlap", 0.4)
    freckle_l_threshold = freckle_config.get("l_threshold", -10)

    lentigo_min_sigma = lentigo_config.get("min_sigma", 3.0)
    lentigo_max_sigma = lentigo_config.get("max_sigma", 14.0)
    lentigo_num_sigma = lentigo_config.get("num_sigma", 6)
    lentigo_threshold = lentigo_config.get("threshold", 0.07)
    lentigo_overlap = lentigo_config.get("overlap", 0.3)

    pih_a_threshold = pih_config.get("a_threshold", 130)
    bp_pih_config = pih_config.get("bp_pih", [])

    # 브레이크포인트 기본값
    bp_melasma       = bp_melasma       or _BP_MELASMA
    bp_freckle_count = bp_freckle_count or _BP_FRECKLE_COUNT
    bp_pih           = bp_pih           or bp_pih_config or _BP_PIH

    # freckle_params는 config에서 로드한 값 사용
    freckle_params = freckle_params or {
        "threshold": freckle_threshold,
        "min_sigma": freckle_min_sigma,
        "max_sigma": freckle_max_sigma,
        "overlap": freckle_overlap
    }

    lab   = cv2.cvtColor(face, cv2.COLOR_BGR2LAB)
    L_ch  = lab[:, :, 0].astype(float)
    a_ch  = lab[:, :, 1].astype(float)
    b_ch  = lab[:, :, 2].astype(float)

    base_a  = stat["base_a"]
    std_a   = stat["std_a"]
    sk_bool = skin_mask > 0
    skin_px = max(int(np.count_nonzero(sk_bool)), 1)

    fh, fw  = face.shape[:2]
    pigment_sk = make_pigment_mask(skin_mask, fh, fw)
    pig_bool   = pigment_sk > 0
    pig_px     = max(int(np.count_nonzero(pig_bool)), 1)

    # ── pig_stat 추출 / stat 주입 ────────────────────────────────
    if pig_bool.any():
        _pig_L = L_ch[pig_bool]; _pig_b = b_ch[pig_bool]; _pig_a = a_ch[pig_bool]
        pig_base_L = float(stat.get("pig_base_L", np.median(_pig_L)))
        pig_std_L  = float(stat.get("pig_std_L",  np.std(_pig_L)))
        pig_base_b = float(stat.get("pig_base_b", np.median(_pig_b)))
        pig_std_b  = float(stat.get("pig_std_b",  np.std(_pig_b)))
        pig_base_a = float(stat.get("pig_base_a", np.median(_pig_a)))
        pig_std_a  = float(stat.get("pig_std_a",  np.std(_pig_a)))
    else:
        pig_bool   = sk_bool; pig_px = skin_px
        pig_base_L = float(stat.get("pig_base_L", stat["base_L"]))
        pig_std_L  = float(stat.get("pig_std_L",  stat["std_L"]))
        pig_base_b = float(stat.get("pig_base_b", stat["base_b"]))
        pig_std_b  = float(stat.get("pig_std_b",  stat.get("std_b", 5.0)))
        pig_base_a = float(stat.get("pig_base_a", base_a))
        pig_std_a  = float(stat.get("pig_std_a",  std_a))

    _ref_base_b = float(stat.get("pig_base_b", pig_base_b))
    _ref_std_b  = float(stat.get("pig_std_b",  pig_std_b))
    _ref_std_L  = float(stat.get("pig_std_L",  pig_std_L))

    # ── (1) 기미 melasma ─────────────────────────────────────────
    _L_norm_mel = _strip_normalize_L(L_ch, pig_bool)
    _std_Lnorm_pig = float(np.std(_L_norm_mel[pig_bool])) if pig_bool.any() else 10.0
    _std_L_capped  = float(np.clip(_ref_std_L, melasma_l_threshold_cap[0], melasma_l_threshold_cap[1]))
    _L_mel_thresh_new = min(melasma_l_threshold_std * _std_L_capped, -12.0)

    _std_b_mel_rel  = float(np.clip(pig_std_b, 2.0, 6.0))
    _b_mel_thresh_rel = pig_base_b + melasma_b_threshold_std * _std_b_mel_rel

    melasma_mask = (
        (_L_norm_mel < _L_mel_thresh_new) &
        pig_bool &
        (b_ch > _b_mel_thresh_rel)
    ).astype(np.uint8) * 255
    # [FIX 2026-05-24] 형태학적 팽창 과도 문제 수정 - (15,15) → (7,7)
    # 얼굴 폭 300px에서 15px 커널은 5% 폭 브리징 허용 → 인접 병변 합쳐짐
    melasma_mask = cv2.morphologyEx(melasma_mask, cv2.MORPH_CLOSE, np.ones((melasma_morph_close, melasma_morph_close), np.uint8))
    melasma_mask = cv2.morphologyEx(melasma_mask, cv2.MORPH_OPEN,  np.ones((melasma_morph_open, melasma_morph_open),  np.uint8))
    melasma_cov  = float(np.count_nonzero(melasma_mask)) / float(pig_px)
    melasma_score = _area_to_score(melasma_cov, bp_melasma)

    # ── 잡티/검버섯 blob (주근깨 중복 제거용 lentigo_count 유지) ──
    _std_b_lent = float(np.clip(_ref_std_b, 2.0, 6.0))
    _lentigo_roi = pigment_sk.copy()
    _lentigo_roi[int(fh * 0.18):int(fh * 0.50), :] = 0
    _lentigo_roi[int(fh * 0.62):int(fh * 0.88), int(fw * 0.25):int(fw * 0.75)] = 0
    _lentigo_roi[0:int(fh * 0.08), :] = 0
    _b_lent_thr = min(_ref_base_b + 1.2 * _std_b_lent, 146.0)
    _a_lent_thr = min(float(stat.get("pig_base_a", pig_base_a)) + 1.2 * float(np.clip(_ref_std_b, 2.0, 6.0)), 142.0)

    gray        = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
    gray_inv_lg = np.uint8(255) - gray
    lentigo_count = 0
    blobs_lg = np.empty((0, 3))
    try:
        blobs_lg = blob_log_cv(gray_inv_lg, min_sigma=lentigo_min_sigma, max_sigma=lentigo_max_sigma,
                              num_sigma=lentigo_num_sigma, threshold=lentigo_threshold, overlap=lentigo_overlap)
    except Exception as e:
        log.debug("blob_log_cv 실패 (lentigo), 폴백 사용: %s", e)
        blobs_lg = np.empty((0, 3))
    for blob in blobs_lg:
        by, bx, br = int(blob[0]), int(blob[1]), max(1, int(blob[2] * 1.414))
        y0, y1 = max(0, by - br), min(face.shape[0], by + br)
        x0, x1 = max(0, bx - br), min(face.shape[1], bx + br)
        roi_L = L_ch[y0:y1, x0:x1]; roi_b = b_ch[y0:y1, x0:x1]; roi_a = a_ch[y0:y1, x0:x1]
        roi_sk = _lentigo_roi[y0:y1, x0:x1]
        if roi_L.size == 0 or roi_sk.sum() == 0:
            continue
        if roi_L.mean() < pig_base_L - 10 and (roi_b.mean() > _b_lent_thr or roi_a.mean() > _a_lent_thr):
            lentigo_count += 1

    # ── (2) 주근깨 freckle ───────────────────────────────────────
    blobs_sm = np.empty((0, 3))
    try:
        blobs_sm = blob_log_cv(
            gray_inv_lg,
            min_sigma=freckle_params["min_sigma"],
            max_sigma=freckle_params["max_sigma"],
            num_sigma=6,
            threshold=freckle_params["threshold"],
            overlap=freckle_params["overlap"],
        )
    except Exception as e:
        log.debug("blob_log_cv 실패 (freckle), 폴백 사용: %s", e)
        blobs_sm = np.empty((0, 3))

    lentigo_centers = {(int(b[0]), int(b[1]), max(1, int(b[2] * 1.414))) for b in blobs_lg}
    freckle_count = 0
    for blob in blobs_sm:
        by, bx, br = int(blob[0]), int(blob[1]), max(1, int(blob[2] * 1.414))
        if br > 8:
            continue
        if any(abs(by - ly) < lr and abs(bx - lx) < lr for ly, lx, lr in lentigo_centers):
            continue
        y0, y1 = max(0, by - br), min(face.shape[0], by + br)
        x0, x1 = max(0, bx - br), min(face.shape[1], bx + br)
        roi_L  = L_ch[y0:y1, x0:x1]
        roi_sk = skin_mask[y0:y1, x0:x1]
        if roi_L.size == 0 or roi_sk.sum() == 0:
            continue
        if roi_L.mean() < pig_base_L + freckle_l_threshold:
            freckle_count += 1
    freckle_score = _count_to_score(freckle_count, bp_freckle_count)

    # PIH (Post-Inflammatory Hyperpigmentation) 계산
    # strip-norm + a 강한 픽셀 감지
    lab = cv2.cvtColor(face, cv2.COLOR_BGR2LAB)
    L_ch, a_ch, b_ch = cv2.split(lab)
    
    # strip normalize 적용
    L_norm = _strip_normalize_L(L_ch, skin_mask)
    
    # PIH 영역 마스크 (a 채널에서 강한 픽셀 감지)
    # a 채널: 녹색(-) ~ 빨간색(+), PIH는 빨간색/갈색 반점
    pig_mask = make_pigment_mask(skin_mask, face.shape[0], face.shape[1])
    
    # a 채널 임계값 (기본값: 130, 범위 0-255)
    pih_mask = (a_ch > pih_a_threshold) & (pig_mask > 0)
    
    # PIH 영역 비율 계산
    pih_area = pih_mask.sum()
    total_skin_area = pig_mask.sum()
    
    if total_skin_area > 0:
        pih_ratio = pih_area / total_skin_area
    else:
        pih_ratio = 0.0
    
    pih_score = _area_to_score(pih_ratio, bp_pih)

    return {
        "melasma_score": round(_clamp(melasma_score), 1),
        "freckle_score": round(_clamp(freckle_score), 1),
        "pih_score": round(_clamp(pih_score), 1),
    }
