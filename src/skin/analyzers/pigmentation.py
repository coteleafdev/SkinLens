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

log = logging.getLogger(__name__)

# ── 지연 import (skimage 선택적 의존) ───────────────────────────
try:
    from skimage.feature import blob_log
    _SKIMAGE_OK = True
except ImportError:
    blob_log = None
    _SKIMAGE_OK = False


# 헬퍼 함수는 scoring_utils에서 import
_clamp = clamp
_strip_normalize_L = strip_normalize_L
_area_to_score = area_to_score
_count_to_score = count_to_score


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
_BP_PIH = [
    (0.0, 100), (0.004, 90), (0.012, 74), (0.025, 54),
    (0.050, 32), (0.085, 10), (0.130, 0),
]


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
    bp_melasma       = bp_melasma       or _BP_MELASMA
    bp_freckle_count = bp_freckle_count or _BP_FRECKLE_COUNT
    bp_pih           = bp_pih           or _BP_PIH
    freckle_params   = freckle_params   or {
        "threshold": 0.08, "min_sigma": 1.0, "max_sigma": 5.0, "overlap": 0.4
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
    _std_L_capped  = float(np.clip(_ref_std_L, 4.0, 15.0))
    _L_mel_thresh_new = min(-2.2 * _std_L_capped, -12.0)

    _std_b_mel_rel  = float(np.clip(pig_std_b, 2.0, 6.0))
    _b_mel_thresh_rel = pig_base_b + 0.3 * _std_b_mel_rel

    melasma_mask = (
        (_L_norm_mel < _L_mel_thresh_new) &
        pig_bool &
        (b_ch > _b_mel_thresh_rel)
    ).astype(np.uint8) * 255
    # [FIX 2026-05-24] 형태학적 팽창 과도 문제 수정 - (15,15) → (7,7)
    # 얼굴 폭 300px에서 15px 커널은 5% 폭 브리징 허용 → 인접 병변 합쳐짐
    melasma_mask = cv2.morphologyEx(melasma_mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    melasma_mask = cv2.morphologyEx(melasma_mask, cv2.MORPH_OPEN,  np.ones((5, 5),  np.uint8))
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
    if _SKIMAGE_OK and blob_log is not None:
        try:
            blobs_lg = blob_log(gray_inv_lg, min_sigma=3, max_sigma=14, num_sigma=6, threshold=0.07, overlap=0.3)
        except Exception as e:
            log.debug("blob_log 실패 (lentigo), 폴백 사용: %s", e)
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
    if _SKIMAGE_OK and blob_log is not None:
        try:
            blobs_sm = blob_log(
                gray_inv_lg,
                min_sigma=freckle_params["min_sigma"],
                max_sigma=freckle_params["max_sigma"],
                num_sigma=6,
                threshold=freckle_params["threshold"],
                overlap=freckle_params["overlap"],
            )
        except Exception as e:
            log.debug("blob_log 실패 (freckle), 폴백 사용: %s", e)
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
        if roi_L.mean() < pig_base_L - 10:
            freckle_count += 1
    freckle_score = _count_to_score(freckle_count, bp_freckle_count)

    # TODO: PIH (Post-Inflammatory Hyperpigmentation) calculation not implemented
    # Returning default score for now
    pih_score = 100.0

    return {
        "melasma_score": round(_clamp(melasma_score), 1),
        "freckle_score": round(_clamp(freckle_score), 1),
        "pih_score": round(_clamp(pih_score), 1),
    }
